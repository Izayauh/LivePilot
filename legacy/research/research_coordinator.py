"""
Research Coordinator

Orchestrates research from multiple sources (YouTube, web articles) and 
aggregates results into a unified ChainSpec for vocal chain generation.
"""

import asyncio
import json
import os
import re
from collections import Counter
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

from pipeline.guardrail import assert_llm_allowed, LLMCallBlocked


@dataclass
class DeviceSpec:
    """Specification for a single device in a chain"""
    plugin_name: str
    category: str  # eq, compressor, reverb, delay, saturation, dynamics
    parameters: Dict[str, Any]  # param_name -> {value, unit, confidence}
    purpose: str  # Brief description of what this device does
    reasoning: str  # Why this device/setting was chosen
    confidence: float  # 0-1 confidence in this device spec
    sources: List[str] = field(default_factory=list)  # URLs/sources


@dataclass
class ChainSpec:
    """Complete specification for a vocal chain"""
    query: str  # Original query
    style_description: str  # Description of the target sound
    devices: List[DeviceSpec]  # Ordered list of devices
    confidence: float  # Overall confidence
    sources: List[str]  # All sources used
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Metadata
    artist: Optional[str] = None
    song: Optional[str] = None
    genre: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "query": self.query,
            "style_description": self.style_description,
            "devices": [
                {
                    "plugin_name": d.plugin_name,
                    "category": d.category,
                    "parameters": d.parameters,
                    "purpose": d.purpose,
                    "reasoning": d.reasoning,
                    "confidence": d.confidence,
                    "sources": d.sources
                }
                for d in self.devices
            ],
            "confidence": self.confidence,
            "sources": self.sources,
            "created_at": self.created_at,
            "artist": self.artist,
            "song": self.song,
            "genre": self.genre,
            "meta": self.meta
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChainSpec':
        """Create from dictionary"""
        devices = [
            DeviceSpec(
                plugin_name=d["plugin_name"],
                category=d["category"],
                parameters=d["parameters"],
                purpose=d["purpose"],
                reasoning=d.get("reasoning", ""),
                confidence=d["confidence"],
                sources=d.get("sources", [])
            )
            for d in data.get("devices", [])
        ]
        
        return cls(
            query=data.get("query", ""),
            style_description=data.get("style_description", ""),
            devices=devices,
            confidence=data.get("confidence", 0.0),
            sources=data.get("sources", []),
            created_at=data.get("created_at", datetime.now().isoformat()),
            artist=data.get("artist"),
            song=data.get("song"),
            genre=data.get("genre"),
            meta=data.get("meta", {})
        )


