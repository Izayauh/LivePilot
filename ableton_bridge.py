#!/usr/bin/env python3
"""
Ableton Bridge CLI — standalone command-line wrapper around Ableton OSC controls.

Used by OpenClaw agents (via the ``exec`` tool) to control Ableton Live
without importing Gemini or any LLM library.

Usage:
    python ableton_bridge.py <function_name> '<json_args>'
    python ableton_bridge.py --list            # list all available functions

Examples:
    python ableton_bridge.py get_track_list '{}'
    python ableton_bridge.py mute_track '{"track_index":0,"muted":1}'
    python ableton_bridge.py set_tempo '{"bpm":120}'
    python ableton_bridge.py add_plugin_to_track '{"track_index":0,"plugin_name":"EQ Eight"}'

All output is JSON on stdout.  Exit code 0 on success, 1 on error.
"""

import json
import os
import sys

# ---------------------------------------------------------------------------
# Ensure repo root is on sys.path so ``ableton_controls`` can be imported
# regardless of the caller's working directory.
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    from ableton_controls import ableton  # module-level singleton (one listener on 11001)
    from ableton_controls.reliable_params import ReliableParameterController
    from livepilot_tools.context_tools import (
        analyze_clip_context as _analyze_clip_context,
        get_creative_context as _get_creative_context,
        get_project_intent as _get_project_intent,
        set_project_intent as _set_project_intent,
    )
    _ABLETON_IMPORT_ERROR = None
except Exception as _import_exc:  # pragma: no cover - exercised in lightweight test envs
    _ABLETON_IMPORT_ERROR = str(_import_exc)

    class _FallbackAbleton:
        """Minimal fallback used when ableton_controls deps are unavailable.

        Keeps CLI introspection (--list) and error handling working in environments
        that don't have full OSC/runtime deps installed.
        """

        def __getattr__(self, _name):
            def _missing(*_args, **_kwargs):
                return {
                    "success": False,
                    "message": (
                        "Ableton runtime dependency unavailable: "
                        f"{_ABLETON_IMPORT_ERROR}"
                    ),
                }

            return _missing

    class ReliableParameterController:  # type: ignore[override]
        def __init__(self, _ableton_obj):
            self._error = _ABLETON_IMPORT_ERROR

        def set_parameter_verified(self, *_args, **_kwargs):
            return {"success": False, "message": f"Ableton runtime dependency unavailable: {self._error}"}

        def set_parameter_by_name(self, *_args, **_kwargs):
            return {"success": False, "message": f"Ableton runtime dependency unavailable: {self._error}"}

        def set_parameters_by_name(self, *_args, **_kwargs):
            return {
                "success": False,
                "total": 0,
                "succeeded": 0,
                "failed": 0,
                "not_found": 0,
                "details": [],
                "message": f"Ableton runtime dependency unavailable: {self._error}",
            }

    ableton = _FallbackAbleton()

    def _get_creative_context(**kwargs):  # type: ignore[no-redef]
        from livepilot_tools.context_tools import get_creative_context
        return get_creative_context(**kwargs)

    def _analyze_clip_context(**kwargs):  # type: ignore[no-redef]
        from livepilot_tools.context_tools import analyze_clip_context
        return analyze_clip_context(**kwargs)

    def _get_project_intent(**kwargs):  # type: ignore[no-redef]
        from livepilot_tools.context_tools import get_project_intent
        return get_project_intent(**kwargs)

    def _set_project_intent(intent, **kwargs):  # type: ignore[no-redef]
        from livepilot_tools.context_tools import set_project_intent
        return set_project_intent(intent, **kwargs)

# ---------------------------------------------------------------------------
# Singleton controller instance — reuse the one from ableton_controls to avoid
# two listeners fighting over port 11001 (SO_REUSEADDR lets both bind, but
# only one socket receives each packet, causing random response loss).
# ---------------------------------------------------------------------------
reliable_params = ReliableParameterController(ableton)


# ---------------------------------------------------------------------------
# Helper utilities (mirror jarvis_engine.py helpers, no Gemini dependency)
# ---------------------------------------------------------------------------

