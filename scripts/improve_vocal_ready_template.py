#!/usr/bin/env python3
"""Create and improve the vocal-ready beat template in Ableton.

This script is intentionally idempotent: it creates missing template tracks,
loads missing starter devices, and records a small run report for future Codex
automation passes. It does not delete or rename existing user tracks.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import socket
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

BRIDGE = REPO_ROOT / "ableton_bridge.py"
CHANGELOG = REPO_ROOT / "docs" / "vocal-ready-template-changelog.md"
STATE_PATH = REPO_ROOT / "templates" / "vocal_ready_template_state.json"
ABLETON_OSC_HOST = "127.0.0.1"
ABLETON_OSC_PORT = 11000
ABLETON_OSC_RESPONSE_PORT = 11001
NEXT_RECOMMENDED_IMPROVEMENT = (
    "When Ableton responds, run a zero-device-load pass to write and verify the SEND - Throw Delay delay profile "
    "with display-string timing readback, then add bridge support for naming or directly addressing return tracks."
)

DEVICE_FALLBACKS = {
    "Auto Filter": ["Auto Filter", "EQ Eight"],
    "Chorus-Ensemble": ["Chorus-Ensemble", "Chorus"],
    "Compressor": ["Compressor", "Glue Compressor"],
    "Drum Rack": ["Drum Rack"],
    "Electric": ["Electric", "Drift"],
    "EQ Eight": ["EQ Eight", "reaeq-standalone", "Q10 Paragraphic EQ Stereo", "F6-RTA Stereo"],
    "Gate": ["Gate", "reagate-standalone"],
    "Glue Compressor": ["Glue Compressor", "Compressor", "Solid Bus Comp"],
    "Limiter": ["Limiter"],
    "Multiband Dynamics": ["Multiband Dynamics", "reaxcomp-standalone"],
    "Operator": ["Drift"],
    "Ping Pong Delay": ["Ping Pong Delay", "Delay", "Simple Delay", "readelay-standalone"],
    "Reverb": ["Reverb", "ValhallaSupermassive", "Abbey Road Plates Stereo"],
    "Saturator": ["Saturator", "Abbey Road Saturator Stereo"],
    "Simple Delay": ["Simple Delay", "Delay", "Ping Pong Delay", "readelay-standalone"],
    "Utility": ["Utility"],
    "Wavetable": ["Drift"],
}

BLOCKED_PLUGINS = {
    "FabFilter Pro-Q 4",
    "Pro-Q 4",
    "Pro-Q 3",
    "FabFilter Pro-Q 3",
}

TRACK_SPECIFIC_BLOCKED_DEVICES = {
    "BASS - Sub 808": {"Arpeggiator", "Marvel GEQ"},
    "MUSIC - Chords": {"Arpeggiator", "Marvel GEQ"},
    "MUSIC - Keys Pad": {"Arpeggiator", "Marvel GEQ"},
    "MUSIC - Lead Hook": {"Marvel GEQ"},
    # Keep 3rd-party EQ options (e.g., Q10/F6) allowed; they are valid fallbacks when verified.
}

ROUTING_PLAN = {
    "DRUMS - Kick": "DRUM BUS",
    "DRUMS - Snare Clap": "DRUM BUS",
    "DRUMS - Hats Perc Top": "DRUM BUS",
    "BASS - Sub 808": "BASS BUS",
    "MUSIC - Chords": "MUSIC BUS - Vocal Pocket",
    "MUSIC - Keys Pad": "MUSIC BUS - Vocal Pocket",
    "MUSIC - Lead Hook": "MUSIC BUS - Vocal Pocket",
    "VOCAL - Lead Placeholder": "VOCAL BUS",
    "VOCAL - Doubles Adlibs": "VOCAL BUS",
    "DRUM BUS": "Master",
    "BASS BUS": "Master",
    "MUSIC BUS - Vocal Pocket": "Master",
    "VOCAL BUS": "Master",
    "FX - Transitions Texture": "MUSIC BUS - Vocal Pocket",
    "REFERENCE / PRINT": "Master",
}

SUPPLEMENTAL_ROUTING_PREFIXES = {
    "DRUMS - ": "DRUM BUS",
    "BASS - ": "BASS BUS",
    "MUSIC - ": "MUSIC BUS - Vocal Pocket",
    "VOCAL - ": "VOCAL BUS",
}

BUS_TRACKS = {
    "DRUM BUS",
    "BASS BUS",
    "MUSIC BUS - Vocal Pocket",
    "VOCAL BUS",
}

CRITICAL_BUS_DEVICES = {
    "DRUM BUS": ("EQ Eight",),
    "BASS BUS": ("EQ Eight",),
    "MUSIC BUS - Vocal Pocket": ("EQ Eight",),
    "VOCAL BUS": ("EQ Eight",),
}

PRIORITY_BUS_DYNAMICS = {
    "DRUM BUS": ("Glue Compressor",),
    "MUSIC BUS - Vocal Pocket": ("Compressor",),
}

PRIORITY_RETURN_DELAYS = {
    "SEND - Throw Delay": ("Ping Pong Delay", "Delay", "Simple Delay"),
}

RETURN_SEND_TARGETS = {
    0: "SEND - Short Plate",
    1: "SEND - Slap Delay",
    2: "SEND - Long Hall",
    3: "SEND - Throw Delay",
    4: "SEND - Parallel Drum Comp",
}

SEND_PLAN = {
    "DRUM BUS": {4: 0.10},
    "DRUMS - Snare Clap": {0: 0.08},
    "DRUMS - Hats Perc Top": {0: 0.03},
    "MUSIC - Chords": {2: 0.035},
    "MUSIC - Keys Pad": {0: 0.06, 1: 0.04},
    "MUSIC - Lead Hook": {0: 0.04, 1: 0.06},
    "FX - Transitions Texture": {3: 0.05},
    "VOCAL - Lead Placeholder": {0: 0.18, 1: 0.12},
    "VOCAL - Doubles Adlibs": {0: 0.14, 1: 0.18},
}

EQ_PROFILES = {
    "DRUMS - Kick": {
        "1 Filter On A": 1.0,
        "1 Filter Type A": 4,
        "1 Frequency A": 28,
        "1 Resonance A": 0.75,
        "2 Filter On A": 1.0,
        "2 Filter Type A": 7,
        "2 Frequency A": 240,
        "2 Gain A": -1.5,
        "2 Resonance A": 1.0,
        "3 Filter On A": 1.0,
        "3 Filter Type A": 7,
        "3 Frequency A": 2800,
        "3 Gain A": 0.8,
        "3 Resonance A": 0.8,
    },
    "DRUMS - Snare Clap": {
        "1 Filter On A": 1.0,
        "1 Filter Type A": 4,
        "1 Frequency A": 95,
        "1 Resonance A": 0.7,
        "2 Filter On A": 1.0,
        "2 Filter Type A": 7,
        "2 Frequency A": 450,
        "2 Gain A": -1.8,
        "2 Resonance A": 1.2,
        "3 Filter On A": 1.0,
        "3 Filter Type A": 7,
        "3 Frequency A": 4200,
        "3 Gain A": -0.8,
        "3 Resonance A": 0.8,
    },
    "DRUMS - Hats Perc Top": {
        "1 Filter On A": 1.0,
        "1 Filter Type A": 4,
        "1 Frequency A": 260,
        "1 Resonance A": 0.7,
        "2 Filter On A": 1.0,
        "2 Filter Type A": 7,
        "2 Frequency A": 7600,
        "2 Gain A": -1.5,
        "2 Resonance A": 1.0,
    },
    "DRUM BUS": {
        "1 Filter On A": 1.0,
        "1 Filter Type A": 4,
        "1 Frequency A": 28,
        "1 Resonance A": 0.7,
        "2 Filter On A": 1.0,
        "2 Filter Type A": 7,
        "2 Frequency A": 320,
        "2 Gain A": -0.8,
        "2 Resonance A": 0.9,
        "3 Filter On A": 1.0,
        "3 Filter Type A": 9,
        "3 Frequency A": 9000,
        "3 Gain A": 0.5,
        "3 Resonance A": 0.7,
    },
    "SEND - Short Plate": {
        "1 Filter On A": 1.0,
        "1 Filter Type A": 4,
        "1 Frequency A": 180,
        "1 Resonance A": 0.7,
        # Use a high-shelf cut as a safe "LP" until EQ Eight LP filter-type mapping is verified locally.
        "3 Filter On A": 1.0,
        "3 Filter Type A": 9,
        "3 Frequency A": 8500,
        "3 Gain A": -6.0,
        "3 Resonance A": 0.7,
    },
    "SEND - Long Hall": {
        "1 Filter On A": 1.0,
        "1 Filter Type A": 4,
        "1 Frequency A": 250,
        "1 Resonance A": 0.7,
        "3 Filter On A": 1.0,
        "3 Filter Type A": 9,
        "3 Frequency A": 6500,
        "3 Gain A": -7.0,
        "3 Resonance A": 0.7,
    },
    "SEND - Slap Delay": {
        "1 Filter On A": 1.0,
        "1 Filter Type A": 4,
        "1 Frequency A": 220,
        "1 Resonance A": 0.7,
        "3 Filter On A": 1.0,
        "3 Filter Type A": 9,
        "3 Frequency A": 5000,
        "3 Gain A": -8.0,
        "3 Resonance A": 0.7,
    },
    "SEND - Throw Delay": {
        "1 Filter On A": 1.0,
        "1 Filter Type A": 4,
        "1 Frequency A": 260,
        "1 Resonance A": 0.7,
        "3 Filter On A": 1.0,
        "3 Filter Type A": 9,
        "3 Frequency A": 4800,
        "3 Gain A": -8.0,
        "3 Resonance A": 0.7,
    },
    "SEND - Parallel Drum Comp": {
        "1 Filter On A": 1.0,
        "1 Filter Type A": 4,
        "1 Frequency A": 35,
        "1 Resonance A": 0.7,
        "2 Filter On A": 1.0,
        "2 Filter Type A": 7,
        "2 Frequency A": 320,
        "2 Gain A": -1.0,
        "2 Resonance A": 0.9,
        "3 Filter On A": 1.0,
        "3 Filter Type A": 9,
        "3 Frequency A": 7800,
        "3 Gain A": -4.5,
        "3 Resonance A": 0.7,
    },
    "BASS - Sub 808": {
        "1 Filter On A": 1.0,
        "1 Filter Type A": 4,
        "1 Frequency A": 24,
        "1 Resonance A": 0.75,
        "2 Filter On A": 1.0,
        "2 Filter Type A": 7,
        "2 Frequency A": 230,
        "2 Gain A": -1.2,
        "2 Resonance A": 0.9,
        "3 Filter On A": 1.0,
        "3 Filter Type A": 9,
        "3 Frequency A": 3200,
        "3 Gain A": -1.5,
        "3 Resonance A": 0.7,
    },
    "BASS BUS": {
        "1 Filter On A": 1.0,
        "1 Filter Type A": 4,
        "1 Frequency A": 24,
        "1 Resonance A": 0.7,
        "2 Filter On A": 1.0,
        "2 Filter Type A": 7,
        "2 Frequency A": 260,
        "2 Gain A": -0.8,
        "2 Resonance A": 0.9,
        "3 Filter On A": 1.0,
        "3 Filter Type A": 7,
        "3 Frequency A": 900,
        "3 Gain A": -0.5,
        "3 Resonance A": 0.8,
    },
    "MUSIC - Chords": {
        "1 Filter On A": 1.0,
        "1 Filter Type A": 4,
        "1 Frequency A": 135,
        "1 Resonance A": 0.7,
        "2 Filter On A": 1.0,
        "2 Filter Type A": 7,
        "2 Frequency A": 330,
        "2 Gain A": -2.0,
        "2 Resonance A": 1.1,
        "3 Filter On A": 1.0,
        "3 Filter Type A": 7,
        "3 Frequency A": 2400,
        "3 Gain A": -1.8,
        "3 Resonance A": 1.0,
    },
    "MUSIC - Keys Pad": {
        "1 Filter On A": 1.0,
        "1 Filter Type A": 4,
        "1 Frequency A": 160,
        "1 Resonance A": 0.7,
        "2 Filter On A": 1.0,
        "2 Filter Type A": 7,
        "2 Frequency A": 370,
        "2 Gain A": -1.8,
        "2 Resonance A": 1.0,
        "3 Filter On A": 1.0,
        "3 Filter Type A": 7,
        "3 Frequency A": 2800,
        "3 Gain A": -1.5,
        "3 Resonance A": 1.0,
    },
    "MUSIC - Lead Hook": {
        "1 Filter On A": 1.0,
        "1 Filter Type A": 4,
        "1 Frequency A": 150,
        "1 Resonance A": 0.7,
        "2 Filter On A": 1.0,
        "2 Filter Type A": 7,
        "2 Frequency A": 3000,
        "2 Gain A": -2.0,
        "2 Resonance A": 1.2,
    },
    "MUSIC BUS - Vocal Pocket": {
        "1 Filter On A": 1.0,
        "1 Filter Type A": 4,
        "1 Frequency A": 95,
        "1 Resonance A": 0.7,
        "2 Filter On A": 1.0,
        "2 Filter Type A": 7,
        "2 Frequency A": 320,
        "2 Gain A": -1.6,
        "2 Resonance A": 1.0,
        "3 Filter On A": 1.0,
        "3 Filter Type A": 7,
        "3 Frequency A": 2500,
        "3 Gain A": -2.4,
        "3 Resonance A": 1.1,
        "4 Filter On A": 1.0,
        "4 Filter Type A": 7,
        "4 Frequency A": 7200,
        "4 Gain A": -1.0,
        "4 Resonance A": 0.8,
        "5 Filter On A": 1.0,
        "5 Filter Type A": 7,
        "5 Frequency A": 1450,
        "5 Gain A": -1.1,
        "5 Resonance A": 0.9,
    },
    "VOCAL - Lead Placeholder": {
        "1 Filter On A": 1.0,
        "1 Filter Type A": 4,
        "1 Frequency A": 78,
        "1 Resonance A": 0.7,
        "2 Filter On A": 1.0,
        "2 Filter Type A": 7,
        "2 Frequency A": 250,
        "2 Gain A": -1.2,
        "2 Resonance A": 1.0,
        "3 Filter On A": 1.0,
        "3 Filter Type A": 7,
        "3 Frequency A": 3600,
        "3 Gain A": 1.1,
        "3 Resonance A": 0.8,
        "4 Filter On A": 1.0,
        "4 Filter Type A": 9,
        "4 Frequency A": 10000,
        "4 Gain A": 0.8,
        "4 Resonance A": 0.7,
    },
    "VOCAL BUS": {
        "1 Filter On A": 1.0,
        "1 Filter Type A": 4,
        "1 Frequency A": 75,
        "1 Resonance A": 0.7,
        "2 Filter On A": 1.0,
        "2 Filter Type A": 7,
        "2 Frequency A": 260,
        "2 Gain A": -1.0,
        "2 Resonance A": 1.0,
        "3 Filter On A": 1.0,
        "3 Filter Type A": 7,
        "3 Frequency A": 3500,
        "3 Gain A": 0.8,
        "3 Resonance A": 0.8,
    },
    "FX - Transitions Texture": {
        "1 Filter On A": 1.0,
        "1 Filter Type A": 4,
        "1 Frequency A": 180,
        "1 Resonance A": 0.7,
        "2 Filter On A": 1.0,
        "2 Filter Type A": 1,
        "2 Frequency A": 9000,
        "2 Resonance A": 0.7,
    },
}

DEFAULT_EQ_PROFILE = {
    "1 Filter On A": 1.0,
    "1 Filter Type A": 4,
    "1 Frequency A": 90,
    "1 Resonance A": 0.7,
}

DEVICE_PROFILES = {
    "compressor": {
        "Threshold": -18,
        "Ratio": 2.2,
        "Attack": 12,
        "Release": 140,
        "Dry/Wet": 70,
        "Makeup": 0,
    },
    "drum_compressor": {
        "Threshold": -12,
        "Ratio": 2.0,
        "Attack": 18,
        "Release": 110,
        "Dry/Wet": 65,
        "Makeup": 0,
    },
    "vocal_compressor": {
        "Threshold": -16,
        "Ratio": 3.0,
        "Attack": 6,
        "Release": 90,
        "Dry/Wet": 80,
        "Makeup": 0,
    },
    "gate": {
        "Threshold": -55,
        "Floor": -8,
        "Attack": 2,
        "Hold": 40,
        "Release": 120,
        "Return": 0,
    },
    "glue_compressor": {
        "Threshold": -10,
        "Ratio": 2.0,
        "Attack": 10,
        "Release": 100,
        "Dry/Wet": 55,
        "Makeup": 0,
    },
    "saturator": {
        "Drive": 2.0,
        "Output": -1.0,
        "Dry/Wet": 65,
        "Soft Clip": 1.0,
    },
    "utility": {
        "Gain": -1.5,
        "Stereo Width": 100,
        "Bass Mono": 1.0,
        "Bass Freq": 120,
    },
    "utility_wide": {
        "Gain": -2.0,
        "Stereo Width": 115,
        "Bass Mono": 1.0,
        "Bass Freq": 150,
    },
    "utility_mono_low": {
        "Gain": -1.0,
        "Stereo Width": 85,
        "Bass Mono": 1.0,
        "Bass Freq": 160,
    },
    "multiband": {
        "Low-Mid Crossover": 180,
        "Mid-High Crossover": 6200,
        "Soft Knee On/Off": 1.0,
        "Master Output": -1.0,
        "Amount": 18,
        "Time Scaling": 80,
    },
    "chorus": {
        "Dry/Wet": 18,
        "Amount": 25,
        "Rate": 0.18,
        "Width": 95,
    },
    "reverb": {
        "Dry/Wet": 12,
        "Decay Time": 1.2,
        "PreDelay": 18,
        "LowCut": 220,
        "HighCut": 7500,
    },
    "long_hall_reverb": {
        "Dry/Wet": 14,
        "Decay Time": 2.8,
        "PreDelay": 24,
        "LowCut": 250,
        "HighCut": 6500,
    },
    "throw_delay": {
        "Dry/Wet": 16,
        "Feedback": 32,
        "Time": 3,
        "Sync": 1.0,
    },
    "instrument": {},
    "drum_rack": {},
}

TRACK_DEVICE_PROFILE_OVERRIDES = {
    "DRUM BUS": {"compressor": "drum_compressor", "glue_compressor": "glue_compressor"},
    "BASS - Sub 808": {"utility": "utility_mono_low"},
    "BASS BUS": {"utility": "utility_mono_low", "compressor": "drum_compressor"},
    "MUSIC - Chords": {"utility": "utility_wide"},
    "MUSIC - Keys Pad": {"utility": "utility_wide"},
    "MUSIC - Lead Hook": {"utility": "utility_wide"},
    "SEND - Long Hall": {"reverb": "long_hall_reverb"},
    "SEND - Throw Delay": {"delay": "throw_delay"},
    "VOCAL - Lead Placeholder": {"compressor": "vocal_compressor"},
    "VOCAL - Doubles Adlibs": {"compressor": "vocal_compressor", "utility": "utility_wide"},
    "VOCAL BUS": {"compressor": "vocal_compressor"},
}


def run_bridge(function: str, params: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
    command = [sys.executable, str(BRIDGE), function, json.dumps(params or {})]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = completed.stdout.strip() or completed.stderr.strip() or "{}"
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        data = {"success": False, "error": output}
    if completed.returncode != 0 and "success" not in data:
        data["success"] = False
    return data


def _pad4(data: bytes) -> bytes:
    return data + (b"\0" * ((4 - len(data) % 4) % 4))


def _build_osc(address: str, args: list[Any]) -> bytes:
    payload = _pad4(address.encode("utf-8") + b"\0")
    tags = ","
    values = b""
    for arg in args:
        if isinstance(arg, bool):
            tags += "i"
            values += struct.pack(">i", int(arg))
        elif isinstance(arg, int):
            tags += "i"
            values += struct.pack(">i", arg)
        elif isinstance(arg, float):
            tags += "f"
            values += struct.pack(">f", arg)
        else:
            tags += "s"
            values += _pad4(str(arg).encode("utf-8") + b"\0")
    return payload + _pad4(tags.encode("utf-8") + b"\0") + values


def _parse_osc(data: bytes) -> tuple[str, list[Any]]:
    def read_string(offset: int) -> tuple[str, int]:
        end = data.index(b"\0", offset)
        return data[offset:end].decode("utf-8", "replace"), (end + 4) & ~3

    address, offset = read_string(0)
    tags, offset = read_string(offset)
    args: list[Any] = []
    for tag in tags[1:]:
        if tag == "i":
            args.append(struct.unpack(">i", data[offset:offset + 4])[0])
            offset += 4
        elif tag == "f":
            args.append(struct.unpack(">f", data[offset:offset + 4])[0])
            offset += 4
        elif tag == "s":
            value, offset = read_string(offset)
            args.append(value)
        elif tag == "T":
            args.append(True)
        elif tag == "F":
            args.append(False)
    return address, args


def osc_send(address: str, args: list[Any]) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(_build_osc(address, args), (ABLETON_OSC_HOST, ABLETON_OSC_PORT))
    finally:
        sock.close()


def osc_request(address: str, args: list[Any], timeout: float = 3.0) -> list[Any]:
    recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    recv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    recv.bind(("127.0.0.8", ABLETON_OSC_RESPONSE_PORT))
    recv.settimeout(timeout)
    send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    send.bind(("127.0.0.8", 0))
    try:
        send.sendto(_build_osc(address, args), (ABLETON_OSC_HOST, ABLETON_OSC_PORT))
        data, _ = recv.recvfrom(65535)
        return _parse_osc(data)[1]
    finally:
        send.close()
        recv.close()


def load_template_tracks() -> list[dict[str, Any]]:
    sys.path.insert(0, str(REPO_ROOT))
    from templates.template_manager import template_manager

    template = template_manager.get_template("vocal_ready_beat")
    if template is None:
        raise RuntimeError("vocal_ready_beat template is missing")
    return [
        {
            "name": track.name,
            "type": track.type,
            "color": track.color,
            "devices": list(track.devices),
            "settings": dict(track.settings),
        }
        for track in template.tracks
    ]


def get_track_map() -> dict[str, int]:
    result = run_bridge("get_track_list")
    if not result.get("success"):
        raise RuntimeError(f"Could not read Ableton tracks: {result}")
    return {track["name"]: int(track["index"]) for track in result.get("tracks", [])}


def create_track(spec: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return {"success": True, "dry_run": True, "message": f"Would create {spec['name']}"}

    if spec["type"] == "midi":
        created = run_bridge("create_midi_track", {"index": -1})
        if not created.get("success"):
            return created
        track_index = created.get("track_index")
        if track_index is None:
            track_index = max(get_track_map().values())
        renamed = run_bridge("set_track_name", {"track_index": track_index, "name": spec["name"]})
        return renamed if not renamed.get("success") else {"success": True, "track_index": track_index}

    created = run_bridge("create_audio_track", {"index": -1, "name": spec["name"]})
    return created


def ensure_tracks(template_tracks: list[dict[str, Any]], dry_run: bool) -> list[str]:
    changes: list[str] = []
    track_map = get_track_map()

    for spec in template_tracks:
        if spec["name"] in track_map:
            continue
        result = create_track(spec, dry_run)
        if result.get("success"):
            changes.append(f"Created track: {spec['name']}")
            track_map = get_track_map() if not dry_run else track_map
        else:
            changes.append(f"Could not create {spec['name']}: {result.get('error') or result.get('message')}")

    return changes


def ensure_track_settings(template_tracks: list[dict[str, Any]], dry_run: bool) -> list[str]:
    changes: list[str] = []
    track_map = get_track_map()

    for spec in template_tracks:
        track_index = track_map.get(spec["name"])
        if track_index is None:
            continue

        color = spec.get("color")
        if color is not None:
            if dry_run:
                changes.append(f"Would color {spec['name']} as {color}")
            else:
                run_bridge("set_track_color", {"track_index": track_index, "color_index": int(color)})

        target_peak = spec.get("settings", {}).get("target_peak_db")
        if target_peak is not None:
            # Conservative fader defaults. Exact dB gain staging belongs inside devices.
            volume = 0.72 if target_peak <= -12 else 0.78 if target_peak <= -8 else 0.82
            if dry_run:
                changes.append(f"Would set starter volume on {spec['name']} to {volume}")
            else:
                run_bridge("set_track_volume", {"track_index": track_index, "volume": volume, "verify": False})

        starter_pan = spec.get("settings", {}).get("starter_pan")
        if starter_pan is not None:
            pan = max(-0.25, min(0.25, float(starter_pan)))
            if dry_run:
                changes.append(f"Would set starter pan on {spec['name']} to {pan:g}")
            else:
                run_bridge("set_track_pan", {"track_index": track_index, "pan": pan, "verify": False})

        if spec.get("settings", {}).get("muted") is True:
            if dry_run:
                changes.append(f"Would mute {spec['name']}")
            else:
                result = run_bridge("mute_track", {"track_index": track_index, "muted": 1, "verify": False})
                if result.get("success"):
                    changes.append(f"Muted {spec['name']}")
                else:
                    changes.append(
                        f"Mute update failed for {spec['name']}: "
                        f"{result.get('error') or result.get('message')}"
                    )

    if not dry_run:
        changes.append("Applied color, conservative volume, and starter pan defaults to template tracks")
    return changes


def get_devices(track_index: int) -> list[str]:
    result = run_bridge("get_track_devices", {"track_index": track_index})
    if not result.get("success"):
        return []
    return [str(device) for device in result.get("devices", [])]


def device_present(devices: list[str], desired: str) -> bool:
    desired_lower = desired.lower()
    fallback_names = [name.lower() for name in DEVICE_FALLBACKS.get(desired, [desired])]
    return any(
        desired_lower in device.lower()
        or any(fallback in device.lower() for fallback in fallback_names)
        for device in devices
    )


def remove_blocked_devices(template_tracks: list[dict[str, Any]], dry_run: bool) -> list[str]:
    changes: list[str] = []
    track_map = get_track_map()
    blocked_lower = tuple(name.lower() for name in BLOCKED_PLUGINS)

    for spec in template_tracks:
        track_index = track_map.get(spec["name"])
        if track_index is None:
            continue

        devices = get_devices(track_index)
        track_blocked = {
            device.lower()
            for device in TRACK_SPECIFIC_BLOCKED_DEVICES.get(spec["name"], set())
        }
        blocked_indices = [
            index for index, device in enumerate(devices)
            if any(blocked in device.lower() for blocked in blocked_lower)
            or device.lower() in track_blocked
        ]
        for device_index in reversed(blocked_indices):
            device_name = devices[device_index]
            if dry_run:
                changes.append(f"Would remove blocked device {device_name} from {spec['name']}")
                continue
            result = run_bridge(
                "delete_device",
                {"track_index": track_index, "device_index": device_index},
                timeout=20,
            )
            if result.get("success"):
                changes.append(f"Removed blocked device {device_name} from {spec['name']}")
            else:
                changes.append(
                    f"Could not remove blocked device {device_name} from {spec['name']}: "
                    f"{result.get('error') or result.get('message')}"
                )

    return changes


def load_first_available(track_index: int, desired: str, dry_run: bool) -> str:
    for candidate in DEVICE_FALLBACKS.get(desired, [desired]):
        if candidate in BLOCKED_PLUGINS:
            continue
        if dry_run:
            return f"Would load {candidate}"
        before = get_devices(track_index)
        result = run_bridge(
            "add_plugin_to_track",
            {"track_index": track_index, "plugin_name": candidate, "position": -1},
            timeout=45,
        )
        after = get_devices(track_index)
        if result.get("success") or len(after) > len(before) or device_present(after, candidate):
            return f"Loaded {candidate}"
    return f"Could not load {desired}"


def ensure_devices(
    template_tracks: list[dict[str, Any]],
    dry_run: bool,
    max_device_loads: int,
) -> list[str]:
    changes: list[str] = []
    track_map = get_track_map()
    loaded_count = 0
    route_prereq_attempted: set[tuple[str, str]] = set()
    priority_attempted: set[tuple[str, str]] = set()

    # Route-dependent MIDI lanes need their instrument/Drum Rack first. With
    # low device caps, loading one full chain before the next lane leaves other
    # sources MIDI-only, so Ableton cannot route them to audio buses yet.
    for spec in template_tracks:
        if spec.get("type") != "midi":
            continue
        track_index = track_map.get(spec["name"])
        devices_to_load = spec.get("devices", [])
        if track_index is None or not devices_to_load:
            continue

        desired = devices_to_load[0]
        devices = get_devices(track_index)
        if device_present(devices, desired):
            continue
        if loaded_count >= max_device_loads:
            changes.append("Stopped device loading at max_device_loads for this run")
            return changes
        result = load_first_available(track_index, desired, dry_run)
        changes.append(f"{spec['name']}: {result}")
        route_prereq_attempted.add((spec["name"], desired))
        loaded_count += 1

    # The bus EQs are the main vocal-pocket control points. Load them before
    # lower-priority source effects so conservative caps still protect the
    # drum/bass/music/vocal bus high-pass profiles and readback checks.
    specs_by_name = {spec["name"]: spec for spec in template_tracks}
    for track_name in sorted(CRITICAL_BUS_DEVICES):
        spec = specs_by_name.get(track_name)
        track_index = track_map.get(track_name)
        if spec is None or track_index is None:
            continue

        devices = get_devices(track_index)
        for desired in CRITICAL_BUS_DEVICES[track_name]:
            if device_present(devices, desired):
                continue
            if loaded_count >= max_device_loads:
                changes.append("Stopped device loading at max_device_loads for this run")
                return changes
            result = load_first_available(track_index, desired, dry_run)
            changes.append(f"{track_name}: {result}")
            priority_attempted.add((track_name, desired))
            loaded_count += 1
            devices = get_devices(track_index) if not dry_run else devices

    # Once the bus EQ checkpoints exist, restore the highest-value bus dynamics
    # before source effects. These are the template's main controlled-density
    # points: drum glue and the music-bus vocal-pocket compressor.
    for track_name in sorted(PRIORITY_BUS_DYNAMICS):
        spec = specs_by_name.get(track_name)
        track_index = track_map.get(track_name)
        if spec is None or track_index is None:
            continue

        devices = get_devices(track_index)
        for desired in PRIORITY_BUS_DYNAMICS[track_name]:
            if device_present(devices, desired):
                continue
            if loaded_count >= max_device_loads:
                changes.append("Stopped device loading at max_device_loads for this run")
                return changes
            result = load_first_available(track_index, desired, dry_run)
            changes.append(f"{track_name}: {result}")
            priority_attempted.add((track_name, desired))
            loaded_count += 1
            devices = get_devices(track_index) if not dry_run else devices

    for spec in template_tracks:
        track_index = track_map.get(spec["name"])
        if track_index is None:
            continue

        devices = get_devices(track_index)
        for desired in spec.get("devices", []):
            if (spec["name"], desired) in route_prereq_attempted or (spec["name"], desired) in priority_attempted:
                continue
            if device_present(devices, desired):
                continue
            if loaded_count >= max_device_loads:
                changes.append("Stopped device loading at max_device_loads for this run")
                return changes
            result = load_first_available(track_index, desired, dry_run)
            changes.append(f"{spec['name']}: {result}")
            loaded_count += 1
            devices = get_devices(track_index) if not dry_run else devices

    return changes


def ensure_routing_and_sends(template_tracks: list[dict[str, Any]], dry_run: bool) -> list[str]:
    changes: list[str] = []
    track_map = get_track_map()
    template_names = {track["name"] for track in template_tracks}

    for source_name, destination_name in expanded_routing_plan(template_names, track_map.keys()).items():
        if source_name not in track_map:
            continue
        if destination_name != "Master" and destination_name not in track_map:
            changes.append(f"Routing skipped for {source_name}: missing destination {destination_name}")
            continue

        track_index = track_map[source_name]
        if dry_run:
            changes.append(f"Would route {source_name} to {destination_name}")
            continue

        try:
            available = osc_request("/live/track/get/available_output_routing_types", [track_index])
            current = osc_request("/live/track/get/output_routing_type", [track_index])
            available_routes = {str(route) for route in available[1:]}
            current_route = str(current[-1]) if current else ""
            if destination_name in available_routes and current_route != destination_name:
                osc_send("/live/track/set/output_routing_type", [track_index, destination_name])
                time.sleep(0.08)
                verify = osc_request("/live/track/get/output_routing_type", [track_index])
                changes.append(f"Routed {source_name} to {verify[-1]}")
            elif current_route == destination_name:
                continue
            else:
                changes.append(f"Routing unavailable for {source_name} -> {destination_name}")
        except Exception as exc:
            changes.append(f"Routing failed for {source_name}: {type(exc).__name__}: {exc}")

    for bus_name in BUS_TRACKS:
        track_index = track_map.get(bus_name)
        if track_index is None:
            continue
        if dry_run:
            changes.append(f"Would set monitoring on {bus_name}")
            continue
        try:
            osc_send("/live/track/set/current_monitoring_state", [track_index, 1])
            changes.append(f"Set monitoring on {bus_name}")
        except Exception as exc:
            changes.append(f"Monitoring update failed for {bus_name}: {type(exc).__name__}: {exc}")

    changes.extend(ensure_return_slots_for_send_plan(track_map, dry_run))

    for track_name, sends in SEND_PLAN.items():
        track_index = track_map.get(track_name)
        if track_index is None:
            continue
        for send_index, level in sends.items():
            if dry_run:
                changes.append(f"Would set send {send_index} on {track_name} to {level}")
                continue
            target_name = RETURN_SEND_TARGETS.get(send_index, f"send {send_index}")
            probe = run_bridge(
                "get_track_send",
                {"track_index": track_index, "send_index": send_index},
                timeout=6,
            )
            if not probe.get("success"):
                changes.append(
                    f"Send update skipped for {track_name} -> {target_name}: return slot unavailable"
                )
                continue
            result = run_bridge(
                "set_track_send",
                {"track_index": track_index, "send_index": send_index, "level": level, "verify": False},
                timeout=15,
            )
            if result.get("success"):
                changes.append(f"Set send {send_index} on {track_name} to {level}")
            else:
                changes.append(
                    f"Send update failed for {track_name} send {send_index}: "
                    f"{result.get('error') or result.get('message')}"
                )

    return changes


def required_return_slot_count() -> int:
    planned_indices = set(RETURN_SEND_TARGETS)
    for sends in SEND_PLAN.values():
        planned_indices.update(int(send_index) for send_index in sends)
    return (max(planned_indices) + 1) if planned_indices else 0


def return_slot_probe_track_index(track_map: dict[str, int]) -> int | None:
    for track_name in SEND_PLAN:
        if track_name in track_map:
            return track_map[track_name]
    return next(iter(track_map.values()), None)


def probe_return_slot_count(track_index: int, max_slots: int) -> int:
    count = 0
    for send_index in range(max_slots):
        result = run_bridge(
            "get_track_send",
            {"track_index": track_index, "send_index": send_index},
            timeout=6,
        )
        if not result.get("success"):
            break
        count = send_index + 1
    return count


def ensure_return_slots_for_send_plan(track_map: dict[str, int], dry_run: bool) -> list[str]:
    """Create enough return slots for the template's named send plan.

    This AbletonOSC setup cannot read or name return tracks directly, but
    normal track sends expose whether a return slot exists. Creating missing
    slots makes the slot-4 parallel drum bus send addressable instead of
    timing out on every run.
    """
    required_count = required_return_slot_count()
    if required_count == 0:
        return []

    probe_track_index = return_slot_probe_track_index(track_map)
    if probe_track_index is None:
        return ["Return slot ensure skipped: no track available for send probing"]

    if dry_run:
        return [f"Would ensure at least {required_count} return slots for template sends"]

    changes: list[str] = []
    existing_count = probe_return_slot_count(probe_track_index, required_count)
    for slot_index in range(existing_count, required_count):
        target_name = RETURN_SEND_TARGETS.get(slot_index, f"send {slot_index}")
        result = run_bridge("create_return_track", timeout=10)
        if result.get("success"):
            changes.append(f"Created return slot {slot_index} for {target_name}")
            time.sleep(0.15)
        else:
            changes.append(
                f"Could not create return slot {slot_index} for {target_name}: "
                f"{result.get('error') or result.get('message')}"
            )
            break
    return changes


def expanded_routing_plan(template_names: set[str], track_names: Any) -> dict[str, str]:
    """Route canonical template tracks plus named template-family additions.

    User-added tracks that keep the template prefixes should land on the same
    buses as the canonical lanes, so printed 808s, extra percussion, or adlib
    tracks keep the vocal-pocket bus behavior without needing a code edit.
    """
    plan = {
        source_name: destination_name
        for source_name, destination_name in ROUTING_PLAN.items()
        if source_name in template_names
    }
    protected_names = set(plan) | set(BUS_TRACKS) | {"REFERENCE / PRINT"}
    for track_name in track_names:
        if track_name in protected_names:
            continue
        for prefix, destination_name in SUPPLEMENTAL_ROUTING_PREFIXES.items():
            if track_name.startswith(prefix):
                plan[track_name] = destination_name
                break
    return plan


def verify_routing_readback_for_template_routes(
    template_tracks: list[dict[str, Any]],
    dry_run: bool,
) -> list[str]:
    """Read back template routing after writes, including supplemental lanes."""
    if dry_run:
        return []

    changes: list[str] = []
    track_map = get_track_map()
    template_names = {track["name"] for track in template_tracks}
    route_plan = expanded_routing_plan(template_names, track_map.keys())

    for source_name, destination_name in sorted(route_plan.items()):
        track_index = track_map.get(source_name)
        if track_index is None:
            continue
        if destination_name != "Master" and destination_name not in track_map:
            changes.append(
                f"Template routing readback skipped on {source_name}: missing destination {destination_name}"
            )
            continue

        try:
            current = osc_request("/live/track/get/output_routing_type", [track_index])
        except Exception as exc:
            changes.append(
                f"Template routing readback failed on {source_name}: {type(exc).__name__}: {exc}"
            )
            continue

        actual_route = str(current[-1]) if current else ""
        if actual_route == destination_name:
            changes.append(f"Verified template routing readback on {source_name} -> {destination_name}")
        else:
            changes.append(
                f"Template routing readback mismatch on {source_name}: "
                f"expected {destination_name} got {actual_route or 'unknown'}"
            )

    return changes


def device_kind(device_name: str) -> str:
    lower = device_name.lower()
    if "eq eight" in lower:
        return "eq"
    if "glue compressor" in lower or "solid bus comp" in lower:
        return "glue_compressor"
    if "compressor" in lower or "cla-76" in lower or "rvox" in lower:
        return "compressor"
    if "gate" in lower:
        return "gate"
    if "multiband" in lower:
        return "multiband"
    if "saturator" in lower:
        return "saturator"
    if "utility" in lower:
        return "utility"
    if "chorus" in lower:
        return "chorus"
    if "reverb" in lower or "plate" in lower or "hall" in lower:
        return "reverb"
    if "delay" in lower:
        return "delay"
    if "drum rack" in lower:
        return "drum_rack"
    if any(name in lower for name in ("drift", "electric", "grand", "instrument")):
        return "instrument"
    return "generic"


def profile_for_device(track_name: str, kind: str) -> dict[str, float]:
    if kind == "eq":
        return EQ_PROFILES.get(track_name, DEFAULT_EQ_PROFILE)
    overrides = TRACK_DEVICE_PROFILE_OVERRIDES.get(track_name, {})
    profile_key = overrides.get(kind, kind)
    return DEVICE_PROFILES.get(profile_key, {})


def _short_error(value: Any, *, limit: int = 140) -> str:
    text = str(value or "").strip().replace("\r", " ").replace("\n", " ")
    while "  " in text:
        text = text.replace("  ", " ")
    if not text:
        return "unknown error"
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def parameter_names_with_retry(
    track_index: int,
    device_index: int,
    *,
    attempts: int = 3,
    base_backoff_seconds: float = 0.12,
) -> tuple[set[str], str | None]:
    if attempts < 1:
        attempts = 1

    last: dict[str, Any] = {}
    for attempt in range(attempts):
        timeout = 15 + (attempt * 5)
        last = run_bridge(
            "get_device_parameters",
            {"track_index": track_index, "device_index": device_index},
            timeout=timeout,
        )
        if last.get("success"):
            names = {str(name) for name in last.get("names", [])}
            return names, None
        if attempt < attempts - 1:
            time.sleep(base_backoff_seconds * (2**attempt))
    return set(), _short_error(last.get("error") or last)


def parameter_name_list_with_retry(
    track_index: int,
    device_index: int,
    *,
    attempts: int = 3,
    base_backoff_seconds: float = 0.12,
) -> tuple[list[str], str | None]:
    if attempts < 1:
        attempts = 1

    last: dict[str, Any] = {}
    for attempt in range(attempts):
        timeout = 15 + (attempt * 5)
        last = run_bridge(
            "get_device_parameters",
            {"track_index": track_index, "device_index": device_index},
            timeout=timeout,
        )
        if last.get("success"):
            names = [str(name) for name in last.get("names", [])]
            return names, None
        if attempt < attempts - 1:
            time.sleep(base_backoff_seconds * (2**attempt))
    return [], _short_error(last.get("error") or last)


def parameter_value_with_retry(
    track_index: int,
    device_index: int,
    param_index: int,
    *,
    attempts: int = 2,
    base_backoff_seconds: float = 0.05,
) -> tuple[float | None, str | None]:
    if attempts < 1:
        attempts = 1

    last: dict[str, Any] = {}
    for attempt in range(attempts):
        timeout = 20 + (attempt * 6)
        last = run_bridge(
            "get_device_parameter_value",
            {"track_index": track_index, "device_index": device_index, "param_index": int(param_index)},
            timeout=timeout,
        )
        if last.get("success"):
            value = last.get("value")
            if isinstance(value, (int, float)):
                return float(value), None
            return None, f"unexpected value payload: {value!r}"
        if attempt < attempts - 1:
            time.sleep(base_backoff_seconds * (2**attempt))
    return None, _short_error(last.get("error") or last)


def parameter_value_string_with_retry(
    track_index: int,
    device_index: int,
    param_index: int,
    *,
    attempts: int = 2,
    base_backoff_seconds: float = 0.05,
) -> tuple[str | None, str | None]:
    if attempts < 1:
        attempts = 1

    last: dict[str, Any] = {}
    for attempt in range(attempts):
        timeout = 20 + (attempt * 6)
        last = run_bridge(
            "get_device_parameter_value_string",
            {"track_index": track_index, "device_index": device_index, "param_index": int(param_index)},
            timeout=timeout,
        )
        if last.get("success"):
            value_string = last.get("value_string")
            if isinstance(value_string, str) and value_string:
                return value_string, None
            return None, f"unexpected value_string payload: {value_string!r}"
        if attempt < attempts - 1:
            time.sleep(base_backoff_seconds * (2**attempt))
    return None, _short_error(last.get("error") or last)


def _float_close(actual: float, expected: float, *, abs_tol: float) -> bool:
    return abs(actual - expected) <= abs_tol


def frequency_hz_to_normalized(freq_hz: float, min_hz: float = 10.0, max_hz: float = 22000.0) -> float:
    """Match LivePilot's EQ Eight frequency normalization for readback checks."""
    freq_hz = max(min_hz, min(float(freq_hz), max_hz))
    return math.log(freq_hz / min_hz) / math.log(max_hz / min_hz)