def _flatten_parameters(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten nested research parameters to simple key-value pairs.

    Research format:  {"freq": {"value": 100, "unit": "Hz", "confidence": 0.8}}
    Flattened format: {"freq": 100}

    Scalars pass through unchanged. Non-dict, non-scalar values are kept as-is.
    """
    flat = {}
    for param_name, param_info in parameters.items():
        if isinstance(param_info, dict) and "value" in param_info:
            flat[param_name] = param_info["value"]
        else:
            flat[param_name] = param_info
    return flat


def chainspec_to_builder_format(chain_spec_dict: Dict[str, Any],
                                 track_type: str = "vocal") -> Dict[str, Any]:
    """Convert ChainSpec.to_dict() output to the format expected by
    PluginChainBuilder.build_chain_from_research().

    Research format (input):
      {"devices": [{"plugin_name", "category", "parameters": {nested}, ...}], ...}

    Builder format (output):
      {"artist_or_style", "track_type", "chain": [{"type", "purpose", "plugin_name", "settings": {flat}}], ...}
    """
    chain_items = []
    for device in chain_spec_dict.get("devices", []):
        flat_settings = _flatten_parameters(device.get("parameters", {}))
        chain_items.append({
            "type": device.get("category", "unknown"),
            "purpose": device.get("purpose", ""),
            "plugin_name": device.get("plugin_name", ""),
            "name": device.get("plugin_name", ""),
            "settings": flat_settings,
        })

    return {
        "artist_or_style": (chain_spec_dict.get("artist")
                            or chain_spec_dict.get("query", "unknown")),
        "track_type": track_type,
        "chain": chain_items,
        "confidence": chain_spec_dict.get("confidence", 0.5),
        "sources": chain_spec_dict.get("sources", []),
        "from_research": True,
    }


@dataclass
class ResearchPolicy:
    """Budget and quality policy for one research run."""
    mode: str
    max_youtube_videos: int
    max_web_articles: int
    max_youtube_extractions: int
    max_web_extractions: int
    max_llm_calls: int
    transcript_char_limit: int
    article_char_limit: int
    enable_intent_analysis: bool
    enable_chain_reasoning: bool
    allow_fallback_query: bool
    allow_source_short_circuit: bool
    short_circuit_confidence: float
    intent_model: str
    extraction_model: str
    reasoning_model: str
    prefer_cache: bool
    cache_max_age_days: int


class ResearchCoordinator:
    """
    Coordinates research from multiple sources and aggregates results.
    
    Orchestrates:
    - YouTube tutorial research
    - Web article research
    - LLM-based intent analysis
    - Result aggregation and conflict resolution
    """
    
    def __init__(self):
        """Initialize the research coordinator"""
        self._youtube_researcher = None
        self._web_researcher = None
        self._llm_client = None
        self._audio_analyst = None
        self._artifact_store = None  # Lazy-loaded artifact chain store
        self._research_cache_path = os.path.join(os.path.dirname(__file__), "research_cache.json")
        self._cheap_model_id = os.getenv("RESEARCH_CHEAP_MODEL", "gemini-2.0-flash-lite")
        self._expensive_model_id = os.getenv("RESEARCH_REASONING_MODEL", "gemini-2.0-flash")
        self._default_budget_mode = os.getenv("RESEARCH_BUDGET_MODE", "balanced").lower().strip()
        if self._default_budget_mode not in {"cheap", "balanced", "deep"}:
            self._default_budget_mode = "balanced"
        self._enable_semantic_cache = os.getenv("RESEARCH_ENABLE_SEMANTIC_CACHE", "1").lower() in {"1", "true", "yes", "on"}
        self._enable_intent_router = os.getenv("RESEARCH_ENABLE_INTENT_ROUTER", "1").lower() in {"1", "true", "yes", "on"}
        self._semantic_cache_threshold = float(os.getenv("RESEARCH_SEMANTIC_CACHE_THRESHOLD", "0.84"))
        self._semantic_cache_max_entries = max(50, int(os.getenv("RESEARCH_SEMANTIC_CACHE_MAX_ENTRIES", "500")))
        self._enable_command_mode_bypass = os.getenv("RESEARCH_ENABLE_COMMAND_MODE_BYPASS", "1").lower() in {"1", "true", "yes", "on"}
        self._strict_artifact_only = os.getenv("RESEARCH_STRICT_ARTIFACT_ONLY", "1").lower() in {"1", "true", "yes", "on"}
        self._allow_legacy_chain_paths = os.getenv("RESEARCH_ALLOW_LEGACY_CHAIN_PATHS", "0").lower() in {"1", "true", "yes", "on"}

    def _resolve_research_policy(
        self,
        budget_mode: Optional[str] = None,
        max_sources: Optional[int] = None,
        max_total_llm_calls: Optional[int] = None,
        prefer_cache: bool = True,
        cache_max_age_days: int = 14
    ) -> ResearchPolicy:
        mode = (budget_mode or self._default_budget_mode or "balanced").lower().strip()
        if mode not in {"cheap", "balanced", "deep"}:
            mode = "balanced"

        base = {
            "cheap": {
                "max_youtube_videos": 1,
                "max_web_articles": 1,
                "max_youtube_extractions": 1,
                "max_web_extractions": 1,
                "max_llm_calls": 2,
                "transcript_char_limit": 6000,
                "article_char_limit": 5000,
                "enable_intent_analysis": False,
                "enable_chain_reasoning": False,
                "allow_fallback_query": False,
                "allow_source_short_circuit": True,
                "short_circuit_confidence": 0.75,
            },
            "balanced": {
                "max_youtube_videos": 2,
                "max_web_articles": 2,
                "max_youtube_extractions": 2,
                "max_web_extractions": 2,
                "max_llm_calls": 6,
                "transcript_char_limit": 10000,
                "article_char_limit": 9000,
                "enable_intent_analysis": True,
                "enable_chain_reasoning": True,
                "allow_fallback_query": True,
                "allow_source_short_circuit": True,
                "short_circuit_confidence": 0.9,
            },
            "deep": {
                "max_youtube_videos": 4,
                "max_web_articles": 3,
                "max_youtube_extractions": 4,
                "max_web_extractions": 3,
                "max_llm_calls": 12,
                "transcript_char_limit": 15000,
                "article_char_limit": 13000,
                "enable_intent_analysis": True,
                "enable_chain_reasoning": True,
                "allow_fallback_query": True,
                "allow_source_short_circuit": False,
                "short_circuit_confidence": 0.95,
            }
        }[mode].copy()

        if max_sources is not None:
            max_sources = max(1, int(max_sources))
            base["max_youtube_videos"] = min(base["max_youtube_videos"], max_sources)
            base["max_web_articles"] = min(base["max_web_articles"], max_sources)
            base["max_youtube_extractions"] = min(base["max_youtube_extractions"], max_sources)
            base["max_web_extractions"] = min(base["max_web_extractions"], max_sources)

        if max_total_llm_calls is not None:
            base["max_llm_calls"] = max(0, int(max_total_llm_calls))

        base["max_youtube_extractions"] = min(base["max_youtube_extractions"], base["max_youtube_videos"])
        base["max_web_extractions"] = min(base["max_web_extractions"], base["max_web_articles"])

        return ResearchPolicy(
            mode=mode,
            max_youtube_videos=base["max_youtube_videos"],
            max_web_articles=base["max_web_articles"],
            max_youtube_extractions=base["max_youtube_extractions"],
            max_web_extractions=base["max_web_extractions"],
            max_llm_calls=base["max_llm_calls"],
            transcript_char_limit=base["transcript_char_limit"],
            article_char_limit=base["article_char_limit"],
            enable_intent_analysis=base["enable_intent_analysis"],
            enable_chain_reasoning=base["enable_chain_reasoning"],
            allow_fallback_query=base["allow_fallback_query"],
            allow_source_short_circuit=base["allow_source_short_circuit"],
            short_circuit_confidence=base["short_circuit_confidence"],
            intent_model=os.getenv("RESEARCH_INTENT_MODEL", "gemini-2.0-flash"),
            extraction_model=os.getenv("RESEARCH_EXTRACTION_MODEL", "gemini-2.0-flash"),
            reasoning_model=os.getenv("RESEARCH_REASONING_MODEL", "gemini-2.0-flash"),
            prefer_cache=prefer_cache,
            cache_max_age_days=max(1, int(cache_max_age_days)),
        )

    def _heuristic_intent(self, query: str) -> Dict[str, Any]:
        """Low-cost fallback intent parsing when LLM intent analysis is disabled."""
        cleaned = (query or "").strip()
        intent = {
            "artist": "",
            "song": "",
            "style": "",
            "characteristics": [],
            "processing_goals": [],
            "original_query": cleaned
        }

        if not cleaned:
            return intent

        style_match = re.search(r"(?:like|style of)\s+(.+)$", cleaned, re.IGNORECASE)
        if style_match:
            intent["style"] = style_match.group(1).strip()

        song_match = re.search(r"(?:from|song)\s+[\"']?([^\"']+)[\"']?", cleaned, re.IGNORECASE)
        if song_match:
            intent["song"] = song_match.group(1).strip()

        artist_match = re.match(r"([a-zA-Z0-9\s\.\-&']+?)\s+(?:vocal|voice|mix|style|chain)", cleaned, re.IGNORECASE)
        if artist_match:
            intent["artist"] = artist_match.group(1).strip()

        query_lower = cleaned.lower()
        if "aggressive" in query_lower:
            intent["characteristics"].append("aggressive")
        if "warm" in query_lower:
            intent["characteristics"].append("warm")
        if "bright" in query_lower:
            intent["characteristics"].append("bright")

        if "clarity" in query_lower or "clear" in query_lower:
            intent["processing_goals"].append("improve_clarity")
        if "punch" in query_lower or "control" in query_lower:
            intent["processing_goals"].append("control_dynamics")
        if "space" in query_lower or "wide" in query_lower:
            intent["processing_goals"].append("add_space")

        return intent

    def _chain_spec_from_cached_data(self, query: str, cached_data: Dict[str, Any], cache_age_days: int) -> ChainSpec:
        devices = []
        for d in cached_data.get("chain", []):
            devices.append(DeviceSpec(
                plugin_name=d.get("name", "Unknown"),
                category=d.get("type", "unknown"),
                parameters=d.get("settings", {}),
                purpose=d.get("purpose", ""),
                reasoning="Loaded from cache",
                confidence=cached_data.get("confidence", 0.5),
                sources=cached_data.get("sources", [])
            ))

        return ChainSpec(
            query=query,
            style_description=cached_data.get("description", "Loaded from cached research"),
            devices=devices,
            confidence=cached_data.get("confidence", 0.5),
            sources=cached_data.get("sources", []),
            artist=cached_data.get("artist_or_style"),
            meta={
                "cache_hit": True,
                "cache_age_days": cache_age_days
            }
        )

    def _get_fresh_cached_chain(self, query: str, max_age_days: int) -> Optional[ChainSpec]:
        from knowledge.plugin_chain_kb import get_plugin_chain_kb

        kb = get_plugin_chain_kb()
        matches = kb.search_chains(query)
        if not matches:
            return None

        for match in matches:
            data = match.get("data", {})
            researched_date = data.get("researched_date")
            cache_age_days = None
            if researched_date:
                try:
                    researched_dt = datetime.strptime(researched_date, "%Y-%m-%d")
                    cache_age_days = (datetime.now() - researched_dt).days
                    if cache_age_days > max_age_days:
                        continue
                except ValueError:
                    pass

            return self._chain_spec_from_cached_data(
                query=query,
                cached_data=data,
                cache_age_days=cache_age_days if cache_age_days is not None else -1
            )

        return None

    def _cache_chain_spec(self, query: str, chain_spec: ChainSpec):
        if not chain_spec.devices:
            return

        from knowledge.plugin_chain_kb import get_plugin_chain_kb
        kb = get_plugin_chain_kb()

        chain_data = [
            {
                "name": d.plugin_name,
                "type": d.category,
                "purpose": d.purpose,
                "settings": _flatten_parameters(d.parameters)
            }
            for d in chain_spec.devices
        ]

        kb.add_chain(
            artist_or_style=chain_spec.artist or query,
            track_type="vocal",
            chain=chain_data,
            sources=chain_spec.sources,
            description=chain_spec.style_description,
            confidence=chain_spec.confidence
        )

    def _get_artifact_store(self):
        """Lazy-load the ArtifactChainStore singleton."""
        if self._artifact_store is None:
            from knowledge.artifact_chain_store import get_artifact_chain_store
            self._artifact_store = get_artifact_chain_store()
        return self._artifact_store

    def _artifact_to_chain_spec(self, query: str, artifact: Dict[str, Any]) -> ChainSpec:
        """Convert a raw artifact dict to a ChainSpec for backward compatibility."""
        devices = []
        for dev in artifact.get("chain", []):
            devices.append(DeviceSpec(
                plugin_name=dev.get("plugin_name", ""),
                category=dev.get("category", "other"),
                parameters=dev.get("parameters", {}),
                purpose=dev.get("purpose", ""),
                reasoning=dev.get("notes", dev.get("purpose", "")),
                confidence=artifact.get("confidence", 0.5),
                sources=artifact.get("sources", []) if isinstance(artifact.get("sources"), list) else [],
            ))
        return ChainSpec(
            query=query,
            style_description=artifact.get("style_description", ""),
            devices=devices,
            confidence=artifact.get("confidence", 0.0),
            sources=artifact.get("sources", []) if isinstance(artifact.get("sources"), list) else [],
            artist=artifact.get("artist"),
            song=artifact.get("song"),
            meta={"artifact_source": artifact.get("source", "unknown")},
        )

    def _normalize_query_key(self, query: str) -> str:
        """Normalize a query string for simple semantic cache keys."""
        return re.sub(r"\s+", " ", (query or "").strip().lower())

    def _tokenize_query(self, query: str) -> List[str]:
        text = self._normalize_query_key(query)
        return re.findall(r"[a-z0-9]+", text)

    def _query_similarity(self, a: str, b: str) -> float:
        """Lightweight semantic-ish similarity without external dependencies."""
        a_tokens = self._tokenize_query(a)
        b_tokens = self._tokenize_query(b)
        if not a_tokens or not b_tokens:
            return 0.0

        a_set = set(a_tokens)
        b_set = set(b_tokens)
        jaccard = len(a_set & b_set) / max(1, len(a_set | b_set))

        a_counts = Counter(a_tokens)
        b_counts = Counter(b_tokens)
        shared = sum(min(a_counts[t], b_counts[t]) for t in (a_set & b_set))
        denom = max(1, min(len(a_tokens), len(b_tokens)))
        overlap = shared / denom

        return (0.7 * jaccard) + (0.3 * overlap)

    def _is_direct_daw_command(self, query: str) -> bool:
        """Detect direct Ableton-control intents that should skip research."""
        q = self._normalize_query_key(query)
        if not q:
            return False

        command_verbs = {
            "set", "change", "increase", "decrease", "turn", "arm", "mute", "unmute",
            "solo", "unsolo", "bypass", "enable", "disable", "load", "insert", "remove",
            "delete", "select", "record", "stop", "play", "freeze", "flatten", "duplicate"
        }
        daw_targets = {
            "track", "clip", "scene", "device", "plugin", "parameter", "macro", "eq",
            "compressor", "reverb", "delay", "saturator", "utility", "volume", "gain",
            "pan", "send", "threshold", "ratio", "attack", "release", "cutoff", "frequency",
            "ableton", "live"
        }

        tokens = set(self._tokenize_query(q))
        has_command = any(v in tokens for v in command_verbs)
        has_target = any(t in tokens for t in daw_targets)

        phrase_hits = any(
            phrase in q
            for phrase in [
                "on track", "on device", "set track", "set device", "arm track",
                "mute track", "solo track", "set parameter", "turn up", "turn down"
            ]
        )

        return (has_command and has_target) or phrase_hits

    def _load_research_cache(self) -> Dict[str, Any]:
        """Load cache, supporting both legacy and structured semantic formats."""
        if not os.path.exists(self._research_cache_path):
            return {"entries": []}
        try:
            with open(self._research_cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("entries"), list):
                return data
            if isinstance(data, dict):
                now = datetime.now().isoformat()
                entries = []
                for k, v in data.items():
                    entries.append({
                        "query_key": str(k),
                        "original_query": str(k),
                        "answer": str(v),
                        "route": "",
                        "created_at": now,
                        "last_hit_at": now,
                        "hit_count": 0,
                    })
                return {"entries": entries}
        except (OSError, json.JSONDecodeError):
            pass
        return {"entries": []}

    def _save_research_cache(self, cache: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self._research_cache_path), exist_ok=True)
        with open(self._research_cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)

    def _get_cached_synthesized_answer(self, query: str) -> Optional[Dict[str, Any]]:
        cache = self._load_research_cache()
        entries = cache.get("entries", [])
        if not isinstance(entries, list):
            return None

        query_key = self._normalize_query_key(query)
        for entry in entries:
            if entry.get("query_key") == query_key:
                entry["last_hit_at"] = datetime.now().isoformat()
                entry["hit_count"] = int(entry.get("hit_count", 0)) + 1
                self._save_research_cache(cache)
                return {
                    "answer": entry.get("answer", ""),
                    "cache_match_type": "exact",
                    "cache_similarity": 1.0,
                    "matched_query": entry.get("original_query") or entry.get("query_key")
                }

        if not self._enable_semantic_cache:
            return None

        best = None
        best_score = 0.0
        for entry in entries:
            candidate = entry.get("original_query") or entry.get("query_key") or ""
            score = self._query_similarity(query, candidate)
            if score > best_score:
                best_score = score
                best = entry

        if best and best_score >= self._semantic_cache_threshold:
            best["last_hit_at"] = datetime.now().isoformat()
            best["hit_count"] = int(best.get("hit_count", 0)) + 1
            self._save_research_cache(cache)
            return {
                "answer": best.get("answer", ""),
                "cache_match_type": "semantic",
                "cache_similarity": round(float(best_score), 4),
                "matched_query": best.get("original_query") or best.get("query_key")
            }

        return None

    def _store_cached_synthesized_answer(self, query: str, answer: str, route: str = "") -> None:
        cache = self._load_research_cache()
        entries = cache.setdefault("entries", [])
        query_key = self._normalize_query_key(query)
        now = datetime.now().isoformat()

        for entry in entries:
            if entry.get("query_key") == query_key:
                entry["original_query"] = query
                entry["answer"] = answer
                entry["route"] = route or entry.get("route", "")
                entry["last_hit_at"] = now
                break
        else:
            entries.append({
                "query_key": query_key,
                "original_query": query,
                "answer": answer,
                "route": route,
                "created_at": now,
                "last_hit_at": now,
                "hit_count": 0,
            })

        entries.sort(key=lambda e: (str(e.get("last_hit_at", "")), int(e.get("hit_count", 0))), reverse=True)
        cache["entries"] = entries[: self._semantic_cache_max_entries]
        self._save_research_cache(cache)

    @staticmethod
    def _parse_json_object(text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None
        content = text.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                parsed = json.loads(content[start:end])
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        return None

    async def call_cheap_llm(self, prompt: str, system_prompt: str = None) -> str:
        """
        Cheap model router/extractor helper.

        Uses gemini-2.0-flash-lite (or RESEARCH_CHEAP_MODEL override).
        """
        self._ensure_initialized()
        assert_llm_allowed()
        if not getattr(self._llm_client, "client", None):
            return ""
        try:
            response = await self._llm_client.client.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                model_id=self._cheap_model_id
            )
            if response and response.success:
                return response.content.strip()
        except LLMCallBlocked as e:
            print(f"[ResearchCoordinator] llm_blocked_execute: {e}")
            raise
        except Exception as e:
            print(f"[ResearchCoordinator] call_cheap_llm error: {e}")
        return ""

    async def call_expensive_llm(self, prompt: str, system_prompt: str = None) -> str:
        """
        Main synthesis helper.

        Uses RESEARCH_REASONING_MODEL (default gemini-2.0-flash).
        """
        self._ensure_initialized()
        assert_llm_allowed()
        if not getattr(self._llm_client, "client", None):
            return ""
        try:
            response = await self._llm_client.client.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                model_id=self._expensive_model_id
            )
            if response and response.success:
                return response.content.strip()
        except LLMCallBlocked as e:
            print(f"[ResearchCoordinator] llm_blocked_execute: {e}")
            raise
        except Exception as e:
            print(f"[ResearchCoordinator] call_expensive_llm error: {e}")
        return ""

    async def _classify_intent_with_cheap_llm(self, query: str) -> Dict[str, Any]:
        """Classify intent with cheap model (fallback to heuristic parser)."""
        prompt = f"""
Classify this research request and return JSON only:
{{
  "artist": "<string>",
  "song": "<string>",
  "style": "<string>",
  "characteristics": ["..."],
  "processing_goals": ["..."],
  "route": "simple_retrieval|complex_technique|specific_fact"
}}

Query: "{query}"
"""
        text = await self.call_cheap_llm(prompt)
        parsed = self._parse_json_object(text)
        if parsed:
            parsed["original_query"] = query
            route = str(parsed.get("route", "")).lower().strip()
            if route not in {"simple_retrieval", "complex_technique", "specific_fact"}:
                parsed["route"] = "complex_technique"
            return parsed

        fallback = self._heuristic_intent(query)
        fallback["route"] = "complex_technique"
        return fallback

    async def _summarize_source_with_cheap_llm(
        self,
        source_name: str,
        extracted_settings: List[Dict[str, Any]]
    ) -> str:
        """Cheap extraction step: summarize source payload for synthesis."""
        payload = json.dumps(extracted_settings[:20], indent=2)[:12000]
        prompt = (
            f"Summarize extracted vocal-chain settings from {source_name}. "
            "Keep it concise and factual, include key plugins/params.\n\n"
            f"{payload}"
        )
        summary = await self.call_cheap_llm(prompt)
        return summary or f"{source_name}: no summary available"
    
    def _ensure_initialized(self):
        """Lazily initialize components"""
        if self._youtube_researcher is None:
            from .youtube_research import get_youtube_researcher
            self._youtube_researcher = get_youtube_researcher()
        
        if self._web_researcher is None:
            from .web_research import get_web_researcher
            self._web_researcher = get_web_researcher()
        
        if self._llm_client is None:
            from .llm_client import get_research_llm
            self._llm_client = get_research_llm()

        if self._audio_analyst is None:
            from .audio_analyst import get_audio_analyst
            self._audio_analyst = get_audio_analyst()

    async def analyze_reference_track(self, file_path: str) -> ChainSpec:
        """
        Analyze a reference track to generate a chain spec.
        
        Args:
            file_path: Path to the reference audio file
            
        Returns:
            ChainSpec based on audio analysis
        """
        self._ensure_initialized()
        
        print(f"Thinking... Analyzing reference track: {os.path.basename(file_path)}")
        
        # Run analysis (it's blocking/heavy, so run in thread)
        analysis = await asyncio.to_thread(self._audio_analyst.analyze_track, file_path)
        
        if not analysis.get("success"):
            raise ValueError(f"Analysis failed: {analysis.get('message')}")
            
        suggestions = analysis.get("chain_spec", [])
        features = analysis.get("features", {})
        
        # Convert suggestions to generic DeviceSpecs
        devices = []
        for s in suggestions:
            devices.append(DeviceSpec(
                plugin_name=s["plugin_name"],
                category=s["category"],
                parameters=s["parameters"],
                purpose=s["purpose"],
                reasoning=f"Based on audio analysis (Centroid: {features.get('spectral_centroid_mean', 0):.0f}Hz)",
                confidence=s["confidence"],
                sources=[f"file://{file_path}"]
            ))
            
        return ChainSpec(
            query=f"Reference: {os.path.basename(file_path)}",
            style_description=f"Analysis: BPM={features.get('tempo'):.1f}, "
                              f"Brightness={features.get('spectral_centroid_mean'):.0f}Hz, "
                              f"DynRange={features.get('rms_std'):.3f}",
            devices=devices,
            confidence=0.7,
            sources=[f"file://{file_path}"]
        )

    async def perform_research(
        self,
        query: str,
        use_youtube: bool = True,
        use_web: bool = True,
        max_youtube_videos: int = 3,
        max_web_articles: int = 2,
        web_urls: List[str] = None,
        budget_mode: Optional[str] = None,
        max_total_llm_calls: Optional[int] = None,
        prefer_cache: bool = True,
        cache_max_age_days: int = 14,
        deep_research: bool = False
    ) -> Dict[str, Any]:
        """
        Intelligent research pipeline with artifact-first caching.

        Default path (deep_research=False):
          1. Check artifact store (knowledge/chains/*.json) — instant, zero LLM
          2. On miss: single-shot LLM call — 1 call produces full artifact
          3. Save artifact for future reuse

        Deep research path (deep_research=True):
          Falls through to web/YouTube scraping pipeline (legacy).
        """
        self._ensure_initialized()

        if query is None:
            query = ""
        if web_urls is None:
            web_urls = []

        policy = self._resolve_research_policy(
            budget_mode=budget_mode,
            max_sources=max(max(1, int(max_youtube_videos)), max(1, int(max_web_articles))),
            max_total_llm_calls=max_total_llm_calls,
            prefer_cache=prefer_cache,
            cache_max_age_days=cache_max_age_days
        )

        if self._enable_command_mode_bypass and self._is_direct_daw_command(query):
            bypass_chain = ChainSpec(
                query=query,
                style_description="Bypassed research: detected direct DAW command intent.",
                devices=[],
                confidence=1.0,
                sources=[],
                meta={
                    "command_mode_bypass": True,
                    "cache_hit": False,
                    "budget_mode": policy.mode,
                    "route": "command_mode",
                    "llm_calls_used": 0,
                    "llm_call_budget": policy.max_llm_calls
                }
            )
            return {
                "query": query,
                "cache_hit": False,
                "intent": {"route": "command_mode"},
                "source_summaries": {},
                "synthesized_answer": bypass_chain.style_description,
                "chain_spec": bypass_chain,
            }

        max_youtube_videos = max(0, min(int(max_youtube_videos), policy.max_youtube_videos))
        max_web_articles = max(0, min(int(max_web_articles), policy.max_web_articles))

        # ============================================================
        # 0) ARTIFACT STORE — primary cache (zero LLM calls)
        # ============================================================
        if policy.prefer_cache and query:
            artifact = self._get_artifact_store().get_artifact_for_execution(
                query, max_age_days=policy.cache_max_age_days
            )
            if artifact is not None:
                print(f"[ResearchCoordinator] artifact_hit query={query}")
                chain_spec = self._artifact_to_chain_spec(query, artifact)
                chain_spec.meta.update({
                    "cache_hit": True,
                    "cache_type": "artifact_store",
                    "cache_match": artifact.get("_cache_match", "exact"),
                    "budget_mode": policy.mode,
                    "llm_calls_used": 0,
                    "llm_call_budget": policy.max_llm_calls
                })
                return {
                    "query": query,
                    "cache_hit": True,
                    "intent": {},
                    "source_summaries": {},
                    "synthesized_answer": chain_spec.style_description,
                    "chain_spec": chain_spec,
                    "artifact": artifact,
                }

        print(f"[ResearchCoordinator] artifact_miss query={query}")

        # ============================================================
        # 0b) Legacy caches (backward compat) - fenced by flag
        # ============================================================
        allow_legacy = self._allow_legacy_chain_paths and bool(deep_research)
        if allow_legacy and policy.prefer_cache and query:
            cached = self._get_cached_synthesized_answer(query)
            if cached and cached.get("answer"):
                cached_answer = cached["answer"]
                cached_chain = self._get_fresh_cached_chain(query, policy.cache_max_age_days)
                if cached_chain is None:
                    cached_chain = ChainSpec(
                        query=query,
                        style_description=cached_answer,
                        devices=[],
                        confidence=0.0,
                        sources=[],
                        meta={}
                    )
                else:
                    cached_chain.style_description = cached_answer

                cached_chain.meta.update({
                    "cache_hit": True,
                    "cache_type": "research_cache_json",
                    "cache_match_type": cached.get("cache_match_type", "exact"),
                    "cache_similarity": cached.get("cache_similarity", 1.0),
                    "cache_matched_query": cached.get("matched_query", query),
                    "budget_mode": policy.mode,
                    "llm_calls_used": 0,
                    "llm_call_budget": policy.max_llm_calls
                })
                return {
                    "query": query,
                    "cache_hit": True,
                    "intent": {},
                    "source_summaries": {},
                    "synthesized_answer": cached_answer,
                    "chain_spec": cached_chain,
                }

            if not web_urls:
                cached_chain = self._get_fresh_cached_chain(query, policy.cache_max_age_days)
                if cached_chain:
                    cached_chain.meta.update({
                        "cache_hit": True,
                        "cache_type": "plugin_chain_kb",
                        "budget_mode": policy.mode,
                        "llm_calls_used": 0,
                        "llm_call_budget": policy.max_llm_calls
                    })
                    if cached_chain.style_description:
                        self._store_cached_synthesized_answer(query, cached_chain.style_description)
                    return {
                        "query": query,
                        "cache_hit": True,
                        "intent": {},
                        "source_summaries": {},
                        "synthesized_answer": cached_chain.style_description,
                        "chain_spec": cached_chain,
                    }

        # ============================================================
        # 1) SINGLE-SHOT RESEARCH — 1 LLM call (default, no scraping)
        # ============================================================
        if (not deep_research) or (self._strict_artifact_only and not deep_research):
            print(f"[ResearchCoordinator] single_shot_called query={query}")
            from .single_shot_research import research_chain_single_shot, build_fallback_artifact

            self._ensure_initialized()
            llm_client = getattr(self._llm_client, "client", self._llm_client)

            artifact = await research_chain_single_shot(
                query, llm_client, model_id=self._expensive_model_id
            )

            if artifact is None:
                print(f"[ResearchCoordinator] Single-shot failed, using fallback")
                artifact = build_fallback_artifact(query)

            # Persist to artifact store for future reuse
            self._get_artifact_store().save_artifact(query, artifact)

            chain_spec = self._artifact_to_chain_spec(query, artifact)
            chain_spec.meta.update({
                "cache_hit": False,
                "cache_type": "single_shot",
                "budget_mode": policy.mode,
                "llm_calls_used": 1,
                "llm_call_budget": policy.max_llm_calls,
                "route": "single_shot"
            })

            # Also persist to legacy caches for backward compat
            self._cache_chain_spec(query, chain_spec)
            self._store_cached_synthesized_answer(
                query, chain_spec.style_description, route="single_shot"
            )

            print(f"[ResearchCoordinator] Single-shot complete: "
                  f"{len(chain_spec.devices)} devices, "
                  f"{chain_spec.confidence:.2f} confidence")

            return {
                "query": query,
                "cache_hit": False,
                "intent": {},
                "source_summaries": {},
                "synthesized_answer": chain_spec.style_description,
                "chain_spec": chain_spec,
                "artifact": artifact,
            }

        # ============================================================
        # 2) DEEP RESEARCH — legacy multi-call pipeline (web/YouTube)
        # ============================================================
        print(f"[ResearchCoordinator] deep_research_called query={query}")

        llm_calls_used = 0

        # 2) Cheap-model intent classification (router)
        intent = self._heuristic_intent(query)
        intent["route"] = "complex_technique"
        if self._enable_intent_router and policy.max_llm_calls > 0:
            intent = await self._classify_intent_with_cheap_llm(query)
            llm_calls_used += 1

        route = str(intent.get("route", "complex_technique")).lower().strip()

        # Route-aware source enabling
        want_youtube = bool(use_youtube and max_youtube_videos > 0)
        want_web = bool((use_web or web_urls) and max_web_articles > 0)
        if route == "simple_retrieval":
            want_youtube = False
        elif route == "specific_fact":
            want_youtube = False

        extraction_budget_total = max(0, policy.max_llm_calls - llm_calls_used - 1)
        youtube_budget = 0
        web_budget = 0
        if want_youtube and want_web:
            youtube_budget = min(policy.max_youtube_extractions, max(1, extraction_budget_total // 2 or 1))
            web_budget = min(policy.max_web_extractions, max(1, extraction_budget_total - youtube_budget or 1))
        elif want_youtube:
            youtube_budget = min(policy.max_youtube_extractions, max(1, extraction_budget_total or 1))
        elif want_web:
            web_budget = min(policy.max_web_extractions, max(1, extraction_budget_total or 1))

        async def run_youtube():
            if not want_youtube:
                return None
            return await self._youtube_researcher.research_vocal_chain(
                query=query,
                max_videos=max_youtube_videos,
                max_llm_extractions=youtube_budget,
                transcript_char_limit=policy.transcript_char_limit,
                model_id=self._cheap_model_id,
                min_confidence_for_early_stop=policy.short_circuit_confidence
            )

        async def run_web():
            if not want_web:
                return None
            return await self._web_researcher.research_vocal_chain(
                query=query,
                max_articles=max_web_articles,
                urls=web_urls,
                max_llm_extractions=web_budget,
                article_char_limit=policy.article_char_limit,
                model_id=self._cheap_model_id,
                min_confidence_for_early_stop=policy.short_circuit_confidence,
                allow_fallback_query=policy.allow_fallback_query
            )

        # 3) Parallel fetch (YouTube + Web simultaneously)
        task_defs = []
        if want_youtube:
            task_defs.append(("youtube", run_youtube()))
        if want_web:
            task_defs.append(("web", run_web()))

        source_results: Dict[str, Any] = {}
        if task_defs:
            gathered = await asyncio.gather(*(c for _, c in task_defs), return_exceptions=True)
            for (source_name, _), result in zip(task_defs, gathered):
                if isinstance(result, Exception):
                    print(f"[ResearchCoordinator] {source_name} research error: {result}")
                    continue
                source_results[source_name] = result

        # 4) Collect extracted settings
        all_extractions: List[Dict[str, Any]] = []
        all_sources: List[str] = []
        source_llm_calls = 0
        for result in source_results.values():
            if result and hasattr(result, "extracted_settings"):
                all_extractions.extend(result.extracted_settings)
                all_sources.extend(getattr(result, "sources", []))
                source_llm_calls += int(getattr(result, "llm_extractions_used", 0))

        llm_calls_used += source_llm_calls

        # 5) Cheap-model data extraction summaries (per source payload)
        summary_tasks = []
        summary_sources = []
        for source_name, result in source_results.items():
            extracted = getattr(result, "extracted_settings", []) if result else []
            summary_sources.append(source_name)
            summary_tasks.append(self._summarize_source_with_cheap_llm(source_name, extracted))

        source_summaries: Dict[str, str] = {}
        if summary_tasks:
            summaries = await asyncio.gather(*summary_tasks, return_exceptions=True)
            for source_name, summary in zip(summary_sources, summaries):
                if isinstance(summary, Exception):
                    source_summaries[source_name] = f"{source_name}: summary failed ({summary})"
                else:
                    source_summaries[source_name] = summary
            llm_calls_used += len(summary_tasks)

        # 6) Aggregate to chain
        chain_spec = self._aggregate_to_chain_spec(
            query=query,
            intent=intent,
            extractions=all_extractions,
            sources=all_sources
        )

        if not chain_spec.devices:
            chain_spec.style_description = "Research failed - no results found from web or YouTube sources."
            chain_spec.confidence = 0.0
            chain_spec.meta = {
                "budget_mode": policy.mode,
                "cache_hit": False,
                "llm_calls_used": llm_calls_used,
                "llm_call_budget": policy.max_llm_calls,
                "route": route
            }
            return {
                "query": query,
                "cache_hit": False,
                "intent": intent,
                "source_summaries": source_summaries,
                "synthesized_answer": chain_spec.style_description,
                "chain_spec": chain_spec,
            }

        # 7) Expensive-model final synthesis only
        synth_prompt = (
            "Synthesize a final concise vocal-chain recommendation from these inputs.\n"
            f"Query: {query}\n"
            f"Intent: {json.dumps(intent, indent=2)}\n"
            f"Source summaries: {json.dumps(source_summaries, indent=2)}\n"
            "Devices:\n"
            f"{json.dumps([d.__dict__ for d in chain_spec.devices], indent=2)}\n"
            "Return plain text summary (2-4 sentences)."
        )
        synthesized_answer = await self.call_expensive_llm(synth_prompt)
        if synthesized_answer:
            llm_calls_used += 1
            chain_spec.style_description = synthesized_answer
        else:
            chain_spec.style_description = (
                f"Compiled from {len(set(all_sources))} sources in {policy.mode} mode."
            )

        chain_spec.meta = {
            "budget_mode": policy.mode,
            "cache_hit": False,
            "llm_calls_used": llm_calls_used,
            "llm_call_budget": policy.max_llm_calls,
            "route": route,
            "source_counts": {
                "youtube": 1 if want_youtube else 0,
                "web": 1 if want_web else 0
            },
            "source_urls_count": len(set(all_sources))
        }

        # Persist both existing KB cache and requested JSON query->answer cache.
        self._cache_chain_spec(query, chain_spec)
        self._store_cached_synthesized_answer(query, chain_spec.style_description, route=route)

        print(f"[ResearchCoordinator] Found {len(chain_spec.devices)} devices "
              f"with {chain_spec.confidence:.2f} confidence")

        return {
            "query": query,
            "cache_hit": False,
            "intent": intent,
            "source_summaries": source_summaries,
            "synthesized_answer": chain_spec.style_description,
            "chain_spec": chain_spec,
        }
    
    async def research_vocal_chain(
        self,
        query: str,
        use_youtube: bool = True,
        use_web: bool = True,
        max_youtube_videos: int = 3,
        max_web_articles: int = 2,
        web_urls: List[str] = None,
        budget_mode: Optional[str] = None,
        max_total_llm_calls: Optional[int] = None,
        prefer_cache: bool = True,
        cache_max_age_days: int = 14,
        deep_research: bool = False,
    ) -> ChainSpec:
        """
        Research vocal chain settings from multiple sources.
        
        Args:
            query: Search query (e.g., "Kanye Runaway vocal chain")
            use_youtube: Whether to search YouTube
            use_web: Whether to search web articles
            max_youtube_videos: Max YouTube videos to analyze
            max_web_articles: Max web articles to analyze
            web_urls: Optional specific URLs to scrape
            budget_mode: Cost/quality profile: cheap|balanced|deep
            max_total_llm_calls: Hard cap for LLM requests
            prefer_cache: Reuse recent cached research when available
            cache_max_age_days: Max age of cache entries in days
            
        Returns:
            ChainSpec with aggregated device specifications
        """
        result = await self.perform_research(
            query=query,
            use_youtube=use_youtube,
            use_web=use_web,
            max_youtube_videos=max_youtube_videos,
            max_web_articles=max_web_articles,
            web_urls=web_urls,
            budget_mode=budget_mode,
            max_total_llm_calls=max_total_llm_calls,
            prefer_cache=prefer_cache,
            cache_max_age_days=cache_max_age_days,
            deep_research=deep_research,
        )
        return result["chain_spec"]
    
    # NOTE: Fallback chain generation has been removed.
    # If research fails, it should fail clearly rather than returning generic results.
    # See _research_vocal_chain for error handling.
    
    def _aggregate_to_chain_spec(self, query: str, intent: Dict,
                                  extractions: List[Dict],
                                  sources: List[str]) -> ChainSpec:
        """
        Aggregate extraction results into a ChainSpec.
        
        Args:
            query: Original query
            intent: Parsed intent from LLM
            extractions: List of extracted device settings
            sources: List of source URLs
            
        Returns:
            Aggregated ChainSpec
        """
        # Collect and merge devices by category
        device_by_category = {}
        
        for extraction in extractions:
            name = extraction.get("name", "Unknown")
            category = extraction.get("category", "unknown").lower()
            
            # Normalize category
            category = self._normalize_category(category)
            
            # Create or update device entry
            key = f"{category}:{name}"
            
            if key not in device_by_category:
                device_by_category[key] = {
                    "name": name,
                    "category": category,
                    "purpose": extraction.get("purpose", ""),
                    "parameters": extraction.get("parameters", {}),
                    "sources": extraction.get("sources", []),
                    "count": 1
                }
            else:
                # Merge parameters
                existing = device_by_category[key]
                existing["count"] += 1
                existing["sources"].extend(extraction.get("sources", []))
                
                # Merge parameters, averaging values
                new_params = extraction.get("parameters", {})
                for param_name, param_info in new_params.items():
                    if param_name in existing["parameters"]:
                        # Average the values
                        old = existing["parameters"][param_name]
                        if isinstance(old, dict) and isinstance(param_info, dict):
                            old_val = old.get("value", 0)
                            new_val = param_info.get("value", 0)
                            old["value"] = (old_val + new_val) / 2
                            old["confidence"] = max(
                                old.get("confidence", 0.5),
                                param_info.get("confidence", 0.5)
                            )
                    else:
                        existing["parameters"][param_name] = param_info
        
        # Convert to DeviceSpec list
        devices = []
        for key, data in device_by_category.items():
            # Calculate confidence based on source count
            base_confidence = 0.5
            source_boost = min(0.3, 0.1 * (data["count"] - 1))
            confidence = base_confidence + source_boost
            
            # Boost confidence if parameters have high confidence
            param_confidences = [
                p.get("confidence", 0.5) if isinstance(p, dict) else 0.5
                for p in data["parameters"].values()
            ]
            if param_confidences:
                avg_param_confidence = sum(param_confidences) / len(param_confidences)
                confidence = (confidence + avg_param_confidence) / 2
            
            device = DeviceSpec(
                plugin_name=data["name"],
                category=data["category"],
                parameters=data["parameters"],
                purpose=data["purpose"],
                reasoning=f"Found in {data['count']} source(s)",
                confidence=min(1.0, confidence),
                sources=list(set(data["sources"]))
            )
            devices.append(device)
        
        # Order devices by signal flow
        devices = self._order_devices_by_signal_flow(devices)
        
        # Calculate overall confidence
        if devices:
            overall_confidence = sum(d.confidence for d in devices) / len(devices)
            # Boost for multiple sources
            source_count = len(set(sources))
            overall_confidence = min(1.0, overall_confidence + 0.05 * (source_count - 1))
        else:
            overall_confidence = 0.0
        
        return ChainSpec(
            query=query,
            style_description="",  # Will be filled by LLM
            devices=devices,
            confidence=overall_confidence,
            sources=list(set(sources)),
            artist=intent.get("artist"),
            song=intent.get("song"),
            genre=intent.get("style")
        )
    
    def _normalize_category(self, category: str) -> str:
        """Normalize device category to standard names"""
        category = category.lower().strip()
        
        mappings = {
            "equalizer": "eq",
            "equaliser": "eq",
            "parametric eq": "eq",
            "comp": "compressor",
            "compression": "compressor",
            "dynamics": "compressor",
            "limiter": "compressor",
            "gate": "dynamics",
            "de-esser": "dynamics",
            "deesser": "dynamics",
            "multiband": "dynamics",
            "dist": "saturation",
            "distortion": "saturation",
            "overdrive": "saturation",
            "tape": "saturation",
            "warmth": "saturation",
            "verb": "reverb",
            "room": "reverb",
            "hall": "reverb",
            "plate": "reverb",
            "echo": "delay",
            "modulation": "modulation",
            "chorus": "modulation",
            "flanger": "modulation",
            "phaser": "modulation"
        }
        
        return mappings.get(category, category)
    
    def _order_devices_by_signal_flow(self, devices: List[DeviceSpec]) -> List[DeviceSpec]:
        """Order devices by typical signal flow"""
        # Standard vocal chain order
        category_order = {
            "eq": 1,       # Initial cleanup EQ
            "dynamics": 2,  # De-essing, gating
            "compressor": 3,
            "saturation": 4,
            "delay": 5,
            "reverb": 6,
            "modulation": 7
        }
        
        # If there are multiple EQs, keep one early and one late
        eq_devices = [d for d in devices if d.category == "eq"]
        other_devices = [d for d in devices if d.category != "eq"]
        
        # Sort non-EQ devices
        other_devices.sort(key=lambda d: category_order.get(d.category, 10))
        
        # Interleave EQs - one at start, others at end
        if len(eq_devices) >= 2:
            result = [eq_devices[0]] + other_devices + eq_devices[1:]
        elif len(eq_devices) == 1:
            result = [eq_devices[0]] + other_devices
        else:
            result = other_devices
        
        return result
    
    async def research_from_cache_or_live(self, query: str,
                                           cache_max_age_days: int = 7) -> ChainSpec:
        """
        Research with caching support.
        
        Args:
            query: Search query
            cache_max_age_days: Max age of cached results to use
            
        Returns:
            ChainSpec (from cache or fresh research)
        """
        return await self.research_vocal_chain(
            query=query,
            prefer_cache=True,
            cache_max_age_days=cache_max_age_days
        )


# Singleton instance
_coordinator: Optional[ResearchCoordinator] = None


def get_research_coordinator() -> ResearchCoordinator:
    """Get the singleton ResearchCoordinator instance"""
    global _coordinator
    if _coordinator is None:
        _coordinator = ResearchCoordinator()
    return _coordinator


# Convenience function
async def research_vocal_chain(query: str, **kwargs) -> ChainSpec:
    """Research vocal chain settings from multiple sources"""
    return await get_research_coordinator().research_vocal_chain(query, **kwargs)

