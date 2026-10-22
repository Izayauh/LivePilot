"""Everyday Live Pilot workflows: one call each, by name, verified, undoable.

Measured 2026-10-13 from 982 recorded calls: dialing one knob took 4-5 calls
(find device, list params, get range, set, read the display string back), and
most sessions repeated that loop by hand. These functions do the whole loop
inside one call over the LivePilot remote script (TCP 9878):

    session()                     what is in the set, compactly
    dial(track, param, to=/by=)   set a knob or fader in display units ("-6 dB")
    chain(track, add=/remove=)    show, add, or remove devices
    audition(tracks, at=)         solo + jump + play; audition(stop=True) restores
    undo(steps)                   revert the last dial/chain changes this tool made

Every write is read back and journaled to data/telemetry/journal.jsonl so undo
can restore the exact previous raw value.
"""

from __future__ import annotations

import json
import math
import re
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from livepilot_tools import remote_script

REPO_ROOT = Path(__file__).resolve().parents[1]
JOURNAL_PATH = REPO_ROOT / "data" / "telemetry" / "journal.jsonl"

MASTER = -1000
MIXER = -1
RESTART_HINT = ("Live is running an older LivePilot script without the workflow handlers. "
                "Run `python scripts/deploy_remote_handlers.py`, save the set, and restart Live once.")

# Injected by the MCP server: loose plugin name -> exact browser name (VST discovery alias table).
plugin_name: Callable[[str], str] | None = None
send: Callable[..., dict] = remote_script.send_command


class LiveError(Exception):
    """A failure with a plain-English fix the caller can relay as-is."""


def _hint(cmd: str, message: str) -> str:
    m = message or ""
    if "10061" in m or "refused" in m:
        return ("Live is not answering on port 9878. Open Ableton with the LivePilot control "
                "surface enabled; if Live just launched, wait for the set to finish loading.")
    if "timed out" in m.lower():
        return "Live did not answer in time. It may be loading, or a dialog/plugin window is blocking it."
    if "Unknown command type" in m and cmd.startswith("lp_"):
        return RESTART_HINT
    return m


# Safe to resend if a reused connection drops mid-request (reads and absolute sets).
REPEAT_SAFE = {"get_session_info", "get_cue_points", "lp_chain", "lp_params", "lp_set",
               "set_track_solo", "jump_to_time", "continue_playback", "stop_playback"}


def _call(cmd: str, params: dict | None = None, timeout: float = 5.0, repeat_safe: bool = False) -> dict:
    if repeat_safe or cmd in REPEAT_SAFE:
        res = send(cmd, params or {}, timeout=timeout, persistent=True)
    else:
        res = send(cmd, params or {}, timeout=timeout)
    if not res.get("success"):
        raise LiveError(_hint(cmd, str(res.get("message", f"{cmd} failed"))))
    return res


def _fail(err: Exception) -> dict:
    return {"success": False, "message": str(err)}


# ---------------------------------------------------------------------------
# Journal (undo)
# ---------------------------------------------------------------------------

def _journal_append(entry: dict) -> dict:
    entry = {"id": uuid.uuid4().hex[:8], "ts": time.time(), "undone": False, "set": _set_sig(_last_info), **entry}
    JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return entry


def _journal_read() -> list[dict]:
    if not JOURNAL_PATH.exists():
        return []
    rows = []
    for line in JOURNAL_PATH.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def _journal_mark_undone(ids: set[str]) -> None:
    rows = _journal_read()
    for row in rows:
        if row.get("id") in ids:
            row["undone"] = True
    JOURNAL_PATH.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


# ---------------------------------------------------------------------------
# Name resolution (shared with Live: ableton_remote_script/LivePilot/lp_dialcore.py)
# ---------------------------------------------------------------------------