def _to_int(value):
    """Coerce a value to int where possible (matches jarvis_engine.to_int)."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return value
    if isinstance(value, (int, float)):
        return int(value)
    return value


def get_track_status_combined(track_index: int):
    """Get combined mute/solo/arm status for a track."""
    try:
        mute_result = ableton.get_track_mute(track_index)
        solo_result = ableton.get_track_solo(track_index)
        arm_result = ableton.get_track_arm(track_index)

        if (not mute_result.get("success")
                or not solo_result.get("success")
                or not arm_result.get("success")):
            return {"success": False, "message": "Failed to query track status",
                    "muted": None, "soloed": None, "armed": None}

        return {
            "success": True,
            "track_index": track_index,
            "track_number": track_index + 1,
            "muted": mute_result.get("muted"),
            "soloed": solo_result.get("soloed"),
            "armed": arm_result.get("armed"),
            "message": (
                f"Track {track_index + 1} status: "
                f"{'Muted' if mute_result.get('muted') else 'Unmuted'}, "
                f"{'Soloed' if solo_result.get('soloed') else 'Not Soloed'}, "
                f"{'Armed' if arm_result.get('armed') else 'Not Armed'}"
            ),
        }
    except Exception as e:
        return {"success": False, "message": f"Error getting track status: {e}",
                "muted": None, "soloed": None, "armed": None}


def get_armed_tracks_list():
    """Get a list of all currently armed tracks."""
    try:
        track_list_result = ableton.get_track_list()
        if not track_list_result.get("success"):
            return {"success": False, "armed_tracks": [],
                    "message": "Failed to query track list"}

        tracks = track_list_result.get("tracks", [])
        armed_tracks = []
        for track in tracks:
            idx = track.get("index")
            name = track.get("name", f"Track {idx + 1}")
            arm_result = ableton.get_track_arm(idx)
            if arm_result.get("success") and arm_result.get("armed"):
                armed_tracks.append({"index": idx, "number": idx + 1, "name": name})

        if not armed_tracks:
            return {"success": True, "armed_tracks": [], "count": 0,
                    "message": "No tracks are currently armed for recording"}

        names = ", ".join(f"Track {t['number']} ({t['name']})" for t in armed_tracks)
        return {"success": True, "armed_tracks": armed_tracks,
                "count": len(armed_tracks),
                "message": f"Found {len(armed_tracks)} armed track(s): {names}"}
    except Exception as e:
        return {"success": False, "armed_tracks": [],
                "message": f"Error getting armed tracks: {e}"}


def find_track_by_name(query: str):
    """Find tracks by name using fuzzy matching."""
    try:
        track_list_result = ableton.get_track_list()
        if not track_list_result.get("success"):
            return {"success": False, "matches": [],
                    "message": "Failed to query track list"}

        tracks = track_list_result.get("tracks", [])
        if not tracks:
            return {"success": True, "matches": [], "count": 0,
                    "message": "No tracks found in project"}

        query_lower = query.lower().strip()
        query_normalized = query_lower.replace("the ", "").replace("track ", "").replace("my ", "")
        matches = []

        for track in tracks:
            track_name = track.get("name", "")
            track_name_lower = track_name.lower()
            track_index = track.get("index")
            score = 0

            if track_name_lower == query_lower:
                score = 100
            elif track_name_lower == query_normalized:
                score = 95
            elif query_normalized in track_name_lower:
                score = 80
            elif track_name_lower in query_normalized:
                score = 70
            else:
                for qw in query_normalized.split():
                    for tw in track_name_lower.split():
                        if qw in tw or tw in qw:
                            score = max(score, 50)
                            break

            if score > 0:
                matches.append({"index": track_index, "number": track_index + 1,
                                "name": track_name, "score": score})

        matches.sort(key=lambda x: x["score"], reverse=True)

        if not matches:
            return {"success": True, "matches": [], "count": 0, "query": query,
                    "message": f"No tracks found matching '{query}'. Use get_track_list to see all available tracks."}

        if len(matches) == 1:
            m = matches[0]
            msg = f"Found 1 match: Track {m['number']} ({m['name']})"
        else:
            top = matches[:3]
            info = ", ".join(f"Track {t['number']} ({t['name']})" for t in top)
            msg = f"Found {len(matches)} match(es) for '{query}'. Top matches: {info}"

        return {"success": True, "matches": matches, "count": len(matches),
                "query": query, "message": msg,
                "best_match": matches[0] if matches else None}
    except Exception as e:
        return {"success": False, "matches": [],
                "message": f"Error finding track: {e}"}


def delete_device_osc(track_index: int, device_index: int):
    """Delete a device from a track using JarvisDeviceLoader OSC endpoint."""
    import socket
    import struct
    import time

    try:
        address = "/jarvis/device/delete"
        addr_bytes = address.encode("utf-8") + b"\x00"
        addr_padded = addr_bytes + b"\x00" * ((4 - len(addr_bytes) % 4) % 4)
        type_tag = ",ii"
        type_bytes = type_tag.encode("utf-8") + b"\x00"
        type_padded = type_bytes + b"\x00" * ((4 - len(type_bytes) % 4) % 4)
        arg_data = struct.pack(">i", track_index) + struct.pack(">i", device_index)
        message = addr_padded + type_padded + arg_data

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(3.0)
        try:
            sock.bind(("127.0.0.1", 11003))
        except OSError:
            sock.bind(("127.0.0.1", 0))

        sock.sendto(message, ("127.0.0.1", 11002))

        try:
            data, _addr = sock.recvfrom(65535)
            sock.close()
            response_str = data.decode("utf-8", errors="ignore")
            return {"success": True,
                    "message": f"Device {device_index} deleted from track {track_index + 1}",
                    "response": response_str}
        except socket.timeout:
            sock.close()
            return {"success": False,
                    "message": "Timeout: No response from JarvisDeviceLoader. Is it installed in Ableton?",
                    "response": None}

    except OSError as e:
        if "10048" in str(e) or "Address already in use" in str(e):
            try:
                sock2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock2.sendto(message, ("127.0.0.1", 11002))
                sock2.close()
                time.sleep(0.5)
                return {"success": True,
                        "message": f"Device delete request sent for device {device_index} on track {track_index + 1}",
                        "response": None}
            except Exception as e2:
                return {"success": False, "message": f"Socket error: {e2}", "response": None}
        return {"success": False, "message": f"Socket error: {e}", "response": None}
    except Exception as e:
        return {"success": False, "message": f"Failed to delete device: {e}"}


# ---------------------------------------------------------------------------
# Function introspection
# ---------------------------------------------------------------------------

def _describe_functions():
    """Return a dict describing all available functions, their args, and types."""
    descriptions = {
        "play":                {"args": {}, "description": "Start playback"},
        "stop":                {"args": {}, "description": "Stop playback"},
        "continue_playback":   {"args": {}, "description": "Continue playback from current position"},
        "start_recording":     {"args": {}, "description": "Start recording"},
        "stop_recording":      {"args": {}, "description": "Stop recording"},
        "toggle_metronome":    {"args": {"state": {"type": "int", "required": True, "description": "1=on, 0=off"}}, "description": "Toggle metronome"},
        "set_tempo":           {"args": {"bpm": {"type": "float", "required": True, "description": "Tempo 20-999"}}, "description": "Set tempo"},
        "set_position":        {"args": {"beat": {"type": "float", "required": True, "description": "Position in beats"}}, "description": "Set playback position"},
        "set_loop":            {"args": {"enabled": {"type": "int", "required": True, "description": "1=on, 0=off"}}, "description": "Enable/disable loop"},
        "set_loop_start":      {"args": {"beat": {"type": "float", "required": True, "description": "Start position in beats"}}, "description": "Set loop start"},
        "set_loop_length":     {"args": {"beats": {"type": "float", "required": True, "description": "Length in beats"}}, "description": "Set loop length"},
        "mute_track":          {"args": {"track_index": {"type": "int", "required": True}, "muted": {"type": "int", "required": True, "description": "1=muted, 0=unmuted"}, "verify": {"type": "bool", "required": False, "description": "Read back to confirm"}}, "description": "Mute/unmute a track"},
        "solo_track":          {"args": {"track_index": {"type": "int", "required": True}, "soloed": {"type": "int", "required": True, "description": "1=soloed, 0=unsoloed"}, "verify": {"type": "bool", "required": False, "description": "Read back to confirm"}}, "description": "Solo/unsolo a track"},
        "arm_track":           {"args": {"track_index": {"type": "int", "required": True}, "armed": {"type": "int", "required": True, "description": "1=armed, 0=disarmed"}, "verify": {"type": "bool", "required": False, "description": "Read back to confirm"}}, "description": "Arm/disarm a track"},
        "set_track_volume":    {"args": {"track_index": {"type": "int", "required": True}, "volume": {"type": "float", "required": True, "description": "0.0-1.0"}, "verify": {"type": "bool", "required": False, "description": "Read back to confirm"}}, "description": "Set track volume"},
        "set_track_pan":       {"args": {"track_index": {"type": "int", "required": True}, "pan": {"type": "float", "required": True, "description": "-1.0 to 1.0"}, "verify": {"type": "bool", "required": False, "description": "Read back to confirm"}}, "description": "Set track pan"},
        "set_track_send":      {"args": {"track_index": {"type": "int", "required": True}, "send_index": {"type": "int", "required": True}, "level": {"type": "float", "required": True, "description": "0.0-1.0"}, "verify": {"type": "bool", "required": False, "description": "Read back to confirm"}}, "description": "Set track send level"},
        "get_track_list":      {"args": {}, "description": "Get all tracks with indices and names"},
        "get_track_mute":      {"args": {"track_index": {"type": "int", "required": True}}, "description": "Get track mute status"},
        "get_track_solo":      {"args": {"track_index": {"type": "int", "required": True}}, "description": "Get track solo status"},
        "get_track_arm":       {"args": {"track_index": {"type": "int", "required": True}}, "description": "Get track arm status"},
        "get_track_volume":    {"args": {"track_index": {"type": "int", "required": True}}, "description": "Get track volume level"},
        "get_track_pan":       {"args": {"track_index": {"type": "int", "required": True}}, "description": "Get track pan position"},
        "get_track_send":      {"args": {"track_index": {"type": "int", "required": True}, "send_index": {"type": "int", "required": True}}, "description": "Get track send level"},
        "get_track_status":    {"args": {"track_index": {"type": "int", "required": True}}, "description": "Get combined mute/solo/arm status"},
        "get_armed_tracks":    {"args": {}, "description": "List all armed tracks"},
        "find_track_by_name":  {"args": {"query": {"type": "str", "required": True}}, "description": "Find tracks by name (fuzzy)"},
        "fire_scene":          {"args": {"scene_index": {"type": "int", "required": True}}, "description": "Fire a scene"},
        "fire_clip":           {"args": {"track_index": {"type": "int", "required": True}, "clip_index": {"type": "int", "required": True}}, "description": "Fire a clip"},
        "stop_clip":           {"args": {"track_index": {"type": "int", "required": True}}, "description": "Stop all clips on a track"},
        "create_audio_track":  {"args": {"index": {"type": "int", "required": False, "description": "-1=end"}}, "description": "Create audio track"},
        "create_midi_track":   {"args": {"index": {"type": "int", "required": False, "description": "-1=end"}}, "description": "Create MIDI track"},
        "create_return_track": {"args": {}, "description": "Create return track"},
        "delete_track":        {"args": {"track_index": {"type": "int", "required": True}}, "description": "Delete a track"},
        "delete_return_track": {"args": {"track_index": {"type": "int", "required": True}}, "description": "Delete a return track"},
        "duplicate_track":     {"args": {"track_index": {"type": "int", "required": True}}, "description": "Duplicate a track"},
        "set_track_name":      {"args": {"track_index": {"type": "int", "required": True}, "name": {"type": "str", "required": True}}, "description": "Rename a track"},
        "set_track_color":     {"args": {"track_index": {"type": "int", "required": True}, "color_index": {"type": "int", "required": True}}, "description": "Set track color"},
        "get_num_devices":     {"args": {"track_index": {"type": "int", "required": True}}, "description": "Get device count on track"},
        "get_track_devices":   {"args": {"track_index": {"type": "int", "required": True}}, "description": "Get device names on track"},
        "get_device_name":     {"args": {"track_index": {"type": "int", "required": True}, "device_index": {"type": "int", "required": True}}, "description": "Get device name"},
        "get_device_class_name": {"args": {"track_index": {"type": "int", "required": True}, "device_index": {"type": "int", "required": True}}, "description": "Get device class name"},
        "get_device_parameters": {"args": {"track_index": {"type": "int", "required": True}, "device_index": {"type": "int", "required": True}}, "description": "Get device parameter names"},
        "get_device_parameter_value": {"args": {"track_index": {"type": "int", "required": True}, "device_index": {"type": "int", "required": True}, "param_index": {"type": "int", "required": True}}, "description": "Get device parameter value"},
        "set_device_parameter": {"args": {"track_index": {"type": "int", "required": True}, "device_index": {"type": "int", "required": True}, "param_index": {"type": "int", "required": True}, "value": {"type": "float", "required": True}}, "description": "Set device parameter (verified)"},
        "set_device_parameter_by_name": {"args": {"track_index": {"type": "int", "required": True}, "device_index": {"type": "int", "required": True}, "param_name": {"type": "str", "required": True}, "value": {"type": "float", "required": True}}, "description": "Set device parameter by name"},
        "set_device_parameters_by_name": {"args": {"track_index": {"type": "int", "required": True}, "device_index": {"type": "int", "required": True}, "params": {"type": "dict", "required": True, "description": "{name: value, ...}"}}, "description": "Set multiple device parameters by name"},
        "set_device_enabled":  {"args": {"track_index": {"type": "int", "required": True}, "device_index": {"type": "int", "required": True}, "enabled": {"type": "int", "required": True}}, "description": "Enable/bypass a device"},
        "delete_device":       {"args": {"track_index": {"type": "int", "required": True}, "device_index": {"type": "int", "required": True}}, "description": "Delete a device from track"},
        "add_plugin_to_track": {"args": {"track_index": {"type": "int", "required": True}, "plugin_name": {"type": "str", "required": True}, "position": {"type": "int", "required": False}}, "description": "Load a plugin onto a track"},
        "get_available_plugins": {"args": {"category": {"type": "str", "required": False}}, "description": "List available plugins"},
        "find_plugin":         {"args": {"query": {"type": "str", "required": True}, "category": {"type": "str", "required": False}}, "description": "Find plugin by name"},
        "refresh_plugin_list": {"args": {}, "description": "Refresh plugin list from Ableton"},
        "diag_osc":            {"args": {"timeout": {"type": "float", "required": False, "description": "Timeout in seconds (default 3.0)"}}, "description": "Run OSC connectivity diagnostic"},
        "get_creative_context": {"args": {}, "description": "Get structured creative context for the current LivePilot session"},
        "analyze_clip_context": {"args": {"track_index": {"type": "int", "required": True}, "clip_index": {"type": "int", "required": True}}, "description": "Summarize MIDI notes in a clip where the controller exposes them"},
        "set_project_intent":  {"args": {"intent": {"type": "dict", "required": False, "description": "Project intent object; direct JSON args are also accepted"}}, "description": "Persist project intent for creative context"},
        "get_project_intent":  {"args": {}, "description": "Get persisted project intent"},
        "describe_functions":  {"args": {}, "description": "List all functions with argument schemas"},
    }
    return {"success": True, "functions": descriptions, "count": len(descriptions)}


# ---------------------------------------------------------------------------
# Function dispatch table
# ---------------------------------------------------------------------------

def _build_dispatch(args: dict):
    """Build and return the function dispatch table for a given args dict.

    The returned dict maps function-name strings to zero-arg callables.
    """
    track_index = _to_int(args.get("track_index"))
    verify = bool(args.get("verify", False))

    return {
        # -- Playback --
        "play":                lambda: ableton.play(),
        "stop":                lambda: ableton.stop(),
        "continue_playback":   lambda: ableton.continue_playback(),
        "start_recording":     lambda: ableton.start_recording(),
        "stop_recording":      lambda: ableton.stop_recording(),
        "toggle_metronome":    lambda: ableton.toggle_metronome(_to_int(args.get("state"))),

        # -- Transport --
        "set_tempo":           lambda: ableton.set_tempo(args.get("bpm")),
        "set_position":        lambda: ableton.set_position(args.get("beat")),
        "set_loop":            lambda: ableton.set_loop(_to_int(args.get("enabled"))),
        "set_loop_start":      lambda: ableton.set_loop_start(args.get("beat")),
        "set_loop_length":     lambda: ableton.set_loop_length(args.get("beats")),

        # -- Track controls --
        "mute_track":          lambda: ableton.mute_track(track_index, _to_int(args.get("muted")), verify=verify),
        "solo_track":          lambda: ableton.solo_track(track_index, _to_int(args.get("soloed")), verify=verify),
        "arm_track":           lambda: ableton.arm_track(track_index, _to_int(args.get("armed")), verify=verify),
        "set_track_volume":    lambda: ableton.set_track_volume(track_index, args.get("volume"), verify=verify),
        "set_track_pan":       lambda: ableton.set_track_pan(track_index, args.get("pan"), verify=verify),
        "set_track_send":      lambda: ableton.set_track_send(
            track_index, _to_int(args.get("send_index")), args.get("level"), verify=verify),

        # -- Scene / clip --
        "fire_scene":          lambda: ableton.fire_scene(_to_int(args.get("scene_index"))),
        "fire_clip":           lambda: ableton.fire_clip(track_index, _to_int(args.get("clip_index"))),
        "stop_clip":           lambda: ableton.stop_clip(track_index),

        # -- Track management --
        "create_audio_track":  lambda: ableton.create_audio_track(_to_int(args.get("index", -1))),
        "create_midi_track":   lambda: ableton.create_midi_track(_to_int(args.get("index", -1))),
        "create_return_track": lambda: ableton.create_return_track(),
        "delete_track":        lambda: ableton.delete_track(track_index),
        "delete_return_track": lambda: ableton.delete_return_track(track_index),
        "duplicate_track":     lambda: ableton.duplicate_track(track_index),
        "set_track_name":      lambda: ableton.set_track_name(track_index, args.get("name")),
        "set_track_color":     lambda: ableton.set_track_color(track_index, _to_int(args.get("color_index"))),

        # -- Track queries --
        "get_track_list":      lambda: ableton.get_track_list(),
        "get_track_mute":      lambda: ableton.get_track_mute(track_index),
        "get_track_solo":      lambda: ableton.get_track_solo(track_index),
        "get_track_arm":       lambda: ableton.get_track_arm(track_index),
        "get_track_volume":    lambda: ableton.get_track_volume(track_index),
        "get_track_pan":       lambda: ableton.get_track_pan(track_index),
        "get_track_send":      lambda: ableton.get_track_send(track_index, _to_int(args.get("send_index"))),
        "get_track_status":    lambda: get_track_status_combined(track_index),
        "get_armed_tracks":    lambda: get_armed_tracks_list(),
        "find_track_by_name":  lambda: find_track_by_name(args.get("query")),

        # -- Device queries --
        "get_num_devices":     lambda: ableton.get_num_devices_sync(track_index),
        "get_track_devices":   lambda: ableton.get_track_devices_sync(track_index),
        "get_device_name":     lambda: ableton.get_device_name(
            track_index, _to_int(args.get("device_index"))),
        "get_device_class_name": lambda: ableton.get_device_class_name(
            track_index, _to_int(args.get("device_index"))),
        "get_device_parameters": lambda: ableton.get_device_parameters_name_sync(
            track_index, _to_int(args.get("device_index"))),
        "get_device_parameter_value": lambda: ableton.get_device_parameter_value_sync(
            track_index, _to_int(args.get("device_index")),
            _to_int(args.get("param_index"))),

        # -- Device control --
        "set_device_parameter": lambda: reliable_params.set_parameter_verified(
            track_index, _to_int(args.get("device_index")),
            _to_int(args.get("param_index")), args.get("value")),
        "set_device_parameter_by_name": lambda: reliable_params.set_parameter_by_name(
            track_index, _to_int(args.get("device_index")),
            args.get("param_name"), args.get("value")),
        "set_device_parameters_by_name": lambda: reliable_params.set_parameters_by_name(
            track_index, _to_int(args.get("device_index")),
            args.get("params", {})),
        "set_device_enabled":  lambda: ableton.set_device_enabled(
            track_index, _to_int(args.get("device_index")),
            _to_int(args.get("enabled"))),
        "delete_device":       lambda: delete_device_osc(
            track_index, _to_int(args.get("device_index"))),

        # -- Plugin management --
        "add_plugin_to_track": lambda: ableton.load_device(
            track_index, args.get("plugin_name"), _to_int(args.get("position", -1))),
        "get_available_plugins": lambda: ableton.get_available_plugins(args.get("category")),
        "find_plugin":         lambda: ableton.find_plugin(
            args.get("query"), args.get("category")),
        "refresh_plugin_list": lambda: ableton.refresh_plugin_list(),

        # -- Diagnostics --
        "diag_osc":            lambda: ableton.diag_osc(float(args.get("timeout", 3.0))),

        # -- Creative context --
        "get_creative_context": lambda: _get_creative_context(controller=ableton, reliable=reliable_params),
        "analyze_clip_context": lambda: _analyze_clip_context(
            track_index=track_index,
            clip_index=_to_int(args.get("clip_index")),
            controller=ableton,
            reliable=reliable_params,
        ),
        "set_project_intent": lambda: _set_project_intent(args.get("intent", args)),
        "get_project_intent": lambda: _get_project_intent(),

        # -- Introspection --
        "describe_functions":  lambda: _describe_functions(),
    }


# Operations that require a track_index argument
TRACK_OPERATIONS = {
    "mute_track", "solo_track", "arm_track",
    "set_track_volume", "set_track_pan", "set_track_send",
    "fire_clip", "stop_clip",
    "get_num_devices", "get_track_devices", "get_device_name",
    "get_device_class_name", "get_device_parameters",
    "get_device_parameter_value", "set_device_parameter",
    "set_device_parameter_by_name", "set_device_parameters_by_name",
    "set_device_enabled",
    "add_plugin_to_track", "delete_device",
    "delete_track", "delete_return_track", "duplicate_track",
    "set_track_name", "set_track_color",
    "get_track_mute", "get_track_solo", "get_track_arm",
    "get_track_volume", "get_track_pan", "get_track_send",
    "get_track_status",
    "analyze_clip_context",
}


def list_functions() -> list[str]:
    """Return sorted list of all available function names."""
    return sorted(_build_dispatch({}).keys())


# ---------------------------------------------------------------------------
# Main CLI entry point
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: ableton_bridge.py <function_name> '<json_args>' | --list"}))
        sys.exit(1)

    # --list mode
    if sys.argv[1] == "--list":
        print(json.dumps({"functions": list_functions()}, indent=2))
        sys.exit(0)

    func_name = sys.argv[1]
    raw_args = sys.argv[2] if len(sys.argv) > 2 else "{}"

    # Parse JSON args (with fallback to --flag style)
    try:
        args = json.loads(raw_args)
    except json.JSONDecodeError:
        # Fallback: parse --key value pairs from argv
        args = {}
        argv = sys.argv[2:]
        i = 0
        while i < len(argv):
            if argv[i].startswith("--"):
                key = argv[i][2:].replace("-", "_")
                if i + 1 < len(argv) and not argv[i+1].startswith("--"):
                    val = argv[i + 1]
                    # Auto-convert numeric strings
                    try:
                        val = int(val)
                    except ValueError:
                        try:
                            val = float(val)
                        except ValueError:
                            pass
                    args[key] = val
                    i += 2
                else:
                    args[key] = True
                    i += 1
            else:
                i += 1
        
        if not args:
            # If we couldn't parse flags either, show the original error
            print(json.dumps({
                "success": False, 
                "error": f"Invalid JSON args. Received: {repr(raw_args)}. Use flag style instead: --track_index 0 --device_index 2"
            }))
            sys.exit(1)

    if not isinstance(args, dict):
        print(json.dumps({"success": False, "error": "Args must be a JSON object"}))
        sys.exit(1)

    # Validate track_index for operations that require it
    if func_name in TRACK_OPERATIONS and args.get("track_index") is None:
        print(json.dumps({
            "success": False,
            "error": f"{func_name} requires 'track_index'. Specify which track (0-based).",
        }))
        sys.exit(1)

    # Build dispatch and execute
    dispatch = _build_dispatch(args)

    if func_name not in dispatch:
        print(json.dumps({
            "success": False,
            "error": f"Unknown function '{func_name}'. Use --list to see available functions.",
        }))
        sys.exit(1)

    try:
        result = dispatch[func_name]()
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))
        sys.exit(1)

    # Normalize output to JSON
    if isinstance(result, dict):
        print(json.dumps(result, indent=2, default=str))
    elif result is None:
        print(json.dumps({"success": True, "message": f"{func_name} executed (no return value)."}))
    else:
        print(json.dumps({"success": True, "result": result}, default=str))


if __name__ == "__main__":
    main()
