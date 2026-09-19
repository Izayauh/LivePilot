"""Jev intent dispatch for Live Pilot.

Turns a plain-language transport/mixer command into bridge function calls
using TypeSafe Jev (typed decisions with probabilities, ~0.3-0.5 s) instead
of a multi-second LLM parse. Code owns the option set, the numbers, the
confidence thresholds, and execution. Jev only picks.

Anything below the confidence gate is returned as ``escalate`` so the caller
(Claude, Hermes) can handle it the slow way. Creative work never comes here.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-latest"

FN_GATE = 0.70      # min confidence on the action choice
TRACK_GATE = 0.60   # min confidence on the track choice when one is needed
STEP = 0.1          # relative nudge for "a bit up/down" on volume/pan/send

# Bounded action set. Jev cannot choose a function that is not listed here.
ACTIONS: dict[str, str | None] = {
    "play": "start playback from the current position",
    "stop": "stop playback",
    "continue_playback": "resume playback where it left off",
    "start_recording": "start recording into the arrangement",
    "stop_recording": "stop recording",
    "set_tempo": "change the song tempo in BPM",
    "metronome_on": "turn the metronome (the click, click track) ON",
    "metronome_off": "turn the metronome (the click, click track) OFF",
    "loop_on": "turn arrangement loop ON",
    "loop_off": "turn arrangement loop OFF",
    "set_position": "jump the playhead to a beat position",
    "mute": "mute, kill, or silence a track",
    "unmute": "unmute or bring back a muted track",
    "solo": "solo a track",
    "unsolo": "unsolo a track, take it out of solo",
    "arm": "arm a track for recording",
    "disarm": "disarm a track, take it out of record",
    "set_track_volume": "raise, lower, or set a track's volume fader",
    "set_track_pan": "pan a track left, right, or center",
    "set_track_send": "change how much of a track goes to a send/return",
    "fire_scene": "launch a scene in session view",
    "device_param": "change one specific parameter on a device, plugin, or effect sitting on a track "
                    "(threshold, ratio, attack, release, frequency, gain, Q, dry/wet, decay, feedback, "
                    "drive, amount, mix)",
    "device_bypass": "bypass, disable, or turn off a device, plugin, or effect on a track",
    "device_enable": "re-enable or turn back on a bypassed device, plugin, or effect on a track",
    "none": "no listed action matches the command",
}

# Choice option -> (bridge function, fixed args). Toggles carry their end state
# in the option name because a separate yes/no on negation was unreliable.
BRIDGE: dict[str, tuple[str, dict[str, Any]]] = {
    "play": ("play", {}), "stop": ("stop", {}), "continue_playback": ("continue_playback", {}),
    "start_recording": ("start_recording", {}), "stop_recording": ("stop_recording", {}),
    "set_tempo": ("set_tempo", {}), "set_position": ("set_position", {}), "fire_scene": ("fire_scene", {}),
    "metronome_on": ("toggle_metronome", {"state": 1}), "metronome_off": ("toggle_metronome", {"state": 0}),
    "loop_on": ("set_loop", {"enabled": 1}), "loop_off": ("set_loop", {"enabled": 0}),
    "mute": ("mute_track", {"muted": 1}), "unmute": ("mute_track", {"muted": 0}),
    "solo": ("solo_track", {"soloed": 1}), "unsolo": ("solo_track", {"soloed": 0}),
    "arm": ("arm_track", {"armed": 1}), "disarm": ("arm_track", {"armed": 0}),
    "set_track_volume": ("set_track_volume", {}), "set_track_pan": ("set_track_pan", {}),
    "set_track_send": ("set_track_send", {}),
    "device_param": ("set_device_parameter_by_name", {}),
    "device_bypass": ("set_device_enabled", {"enabled": 0}),
    "device_enable": ("set_device_enabled", {"enabled": 1}),
}
DEVICE_ACTIONS = {"device_param", "device_bypass", "device_enable"}
DEVICE_GATE = 0.60  # min confidence on device and parameter choices

NEEDS_TRACK = {"mute", "unmute", "solo", "unsolo", "arm", "disarm",
               "set_track_volume", "set_track_pan", "set_track_send",
               "device_param", "device_bypass", "device_enable"}
SPLIT_RE = re.compile(r"\s*(?:,|;|\bthen\b|\band then\b|\band\b)\s*", re.I)
NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _api_key() -> str:
    key = os.environ.get("TYPESAFE_API_KEY")
    if key:
        return key
    env = REPO_ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("TYPESAFE_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("TYPESAFE_API_KEY not set (env or live-pilot/.env)")


def jev_ask(state: Any, questions: dict[str, dict[str, Any]], timeout: int = 20) -> dict[str, Any]:
    """One System One request. Retries 429/529 with backoff."""
    body = json.dumps({"model": JEV_MODEL, "state": state, "questions": questions}).encode()
    headers = {"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"}
    delay = 0.5
    for attempt in range(4):
        req = urllib.request.Request(JEV_URL, data=body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 529) and attempt < 3:
                time.sleep(delay)
                delay *= 2
                continue
            raise RuntimeError(f"Jev HTTP {exc.code}: {exc.read().decode()[:300]}") from exc
    raise RuntimeError("Jev: retries exhausted")


def _numbers(clause: str, *names: str) -> list[float]:
    """Numbers in the clause, ignoring any that belong to a track or device name ("3-Audio")."""
    text = clause
    for n in names:
        if n:
            text = re.sub(re.escape(n), " ", text, flags=re.I)
    return [float(x) for x in NUM_RE.findall(text)]


def _clauses(command: str) -> list[str]:
    parts = [p.strip() for p in SPLIT_RE.split(command) if p and p.strip()]
    return parts or [command.strip()]


def _questions(track_names: list[str]) -> dict[str, dict[str, Any]]:
    track_criteria: dict[str, str | None] = {name: None for name in track_names}
    track_criteria["none"] = "the command does not refer to any listed track"
    return {
        "fn": {
            "type": "choice",
            "instructions": "Which single Ableton Live action does `command` ask for?",
            "criteria": ACTIONS,
        },
        "track": {
            "type": "choice",
            "instructions": "If `command` refers to a track, which entry of `tracks` does it mean? "
                            "Match nicknames and partial names (vox, vocals, lead vocal all mean a vocal track).",
            "criteria": track_criteria,
        },
        "direction": {
            "type": "choice",
            "instructions": "Speculative: if `command` changes a level or pan without an exact number, "
                            "which way?",
            "criteria": {"up": "a bit louder, higher, more, or a bit right (for pan)",
                         "down": "a bit quieter, lower, less, or a bit left (for pan)",
                         "max": "all the way up, full, hard right (for pan)",
                         "min": "all the way down, zero, silent, hard left (for pan)",
                         "center": "reset to center or default",
                         "exact": "an explicit number is given",
                         "none": "not a level or pan change"},
        },
    }


def _args_for(action: str, ans: dict[str, Any], clause: str,
              track_index: int | None, track_name: str | None = None) -> tuple[str, dict[str, Any], str | None]:
    """Map a chosen action to (bridge function, args, problem)."""
    fn, fixed = BRIDGE[action]
    nums = _numbers(clause, track_name or "")
    direction = ans["direction"]["choice"]
    args: dict[str, Any] = dict(fixed)

    if fn == "set_tempo":
        if not nums:
            return fn, args, "tempo needs a number"
        return fn, {"bpm": nums[0]}, None
    if fn == "set_position":
        if not nums:
            return fn, args, "position needs a beat number"
        return fn, {"beat": nums[0]}, None
    if fn == "fire_scene":
        if not nums:
            return fn, args, "scene needs a number"
        return fn, {"scene_index": int(nums[0]) - 1}, None  # spoken 1-based
    if action not in NEEDS_TRACK:
        return fn, args, None

    if track_index is None:
        return fn, args, "no track resolved"
    args["track_index"] = track_index
    if action in DEVICE_ACTIONS:
        return fn, args, None  # device + param resolved in the second stage
    args["verify"] = True
    if fn in ("set_track_volume", "set_track_pan", "set_track_send"):
        key = {"set_track_volume": "volume", "set_track_pan": "pan", "set_track_send": "level"}[fn]
        if fn == "set_track_send":
            # "send 2" style; default to the first send
            args["send_index"] = int(nums.pop(0)) - 1 if len(nums) > 1 else 0
        if direction == "exact" and nums:
            args[key] = nums[0]
        elif direction == "center" and fn == "set_track_pan":
            args[key] = 0.0
        elif direction in ("up", "down"):
            args["_relative"] = STEP if direction == "up" else -STEP
        elif direction in ("max", "min"):
            lo, hi = (-1.0, 1.0) if fn == "set_track_pan" else (0.0, 1.0)
            args[key] = hi if direction == "max" else lo
        else:
            return fn, args, f"{key} needs a number or a direction"
    return fn, args, None


def _resolve_device(clause: str, action: str, track_index: int, track_name: str,
                    dispatch) -> tuple[dict[str, Any], str | None]:
    """Second Jev stage: pick the device, then (for device_param) the parameter.

    Options come from the live bridge, so Jev can only name what is really on
    the track. Values are taken from the sentence in human units (the bridge's
    verified setter normalizes dB, Hz, ms, ratios). Relative device changes
    ("a bit more reverb") have no range info to nudge against, so they escalate.
    """
    devs = dispatch("get_track_devices", {"track_index": track_index})
    names = devs.get("devices") or []
    if not devs.get("success") or not names:
        return {}, f"no devices readable on {track_name}"
    crit: dict[str, str | None] = {n: None for n in names}
    crit["none"] = "the command does not name or imply any listed device"
    q = {"device": {"type": "choice",
                    "instructions": "Which entry of `devices` on this track does `command` refer to? "
                                    "Match by function too (an EQ Eight is the eq, a Compressor is the comp, "
                                    "a Reverb is the verb). If only one device could do what is asked, pick it.",
                    "criteria": crit}}
    ans = jev_ask({"command": clause, "track": track_name, "devices": names}, q)["answers"]["device"]
    if ans["choice"] == "none" or ans["confidence"] < DEVICE_GATE:
        return {}, f"device unclear ({ans['choice']} @ {ans['confidence']:.2f})"
    device_index = names.index(ans["choice"])
    out: dict[str, Any] = {"track_index": track_index, "device_index": device_index,
                           "_device": ans["choice"], "_device_confidence": ans["confidence"]}
    if action != "device_param":
        return out, None

    params = dispatch("get_device_parameters", {"track_index": track_index, "device_index": device_index})
    pnames = params.get("names") or []
    if not params.get("success") or not pnames:
        return out, f"no parameters readable on {ans['choice']}"
    pcrit: dict[str, str | None] = {n: None for n in pnames}
    pcrit["none"] = "no listed parameter matches what the command wants to change"
    pq = {"param": {"type": "choice",
                    "instructions": "Which entry of `parameters` on `device` does `command` want to change? "
                                    "Map musical words to controls: lows/low end = a low-shelf or low band "
                                    "frequency or gain, highs = high band, tighter = attack or ratio, "
                                    "louder out = output/makeup gain, wetter = dry/wet or mix. "
                                    "EQ Eight bands are numbered 1 (lowest) to 8 (highest): a low cut or "
                                    "high-pass is band 1 frequency, a high cut or low-pass is band 8 frequency.",
                    "criteria": pcrit}}
    pans = jev_ask({"command": clause, "device": ans["choice"], "parameters": pnames}, pq)["answers"]["param"]
    if pans["choice"] == "none" or pans["confidence"] < DEVICE_GATE:
        return out, f"parameter unclear ({pans['choice']} @ {pans['confidence']:.2f})"
    nums = _numbers(clause, track_name, ans["choice"])
    if not nums:
        return out, (f"{pans['choice']} on {ans['choice']} needs an explicit value "
                     "(relative device nudges are not supported)")
    out.update({"param_name": pans["choice"], "value": nums[-1], "_param_confidence": pans["confidence"]})
    return out, None


def plan_command(command: str, tracks: list[dict[str, Any]],
                 song: dict[str, Any] | None = None, dispatch=None) -> dict[str, Any]:
    """Plan without executing. One Jev call per clause, plus one or two more
    for device work (device pick, parameter pick) using live bridge reads via
    ``dispatch``. Without ``dispatch`` device clauses escalate."""
    names = [t["name"] for t in tracks]
    index_by_name = {t["name"]: t["index"] for t in tracks}
    questions = _questions(names)
    steps = []
    t0 = time.time()
    for clause in _clauses(command):
        state = {"command": clause, "full_command": command, "tracks": names}
        if song:
            state["song"] = {k: song.get(k) for k in ("tempo", "is_playing", "record_mode", "loop")}
        ans = jev_ask(state, questions)["answers"]
        action = ans["fn"]["choice"]
        fn_conf = ans["fn"]["confidence"]
        track = ans["track"]["choice"]
        track_conf = ans["track"]["confidence"]
        step: dict[str, Any] = {
            "clause": clause, "action": action, "function": None, "fn_confidence": fn_conf,
            "track": None if track == "none" else track, "track_confidence": track_conf,
            "args": {}, "status": "ready", "reason": None,
        }
        if action == "none" or fn_conf < FN_GATE:
            step["status"], step["reason"] = "escalate", f"action unclear ({action} @ {fn_conf:.2f})"
        elif action in NEEDS_TRACK and (track == "none" or track_conf < TRACK_GATE):
            step["status"], step["reason"] = "escalate", f"track unclear ({track} @ {track_conf:.2f})"
        else:
            idx = index_by_name.get(track) if action in NEEDS_TRACK else None
            fn, args, problem = _args_for(action, ans, clause, idx, track if action in NEEDS_TRACK else None)
            if action in DEVICE_ACTIONS and not problem:
                if dispatch is None:
                    problem = "device work needs a live bridge"
                else:
                    dev_args, problem = _resolve_device(clause, action, idx, track, dispatch)
                    args.update(dev_args)
            step["function"], step["args"] = fn, args
            if problem:
                step["status"], step["reason"] = "escalate", problem
        steps.append(step)
    return {
        "command": command,
        "steps": steps,
        "all_ready": all(s["status"] == "ready" for s in steps),
        "jev_seconds": round(time.time() - t0, 2),
    }


def execute_plan(plan: dict[str, Any], dispatch) -> dict[str, Any]:
    """Run ready steps through ``dispatch(function_name, args)``. Escalated steps are skipped."""
    results = []
    for step in plan["steps"]:
        if step["status"] != "ready":
            results.append({"clause": step["clause"], "skipped": step["reason"]})
            continue
        args = {k: v for k, v in step["args"].items() if not k.startswith("_") or k == "_relative"}
        rel = args.pop("_relative", None)
        if rel is not None:
            key = {"set_track_volume": "volume", "set_track_pan": "pan", "set_track_send": "level"}[step["function"]]
            getter = {"volume": "get_track_volume", "pan": "get_track_pan", "level": "get_track_send"}[key]
            gargs = {"track_index": args["track_index"]}
            if key == "level":
                gargs["send_index"] = args["send_index"]
            current = dispatch(getter, gargs)
            base = float(current.get(key, current.get("value", 0.0)) or 0.0)
            lo, hi = (-1.0, 1.0) if key == "pan" else (0.0, 1.0)
            args[key] = max(lo, min(hi, round(base + rel, 3)))
        results.append({"clause": step["clause"], "function": step["function"],
                        "args": args, "result": dispatch(step["function"], args)})
    return {"command": plan["command"], "results": results}


if __name__ == "__main__":  # quick manual test against the live bridge
    import argparse
    import sys

    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(REPO_ROOT / "legacy"))
    from mcp_server.server import _dispatch

    ap = argparse.ArgumentParser()
    ap.add_argument("command")
    ap.add_argument("--execute", action="store_true")
    a = ap.parse_args()
    tl = _dispatch("get_track_list")
    song = _dispatch("get_song_status")
    plan = plan_command(a.command, tl.get("tracks", []),
                        song.get("data") if song.get("success") else None, dispatch=_dispatch)
    print(json.dumps(plan, indent=1))
    if a.execute and plan["all_ready"]:
        print(json.dumps(execute_plan(plan, _dispatch), indent=1))
