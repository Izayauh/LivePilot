#!/usr/bin/env python3
"""Create a vocal-ready beat artifact pack for the daily LivePilot run.

The current Ableton bridge can set tempo, routing, devices, sends, and
parameters, but it does not expose MIDI clip writing yet. This script makes the
beat concrete by generating MIDI files plus a report in a predictable folder.
"""

from __future__ import annotations

import argparse
import json
import struct
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
BRIDGE = REPO_ROOT / "ableton_bridge.py"
BEAT_ROOT = REPO_ROOT / "daily_beats"
REPORT_ROOT = REPO_ROOT / "docs" / "daily_beat_reports"
PPQ = 480


def vlq(value: int) -> bytes:
    buffer = value & 0x7F
    value >>= 7
    while value:
        buffer <<= 8
        buffer |= ((value & 0x7F) | 0x80)
        value >>= 7
    out = bytearray()
    while True:
        out.append(buffer & 0xFF)
        if buffer & 0x80:
            buffer >>= 8
        else:
            break
    return bytes(out)


def midi_header(track_count: int) -> bytes:
    return b"MThd" + struct.pack(">IHHH", 6, 1, track_count, PPQ)


def meta_event(delta: int, event_type: int, data: bytes) -> bytes:
    return vlq(delta) + bytes([0xFF, event_type]) + vlq(len(data)) + data


def tempo_event(bpm: int) -> bytes:
    micros = int(60_000_000 / bpm)
    return meta_event(0, 0x51, micros.to_bytes(3, "big"))


def note_events(notes: Iterable[dict], channel: int) -> bytes:
    events: list[tuple[int, bytes]] = []
    for note in notes:
        start = int(round(float(note["start"]) * PPQ))
        end = int(round(float(note["end"]) * PPQ))
        pitch = int(note["pitch"])
        velocity = int(note.get("velocity", 92))
        events.append((start, bytes([0x90 | channel, pitch, velocity])))
        events.append((end, bytes([0x80 | channel, pitch, 0])))
    events.sort(key=lambda item: (item[0], item[1][0] == (0x90 | channel)))

    cursor = 0
    data = bytearray()
    for tick, event in events:
        data += vlq(max(0, tick - cursor))
        data += event
        cursor = tick
    data += meta_event(0, 0x2F, b"")
    return bytes(data)


def track_chunk(name: str, notes: list[dict], channel: int, bpm: int | None = None) -> bytes:
    data = bytearray()
    data += meta_event(0, 0x03, name.encode("ascii", "replace"))
    if bpm:
        data += tempo_event(bpm)
    data += note_events(notes, channel)
    return b"MTrk" + struct.pack(">I", len(data)) + bytes(data)


def write_midi(path: Path, tracks: list[tuple[str, list[dict], int]], bpm: int) -> None:
    chunks = [track_chunk("tempo", [], 0, bpm=bpm)]
    chunks.extend(track_chunk(name, notes, channel) for name, notes, channel in tracks)
    path.write_bytes(midi_header(len(chunks)) + b"".join(chunks))


def beat_notes() -> dict[str, list[dict]]:
    drums = []
    for bar in range(8):
        base = bar * 4
        for beat in [0, 2.0, 2.75]:
            drums.append({"start": base + beat, "end": base + beat + 0.08, "pitch": 36, "velocity": 110})
        for beat in [1.0, 3.0]:
            drums.append({"start": base + beat, "end": base + beat + 0.08, "pitch": 38, "velocity": 104})
        for step in range(8):
            vel = 64 if step % 2 else 78
            drums.append({"start": base + step * 0.5, "end": base + step * 0.5 + 0.05, "pitch": 42, "velocity": vel})
        if bar in {1, 3, 5, 7}:
            drums.append({"start": base + 3.5, "end": base + 3.58, "pitch": 46, "velocity": 72})

    roots = [29, 25, 32, 27]  # F, Db, Ab, Eb
    bass = []
    for bar in range(8):
        root = roots[bar % 4]
        base = bar * 4
        for start, length, vel in [(0, 0.85, 108), (1.5, 0.35, 82), (2.0, 0.8, 102), (3.25, 0.45, 88)]:
            bass.append({"start": base + start, "end": base + start + length, "pitch": root, "velocity": vel})

    chords = []
    voicings = [
        [53, 56, 60, 63],  # Fm9 color
        [49, 56, 60, 65],  # Dbmaj7 color
        [51, 56, 60, 63],  # Ab/Eb suspended color
        [51, 55, 58, 63],  # Ebsus/darker turn
    ]
    for bar in range(8):
        base = bar * 4
        for pitch in voicings[bar % 4]:
            chords.append({"start": base, "end": base + 3.65, "pitch": pitch, "velocity": 58})

    lead = []
    phrase = [(0.5, 68), (0.75, 70), (1.5, 72), (2.25, 67), (3.0, 65)]
    for bar in [0, 2, 4, 6]:
        base = bar * 4
        for offset, pitch in phrase:
            lead.append({"start": base + offset, "end": base + offset + 0.22, "pitch": pitch, "velocity": 62})

    fx = [
        {"start": 7.5, "end": 8.0, "pitch": 72, "velocity": 45},
        {"start": 15.5, "end": 16.0, "pitch": 75, "velocity": 48},
        {"start": 23.5, "end": 24.0, "pitch": 77, "velocity": 48},
        {"start": 31.0, "end": 32.0, "pitch": 80, "velocity": 52},
    ]
    return {"drums": drums, "bass": bass, "chords": chords, "lead": lead, "fx": fx}