def expected_readback_value(param_name: str, expected_value: float) -> float:
    if "Frequency" in param_name and expected_value > 1.0:
        return frequency_hz_to_normalized(expected_value)
    return expected_value


def _piecewise_normalize(value: float, points: list[tuple[float, float]]) -> float:
    if value <= points[0][0]:
        return points[0][1]
    if value >= points[-1][0]:
        return points[-1][1]
    for (value_a, norm_a), (value_b, norm_b) in zip(points, points[1:]):
        if value_a <= value <= value_b:
            position = (value - value_a) / (value_b - value_a)
            return norm_a + position * (norm_b - norm_a)
    return points[-1][1]


def _nearest_enum(value: float, choices: list[float]) -> float:
    return float(min(range(len(choices)), key=lambda index: abs(choices[index] - value)))


def expected_dynamics_readback_value(device_name: str, param_name: str, expected_value: float) -> float:
    """Match the compressor-oriented normalization used by reliable parameter writes.

    Keep this local instead of importing ableton_controls in the template script.
    Importing that package initializes controller state in this process, which can
    interfere with the subprocess bridge calls that do the actual Ableton I/O.
    """
    param_lower = param_name.lower()
    device_lower = device_name.lower()
    if "glue compressor" in device_lower:
        if "threshold" in param_lower:
            return expected_value
        if "ratio" in param_lower and expected_value >= 1.0:
            return _nearest_enum(expected_value, [2.0, 4.0, 10.0])
        if "attack" in param_lower and expected_value > 0:
            return _nearest_enum(expected_value, [0.01, 0.1, 0.3, 1.0, 3.0, 10.0, 30.0])
        if "release" in param_lower and expected_value > 0:
            return _nearest_enum(expected_value, [100.0, 300.0, 600.0, 1200.0, 2400.0, 4800.0, 10000.0])
    if "threshold" in param_lower and "compressor" in device_lower and expected_value <= 0:
        return _piecewise_normalize(
            expected_value,
            [(-70.0, 0.0), (-34.4, 0.2), (-14.0, 0.5), (-4.0, 0.75), (6.0, 1.0)],
        )
    if "ratio" in param_lower and expected_value >= 1.0:
        return _piecewise_normalize(
            expected_value,
            [(1.0, 0.0), (1.25, 0.2), (2.0, 0.5), (4.0, 0.75), (100.0, 1.0)],
        )
    if "attack" in param_lower and 0 < expected_value <= 1000:
        attack_ms = max(0.1, min(expected_value, 1000.0))
        return max(0.0, min(1.0, ((math.log10(attack_ms) + 1.0) / 4.0) ** 0.707))
    if "release" in param_lower and 0 < expected_value <= 10000:
        return _piecewise_normalize(
            expected_value,
            [(1.0, 0.0), (50.0, 0.2), (459.0, 0.5), (1360.0, 0.75), (3000.0, 1.0)],
        )
    if any(keyword in param_lower for keyword in ("dry/wet", "dry_wet", "mix", "wet")) and expected_value > 1:
        return max(0.0, min(expected_value / 100.0, 1.0))
    return expected_value


