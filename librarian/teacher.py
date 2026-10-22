from __future__ import annotations

from typing import Dict, Optional

from .extractor import get_device_why, get_param_why
from .session_context import get_librarian_session_context


def explain_setting(plugin_name: str, param_name: str) -> Dict:
    ctx = get_librarian_session_context().get_active()
    if not ctx:
        return {
            "found": False,
            "message": "No chain currently loaded. Load a chain first, then ask about parameters.",
        }

    song_data = ctx.get("active_song_data", {})
    section = ctx.get("active_section", "verse")
    reason = get_param_why(song_data, section, plugin_name, param_name)
    if not reason:
        return {"found": False, "message": f"No reasoning found for {plugin_name}.{param_name} in active chain."}

    value = None
    for d in ((song_data.get("sections", {}) or {}).get(section, {}) or {}).get("chain", []):
        if d.get("plugin", "").strip().lower() == plugin_name.strip().lower():
            value = (d.get("key_params", {}) or {}).get(param_name)
            break

    song = song_data.get("song", {})
    return {
        "found": True,
        "plugin": plugin_name,
        "param": param_name,
        "value": value,
        "reason": reason,
        "device_context": get_device_why(song_data, section, plugin_name),
        "section_intent": ((song_data.get("sections", {}) or {}).get(section, {}) or {}).get("intent"),
        "section": section,
        "song": song.get("title"),
        "artist": song.get("artist"),
    }


def explain_device(plugin_name: str) -> Dict:
    ctx = get_librarian_session_context().get_active()
    if not ctx:
        return {"found": False, "message": "No chain currently loaded. Load a chain first."}
    song_data = ctx.get("active_song_data", {})
    section = ctx.get("active_section", "verse")
    reason = get_device_why(song_data, section, plugin_name)
    if not reason:
        return {"found": False, "message": f"No device explanation found for {plugin_name}."}
    return {"found": True, "plugin": plugin_name, "reason": reason, "section": section}


def explain_section_intent(section_name: str) -> Dict:
    ctx = get_librarian_session_context().get_active()
    if not ctx:
        return {"found": False, "message": "No chain currently loaded. Load a chain first."}
    song_data = ctx.get("active_song_data", {})
    section_data = (song_data.get("sections", {}) or {}).get(section_name)
    if not section_data:
        return {"found": False, "message": f"Section '{section_name}' not found in active song."}
    return {"found": True, "section": section_name, "intent": section_data.get("intent", "")}


def get_full_chain_explanation(section_name: Optional[str] = None) -> Dict:
    ctx = get_librarian_session_context().get_active()
    if not ctx:
        return {"found": False, "message": "No chain currently loaded. Load a chain first."}
    song_data = ctx.get("active_song_data", {})
    section = section_name or ctx.get("active_section", "verse")
    section_data = (song_data.get("sections", {}) or {}).get(section)
    if not section_data:
        return {"found": False, "message": f"Section '{section}' not found in active song."}
    return {
        "found": True,
        "section": section,
        "intent": section_data.get("intent", ""),
        "chain": section_data.get("chain", []),
    }
