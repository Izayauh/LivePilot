"""Validated, verified MIDI writes shared by all LivePilot front doors."""
from __future__ import annotations

import math
from collections.abc import Mapping


def normalize_notes(notes):
    if not isinstance(notes, (list, tuple)):
        raise ValueError("notes must be a list of five-field notes")
    result = []
    fields = ("pitch", "start_time", "duration", "velocity", "mute")
    for index, note in enumerate(notes):
        if isinstance(note, Mapping):
            if not all(key in note for key in fields[:4]):
                raise ValueError(f"Note {index}: pitch, start_time, duration and velocity are required")
            values = [note[key] for key in fields[:4]] + [note.get("mute", note.get("muted", False))]
        elif isinstance(note, (list, tuple)) and len(note) == 5:
            values = list(note)
        else:
            raise ValueError(f"Note {index}: expected exactly five fields")
        pitch, start, duration, velocity, mute = values
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
               for v in values[:4]):
            raise ValueError(f"Note {index}: numeric fields must be finite numbers")
        if pitch != int(pitch) or not 0 <= pitch <= 127:
            raise ValueError(f"Note {index}: pitch must be an integer from 0 to 127")
        if start < 0 or duration <= 0 or not 1 <= velocity <= 127:
            raise ValueError(f"Note {index}: invalid start, duration or velocity")
        if mute not in (False, True, 0, 1):
            raise ValueError(f"Note {index}: mute must be boolean or 0/1")
        result.append(dict(zip(fields, (int(pitch), float(start), float(duration), float(velocity), bool(mute)))))
    return result


def notes_match(expected, actual, tolerance=0.0001):
    """Compare multisets, preserving duplicates and allowing OSC float32 rounding."""
    remaining = normalize_notes(actual)
    for note in normalize_notes(expected):
        for i, candidate in enumerate(remaining):
            if (candidate['pitch'] == note['pitch'] and candidate['mute'] == note['mute']
                    and all(math.isclose(candidate[k], note[k], abs_tol=tolerance, rel_tol=1e-6)
                            for k in ('start_time', 'duration', 'velocity'))):
                remaining.pop(i)
                break
        else:
            return False
    return not remaining


def add_clip_notes(track_index, clip_index, notes, mode="replace", *, send=None):
    """Validate before mutation, replace by default, and verify the entire clip.

    One LivePilot TCP call (lp_notes_write) reads, clears, writes and reads back inside
    Live's tick; the old AbletonOSC path took five round trips (~330 ms, 2026-10-14).
    """
    if mode not in ("replace", "append"):
        raise ValueError("mode must be replace or append")
    incoming = normalize_notes(notes)
    if send is None:
        from livepilot_tools.remote_script import send_command as send
    res = send("lp_notes_write", {
        "track_index": int(track_index), "clip_index": int(clip_index), "mode": mode,
        "notes": [[n["pitch"], n["start_time"], n["duration"], n["velocity"], int(n["mute"])] for n in incoming]},
        timeout=10.0)
    if not res.get("success"):
        return {"success": False, "verified": False, "message": res.get("message", "note write failed")}
    expected = (normalize_notes(res["before"]) + incoming) if mode == "append" else incoming
    verified = notes_match(expected, res["after"])
    out = {"success": verified, "verified": verified, "mode": mode,
           "track_index": int(track_index), "clip_index": int(clip_index),
           "notes_added": len(incoming) if verified else 0, "expected_count": len(expected),
           "message": "MIDI notes verified" if verified else "MIDI readback mismatch; write was not verified"}
    if not verified:
        out["readback"] = res["after"]
    return out