def should_report_dynamics_value_string(device_name: str, param_name: str) -> bool:
    """Use display strings for Glue values whose raw readback is enum/normalized."""
    if "glue compressor" not in device_name.lower():
        return False
    return param_name in {"Threshold", "Ratio", "Attack", "Release", "Dry/Wet"}


def _first_display_number(value_string: str) -> float | None:
    match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", value_string)
    if not match:
        return None
    return float(match.group(0))


def glue_display_value_matches(param_name: str, expected_value: float, value_string: str) -> bool:
    """Compare Glue Compressor display strings in musical units where possible."""
    display_value = _first_display_number(value_string)
    if display_value is None:
        return False

    if param_name == "Threshold":
        return abs(display_value - expected_value) <= 0.75
    if param_name == "Ratio":
        return abs(display_value - expected_value) <= 0.05
    if param_name == "Attack":
        return abs(display_value - expected_value) <= 0.25
    if param_name == "Release":
        # Glue release is commonly displayed in seconds for values >= 100 ms.
        display_ms = display_value * 1000.0 if display_value < 10.0 else display_value
        return abs(display_ms - expected_value) <= 15.0
    if param_name == "Dry/Wet":
        return abs(display_value - expected_value) <= 1.0
    return True


def expected_delay_readback_value(param_name: str, expected_value: float) -> float:
    param_lower = param_name.lower()
    if any(keyword in param_lower for keyword in ("dry/wet", "dry_wet", "mix", "wet", "feedback")):
        if expected_value > 1:
            return max(0.0, min(expected_value / 100.0, 1.0))
    return expected_value


