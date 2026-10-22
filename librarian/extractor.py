from __future__ import annotations

from typing import Any, Dict, List, Optional


# Maps JSON schema-friendly names to names expected by reliable_params semantic mappings.
PARAM_ALIASES_BY_PLUGIN: Dict[str, Dict[str, str]] = {
    "eq eight": {
        "high_pass_freq": "band1_freq_hz",
        "low_mid_cut_freq": "band2_freq_hz",
        "low_mid_cut_gain": "band2_gain_db",
    },
    "delay": {
        "time_left": "delay_time_ms",
        "time_right": "delay_time_ms",
        "sync": "filter_on",
    },
    "reverb": {
        "decay_time": "decay_time_ms",
        "predelay": "predelay_ms",
        "dry_wet": "dry_wet_pct",
    },
    "compressor": {
        "threshold": "threshold_db",
        "attack": "attack_ms",
        "release": "release_ms",
    },
}


def _normalize_plugin_params(plugin_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    aliases = PARAM_ALIASES_BY_PLUGIN.get((plugin_name or "").strip().lower(), {})
    out: Dict[str, Any] = {}
    for k, v in (params or {}).items():
        out[aliases.get(k, k)] = v
    return out


def get_section_chain(song_data: dict, section_name: str) -> List[dict]:
    sections = song_data.get("sections", {}) or {}
    sec = sections.get(section_name, {}) or {}
    chain = sec.get("chain", [])
    return chain if isinstance(chain, list) else []


def to_builder_format(devices: List[dict], song_meta: dict, section_name: str) -> dict:
    chain = []
    for d in devices:
        chain.append(
            {
                "type": d.get("stage", "unknown"),
                "purpose": d.get("why", ""),
                "plugin_name": d.get("plugin", ""),
                "name": d.get("plugin", ""),
                "settings": _normalize_plugin_params(d.get("plugin", ""), d.get("key_params", {}) or {}),
            }
        )
    return {
        "artist_or_style": song_meta.get("artist") or song_meta.get("title") or "unknown",
        "track_type": "vocal",
        "chain": chain,
        "confidence": song_meta.get("confidence", 0.5),
        "sources": ["local_library"],
        "from_research": False,
        "from_library": True,
        "section": section_name,
    }


def to_chainspec_format(song_data: dict, section_name: str, query: str = "") -> dict:
    song = song_data.get("song", {}) or {}
    section = (song_data.get("sections", {}) or {}).get(section_name, {}) or {}
    devices_out: List[Dict[str, Any]] = []
    for d in get_section_chain(song_data, section_name):
        params = _normalize_plugin_params(d.get("plugin", ""), d.get("key_params", {}) or {})
        params_with_meta = {
            k: {
                "value": v,
                "unit": None,
                "confidence": float(song_data.get("confidence", 0.7)),
            }
            for k, v in params.items()
        }
        devices_out.append(
            {
                "plugin_name": d.get("plugin", ""),
                "category": d.get("stage", "unknown"),
                "parameters": params_with_meta,
                "purpose": d.get("why", ""),
                "reasoning": d.get("why", ""),
                "confidence": float(song_data.get("confidence", 0.7)),
                "sources": ["local_library"],
            }
        )

    return {
        "query": query or f"{song.get('title','')} {section_name}".strip(),
        "style_description": section.get("intent", ""),
        "devices": devices_out,
        "confidence": float(song_data.get("confidence", 0.7)),
        "sources": ["local_library"],
        "artist": song.get("artist"),
        "song": song.get("title"),
        "genre": song.get("genre"),
        "meta": {
            "cache_hit": True,
            "cache_type": "local_library",
            "llm_calls_used": 0,
            "section": section_name,
        },
    }


def get_param_why(song_data: dict, section_name: str, plugin_name: str, param_name: str) -> Optional[str]:
    for d in get_section_chain(song_data, section_name):
        if (d.get("plugin", "").strip().lower() == plugin_name.strip().lower()):
            return (d.get("param_why", {}) or {}).get(param_name)
    return None


def get_device_why(song_data: dict, section_name: str, plugin_name: str) -> Optional[str]:
    for d in get_section_chain(song_data, section_name):
        if (d.get("plugin", "").strip().lower() == plugin_name.strip().lower()):
            return d.get("why")
    return None