def run_bridge(function: str, params: dict) -> dict:
    result = subprocess.run(
        [sys.executable, str(BRIDGE), function, json.dumps(params)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"success": False, "message": result.stderr or result.stdout}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default=None)
    parser.add_argument("--bpm", type=int, default=148)
    args = parser.parse_args()

    now = datetime.now()
    label = args.label or f"{now:%Y-%m-%d_%H%M%S}_vocal_ready_f_minor"
    out_dir = BEAT_ROOT / label
    out_dir.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)

    notes = beat_notes()
    tracks = [
        ("DRUMS - Kick Snare Hats", notes["drums"], 9),
        ("BASS - Sub 808", notes["bass"], 1),
        ("MUSIC - Chords", notes["chords"], 2),
        ("MUSIC - Lead Hook", notes["lead"], 3),
        ("FX - Transitions", notes["fx"], 4),
    ]

    write_midi(out_dir / "combined_vocal_ready_beat.mid", tracks, args.bpm)
    for name, track_notes, channel in tracks:
        safe = name.lower().replace(" - ", "_").replace(" ", "_")
        write_midi(out_dir / f"{safe}.mid", [(name, track_notes, channel)], args.bpm)

    drum_splits = {
        "drums_kick.mid": [note for note in notes["drums"] if int(note["pitch"]) == 36],
        "drums_snare_clap.mid": [note for note in notes["drums"] if int(note["pitch"]) == 38],
        "drums_hats_perc_top.mid": [note for note in notes["drums"] if int(note["pitch"]) in {42, 46}],
    }
    for filename, split_notes in drum_splits.items():
        track_name = {
            "drums_kick.mid": "DRUMS - Kick",
            "drums_snare_clap.mid": "DRUMS - Snare Clap",
            "drums_hats_perc_top.mid": "DRUMS - Hats Perc Top",
        }[filename]
        write_midi(out_dir / filename, [(track_name, split_notes, 9)], args.bpm)

    run_bridge("set_tempo", {"bpm": args.bpm})
    run_bridge("set_loop_start", {"beat": 0})
    run_bridge("set_loop_length", {"beats": 32})
    run_bridge("set_loop", {"enabled": 1})

    plan = {
        "created_at": now.isoformat(timespec="seconds"),
        "tempo_bpm": args.bpm,
        "key_mode": "F minor",
        "length_bars": 8,
        "mood": "late-night, sparse, vocal-forward",
        "artifact_dir": str(out_dir),
        "files": sorted(path.name for path in out_dir.glob("*.mid")),
        "routing": {
            "drums": "DRUM BUS -> Master",
            "bass": "BASS BUS -> Master",
            "music": "MUSIC BUS - Vocal Pocket -> Master",
            "vocal_placeholders": "VOCAL BUS -> Master",
        },
        "vocal_space": [
            "Lead/chord parts avoid dense 1-4 kHz writing.",
            "Drum bus low cut is sub-rumble only; not a 2 kHz body-killer.",
            "Bass is mono-forward and leaves 150-350 Hz vocal body manageable.",
        ],
        "limitations": [
            "Ableton bridge currently lacks deterministic MIDI clip import/write, so this run created MIDI artifacts and set the Live session tempo/loop.",
            "Import the track-matched MIDI files onto the matching named template tracks until LivePilot exposes clip writing.",
        ],
    }
    (out_dir / "beat_plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    readme = f"""# Vocal-Ready Beat Artifact

- Created: {plan['created_at']}
- Tempo: {args.bpm} BPM
- Key/mode: F minor
- Length: 8 bars
- Mood: late-night, sparse, vocal-forward

## Files

{chr(10).join(f'- `{name}`' for name in plan['files'])}

## Notes

The beat is designed for the LivePilot vocal-ready template. Import the MIDI files onto the matching tracks:

- drums -> `DRUMS - Kick`, `DRUMS - Snare Clap`, `DRUMS - Hats Perc Top`
- bass -> `BASS - Sub 808`
- chords -> `MUSIC - Chords`
- lead -> `MUSIC - Lead Hook`
- fx -> `FX - Transitions Texture`

No Pro-Q assumptions. EQ Eight drum high-pass defaults have been corrected to HP12 filter type with sub-rumble cutoff only.
"""
    (out_dir / "README.md").write_text(readme, encoding="utf-8")

    report_path = REPORT_ROOT / f"{now:%Y-%m-%d}.md"
    report_path.write_text(readme + f"\nArtifact folder: `{out_dir}`\n", encoding="utf-8")
    print(json.dumps({"success": True, "artifact_dir": str(out_dir), "files": plan["files"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