def should_report_delay_value_string(param_name: str) -> bool:
    return param_name in {"Time", "Sync", "Feedback", "Dry/Wet"}


def delay_display_value_matches(param_name: str, expected_value: float, value_string: str) -> bool:
    """Compare delay display strings where units are stable enough to validate."""
    if param_name in {"Time", "Sync"}:
        return bool(value_string.strip())

    display_value = _first_display_number(value_string)
    if display_value is None:
        return False
    return abs(display_value - expected_value) <= 1.0


def find_priority_return_delay_device(
    devices: list[str],
    desired_devices: tuple[str, ...],
) -> tuple[int | None, str | None]:
    desired_names: list[str] = []
    for desired_device in desired_devices:
        desired_names.append(desired_device.lower())
        desired_names.extend(
            name.lower()
            for name in DEVICE_FALLBACKS.get(desired_device, [desired_device])
        )

    for device_index, device_name in enumerate(devices):
        device_lower = device_name.lower()
        if any(desired_name in device_lower for desired_name in desired_names):
            return device_index, device_name
    return None, None


def verify_return_delay_readback_for_template_returns(template_tracks: list[dict[str, Any]], dry_run: bool) -> list[str]:
    """Read back priority delay-return settings, including musical display strings when available."""
    if dry_run:
        return []

    changes: list[str] = []
    track_map = get_track_map()
    tolerance = 0.025

    for track_name, desired_devices in PRIORITY_RETURN_DELAYS.items():
        track_index = track_map.get(track_name)
        if track_index is None:
            changes.append(f"Return delay verification skipped on {track_name}: return track not exposed by bridge")
            continue

        devices_result = run_bridge("get_track_devices", {"track_index": track_index}, timeout=20)
        if not devices_result.get("success"):
            changes.append(f"Return delay verification skipped on {track_name}: {_short_error(devices_result)}")
            continue
        devices = [str(name) for name in devices_result.get("devices", [])]

        device_index, actual_device = find_priority_return_delay_device(devices, desired_devices)
        if device_index is None or actual_device is None:
            changes.append(f"Return delay verification skipped on {track_name}: delay device not found")
            continue

        name_list, name_err = parameter_name_list_with_retry(track_index, device_index, attempts=3)
        if name_err:
            changes.append(
                f"Return delay verification skipped on {track_name}: "
                f"{actual_device} parameters unavailable ({name_err})"
            )
            continue

        expected_profile = {"Device On": 1.0}
        expected_profile.update(profile_for_device(track_name, "delay"))
        critical_params = [
            param_name
            for param_name in ("Device On", "Dry/Wet", "Feedback", "Time", "Sync")
            if param_name in expected_profile
        ]
        index_by_name = {name: idx for idx, name in enumerate(name_list)}
        mismatches: list[str] = []
        display_readbacks: list[str] = []

        for param_name in critical_params:
            param_index = index_by_name.get(param_name)
            if param_index is None:
                mismatches.append(f"{param_name}=missing")
                continue

            actual, value_err = parameter_value_with_retry(track_index, device_index, param_index, attempts=2)
            if value_err:
                mismatches.append(f"{param_name}=error({value_err})")
                continue

            source_value = float(expected_profile[param_name])
            expected_value = expected_delay_readback_value(param_name, source_value)
            if not _float_close(float(actual), expected_value, abs_tol=tolerance):
                mismatches.append(f"{param_name} expected {expected_value:g} got {float(actual):g}")
                continue

            if should_report_delay_value_string(param_name):
                value_string, string_err = parameter_value_string_with_retry(
                    track_index,
                    device_index,
                    param_index,
                    attempts=2,
                )
                if string_err:
                    mismatches.append(f"{param_name} display=error({string_err})")
                elif value_string:
                    if not delay_display_value_matches(param_name, source_value, value_string):
                        mismatches.append(f"{param_name} display expected {source_value:g} got {value_string}")
                        continue
                    display_readbacks.append(f"{param_name}={value_string}")

        if mismatches:
            preview = "; ".join(mismatches[:4])
            suffix = "..." if len(mismatches) > 4 else ""
            changes.append(f"Return delay readback mismatch on {track_name}: {preview}{suffix}")
        else:
            display = ""
            if display_readbacks:
                display = f" ({'; '.join(display_readbacks)})"
            changes.append(f"Verified return delay readback on {track_name}: {actual_device}{display}")

    return changes