def _load_dialcore():
    import importlib.util

    path = REPO_ROOT / "ableton_remote_script" / "LivePilot" / "lp_dialcore.py"
    spec = importlib.util.spec_from_file_location("lp_dialcore", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core = _load_dialcore()
parse_display = core.parse_display


def _pick(spec: str, items: list[tuple[Any, str]], what: str) -> tuple[Any, str]:
    try:
        return core.pick(spec, items, what)
    except core.DialError as e:
        raise LiveError(str(e))


_last_info: dict = {}


def _session_info() -> dict:
    global _last_info
    _last_info = _call("get_session_info")
    return _last_info


def _set_sig(info: dict) -> str:
    return core.set_sig([t.get("name") for t in info.get("tracks", [])]
                        + [r.get("name") for r in info.get("return_tracks", [])])


def resolve_track(spec: Any, info: dict | None = None) -> tuple[int, str]:
    """Track spec -> (remote-script index, name). Accepts index, name, 'master', 'return A', 'A-Reverb'."""
    info = info or _session_info()
    tracks = [(t["index"], t["name"]) for t in info.get("tracks", [])]
    returns = [(-(r["index"] + 1), r["name"]) for r in info.get("return_tracks", [])]
    try:
        return core.resolve_track(spec, tracks, returns)
    except core.DialError as e:
        raise LiveError(str(e))


def _chain(rs_index: int) -> dict:
    return _call("lp_chain", {"track_index": rs_index})


def resolve_device(devices: list[dict], spec: Any) -> tuple[int, str]:
    """Device spec -> (index, name) within an lp_chain device list; None/'mixer' is the mixer."""
    if spec is None or core.norm(spec) in ("mixer", "fader", "channel"):
        return MIXER, "Mixer"
    if isinstance(spec, int) or (isinstance(spec, str) and spec.strip().isdigit()):
        idx = int(spec)
        if 0 <= idx < len(devices):
            return idx, devices[idx]["name"]
        raise LiveError(f"No device {idx} on this track ({len(devices)} devices).")
    items = [(d["index"], d["name"]) for d in devices]
    try:
        return _pick(str(spec), items, "device")
    except LiveError:
        by_class = [(d["index"], d["class_name"]) for d in devices]
        key, _ = _pick(str(spec), by_class, "device")
        return key, devices[key]["name"]


_live_labels: dict[str, str | None] = {}


def live_label(version: Any) -> str | None:
    """'Live 12.1 Suite' from the remote script's version ('12.1.10') plus the edition in the
    installed exe's name, since Live's Python API does not expose the edition. Cached per
    version; None when nothing is known."""
    key = str(version or "")
    if key not in _live_labels:
        try:
            _live_labels[key] = _read_live_label(key)
        except Exception:  # a label is a nicety; it must never break session()
            _live_labels[key] = None
    return _live_labels[key]


def _read_live_label(version: str) -> str | None:
    from studio import config  # imported here: workflows also runs without Studio
    installs = {m.groups() for p in config.live_exes()
                if (m := re.fullmatch(r"Ableton Live (\d+) (\w+)", p.stem))}
    parts = version.split(".")
    major = parts[0] or (next(iter(installs))[0] if len({v for v, _ in installs}) == 1 else "")
    if not major:
        return None
    editions = {e for v, e in installs if v == major}
    number = ".".join(parts[:2]) if len(parts) > 1 else major
    return f"Live {number}" + (f" {editions.pop()}" if len(editions) == 1 else "")


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------

def session() -> dict:
    """Compact view of the set: which Live, transport, tracks (mute/solo/arm), returns."""
    try:
        info = _session_info()
    except LiveError as e:
        return _fail(e)
    num = info.get("signature_numerator") or 4
    pos = float(info.get("current_song_time") or 0.0)

    def flags(t):
        return "".join(c for c, k in (("M", "mute"), ("S", "solo"), ("R", "arm")) if t.get(k))

    tracks = [f"{t['index']}:{t['name']}" + (f" [{flags(t)}]" if flags(t) else "") for t in info.get("tracks", [])]
    returns = [f"{chr(65 + r['index'])}:{r['name']}" + (f" [{flags(r)}]" if flags(r) else "")
               for r in info.get("return_tracks", [])]
    live = live_label(info.get("live_version"))
    return {
        "success": True,
        **({"live": live} if live else {}),
        "tempo": info.get("tempo"),
        "playing": info.get("is_playing"),
        "bar": round(pos / num + 1, 2),
        "loop": info.get("loop"),
        "tracks": tracks,
        "returns": returns,
        "summary": f"{round(float(info.get('tempo') or 0), 1):g} BPM, {'playing' if info.get('is_playing') else 'stopped'} at bar "
                   f"{pos / num + 1:.1f}, {len(tracks)} tracks, {len(returns)} returns",
    }


def dial(track: Any, param: Any, to: Any = None, by: Any = None, device: Any = None) -> dict:
    """Set one knob or fader and read it back. `to` absolute, `by` relative.

    Strings are display values ('-6 dB', '310 ms', '2.5 kHz', '40 %', '30L', 'On');
    numbers are raw Live values. Omit `device` for the mixer (volume, pan, send A).
    With neither `to` nor `by`, just reads the current value. One Live round trip:
    lp_dial resolves, solves, sets and reads back inside Live.
    """
    try:
        # A relative change must never be resent; reads and absolute sets can be.
        res = _call("lp_dial", {"track": track, "param": param, "to": to, "by": by, "device": device},
                    repeat_safe=by is None)
        label = res["label"]
        if res.get("read_only"):
            return {"success": True, "value": res["before"], "raw": res["before_raw"], "range": res["range"],
                    "summary": f"{label} is {res['before']}"}
        verified = bool(res["verified"])
        entry = _journal_append({"kind": "param", "track": res["track"], "device": res["device"],
                                 "device_name": res["device_name"], "param": res["param"], "label": label,
                                 "before_raw": res["before_raw"], "before": res["before"],
                                 "after_raw": res["after_raw"], "after": res["after"], "set": res["set"]})
        out = {"success": verified, "verified": verified, "before": res["before"], "after": res["after"],
               "undo_id": entry["id"],
               "summary": f"{label}: {res['before']} -> {res['after']}" + ("" if verified else " (READBACK MISMATCH)")}
        warning = _eq_band_warning(res)
        if warning:
            out["warning"] = warning
            out["summary"] += f" WARNING: {warning}"
        return out
    except LiveError as e:
        return _fail(e)


_EQ_FREQ = re.compile(r"^(\d) Frequency ([AB])$")


def _eq_band_warning(res: dict) -> str | None:
    """EQ Eight: moving a band's Frequency does nothing while that band is a shelf or bell at 0 dB.

    Band 1 defaults to Low Shelf, so "HPF at 30 Hz" read back fine and filtered nothing (2026-10-20).
    """
    name = res["label"].rsplit(" > ", 1)[-1]
    match = _EQ_FREQ.match(name)
    if not match or res["device"] == MIXER:
        return None
    band, side = match.groups()
    try:  # the set already landed; a failed check must not turn it into a failure
        params = {p["name"]: p for p in _call("lp_params", {"track_index": res["track"],
                                                            "device_index": res["device"]})["parameters"]}
    except LiveError:
        return None
    kind, gain = params.get(f"{band} Filter Type {side}"), params.get(f"{band} Gain {side}")
    if not kind or not gain:
        return None
    items = kind.get("value_items") or []
    shape = str(items[int(kind["value"])] if 0 <= int(kind["value"]) < len(items) else kind.get("value_string", ""))
    db = re.search(r"-?\d+(?:\.\d+)?", str(gain.get("value_string", "")))  # display, so the raw scale never matters
    if ("shelf" in shape.lower() or "bell" in shape.lower()) and db and abs(float(db.group())) < 0.05:
        return (f"band {band} is {shape} at 0 dB, this does nothing. For a high-pass, set "
                f"'{band} Filter Type {side}' to High Pass 48dB first; for a cut or boost, set '{band} Gain {side}'.")
    return None


def _names(devices: list[dict]) -> list[str]:
    return [d["name"] + ("" if d.get("is_active", True) else " (off)") for d in devices]


def _load(target: dict, name: str, position: int) -> dict:
    """One round trip: Live loads the device and returns the new chain. Live counts the
    chain itself, so success means exactly one new device, whatever the loader replied."""
    return _call("lp_chain_add", {**target, "name": plugin_name(name) if plugin_name else name, "position": int(position)}, timeout=35.0)


def chain(track: Any, add: str | None = None, remove: Any = None, position: int = -1) -> dict:
    """Show a track's device chain, or add/remove one device and show the result."""
    try:
        if add and remove is not None:
            raise LiveError("Add or remove one device per call.")
        if add:
            res = _load({"track": track}, add, position)
            devices = res["devices"]
            new_index = res["device_index"] if res.get("device_index") is not None else len(devices) - 1
            name = devices[new_index]["name"]
            entry = _journal_append({"kind": "chain_add", "track": res["track_index"], "device": new_index,
                                     "name": name, "label": f"{res['track_name']} + {name}"})
            return {"success": True, "chain": _names(devices), "undo_id": entry["id"],
                    "summary": f"Added {name} to {res['track_name']} at slot {new_index}"}
        current = _call("lp_chain", {"track": track})
        rs_index, track_name = current["track_index"], current["track_name"]
        if remove is not None:
            device_index, device_name = resolve_device(current["devices"], remove)
            if device_index == MIXER:
                raise LiveError("The mixer cannot be removed.")
            params = _call("lp_params", {"track_index": rs_index, "device_index": device_index})["parameters"]
            _call("delete_device", {"track_index": rs_index, "device_index": device_index})
            entry = _journal_append({"kind": "chain_remove", "track": rs_index, "device": device_index,
                                     "name": device_name, "label": f"{track_name} - {device_name}",
                                     "params": [[p["index"], p["value"]] for p in params]})
            return {"success": True, "chain": _names(_chain(rs_index)["devices"]), "undo_id": entry["id"],
                    "summary": f"Removed {device_name} from {track_name} (undo re-adds it with its settings)"}
        names = _names(current["devices"])
        return {"success": True, "chain": names,
                "summary": f"{track_name}: " + (" > ".join(names) if names else "no devices")}
    except LiveError as e:
        return _fail(e)


_audition_saved: dict | None = None


def _bar_to_beat(at: Any, info: dict) -> tuple[float, str]:
    num = info.get("signature_numerator") or 4
    if isinstance(at, (int, float)):
        return (float(at) - 1.0) * num, f"bar {at:g}"
    s = core.norm(at)
    m = re.fullmatch(r"(?:bar\s*)?(\d+(?:\s\d+)?)", s)
    if m:
        bar = float(m.group(1).replace(" ", "."))
        return (bar - 1.0) * num, f"bar {bar:g}"
    m = re.fullmatch(r"beat\s*(\d+(?:\s\d+)?)", s)
    if m:
        beat = float(m.group(1).replace(" ", "."))
        return beat, f"beat {beat:g}"
    cues = _call("get_cue_points").get("cue_points", [])
    key, name = _pick(str(at), [(c["time"], c["name"]) for c in cues], "locator")
    return float(key), f"locator '{name}'"


def audition(tracks: Any = None, at: Any = None, play: bool = True, stop: bool = False) -> dict:
    """Solo `tracks` (name or list), jump to `at` (bar number, 'beat 64', or a locator name), play.

    audition(stop=True) stops and puts every solo back the way it was.
    """
    global _audition_saved
    try:
        info = _session_info()
        if stop:
            _call("stop_playback")
            restored = _audition_saved is not None
            if _audition_saved:
                for rs_index, solo in _audition_saved.items():
                    _call("set_track_solo", {"track_index": rs_index, "solo": solo})
                _audition_saved = None
            return {"success": True, "summary": "Stopped" + ("; solos are back how they were" if restored else "")}
        targets = [] if tracks is None else (tracks if isinstance(tracks, list) else [tracks])
        resolved = [resolve_track(t, info) for t in targets]
        if resolved and _audition_saved is None:
            _audition_saved = {t["index"]: bool(t.get("solo")) for t in info.get("tracks", [])}
            _audition_saved.update({-(r["index"] + 1): bool(r.get("solo")) for r in info.get("return_tracks", [])})
        want = {rs for rs, _ in resolved}
        if resolved:
            current = {t["index"]: bool(t.get("solo")) for t in info.get("tracks", [])}
            current.update({-(r["index"] + 1): bool(r.get("solo")) for r in info.get("return_tracks", [])})
            for rs_index, solo in current.items():
                if solo != (rs_index in want):
                    _call("set_track_solo", {"track_index": rs_index, "solo": rs_index in want})
        where, beat = "", None
        if at is not None:
            beat, where = _bar_to_beat(at, info)
        # Verified live 2026-10-13 (Live 11.3): a jump made while stopped is ignored by
        # continue_playback, and start_playback restarts near the song start. So start
        # first, then jump while playing.
        if play:
            _call("continue_playback")
        if beat is not None:
            _call("jump_to_time", {"beat_time": beat})
        parts = []
        if resolved:
            parts.append("soloed " + ", ".join(n for _, n in resolved))
        if where:
            parts.append("from " + where)
        parts.append("playing" if play else "not playing")
        text = "; ".join(parts)
        return {"success": True, "summary": text[0].upper() + text[1:] + ". audition(stop=True) restores solos."}
    except LiveError as e:
        return _fail(e)


def undo(steps: int = 1) -> dict:
    """Revert the last `steps` dial/chain changes made through these workflows."""
    try:
        pending = [r for r in _journal_read() if not r.get("undone")][-max(1, int(steps)):]
        if not pending:
            return {"success": True, "summary": "Nothing to undo."}
        here = _set_sig(_session_info())
        if any(r.get("set") and r["set"] != here for r in pending):
            raise LiveError("Those changes were made in a different set (the track names differ), "
                            "so nothing was undone. Use Live's own undo (Ctrl+Z) in that set.")
        done, notes = set(), []
        try:
            _undo_rows(reversed(pending), done, notes)
        finally:
            _journal_mark_undone(done)
        return {"success": True, "undone": len(done), "summary": "Undid: " + "; ".join(notes)}
    except LiveError as e:
        return _fail(e)


def _undo_rows(rows, done: set, notes: list) -> None:
    for row in rows:
        kind = row["kind"]
        if kind == "param":
            if row["device"] != MIXER:
                devices = _chain(row["track"])["devices"]
                here = devices[row["device"]]["name"] if row["device"] < len(devices) else None
                if row.get("device_name") and here != row["device_name"]:
                    raise LiveError(f"{row['device_name']} is no longer at slot {row['device']} "
                                    f"(found {here or 'nothing'}); stopped before changing anything else.")
            res = _call("lp_set", {"track_index": row["track"], "device_index": row["device"],
                                   "parameter_index": row["param"], "value": row["before_raw"]})
            notes.append(f"{row['label']} back to {res.get('value_string')}")
        elif kind == "chain_add":
            devices = _chain(row["track"])["devices"]
            if row["device"] >= len(devices) or devices[row["device"]]["name"] != row["name"]:
                raise LiveError(f"{row['name']} is no longer at slot {row['device']}; not deleting anything.")
            _call("delete_device", {"track_index": row["track"], "device_index": row["device"]})
            notes.append(f"removed {row['name']}")
        elif kind == "chain_remove":
            try:
                _load({"track_index": row["track"]}, row["name"], row["device"])
            except LiveError as e:
                raise LiveError(f"Could not re-add {row['name']}: {e}")
            for p_index, value in row.get("params", []):
                _call("lp_set", {"track_index": row["track"], "device_index": row["device"],
                                 "parameter_index": p_index, "value": value})
            notes.append(f"re-added {row['name']} with its settings")
        done.add(row["id"])


BOUNCE_DIR = REPO_ROOT / "data" / "bounces"


def _loopback_device():
    import sounddevice as sd

    found = [(i, d) for i, d in enumerate(sd.query_devices())
             if d["max_input_channels"] >= 2 and "loop-back" in d["name"].lower()]
    wasapi = [x for x in found if "wasapi" in sd.query_hostapis(x[1]["hostapi"])["name"].lower()]
    if not (wasapi or found):
        raise RuntimeError("No Loop-back input found; is the Audient iD14 connected?")
    return (wasapi or found)[0]


def bounce(at: Any = 1, bars: float = 8, name: str = "bounce", tail: float = 1.5) -> dict:
    """Play `bars` from `at` and record the master through the audio interface's loop-back.

    Never touches Ableton's own (locked) recording files. Returns the WAV path plus level
    readings, and flags silence so a failed capture is never reported as a take.
    """
    import numpy as np
    import sounddevice as sd
    import soundfile as sf

    try:
        info = _session_info()
        beat, where = _bar_to_beat(at, info)
        tempo = float(info.get("tempo") or 120.0)
        num = info.get("signature_numerator") or 4
        seconds = float(bars) * num * 60.0 / tempo + float(tail)
        index, device = _loopback_device()
        rate = int(device.get("default_samplerate") or 44100)
        retried = []
        for attempt in (1, 2):  # a silent or broken capture is re-recorded once before anyone hears it
            if info.get("is_playing") or attempt == 2:  # each transport write costs ~0.2 s; skip when stopped
                _call("stop_playback")
            # Live's Back to Arrangement state silently mutes tracks that were touched in Session view
            # (the Metanoia guitar, 2026-10-14). Clear it on every bounce so no agent has to remember.
            _call("back_to_arranger")
            # Same order audition() verified on Live 11.3: start, then jump while playing.
            _call("continue_playback")
            _call("jump_to_time", {"beat_time": beat})
            try:
                audio = sd.rec(int(seconds * rate), samplerate=rate, channels=2, device=index, dtype="float32")
                sd.wait()
            finally:
                _call("stop_playback")
            mono = audio.mean(axis=1)
            peak = float(np.abs(mono).max())
            silent = peak < 10 ** (-60 / 20)
            dropouts = _dropouts(mono[: int((seconds - float(tail)) * rate)], rate)
            if not silent and not dropouts:
                break
            retried.append("silent" if silent else f"{len(dropouts)} dropout(s) at {dropouts[:3]} s")
    except LiveError as e:
        return _fail(e)
    except Exception as e:  # device or file problems
        return {"success": False, "error": str(e)}
    BOUNCE_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-") or "bounce"
    path = BOUNCE_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{slug}.wav"
    sf.write(path, audio, rate)
    rms = float(np.sqrt(np.mean(mono ** 2)))
    db = lambda v: round(20 * math.log10(v), 1) if v > 0 else -120.0
    ok = not silent and not dropouts
    error = None
    if silent:
        error = "Capture was silent twice: check the master output goes to the Audient and nothing is muted."
    elif dropouts:
        error = f"Capture had dropouts twice (digital silence at {dropouts[:5]} s): do not send this take."
    return {
        "success": ok,
        "retried": retried or None,
        "dropouts_at": dropouts or None,
        "path": str(path),
        "seconds": round(seconds, 2),
        "from": where,
        "bars": bars,
        "tempo": tempo,
        "peak_dbfs": db(peak),
        "rms_dbfs": db(rms),
        "silent": silent,
        "device": device["name"],
        "error": error,
    }


def _dropouts(mono, rate: int) -> list[float]:
    """Start times (s) of capture dropouts: 20 ms of digital silence cut in and out of loud sound.

    Loop-back glitches write true zeros mid-signal, so the sound right before and right after
    the gap is loud. A musical rest with any reverb tail stays far above -90 dBFS, and a dry
    sparse part (a soloed kick, 2026-10-20) decays into its silence, so neither is flagged.
    """
    import numpy as np

    hop = max(1, int(rate * 0.02))
    edge = max(1, int(rate * 0.005))
    frames = len(mono) // hop
    if frames < 3:
        return []
    level = np.abs(mono[: frames * hop])
    peaks = level.reshape(frames, hop).max(axis=1)
    floor, loud = 10 ** (-90 / 20), 10 ** (-40 / 20)
    dead = peaks < floor
    sounding = np.flatnonzero(level >= floor)
    found = []
    for i in np.flatnonzero(dead):
        if i == 0 or dead[i - 1]:
            continue  # only the first frame of each gap
        end = i
        while end < frames and dead[end]:
            end += 1
        if end >= frames:
            continue  # silence runs to the end: the passage stopped, not a glitch
        cut = sounding[np.searchsorted(sounding, i * hop) - 1]  # last sounding sample before the gap
        back = sounding[np.searchsorted(sounding, end * hop)]  # first one after it
        if level[max(0, cut - edge + 1): cut + 1].max() > loud and level[back: back + edge].max() > loud:
            found.append(round(float(i * hop / rate), 2))
    return found
