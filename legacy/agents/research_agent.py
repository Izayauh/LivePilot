"""
Research Agent

Searches the web, YouTube, and documentation for audio engineering techniques.
Provides the Audio Engineer and Planner agents with up-to-date production knowledge.

Now integrated with Firecrawl MCP for comprehensive web research.
"""

from typing import Dict, Any, List, Optional
from agents import AgentType, AgentMessage
from agent_system import BaseAgent
import asyncio
import json
import re

# Import YouTube parser for extracting settings from text
try:
    from research.youtube_parser import YouTubeSettingsParser, parse_settings_from_text
    YOUTUBE_PARSER_AVAILABLE = True
except ImportError:
    YOUTUBE_PARSER_AVAILABLE = False

# Import micro settings knowledge base for precise numeric values
try:
    from knowledge.micro_settings_kb import get_micro_settings_kb
    MICRO_SETTINGS_AVAILABLE = True
except ImportError:
    MICRO_SETTINGS_AVAILABLE = False

# Import ResearchBot for deep research delegation
try:
    from research_bot import get_research_bot
    RESEARCH_BOT_AVAILABLE = True
except ImportError:
    RESEARCH_BOT_AVAILABLE = False


class ResearchAgent(BaseAgent):
    """
    Researches production techniques from external sources
    
    Responsibilities:
    - Search web for production techniques
    - Extract information from YouTube tutorials
    - Search Ableton documentation
    - Aggregate and summarize findings
    - Learn and cache new techniques
    - Research plugin chains for specific artists/styles
    """
    
    def __init__(self, orchestrator):
        super().__init__(AgentType.RESEARCHER, orchestrator)
        
        # Cache for research results
        self.research_cache: Dict[str, Dict] = {}
        
        # Plugin chain research cache
        self.plugin_chain_cache: Dict[str, Dict] = {}
        
        # Common search sources
        self.sources = {
            "youtube": "https://www.youtube.com/results?search_query=",
            "reddit": "https://www.reddit.com/r/audioengineering/search/?q=",
            "ableton_docs": "https://www.ableton.com/en/live-manual/",
            "gearslutz": "https://gearspace.com/board/search.php?searchword=",
            "sound_on_sound": "https://www.soundonsound.com/",
        }
        
        # Firecrawl integration flag
        self._firecrawl_available = True  # Will be set based on MCP availability
        
        # YouTube parser for extracting settings from scraped content
        self._youtube_parser = YouTubeSettingsParser() if YOUTUBE_PARSER_AVAILABLE else None

        # Micro settings KB for precise numeric values
        self._micro_kb = get_micro_settings_kb() if MICRO_SETTINGS_AVAILABLE else None
    
    async def process(self, message: AgentMessage) -> AgentMessage:
        """Process research requests"""
        content = message.content
        action = content.get("action", "research")
        
        if action == "research":
            results = await self._research_topic(
                topic=content.get("topic", ""),
                context=content.get("engineer_analysis", {})
            )
            return AgentMessage(
                sender=self.agent_type,
                recipient=message.sender,
                content={
                    "success": True,
                    "research": results
                },
                correlation_id=message.correlation_id
            )
        
        elif action == "research_plugin_chain":
            results = await self._research_plugin_chain(
                artist_or_style=content.get("artist_or_style", ""),
                track_type=content.get("track_type", "vocal")
            )
            return AgentMessage(
                sender=self.agent_type,
                recipient=message.sender,
                content={
                    "success": True,
                    "plugin_chain": results
                },
                correlation_id=message.correlation_id
            )
        
        elif action == "answer_question":
            answer = await self._answer_question(content.get("question", ""))
            return AgentMessage(
                sender=self.agent_type,
                recipient=message.sender,
                content={
                    "success": True,
                    "answer": answer
                },
                correlation_id=message.correlation_id
            )
        
        elif action == "search_youtube":
            results = await self._search_youtube(content.get("query", ""))
            return AgentMessage(
                sender=self.agent_type,
                recipient=message.sender,
                content={
                    "success": True,
                    "youtube_results": results
                },
                correlation_id=message.correlation_id
            )
        
        elif action == "search_docs":
            results = await self._search_documentation(content.get("query", ""))
            return AgentMessage(
                sender=self.agent_type,
                recipient=message.sender,
                content={
                    "success": True,
                    "doc_results": results
                },
                correlation_id=message.correlation_id
            )
        
        elif action == "search_web":
            results = await self._search_web(content.get("query", ""))
            return AgentMessage(
                sender=self.agent_type,
                recipient=message.sender,
                content={
                    "success": True,
                    "web_results": results
                },
                correlation_id=message.correlation_id
            )
        
        return AgentMessage(
            sender=self.agent_type,
            recipient=message.sender,
            content={"error": f"Unknown action: {action}"},
            correlation_id=message.correlation_id
        )
    
    # ==================== PLUGIN CHAIN RESEARCH ====================
    
    async def _research_plugin_chain(self, artist_or_style: str, track_type: str = "vocal") -> Dict[str, Any]:
        """
        Research a plugin chain for a specific artist or style
        
        Args:
            artist_or_style: Artist name or style (e.g., "Billie Eilish", "modern pop")
            track_type: Type of track (vocal, drums, bass, master, etc.)
            
        Returns:
            Dict with plugin chain details and sources
        """
        print(f"[RESEARCH] Searching for plugin chain: {artist_or_style} ({track_type})")
        cache_key = f"{artist_or_style.lower()}_{track_type.lower()}"
        
        # Check cache first
        if cache_key in self.plugin_chain_cache:
            cached = self.plugin_chain_cache[cache_key]
            cached["from_cache"] = True
            print(f"[RESEARCH] Found cached result for {artist_or_style}")
            return cached
        
        # Build search queries
        search_queries = [
            f"{artist_or_style} {track_type} chain plugins",
            f"{artist_or_style} mixing {track_type} processing",
            f"how to mix like {artist_or_style} {track_type}",
            f"{artist_or_style} producer {track_type} signal chain",
        ]
        
        # Collect research from multiple sources
        all_findings = []
        sources_checked = []
        
        # Search web using Firecrawl
        for query in search_queries[:2]:  # Limit to avoid too many requests
            try:
                web_results = await self._search_web_firecrawl(query)
                if web_results:
                    all_findings.extend(web_results)
                    sources_checked.append(f"web: {query}")
            except Exception as e:
                print(f"[Research] Web search error: {e}")
        
        # Add built-in knowledge
        builtin = self._get_builtin_chain_knowledge(artist_or_style, track_type)
        if builtin:
            all_findings.append(builtin)
            sources_checked.append("builtin_knowledge")
        
        # Parse and extract plugin chain from findings
        plugin_chain = self._extract_plugin_chain(all_findings, track_type)
        print(f"[RESEARCH] Extracted chain: {len(plugin_chain)} plugins from {len(sources_checked)} sources")
        
        result = {
            "artist_or_style": artist_or_style,
            "track_type": track_type,
            "chain": plugin_chain,
            "sources": sources_checked,
            "confidence": self._calculate_confidence(plugin_chain, len(sources_checked)),
            "from_cache": False
        }
        
        # Cache the result
        self.plugin_chain_cache[cache_key] = result
        
        return result
    
    async def _search_web_firecrawl(self, query: str) -> List[Dict]:
        """
        Search the web using the web_research module.

        Uses Serper API (Google search) and BeautifulSoup for scraping,
        with LLM-based extraction of plugin chain settings.
        """
        try:
            from research.web_research import get_web_researcher
            from research.research_coordinator import get_research_coordinator

            # Use the research coordinator for comprehensive research
            coordinator = get_research_coordinator()
            chain_spec = await coordinator.research_vocal_chain(
                query,
                use_youtube=True,
                use_web=True,
                max_youtube_videos=2,
                max_web_articles=2
            )

            if chain_spec and chain_spec.devices:
                # Convert ChainSpec devices to the format expected by _extract_plugin_chain
                results = []
                for device in chain_spec.devices:
                    # Convert parameters to simple values
                    settings = {}
                    for param_name, param_info in device.parameters.items():
                        if isinstance(param_info, dict):
                            settings[param_name] = param_info.get("value", param_info)
                        else:
                            settings[param_name] = param_info

                    results.append({
                        "type": device.category,
                        "name": device.plugin_name,
                        "purpose": device.purpose,
                        "settings": settings,
                        "sources": device.sources,
                        "confidence": device.confidence,
                        "source": "web_research"
                    })

                print(f"[RESEARCH] Web search found {len(results)} devices for: {query}")
                return results

            print(f"[RESEARCH] Web search returned no results for: {query}")
            return []

        except ImportError as e:
            print(f"[RESEARCH] Web research module not available: {e}")
            return []
        except Exception as e:
            print(f"[RESEARCH] Web search error for '{query}': {e}")
            return []
    
    def _build_search_operators(self, query: str) -> str:
        """Build search operators for better results"""
        # Focus on audio production sites
        operators = [
            f'"{query}"',  # Exact match
            'site:reddit.com/r/audioengineering OR site:reddit.com/r/mixingmastering',
            'site:gearslutz.com OR site:gearspace.com',
            'site:soundonsound.com',
            'site:attackmagazine.com',
        ]
        return ' OR '.join(operators)
    
    async def deep_research(self, artist: str, style: str = "",
                           era: str = "", track_type: str = "vocal") -> Dict:
        """
        Delegate to ResearchBot for deep research with web + YouTube + LLM extraction.

        Returns research result with precise numeric parameter values.
        """
        if not RESEARCH_BOT_AVAILABLE:
            return {"success": False, "message": "ResearchBot not available"}

        bot = get_research_bot()
        style_hint = style or era
        result = await bot.research_micro_settings(artist, style_hint, track_type)
        return {
            "success": result.get("confidence", 0) > 0,
            "devices": result.get("devices", {}),
            "confidence": result.get("confidence", 0),
            "sources": result.get("sources", []),
        }

    def _get_builtin_chain_knowledge(self, artist_or_style: str, track_type: str) -> Optional[Dict]:
        """Get built-in knowledge about common plugin chains.

        Now checks micro_settings_kb first for precise numeric values,
        falling back to the original string-based chains.
        """
        # Try micro settings KB first (precise numeric values)
        if self._micro_kb:
            micro = self._micro_kb.get_settings(artist_or_style, "", track_type)
            if micro:
                # Convert micro settings format to chain format expected downstream
                chain = []
                for key, dev_config in micro.get("devices", {}).items():
                    chain.append({
                        "type": dev_config.get("device", "").lower().replace(" ", "_"),
                        "purpose": dev_config.get("purpose", key),
                        "desired_plugin": dev_config.get("device", ""),
                        "settings": dev_config.get("parameters", {}),
                    })
                return {
                    "source": "micro_settings_kb",
                    "artist": artist_or_style,
                    "data": {
                        "description": micro.get("description", ""),
                        "chain": chain,
                    }
                }

        artist_lower = artist_or_style.lower()

        # Built-in artist/style specific chains (legacy string-based fallback)
        known_chains = {
            "billie eilish": {
                "vocal": {
                    "description": "Intimate, breathy vocal with dark reverb",
                    "chain": [
                        {"type": "eq", "purpose": "high_pass", "settings": {"freq": "80-100Hz"}},
                        {"type": "compressor", "purpose": "gentle_control", "settings": {"ratio": "2:1", "attack": "medium"}},
                        {"type": "de-esser", "purpose": "sibilance_control"},
                        {"type": "eq", "purpose": "presence", "settings": {"boost": "2-3kHz subtle"}},
                        {"type": "saturation", "purpose": "warmth", "settings": {"subtle": True}},
                        {"type": "reverb", "purpose": "atmosphere", "settings": {"dark": True, "long_decay": True}},
                        {"type": "delay", "purpose": "depth", "settings": {"subtle": True, "filtered": True}},
                    ],
                    "notes": "Keep it intimate and close. Heavy use of whisper processing."
                }
            },
            "the weeknd": {
                "vocal": {
                    "description": "Smooth R&B vocal with modern production",
                    "chain": [
                        {"type": "eq", "purpose": "high_pass", "settings": {"freq": "100Hz"}},
                        {"type": "compressor", "purpose": "control", "settings": {"ratio": "4:1"}},
                        {"type": "de-esser", "purpose": "sibilance_control"},
                        {"type": "eq", "purpose": "air", "settings": {"boost": "10-12kHz"}},
                        {"type": "reverb", "purpose": "space", "settings": {"plate": True}},
                        {"type": "delay", "purpose": "width", "settings": {"stereo": True}},
                    ]
                }
            },
            "kanye west": {
                "vocal": {
                    "description": "Modern Kanye (Donda/Vultures): Aggressive compression, prominent presence, tight delays, upfront sound",
                    "chain": [
                        {"type": "eq", "purpose": "high_pass", "settings": {"freq": "100-120Hz", "notes": "Clean up low end rumble"}},
                        {"type": "compressor", "purpose": "aggressive_compression", "settings": {
                            "ratio": "8:1",
                            "threshold": "-18dB",
                            "attack": "fast",
                            "release": "medium-fast",
                            "notes": "Very aggressive - almost squashing for upfront sound, makes vocal sit on top of dense mix"
                        }},
                        {"type": "de-esser", "purpose": "sibilance_control", "settings": {
                            "freq": "6-8kHz",
                            "notes": "Control harshness from aggressive compression"
                        }},
                        {"type": "saturation", "purpose": "character", "settings": {
                            "moderate": True,
                            "notes": "Add harmonic saturation for grit and warmth, compensates for digital clarity"
                        }},
                        {"type": "eq", "purpose": "presence_boost", "settings": {
                            "boost": "2-5kHz aggressive",
                            "cut": "200-400Hz subtle",
                            "notes": "Make vocal cut through dense instrumentation, remove mud. This is THE Kanye signature move."
                        }},
                        {"type": "delay", "purpose": "rhythmic_space", "settings": {
                            "time": "1/8_note",
                            "feedback": "20-30%",
                            "mix": "15-25%",
                            "filtered": True,
                            "notes": "Tight, rhythmic delays that accent the beat. Not washy."
                        }},
                        {"type": "reverb", "purpose": "depth", "settings": {
                            "short": True,
                            "mix": "10-15%",
                            "predelay": "20-40ms",
                            "notes": "Keep it tight, not washy. Just enough to add dimension without losing clarity."
                        }},
                    ],
                    "notes": "Modern Kanye vocal chains (Donda/Vultures era) are HEAVILY processed and sit right on top of the mix. Key characteristics: 1) Aggressive compression (8:1 or higher) for consistent, upfront sound. 2) Prominent 2-5kHz presence boost to cut through dense production. 3) Tight, rhythmic delays (not ambient). 4) Minimal reverb for clarity. 5) Saturation for character and warmth. NOTE: Auto-Tune is signature but must be added manually (fast retune 10-20ms, chromatic or natural minor scale, formant natural or slight shift). The vocal should sound larger than life - almost squashed but clear.",
                    "autotune_required": True,
                    "autotune_settings": "Fast retune (10-20ms), chromatic or natural minor scale, formant natural or slight shift upward for brightness"
                },
                "drums": {
                    "description": "Punchy, saturated drum bus with weight",
                    "chain": [
                        {"type": "eq", "purpose": "low_end_control", "settings": {"boost": "60-80Hz", "notes": "Add weight and power"}},
                        {"type": "compressor", "purpose": "glue", "settings": {"ratio": "4:1", "attack": "slow", "notes": "Preserve transients"}},
                        {"type": "saturation", "purpose": "punch", "settings": {"heavy": True, "notes": "Add harmonic excitement and aggression"}},
                        {"type": "limiter", "purpose": "peaks", "settings": {"notes": "Catch peaks, add final punch"}}
                    ]
                }
            },
            "kanye": {
                "vocal": "kanye west.vocal",
                "drums": "kanye west.drums"
            },
            "modern pop": {
                "vocal": {
                    "description": "Polished, upfront pop vocal",
                    "chain": [
                        {"type": "eq", "purpose": "high_pass", "settings": {"freq": "80Hz"}},
                        {"type": "compressor", "purpose": "leveling", "settings": {"ratio": "4:1", "attack": "fast"}},
                        {"type": "de-esser", "purpose": "sibilance_control"},
                        {"type": "eq", "purpose": "presence_and_air", "settings": {"boost": "3-5kHz, 10kHz"}},
                        {"type": "limiter", "purpose": "peaks"},
                        {"type": "reverb", "purpose": "polish", "settings": {"short": True}},
                    ]
                }
            },
            "hip hop": {
                "vocal": {
                    "description": "Punchy, upfront hip hop vocal",
                    "chain": [
                        {"type": "eq", "purpose": "high_pass", "settings": {"freq": "100Hz"}},
                        {"type": "compressor", "purpose": "punch", "settings": {"ratio": "6:1", "fast_attack": True}},
                        {"type": "de-esser", "purpose": "sibilance_control"},
                        {"type": "saturation", "purpose": "grit", "settings": {"moderate": True}},
                        {"type": "eq", "purpose": "presence", "settings": {"boost": "2-4kHz"}},
                        {"type": "delay", "purpose": "space", "settings": {"1/4_note": True}},
                    ]
                }
            },
            "rock": {
                "vocal": {
                    "description": "Powerful rock vocal with edge",
                    "chain": [
                        {"type": "eq", "purpose": "high_pass", "settings": {"freq": "120Hz"}},
                        {"type": "compressor", "purpose": "aggression", "settings": {"ratio": "8:1"}},
                        {"type": "distortion", "purpose": "edge", "settings": {"subtle": True}},
                        {"type": "eq", "purpose": "cut_through", "settings": {"boost": "2-4kHz"}},
                        {"type": "reverb", "purpose": "space", "settings": {"room": True}},
                    ]
                }
            }
        }
        
        # Check for artist/style match (with alias support)
        for key, styles in known_chains.items():
            if key in artist_lower:
                if track_type.lower() in styles:
                    style_data = styles[track_type.lower()]

                    # Handle aliases (e.g., "kanye" -> "kanye west.vocal")
                    if isinstance(style_data, str) and "." in style_data:
                        # It's a reference like "kanye west.vocal"
                        ref_artist, ref_type = style_data.split(".")
                        if ref_artist in known_chains and ref_type in known_chains[ref_artist]:
                            style_data = known_chains[ref_artist][ref_type]
                            # Update key to actual artist for proper attribution
                            key = ref_artist

                    return {
                        "source": "builtin_knowledge",
                        "artist": key,
                        "data": style_data
                    }
        
        # Default chain if nothing specific found
        default_chains = {
            "vocal": {
                "description": "Standard vocal processing chain",
                "chain": [
                    {"type": "eq", "purpose": "high_pass"},
                    {"type": "compressor", "purpose": "dynamics"},
                    {"type": "de-esser", "purpose": "sibilance"},
                    {"type": "eq", "purpose": "tone_shaping"},
                    {"type": "reverb", "purpose": "space"},
                ]
            },
            "drums": {
                "description": "Standard drum bus processing",
                "chain": [
                    {"type": "eq", "purpose": "cleanup"},
                    {"type": "compressor", "purpose": "glue"},
                    {"type": "saturation", "purpose": "punch"},
                    {"type": "limiter", "purpose": "control"},
                ]
            },
            "bass": {
                "description": "Standard bass processing",
                "chain": [
                    {"type": "eq", "purpose": "low_end_control"},
                    {"type": "compressor", "purpose": "consistency"},
                    {"type": "saturation", "purpose": "harmonics"},
                ]
            },
            "master": {
                "description": "Standard mastering chain",
                "chain": [
                    {"type": "eq", "purpose": "tonal_balance"},
                    {"type": "compressor", "purpose": "glue"},
                    {"type": "limiter", "purpose": "loudness"},
                ]
            }
        }
        
        if track_type.lower() in default_chains:
            return {
                "source": "builtin_default",
                "artist": "generic",
                "data": default_chains[track_type.lower()]
            }
        
        return None
    
    def _extract_plugin_chain(self, findings: List[Dict], track_type: str) -> List[Dict]:
        """
        Extract a structured plugin chain from research findings
        
        Args:
            findings: List of research results
            track_type: Type of track being processed
            
        Returns:
            List of plugins in chain order
        """
        chain = []
        
        # Process builtin knowledge first (most reliable)
        for finding in findings:
            if finding.get("source") in ["builtin_knowledge", "builtin_default", "micro_settings_kb"]:
                data = finding.get("data", {})
                for plugin in data.get("chain", []):
                    chain.append({
                        "type": plugin.get("type"),
                        "purpose": plugin.get("purpose", ""),
                        "settings": plugin.get("settings", {}),
                        "confidence": 0.95 if finding["source"] == "micro_settings_kb" else (0.9 if finding["source"] == "builtin_knowledge" else 0.7)
                    })
                break  # Use first builtin match
        
        # If no builtin, try to parse web findings
        if not chain:
            for finding in findings:
                if finding.get("needs_firecrawl"):
                    # This will be handled by the engine using Firecrawl MCP
                    # For now, return a basic chain
                    chain = self._get_default_chain(track_type)
        
        return chain
    
    def _get_default_chain(self, track_type: str) -> List[Dict]:
        """Get a default chain for a track type"""
        defaults = {
            "vocal": [
                {"type": "eq", "purpose": "high_pass", "confidence": 0.8},
                {"type": "compressor", "purpose": "dynamics", "confidence": 0.8},
                {"type": "de-esser", "purpose": "sibilance", "confidence": 0.7},
                {"type": "reverb", "purpose": "space", "confidence": 0.7},
            ],
            "drums": [
                {"type": "eq", "purpose": "shape", "confidence": 0.8},
                {"type": "compressor", "purpose": "punch", "confidence": 0.8},
                {"type": "saturation", "purpose": "color", "confidence": 0.6},
            ],
            "bass": [
                {"type": "eq", "purpose": "low_control", "confidence": 0.8},
                {"type": "compressor", "purpose": "consistency", "confidence": 0.8},
            ],
            "master": [
                {"type": "eq", "purpose": "balance", "confidence": 0.8},
                {"type": "compressor", "purpose": "glue", "confidence": 0.8},
                {"type": "limiter", "purpose": "loudness", "confidence": 0.9},
            ],
        }
        return defaults.get(track_type.lower(), defaults["vocal"])
    
    def _calculate_confidence(self, chain: List[Dict], source_count: int) -> float:
        """Calculate overall confidence in research results"""
        if not chain:
            return 0.0
        
        avg_confidence = sum(p.get("confidence", 0.5) for p in chain) / len(chain)
        source_bonus = min(source_count * 0.1, 0.2)
        
        return min(avg_confidence + source_bonus, 1.0)
    
    def parse_scraped_content(self, 
                             content: str, 
                             artist_or_style: str, 
                             track_type: str = "vocal",
                             source_url: str = "",
                             source_title: str = "") -> Dict[str, Any]:
        """
        Parse scraped web content (from Firecrawl) to extract plugin chain settings.
        
        Args:
            content: Text content from scraped page
            artist_or_style: Artist or style being researched
            track_type: Type of track
            source_url: URL the content came from
            source_title: Title of the source page
            
        Returns:
            Dict with extracted devices and settings
        """
        if not self._youtube_parser:
            return {
                "success": False,
                "message": "YouTube parser not available",
                "devices": []
            }
        
        try:
            # Parse the content
            chain = self._youtube_parser.parse_text(content, artist_or_style, track_type)
            chain.source_url = source_url
            chain.source_title = source_title
            
            # Convert to device list
            device_list = self._youtube_parser.chain_to_device_list(chain)
            
            return {
                "success": True,
                "artist_or_style": artist_or_style,
                "track_type": track_type,
                "devices": device_list,
                "device_count": len(device_list),
                "source_url": source_url,
                "source_title": source_title,
                "raw_devices": [
                    {
                        "name": d.name,
                        "type": d.device_type,
                        "settings": d.settings,
                        "raw_text": d.raw_text[:200] if d.raw_text else ""
                    }
                    for d in chain.devices
                ]
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error parsing content: {e}",
                "devices": []
            }
    
    def merge_research_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Merge multiple research results into a single plugin chain.
        
        Combines devices from multiple sources, deduplicates, and
        assigns confidence based on how many sources agree.
        
        Args:
            results: List of parse_scraped_content results
            
        Returns:
            Merged plugin chain with confidence scores
        """
        if not results:
            return {"success": False, "devices": [], "message": "No results to merge"}
        
        # Track device mentions across sources
        device_mentions = {}  # device_type -> {name: count, settings: [...]}
        
        for result in results:
            if not result.get("success"):
                continue
            
            for device in result.get("devices", []):
                dtype = device.get("type", "unknown")
                name = device.get("name", "Unknown")
                
                if dtype not in device_mentions:
                    device_mentions[dtype] = {"names": {}, "settings_list": []}
                
                if name not in device_mentions[dtype]["names"]:
                    device_mentions[dtype]["names"][name] = 0
                device_mentions[dtype]["names"][name] += 1
                
                if device.get("settings"):
                    device_mentions[dtype]["settings_list"].append(device["settings"])
        
        # Build merged chain with most common devices
        merged_chain = []
        
        # Standard order for processing chain
        device_order = ["eq", "compressor", "de_esser", "saturation", "modulation", "reverb", "delay", "limiter"]
        
        for dtype in device_order:
            if dtype in device_mentions:
                # Get most common name for this device type
                names = device_mentions[dtype]["names"]
                best_name = max(names.keys(), key=lambda n: names[n])
                mention_count = names[best_name]
                
                # Average settings if multiple
                merged_settings = {}
                for settings in device_mentions[dtype]["settings_list"]:
                    for key, value in settings.items():
                        if key not in merged_settings:
                            merged_settings[key] = []
                        merged_settings[key].append(value)
                
                # Average numeric settings
                final_settings = {}
                for key, values in merged_settings.items():
                    if all(isinstance(v, (int, float)) for v in values):
                        final_settings[key] = sum(values) / len(values)
                    else:
                        final_settings[key] = values[0]  # Use first value
                
                merged_chain.append({
                    "name": best_name,
                    "type": dtype,
                    "settings": final_settings,
                    "confidence": min(0.5 + mention_count * 0.1, 1.0),
                    "source_count": mention_count
                })
        
        return {
            "success": True,
            "devices": merged_chain,
            "device_count": len(merged_chain),
            "total_sources": len([r for r in results if r.get("success")]),
            "message": f"Merged {len(merged_chain)} devices from {len(results)} sources"
        }
    
    # ==================== GENERAL RESEARCH ====================
    
    async def _research_topic(self, topic: str, context: Dict = None) -> Dict[str, Any]:
        """
        Research a production topic using available resources
        """
        print(f"[RESEARCH] Researching topic: {topic}")
        # Check cache first
        cache_key = topic.lower().strip()
        if cache_key in self.research_cache:
            return self.research_cache[cache_key]
        
        results = {
            "topic": topic,
            "sources_checked": [],
            "techniques_found": [],
            "recommendations": [],
            "related_topics": [],
            "confidence": 0.0
        }
        
        # Use built-in knowledge first
        builtin_knowledge = self._search_builtin_knowledge(topic)
        if builtin_knowledge:
            results["techniques_found"].extend(builtin_knowledge)
            results["sources_checked"].append("internal_knowledge_base")
            results["confidence"] = 0.8
        
        # If we have Firecrawl MCP available, use it for web search
        # For now, we'll use the built-in knowledge and flag for external research
        if not builtin_knowledge or results["confidence"] < 0.7:
            results["needs_external_research"] = True
            results["suggested_searches"] = self._generate_search_queries(topic)
        
        # Cache the results
        self.research_cache[cache_key] = results
        
        return results
    
    async def _search_web(self, query: str) -> List[Dict]:
        """
        Search the web for a query using Firecrawl MCP
        
        Returns structured search results
        """
        return [{
            "query": query,
            "needs_firecrawl": True,
            "suggested_search": f"{query} audio production mixing"
        }]
    
    def _search_builtin_knowledge(self, topic: str) -> List[Dict]:
        """Search built-in audio engineering knowledge"""
        topic_lower = topic.lower()
        found = []
        
        # Keyword to technique mappings
        keyword_mappings = {
            "punch": [
                {
                    "technique": "Parallel Compression",
                    "description": "Blend heavily compressed signal with dry for punch without losing dynamics",
                    "steps": [
                        "Create a bus/return track",
                        "Add compressor with high ratio (8:1 or more)",
                        "Fast attack (1-10ms), medium release",
                        "Blend 20-40% with original"
                    ]
                },
                {
                    "technique": "Transient Shaping",
                    "description": "Enhance attack transients for more punch",
                    "steps": [
                        "Add transient shaper (e.g., Drum Buss)",
                        "Increase attack parameter",
                        "Optionally reduce sustain for tighter sound"
                    ]
                }
            ],
            "warm": [
                {
                    "technique": "Saturation",
                    "description": "Add harmonic content for warmth",
                    "steps": [
                        "Add Saturator or tape emulation",
                        "Set subtle drive (10-20%)",
                        "Optionally roll off harsh highs"
                    ]
                },
                {
                    "technique": "Tube Compression",
                    "description": "Use tube-style compression for analog warmth",
                    "steps": [
                        "Add tube-style compressor",
                        "Use moderate ratio (2-4:1)",
                        "Slower attack for more character"
                    ]
                }
            ],
            "bright": [
                {
                    "technique": "High Shelf Boost",
                    "description": "Boost high frequencies for brightness",
                    "steps": [
                        "Add EQ Eight",
                        "Add high shelf at 8-12kHz",
                        "Boost 2-4dB to taste"
                    ]
                },
                {
                    "technique": "Air EQ",
                    "description": "Add presence in the 10-16kHz range",
                    "steps": [
                        "Add EQ with air band (10kHz+)",
                        "Gentle boost for sparkle",
                        "Check for harshness"
                    ]
                }
            ],
            "sidechain": [
                {
                    "technique": "Sidechain Compression",
                    "description": "Duck one signal when another plays",
                    "steps": [
                        "Add compressor to target track (e.g., bass)",
                        "Enable sidechain input",
                        "Route kick to sidechain",
                        "Adjust ratio (4:1 to 10:1)",
                        "Fast attack, medium release"
                    ]
                }
            ],
            "wide": [
                {
                    "technique": "Stereo Widening",
                    "description": "Increase stereo width of a sound",
                    "steps": [
                        "Add Utility device",
                        "Increase Width parameter",
                        "Check mono compatibility",
                        "Alternatively use chorus or haas effect"
                    ]
                }
            ],
            "compression": [
                {
                    "technique": "Basic Compression",
                    "description": "Control dynamics with compression",
                    "settings": {
                        "threshold": "Set so peaks trigger 3-6dB reduction",
                        "ratio": "2:1 to 4:1 for subtle, 6:1+ for aggressive",
                        "attack": "Fast for control, slow for punch",
                        "release": "Match song tempo or use auto"
                    }
                }
            ],
            "eq": [
                {
                    "technique": "Subtractive EQ",
                    "description": "Cut problems before boosting",
                    "common_cuts": {
                        "mud": "200-400Hz",
                        "boxiness": "300-600Hz",
                        "harshness": "2-4kHz"
                    }
                },
                {
                    "technique": "High Pass Filter",
                    "description": "Remove unnecessary low frequencies",
                    "settings": {
                        "vocals": "80-120Hz",
                        "guitars": "80-100Hz",
                        "most_instruments": "30-60Hz"
                    }
                }
            ],
            "vocal": [
                {
                    "technique": "Vocal Chain",
                    "description": "Standard vocal processing",
                    "steps": [
                        "1. High-pass filter (80-120Hz)",
                        "2. Subtractive EQ for problems",
                        "3. Compression (3-6dB reduction)",
                        "4. De-esser if sibilant",
                        "5. Presence/air EQ boost",
                        "6. Reverb/delay to taste"
                    ]
                }
            ],
            "master": [
                {
                    "technique": "Mastering Chain",
                    "description": "Basic mastering setup",
                    "steps": [
                        "1. Corrective EQ",
                        "2. Multiband compression (optional)",
                        "3. Stereo enhancement (subtle)",
                        "4. Limiter for loudness",
                        "5. Final EQ tweaks"
                    ],
                    "targets": {
                        "streaming": "-14 LUFS",
                        "true_peak": "-1dB"
                    }
                }
            ]
        }
        
        # Search for matching keywords
        for keyword, techniques in keyword_mappings.items():
            if keyword in topic_lower:
                found.extend(techniques)
        
        return found
    
    def _generate_search_queries(self, topic: str) -> List[str]:
        """Generate search queries for external research"""
        base_queries = [
            f"{topic} ableton live tutorial",
            f"how to {topic} in ableton",
            f"{topic} mixing technique",
            f"{topic} audio production tips",
        ]
        return base_queries
    
    async def _answer_question(self, question: str) -> str:
        """Answer a direct question about audio production"""
        question_lower = question.lower()
        
        # Check for common questions
        if "what is" in question_lower:
            # Extract the subject
            if "compression" in question_lower:
                return ("Compression reduces the dynamic range of audio by attenuating loud signals "
                        "and boosting quiet ones. Key parameters are threshold, ratio, attack, and release. "
                        "It's used to control dynamics, add punch, and glue elements together.")
            
            if "eq" in question_lower or "equalization" in question_lower:
                return ("EQ (equalization) adjusts the balance of frequency components in audio. "
                        "You can cut or boost specific frequencies to shape the tone. "
                        "Common types: parametric, shelving, and graphic EQ.")
            
            if "sidechain" in question_lower:
                return ("Sidechain compression uses one audio signal to control compression on another. "
                        "Common use: ducking bass when kick hits. The kick triggers the compressor "
                        "on the bass, creating space and the classic 'pumping' effect.")
            
            if "reverb" in question_lower:
                return ("Reverb simulates the natural reflections in acoustic spaces. "
                        "Key parameters: decay time, pre-delay, size, wet/dry mix. "
                        "Used for depth, space, and blending elements together.")
        
        if "how to" in question_lower or "how do" in question_lower:
            # Research the topic
            research = await self._research_topic(question)
            if research.get("techniques_found"):
                technique = research["techniques_found"][0]
                steps = technique.get("steps", [])
                if steps:
                    return f"{technique.get('technique', 'Technique')}: {technique.get('description', '')}. Steps: {', '.join(steps)}"
        
        return "I don't have a specific answer for that. Try asking about compression, EQ, reverb, or specific mixing techniques."
    
    async def _search_youtube(self, query: str) -> List[Dict]:
        """
        Search YouTube for tutorials
        Note: This would use YouTube API or Firecrawl in production
        """
        # Placeholder - would integrate with YouTube API
        return [
            {
                "type": "youtube_search_query",
                "query": f"{query} ableton tutorial",
                "url": f"{self.sources['youtube']}{query.replace(' ', '+')}"
            }
        ]
    
    async def _search_documentation(self, query: str) -> List[Dict]:
        """
        Search Ableton documentation
        Note: This would use Firecrawl in production
        """
        # Placeholder - would scrape actual docs
        return [
            {
                "type": "documentation_search",
                "source": "Ableton Live Manual",
                "url": self.sources["ableton_docs"]
            }
        ]
    
    def clear_cache(self):
        """Clear the research cache"""
        self.research_cache.clear()
        self.plugin_chain_cache.clear()
    
    def get_cached_topics(self) -> List[str]:
        """Get list of cached research topics"""
        return list(self.research_cache.keys())
    
    def get_cached_chains(self) -> List[str]:
        """Get list of cached plugin chains"""
        return list(self.plugin_chain_cache.keys())


# Standalone function for use outside agent system
async def research_plugin_chain(artist_or_style: str, track_type: str = "vocal") -> Dict:
    """
    Research a plugin chain without using the agent system
    
    Args:
        artist_or_style: Artist name or style
        track_type: Type of track
        
    Returns:
        Plugin chain research results
    """
    agent = ResearchAgent(None)
    return await agent._research_plugin_chain(artist_or_style, track_type)