def find_eq_eight_device_for_readback(
    track_index: int,
    devices: list[str],
    required_params: list[str],
) -> tuple[int | None, list[str], str | None]:
    """Find an exact EQ Eight device whose exposed params match the bus profile."""
    eq_indices = [
        index for index, device_name in enumerate(devices)
        if device_name.strip().lower() == "eq eight"
    ]
    if not eq_indices:
        return None, [], "EQ Eight not found"

    fallback_index: int | None = None
    fallback_names: list[str] = []
    fallback_error: str | None = None

    for device_index in eq_indices:
        name_list, name_err = parameter_name_list_with_retry(track_index, device_index, attempts=3)
        if name_err:
            fallback_error = name_err
            continue
        if fallback_index is None:
            fallback_index = device_index
            fallback_names = name_list
        if all(param_name in name_list for param_name in required_params):
            return device_index, name_list, None

    if fallback_index is not None:
        return fallback_index, fallback_names, None
    return None, [], fallback_error or "EQ Eight parameters unavailable"


def verify_eq_readback_for_critical_tracks(template_tracks: list[dict[str, Any]], dry_run: bool) -> list[str]:
    """Read back critical EQ Eight params on key busses and report mismatches.

    This is intentionally read-only (no parameter writes). It protects the
    template against silent mapping issues (ex: EQ Eight filter-type mixups)
    by verifying the bus HP filters that most affect vocal space.
    """
    if dry_run:
        return []

    changes: list[str] = []
    track_map = get_track_map()

    verify_param_tolerances = {
        "Filter Type": 0.01,
        "Frequency": 0.015,
        "Gain": 0.15,
    }

    track_names = sorted(BUS_TRACKS)
    for track_name in track_names:
        track_index = track_map.get(track_name)
        if track_index is None:
            continue

        devices_result = run_bridge("get_track_devices", {"track_index": track_index}, timeout=20)
        if not devices_result.get("success"):
            changes.append(f"Return EQ verification skipped on {track_name}: {_short_error(devices_result)}")
            continue
        devices = [str(name) for name in devices_result.get("devices", [])]
        expected = EQ_PROFILES.get(track_name, {})
        if not expected:
            continue

        critical_params = [name for name in ("1 Filter Type A", "1 Frequency A") if name in expected]
        if not critical_params:
            continue

        device_index, name_list, device_err = find_eq_eight_device_for_readback(
            track_index,
            devices,
            critical_params,
        )
        if device_index is None:
            changes.append(f"Bus EQ verification skipped on {track_name}: {device_err}")
            continue

        index_by_name = {name: idx for idx, name in enumerate(name_list)}
        mismatches: list[str] = []
        for param_name in critical_params:
            param_index = index_by_name.get(param_name)
            if param_index is None:
                mismatches.append(f"{param_name}=missing")
                continue

            actual, value_err = parameter_value_with_retry(track_index, device_index, param_index, attempts=2)
            if value_err:
                mismatches.append(f"{param_name}=error({value_err})")
                continue

            expected_value = expected_readback_value(param_name, float(expected[param_name]))
            if "Filter Type" in param_name:
                ok = _float_close(float(actual), expected_value, abs_tol=verify_param_tolerances["Filter Type"])
            elif "Frequency" in param_name:
                ok = _float_close(float(actual), expected_value, abs_tol=verify_param_tolerances["Frequency"])
            elif "Gain" in param_name:
                ok = _float_close(float(actual), expected_value, abs_tol=verify_param_tolerances["Gain"])
            else:
                ok = _float_close(float(actual), expected_value, abs_tol=0.01)

            if not ok:
                source_value = float(expected[param_name])
                if expected_value != source_value:
                    mismatches.append(
                        f"{param_name} expected {source_value:g}Hz/{expected_value:g} normalized got {float(actual):g}"
                    )
                else:
                    mismatches.append(f"{param_name} expected {expected_value:g} got {float(actual):g}")

        if mismatches:
            preview = "; ".join(mismatches[:4])
            suffix = "…" if len(mismatches) > 4 else ""
            changes.append(f"Bus EQ Eight readback mismatch on {track_name}: {preview}{suffix}")
        else:
            changes.append(f"Verified bus EQ Eight readback on {track_name}")

    return changes


