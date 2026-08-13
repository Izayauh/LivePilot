#!/usr/bin/env python3
"""Generate custom R&B MIDI files for the 'Practical Routes' instrumental in C minor at 82 BPM.
"""
from __future__ import annotations
import struct
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "daily_beats" / "20260520_practical_routes"
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

def note_events(notes: list[dict], channel: int) -> bytes:
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

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bpm = 82

    # Chords (Cm9 - Abmaj7 - Fm9 - G7alt)
    chords = []
    voicings = [
        # Cm9: C3(48), G3(55), Bb3(58), D4(62), Eb4(63)
        [48, 55, 58, 62, 63],
        # Abmaj7: Ab2(44), G3(55), C4(60), Eb4(63), G4(67)
        [44, 55, 60, 63, 67],
        # Fm9: F2(41), G3(55), Ab3(56), C4(60), Eb4(63)
        [41, 55, 56, 60, 63],
        # G7alt: G2(43), F3(53), Ab3(56), B3(59), Eb4(63)
        [43, 53, 56, 59, 63]
    ]

    for bar in range(8):
        base = bar * 4
        chord_voicing = voicings[bar % 4]
        # Play chord starting at beat 0, extending to beat 3.75 of the bar
        for pitch in chord_voicing:
            chords.append({
                "start": base,
                "end": base + 3.75,
                "pitch": pitch,
                "velocity": 65
            })

    # Sub Bass
    bass = []
    for bar in range(8):
        base = bar * 4
        # Core pitches: C2(36), Ab1(32), F1(29), G1(31)
        root_pitches = [36, 32, 29, 31]
        root = root_pitches[bar % 4]
        
        # Simple R&B groove
        bass.append({"start": base + 0.0, "end": base + 2.5, "pitch": root, "velocity": 85})
        
        # Add some tasteful melodic passing notes
        if bar % 4 == 0:  # Cm9 bar
            bass.append({"start": base + 2.75, "end": base + 3.25, "pitch": 39, "velocity": 80})  # Eb2
            bass.append({"start": base + 3.5, "end": base + 3.75, "pitch": 43, "velocity": 80})   # G2
        elif bar % 4 == 1:  # Abmaj7 bar
            bass.append({"start": base + 3.0, "end": base + 3.75, "pitch": 32, "velocity": 85})   # Ab1
        elif bar % 4 == 2:  # Fm9 bar
            bass.append({"start": base + 2.75, "end": base + 3.25, "pitch": 32, "velocity": 80})  # Ab1
            bass.append({"start": base + 3.5, "end": base + 3.75, "pitch": 34, "velocity": 80})   # Bb1
        elif bar % 4 == 3:  # G7alt bar
            bass.append({"start": base + 3.0, "end": base + 3.75, "pitch": 31, "velocity": 85})   # G1

    # Drums (Swung boom bap rim & kick)
    drums = []
    for bar in range(8):
        base = bar * 4
        # Snare/Rim on 2 and 4 (beat 1.0 and 3.0)
        drums.append({"start": base + 1.0, "end": base + 1.1, "pitch": 38, "velocity": 95})
        drums.append({"start": base + 3.0, "end": base + 3.1, "pitch": 38, "velocity": 95})

        # Kick drum placement (Dilla swing)
        if bar % 2 == 0:
            drums.append({"start": base + 0.0, "end": base + 0.15, "pitch": 36, "velocity": 105})
            drums.append({"start": base + 2.26, "end": base + 2.4, "pitch": 36, "velocity": 100})
        else:
            drums.append({"start": base + 0.0, "end": base + 0.15, "pitch": 36, "velocity": 105})
            drums.append({"start": base + 2.26, "end": base + 2.4, "pitch": 36, "velocity": 100})
            drums.append({"start": base + 3.76, "end": base + 3.9, "pitch": 36, "velocity": 90})

        # Swung shaker/hats
        for step in range(8):
            # Swung 8th notes (0.0, 0.54, 1.0, 1.54, 2.0, 2.54, 3.0, 3.54)
            start_beat = step * 0.5
            if step % 2 == 1:
                start_beat += 0.04 # Swung 8th note delay
            drums.append({
                "start": base + start_beat,
                "end": base + start_beat + 0.05,
                "pitch": 42,
                "velocity": 50 if step % 2 == 1 else 65
            })

    # Write separate tracks
    write_midi(OUT_DIR / "rhodes_chords.mid", [("MUSIC - Rhodes Chords", chords, 2)], bpm)
    write_midi(OUT_DIR / "sub_bass.mid", [("BASS - Sub", bass, 1)], bpm)
    write_midi(OUT_DIR / "drums.mid", [("DRUMS - Kick Snare Rim", drums, 9)], bpm)
    write_midi(OUT_DIR / "combined_instrumental.mid", [
        ("MUSIC - Rhodes Chords", chords, 2),
        ("BASS - Sub", bass, 1),
        ("DRUMS - Kick Snare Rim", drums, 9)
    ], bpm)

    print(f"Generated R&B MIDI files in: {OUT_DIR}")

if __name__ == "__main__":
    main()
