"""
Single-Shot Research

Produces a complete vocal chain artifact in ONE LLM call.
No web scraping, no YouTube scraping, no multi-step pipeline.
Relies on the LLM's training data to produce production-quality specs.

Usage:
    from research.single_shot_research import research_chain_single_shot
    artifact = await research_chain_single_shot("Travis Scott Utopia vocal chain", llm_client)
"""

import json
import logging
from typing import Dict, Any, Optional

from pipeline.guardrail import assert_llm_allowed, LLMCallBlocked

logger = logging.getLogger("jarvis.research.single_shot")

# The one prompt that replaces 5-8 LLM calls
_SINGLE_SHOT_PROMPT = """\
You are an expert audio engineer and music producer. Given a vocal chain request, \
return a COMPLETE JSON artifact with ordered plugins, exact numeric parameter values, \
and fallback alternatives. This must be ready to load directly into Ableton Live.

RULES:
1. Use Ableton stock plugin names exactly (e.g. "EQ Eight", "Compressor", "Glue Compressor", \
"Multiband Dynamics", "Saturator", "Reverb", "Delay", "Limiter", "Utility", "Auto Filter").
2. Parameters must use exact Ableton parameter names and NUMERIC values only. \
No vague terms like "medium" or "subtle" — use actual numbers.
3. For each plugin, include "fallbacks" — alternative stock plugins that could substitute.
4. Order the chain by signal flow (typically: EQ/cleanup → compression → de-essing → \
saturation → EQ/tone → reverb/delay → limiting).
5. Include "safe_ranges" for any parameter where going out of bounds could cause issues.
6. Confidence should reflect how well-documented this particular artist/style's \
processing is.

Return ONLY valid JSON, no markdown fences, no explanation. Use this exact schema:

{{
  "artist": "<artist name or empty>",
  "song": "<song/album or empty>",
  "track_type": "vocal",
  "style_description": "<2-3 sentence description of the vocal sound>",
  "confidence": <0.0 to 1.0>,
  "chain": [
    {{
      "plugin_name": "<exact Ableton device name>",
      "category": "<eq|compressor|gate|de-esser|saturation|reverb|delay|limiter|utility|other>",
      "purpose": "<what this plugin does in the chain>",
      "parameters": {{
        "<exact param name>": <numeric value>,
        ...
      }},
      "fallbacks": ["<alt plugin 1>", ...]
    }}
  ],
  "safe_ranges": {{
    "<param name>": [<min>, <max>],
    ...
  }},
  "notes": "<any relevant production notes>"
}}

VOCAL CHAIN REQUEST: "{query}"
"""


async def research_chain_single_shot(
    query: str,
    llm_client,
    model_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Produce a full chain artifact in a single LLM call.

    Args:
        query: User's chain request (e.g. "Travis Scott Utopia vocal chain")
        llm_client: BaseLLMClient or compatible (must have .generate())
        model_id: Optional override for which model to use

    Returns:
        Parsed artifact dict, or None on failure.
    """
    prompt = _SINGLE_SHOT_PROMPT.format(query=query)

    try:
        assert_llm_allowed()
        logger.info(f"[SingleShot] Researching: {query}")

        kwargs = {"prompt": prompt}
        if model_id:
            kwargs["model_id"] = model_id

        response = await llm_client.generate(**kwargs)

        if not response or not getattr(response, "success", False):
            error = getattr(response, "error", "unknown") if response else "no response"
            logger.warning(f"[SingleShot] LLM call failed: {error}")
            return None

        raw = response.content.strip()
        artifact = _parse_artifact_json(raw)

        if artifact is None:
            logger.warning(f"[SingleShot] Failed to parse LLM response as JSON")
            logger.debug(f"[SingleShot] Raw response: {raw[:500]}")
            return None

        # Validate minimum structure
        if not artifact.get("chain"):
            logger.warning("[SingleShot] LLM returned empty chain")
            return None

        artifact["source"] = f"single-shot-{model_id or 'default'}"
        artifact["query"] = query
        artifact.setdefault("track_type", "vocal")

        logger.info(
            f"[SingleShot] Got {len(artifact['chain'])} plugins "
            f"with confidence {artifact.get('confidence', 0):.2f}"
        )
        return artifact

    except LLMCallBlocked as e:
        logger.error(f"[SingleShot] llm_blocked_execute: {e}")
        raise
    except Exception as e:
        logger.error(f"[SingleShot] Research failed: {e}")
        return None


def _parse_artifact_json(text: str) -> Optional[Dict[str, Any]]:
    """Parse JSON from LLM response, handling markdown fences and junk."""
    if not text:
        return None

    content = text.strip()

    # Strip markdown code fences
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    # Try direct parse
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass

    # Try extracting first JSON object
    start = content.find("{")
    end = content.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            parsed = json.loads(content[start:end])
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def build_fallback_artifact(query: str, track_type: str = "vocal") -> Dict[str, Any]:
    """
    Return a safe, generic stock chain when the LLM call fails.
    This ensures the user always gets *something* loaded.
    """
    if track_type == "vocal":
        return {
            "query": query,
            "artist": "",
            "song": "",
            "track_type": "vocal",
            "style_description": "Generic vocal chain — LLM research was unavailable.",
            "confidence": 0.4,
            "source": "fallback-stock",
            "chain": [
                {
                    "plugin_name": "EQ Eight",
                    "category": "eq",
                    "purpose": "high_pass_cleanup",
                    "parameters": {},
                    "fallbacks": [],
                },
                {
                    "plugin_name": "Compressor",
                    "category": "compressor",
                    "purpose": "dynamics_control",
                    "parameters": {},
                    "fallbacks": ["Glue Compressor"],
                },
                {
                    "plugin_name": "EQ Eight",
                    "category": "eq",
                    "purpose": "tone_shaping",
                    "parameters": {},
                    "fallbacks": [],
                },
                {
                    "plugin_name": "Reverb",
                    "category": "reverb",
                    "purpose": "space",
                    "parameters": {},
                    "fallbacks": [],
                },
            ],
            "safe_ranges": {},
            "notes": "Fallback chain — no specific research available.",
        }

    # Generic non-vocal fallback
    return {
        "query": query,
        "artist": "",
        "song": "",
        "track_type": track_type,
        "style_description": f"Generic {track_type} chain — LLM research was unavailable.",
        "confidence": 0.3,
        "source": "fallback-stock",
        "chain": [
            {
                "plugin_name": "EQ Eight",
                "category": "eq",
                "purpose": "cleanup",
                "parameters": {},
                "fallbacks": [],
            },
            {
                "plugin_name": "Compressor",
                "category": "compressor",
                "purpose": "dynamics",
                "parameters": {},
                "fallbacks": ["Glue Compressor"],
            },
        ],
        "safe_ranges": {},
        "notes": "Fallback chain — no specific research available.",
    }