def find_priority_bus_dynamics_device(
    devices: list[str],
    desired_device: str,
) -> tuple[int | None, str | None]:
    desired_lower = desired_device.lower()
    fallback_names = [
        name.lower()
        for name in DEVICE_FALLBACKS.get(desired_device, [desired_device])
    ]
    for device_index, device_name in enumerate(devices):
        device_lower = device_name.lower()
        if desired_lower in device_lower or any(fallback in device_lower for fallback in fallback_names):
            return device_index, device_name
    return None, None


def verify_priority_bus_dynamics_readback(template_tracks: list[dict[str, Any]], dry_run: bool) -> list[str]:
    """Read back priority bus dynamics settings after parameter profiles run."""
    if dry_run:
        return []

    changes: list[str] = []
    track_map = get_track_map()
    tolerance = 0.025

    for track_name in sorted(PRIORITY_BUS_DYNAMICS):
        track_index = track_map.get(track_name)
        if track_index is None:
            continue

        devices_result = run_bridge("get_track_devices", {"track_index": track_index}, timeout=20)
        if not devices_result.get("success"):
            changes.append(f"Bus dynamics verification skipped on {track_name}: {_short_error(devices_result)}")
            continue
        devices = [str(name) for name in devices_result.get("devices", [])]

        for desired_device in PRIORITY_BUS_DYNAMICS[track_name]:
            device_index, actual_device = find_priority_bus_dynamics_device(devices, desired_device)
            if device_index is None or actual_device is None:
                changes.append(f"Bus dynamics verification skipped on {track_name}: {desired_device} not found")
                continue

            name_list, name_err = parameter_name_list_with_retry(track_index, device_index, attempts=3)
            if name_err:
                changes.append(
                    f"Bus dynamics verification skipped on {track_name}: "
                    f"{actual_device} parameters unavailable ({name_err})"
                )
                continue

            kind = device_kind(actual_device)
            expected_profile = {"Device On": 1.0}
            expected_profile.update(profile_for_device(track_name, kind))
            critical_params = [
                param_name
                for param_name in ("Device On", "Threshold", "Ratio", "Attack", "Release", "Dry/Wet")
                if param_name in expected_profile
            ]
            index_by_name = {name: idx for idx, name in enumerate(name_list)}
            mismatches: list[str] = []
            display_readbacks: list[str] = []

            for param_name in critical_params:
                param_index = index_by_name.get(param_name)
                if param_index is None:
                    mismatches.append(f"{param_name}=missing")
                    continue

                actual, value_err = parameter_value_with_retry(track_index, device_index, param_index, attempts=2)
                if value_err:
                    mismatches.append(f"{param_name}=error({value_err})")
                    continue

                source_value = float(expected_profile[param_name])
                expected_value = expected_dynamics_readback_value(actual_device, param_name, source_value)
                if not _float_close(float(actual), expected_value, abs_tol=tolerance):
                    mismatches.append(f"{param_name} expected {expected_value:g} got {float(actual):g}")
                    continue

                if should_report_dynamics_value_string(actual_device, param_name):
                    value_string, string_err = parameter_value_string_with_retry(
                        track_index,
                        device_index,
                        param_index,
                        attempts=2,
                    )
                    if string_err:
                        mismatches.append(f"{param_name} display=error({string_err})")
                    elif value_string:
                        if not glue_display_value_matches(param_name, source_value, value_string):
                            mismatches.append(
                                f"{param_name} display expected {source_value:g} got {value_string}"
                            )
                            continue
                        display_readbacks.append(f"{param_name}={value_string}")

            if mismatches:
                preview = "; ".join(mismatches[:4])
                suffix = "..." if len(mismatches) > 4 else ""
                changes.append(f"Bus dynamics readback mismatch on {track_name}: {preview}{suffix}")
            else:
                display = ""
                if display_readbacks:
                    display = f" ({'; '.join(display_readbacks)})"
                changes.append(f"Verified bus dynamics readback on {track_name}: {actual_device}{display}")

    return changes


def verify_send_readback_for_template_sends(template_tracks: list[dict[str, Any]], dry_run: bool) -> list[str]:
    """Read back default send levels for the core vocal-ready ambience plan."""
    if dry_run:
        return []

    changes: list[str] = []
    track_map = get_track_map()
    tolerance = 0.015

    for track_name, sends in SEND_PLAN.items():
        track_index = track_map.get(track_name)
        if track_index is None:
            continue

        mismatches: list[str] = []
        skipped: list[str] = []
        for send_index, expected_level in sends.items():
            target_name = RETURN_SEND_TARGETS.get(send_index, f"send {send_index}")
            result = run_bridge(
                "get_track_send",
                {"track_index": track_index, "send_index": int(send_index)},
                timeout=10,
            )
            if not result.get("success"):
                if send_index >= 2:
                    skipped.append(f"{target_name}=return slot unavailable")
                    continue
                mismatches.append(f"{target_name}=error({_short_error(result)})")
                continue

            actual = result.get("level")
            if not isinstance(actual, (int, float)):
                mismatches.append(f"{target_name}=missing")
                continue

            if not _float_close(float(actual), float(expected_level), abs_tol=tolerance):
                mismatches.append(f"{target_name} expected {expected_level:g} got {float(actual):g}")

        if mismatches:
            preview = "; ".join(mismatches[:4])
            suffix = "…" if len(mismatches) > 4 else ""
            changes.append(f"Template send readback mismatch on {track_name}: {preview}{suffix}")
        elif skipped:
            preview = "; ".join(skipped[:4])
            suffix = "…" if len(skipped) > 4 else ""
            changes.append(f"Template send readback skipped on {track_name}: {preview}{suffix}")
        else:
            changes.append(f"Verified template send readback on {track_name}")

    return changes


def set_device_parameter(track_index: int, device_index: int, param_name: str, value: float) -> dict[str, Any]:
    return run_bridge(
        "set_device_parameter_by_name",
        {
            "track_index": track_index,
            "device_index": device_index,
            "param_name": param_name,
            "value": value,
        },
        timeout=25,
    )


def set_device_parameter_with_retry(
    track_index: int,
    device_index: int,
    param_name: str,
    value: float,
    *,
    attempts: int = 2,
    base_backoff_seconds: float = 0.05,
) -> dict[str, Any]:
    if attempts < 1:
        attempts = 1

    last: dict[str, Any] = {}
    for attempt in range(attempts):
        last = set_device_parameter(track_index, device_index, param_name, value)
        if last.get("success"):
            return last
        if attempt < attempts - 1:
            time.sleep(base_backoff_seconds * (2**attempt))
    return last


def parameter_profile_track_order(template_tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prioritize bus profiles so capped runs still protect the vocal pocket."""
    bus_tracks = [track for track in template_tracks if track["name"] in BUS_TRACKS]
    source_tracks = [track for track in template_tracks if track["name"] not in BUS_TRACKS]
    return bus_tracks + source_tracks


def parameter_profile_work_items(
    template_tracks: list[dict[str, Any]],
    track_map: dict[str, int],
    devices_by_track: dict[str, list[str]],
) -> list[tuple[dict[str, Any], int, int, str]]:
    bus_eq_items: list[tuple[dict[str, Any], int, int, str]] = []
    remaining_items: list[tuple[dict[str, Any], int, int, str]] = []

    for spec in parameter_profile_track_order(template_tracks):
        track_name = spec["name"]
        track_index = track_map.get(track_name)
        if track_index is None:
            continue

        for device_index, device_name in enumerate(devices_by_track.get(track_name, [])):
            item = (spec, track_index, device_index, device_name)
            if track_name in BUS_TRACKS and device_kind(device_name) == "eq":
                bus_eq_items.append(item)
            else:
                remaining_items.append(item)

    return bus_eq_items + remaining_items


def apply_parameter_profiles(template_tracks: list[dict[str, Any]], dry_run: bool) -> list[str]:
    changes: list[str] = []
    track_map = get_track_map()

    # Per-run safety caps to prevent long or stuck parameter passes from stalling the automation.
    max_devices: int = int(getattr(apply_parameter_profiles, "max_devices", 0) or 0)
    max_writes: int = int(getattr(apply_parameter_profiles, "max_writes", 0) or 0)
    max_seconds: float = float(getattr(apply_parameter_profiles, "max_seconds", 0.0) or 0.0)
    start_time = time.monotonic()
    processed_devices = 0
    attempted_writes = 0

    devices_by_track = {
        spec["name"]: get_devices(track_map[spec["name"]])
        for spec in template_tracks
        if spec["name"] in track_map
    }

    for spec, track_index, device_index, device_name in parameter_profile_work_items(
        template_tracks,
        track_map,
        devices_by_track,
    ):
        track_name = spec["name"]
        if max_seconds and (time.monotonic() - start_time) >= max_seconds:
            changes.append(
                f"Parameter profiles capped after {processed_devices} devices / {attempted_writes} writes "
                f"(time budget {max_seconds:.0f}s)"
            )
            return changes
        if max_devices and processed_devices >= max_devices:
            changes.append(
                f"Parameter profiles capped after {processed_devices} devices / {attempted_writes} writes "
                f"(device cap {max_devices})"
            )
            return changes

        kind = device_kind(device_name)
        params = {"Device On": 1.0}
        params.update(profile_for_device(track_name, kind))
        if dry_run:
            changes.append(f"Would set {len(params)} params on {track_name}: {device_name}")
            processed_devices += 1
            continue

        available_params, param_error = parameter_names_with_retry(track_index, device_index)
        if param_error:
            changes.append(
                "Parameter read failed on "
                f"{track_name}: {device_name} (track={track_index} device={device_index} err={param_error})"
            )
            processed_devices += 1
            continue
        applied = 0
        skipped = 0
        failed = 0
        failed_param_names: list[str] = []
        for param_name, value in params.items():
            if max_seconds and (time.monotonic() - start_time) >= max_seconds:
                changes.append(
                    f"Parameter profiles capped after {processed_devices} devices / {attempted_writes} writes "
                    f"(time budget {max_seconds:.0f}s)"
                )
                return changes
            if max_writes and attempted_writes >= max_writes:
                changes.append(
                    f"Parameter profiles capped after {processed_devices} devices / {attempted_writes} writes "
                    f"(write cap {max_writes})"
                )
                return changes
            if param_name not in available_params:
                skipped += 1
                continue
            attempted_writes += 1
            result = set_device_parameter_with_retry(
                track_index,
                device_index,
                param_name,
                value,
                attempts=2,
                base_backoff_seconds=0.05,
            )
            if result.get("success"):
                applied += 1
            else:
                failed += 1
                failed_param_names.append(param_name)
        if applied or failed:
            failed_detail = ""
            if failed_param_names:
                max_failed_names = 6
                shown = failed_param_names[:max_failed_names]
                suffix = "…" if len(failed_param_names) > max_failed_names else ""
                failed_detail = f": {', '.join(shown)}{suffix}"
            changes.append(
                f"Set {applied} params on {track_name}: {device_name} "
                f"(skipped {skipped}, failed {failed}{failed_detail})"
            )
        else:
            changes.append(
                f"No writable profile params matched on {track_name}: {device_name} "
                f"(kind={kind})"
            )

        processed_devices += 1

    return changes


def write_state_and_changelog(changes: list[str], dry_run: bool) -> None:
    if dry_run:
        return

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state = {
        "template": "vocal_ready_beat",
        "last_run_utc": now,
        "last_changes": changes,
        "next_recommended_improvement": NEXT_RECOMMENDED_IMPROVEMENT,
    }
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    if not CHANGELOG.exists():
        CHANGELOG.write_text("# Vocal-Ready Template Changelog\n\n", encoding="utf-8")
    with CHANGELOG.open("a", encoding="utf-8") as handle:
        handle.write(f"## {now}\n")
        if changes:
            for change in changes:
                handle.write(f"- {change}\n")
        else:
            handle.write("- Verified template; no missing tracks or devices found in this pass.\n")
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Plan without changing Ableton or state files")
    parser.add_argument(
        "--max-device-loads",
        type=int,
        default=18,
        help="Cap device loads per run so recurring automation stays stable",
    )
    parser.add_argument(
        "--max-parameter-devices",
        type=int,
        default=32,
        help="Cap number of devices to apply parameter profiles to per run (0 disables cap)",
    )
    parser.add_argument(
        "--max-parameter-writes",
        type=int,
        default=260,
        help="Cap number of parameter writes per run (0 disables cap)",
    )
    parser.add_argument(
        "--max-parameter-seconds",
        type=float,
        default=75.0,
        help="Time budget in seconds for parameter profile application (0 disables cap)",
    )
    parser.add_argument(
        "--skip-parameters",
        action="store_true",
        help="Skip routing, send, and device-parameter profile application",
    )
    args = parser.parse_args()

    template_tracks = load_template_tracks()
    changes: list[str] = []
    changes.extend(ensure_tracks(template_tracks, args.dry_run))
    changes.extend(ensure_track_settings(template_tracks, args.dry_run))
    changes.extend(remove_blocked_devices(template_tracks, args.dry_run))
    changes.extend(ensure_devices(template_tracks, args.dry_run, args.max_device_loads))
    if not args.skip_parameters:
        apply_parameter_profiles.max_devices = args.max_parameter_devices
        apply_parameter_profiles.max_writes = args.max_parameter_writes
        apply_parameter_profiles.max_seconds = args.max_parameter_seconds
        changes.extend(ensure_routing_and_sends(template_tracks, args.dry_run))
        changes.append(
            "Automation improvement: SEND - Throw Delay now has delay display-string readback."
        )
        changes.append(
            "Why it improves vocal-ready beat creation: throw timing, sync, feedback, and wet settings can be verified in musical display units instead of raw numbers when the bridge exposes the return."
        )
        changes.extend(verify_routing_readback_for_template_routes(template_tracks, args.dry_run))
        changes.extend(apply_parameter_profiles(template_tracks, args.dry_run))
        changes.extend(verify_eq_readback_for_critical_tracks(template_tracks, args.dry_run))
        changes.extend(verify_priority_bus_dynamics_readback(template_tracks, args.dry_run))
        changes.extend(verify_return_delay_readback_for_template_returns(template_tracks, args.dry_run))
        changes.extend(verify_send_readback_for_template_sends(template_tracks, args.dry_run))
        changes.append(f"Best next improvement: {NEXT_RECOMMENDED_IMPROVEMENT}")
    write_state_and_changelog(changes, args.dry_run)

    print(json.dumps({"success": True, "changes": changes, "dry_run": args.dry_run}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
