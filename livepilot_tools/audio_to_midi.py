"""Audio to MIDI for hummed parts: an arrangement audio clip becomes a MIDI clip on a new track.

Live 11 has no audio-to-MIDI in its API, so this reads the clip's own file and listens here:
"melody" tracks pitch with pYIN (one note at a time: hummed bass, a sung line), "hits" finds
onsets (beatboxed hats, claps) and puts each on one drum pitch. Seconds in the file map onto
song beats through the clip's warp markers, so the notes land where the audio plays.
"""

from __future__ import annotations

import numpy as np

from livepilot_tools import remote_script

SR = 22050
HOP = 256
KEYS = {"c": 0, "c#": 1, "db": 1, "d": 2, "d#": 3, "eb": 3, "e": 4, "f": 5, "f#": 6, "gb": 6,
        "g": 7, "g#": 8, "ab": 8, "a": 9, "a#": 10, "bb": 10, "b": 11}
MINOR = [0, 2, 3, 5, 7, 8, 10]
MAJOR = [0, 2, 4, 5, 7, 9, 11]


def beat_map(info: dict):
    """File seconds -> arrangement beats, piecewise through the warp markers, extended past the last one."""
    marks = sorted(info["warp_markers"])
    if len(marks) < 2:
        slope = info["tempo"] / 60.0
        marks = [[0.0, info["start_marker"]], [1.0, info["start_marker"] + slope]]
    secs = np.array([m[0] for m in marks])
    beats = np.array([m[1] for m in marks])
    head = (beats[1] - beats[0]) / (secs[1] - secs[0])
    tail = (beats[-1] - beats[-2]) / (secs[-1] - secs[-2])

    def to_beat(s):
        s = np.asarray(s, dtype=float)
        b = np.interp(s, secs, beats)
        b = np.where(s < secs[0], beats[0] + (s - secs[0]) * head, b)
        b = np.where(s > secs[-1], beats[-1] + (s - secs[-1]) * tail, b)
        return info["start_time"] + b - info["start_marker"]

    return to_beat


def _load(info: dict, to_beat):
    import librosa

    y, _ = librosa.load(info["file_path"], sr=SR, mono=True)
    t = np.arange(len(y)) / SR
    beat = to_beat(t[::HOP])
    keep = (beat >= info["start_time"]) & (beat < info["end_time"])  # only what the clip actually plays
    return y, keep


def melody(info: dict, to_beat, min_note_s: float = 0.08) -> list[list]:
    """[[midi, start_s, end_s, velocity]] for a one-voice line."""
    import librosa

    y, keep = _load(info, to_beat)
    f0, voiced, _ = librosa.pyin(y, fmin=40, fmax=800, sr=SR, frame_length=2048, hop_length=HOP)
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=HOP)[0]
    n = min(len(f0), len(keep), len(rms))
    midi = np.where(voiced[:n] & keep[:n], librosa.hz_to_midi(np.nan_to_num(f0[:n], nan=1.0)), np.nan)
    loud = float(np.percentile(rms[:n][~np.isnan(midi)], 95)) if np.any(~np.isnan(midi)) else 1.0
    frame_s = HOP / SR
    notes, i = [], 0
    while i < n:
        if np.isnan(midi[i]):
            i += 1
            continue
        j = i
        while j + 1 < n and not np.isnan(midi[j + 1]) and abs(midi[j + 1] - np.median(midi[i:j + 1])) < 0.8:
            j += 1
        if (j - i + 1) * frame_s >= min_note_s:
            vel = int(np.clip(40 + 87 * np.median(rms[i:j + 1]) / loud, 30, 127))
            notes.append([int(round(np.median(midi[i:j + 1]))), i * frame_s, (j + 1) * frame_s, vel])
        i = j + 1
    return notes


def hits(info: dict, to_beat, pitch: int = 42) -> list[list]:
    """[[pitch, start_s, end_s, velocity]], one per onset."""
    import librosa

    y, keep = _load(info, to_beat)
    env = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
    frames = librosa.onset.onset_detect(onset_envelope=env, sr=SR, hop_length=HOP, backtrack=True, units="frames")
    frames = [f for f in frames if f < len(keep) and keep[f]]
    top = float(np.percentile(env[frames], 95)) if frames else 1.0
    frame_s = HOP / SR
    return [[pitch, f * frame_s, f * frame_s + 0.1, int(np.clip(50 + 77 * env[f] / top, 30, 127))] for f in frames]


def readable(path: str) -> bool:
    """Live locks some of this session's recordings against every reader, itself included, until the set reopens."""
    try:
        with open(path, "rb"):
            return True
    except OSError:
        return False


def key_check(pitches: list[int], key: str) -> list[int]:
    """Pitches outside the key, e.g. key='E minor'."""
    root, _, kind = key.strip().lower().partition(" ")
    scale = MAJOR if kind.startswith("maj") else MINOR
    allowed = {(KEYS[root] + s) % 12 for s in scale}
    return sorted({p for p in pitches if p % 12 not in allowed})


def convert(track: int, clip: int = 0, kind: str = "melody", octave: int = 0, grid: float = 0.25,
            key: str | None = None, name: str | None = None, drum_pitch: int = 42, reopen: bool = False) -> dict:
    """Read arrangement clip `clip` on `track`, write its notes into a new MIDI track right after it.

    octave shifts melody notes (-2 for a hum sung up high that should be bass); grid snaps note
    starts in beats (0.25 = 16ths, 0 = as played). The source track is left untouched.
    reopen=True closes and reopens the set first when Live has the recording locked.
    Undo = delete the new track.
    """
    info = remote_script.send_command("lp_audio_clip", {"track_index": track, "clip_index": clip})
    if not info.get("success"):
        return info
    if not readable(info["file_path"]):
        if not reopen:
            return {"success": False, "locked": True,
                    "message": "Live is holding that recording locked until the set is reopened (about a minute). "
                               "Ask him, then call again with reopen=true."}
        from livepilot_tools import live_app
        res = live_app.restart()
        if not res.get("success") or not readable(info["file_path"]):
            return {"success": False, "message": f"Reopened the set but the recording is still locked: {res}"}
    to_beat = beat_map(info)
    raw = hits(info, to_beat, drum_pitch) if kind == "hits" else melody(info, to_beat)
    if not raw:
        return {"success": False, "message": f"Heard no {'hits' if kind == 'hits' else 'notes'} in {info['name']}."}
    start = np.floor(info["start_time"] / grid) * grid if grid else info["start_time"]  # the grid is the song's
    length = info["end_time"] - start
    notes = []
    for pitch, s0, s1, vel in raw:
        b0, b1 = float(to_beat(s0)) - start, float(to_beat(s1)) - start
        if grid:
            b0 = round(b0 / grid) * grid
            b1 = max(b0 + grid, round(b1 / grid) * grid)
        if 0 <= b0 < length:
            p = pitch + (0 if kind == "hits" else 12 * octave)
            notes.append([int(np.clip(p, 0, 127)), b0, min(b1, length) - b0, vel, 0])
    loudest = {}  # one "tss" fires two or three onsets; snapped to the same step they are one hit
    for n in notes:
        if n[1] not in loudest or n[3] > loudest[n[1]][3]:
            loudest[n[1]] = n
    notes = sorted(loudest.values(), key=lambda n: n[1])
    if kind != "hits":  # one voice: a note may not overlap the next
        for a, b in zip(notes, notes[1:]):
            a[2] = min(a[2], b[1] - a[1])

    src = remote_script.send_command("get_track_info", {"track_index": track})
    new_name = name or f"{'Hits' if kind == 'hits' else 'Notes'} from {src.get('name', f'track {track}')}"
    made = remote_script.send_command("create_midi_track", {"index": track + 1, "name": new_name})
    if not made.get("success"):
        return made
    t = int(made.get("index", track + 1))
    steps = [("create_clip", {"track_index": t, "clip_index": 0, "length": length}),
             ("lp_notes_write", {"track_index": t, "clip_index": 0, "notes": notes}),
             ("create_arrangement_clip", {"track_index": t, "clip_slot_index": 0, "start_time": start,
                                          "length": length, "name": new_name}),
             ("delete_clip", {"track_index": t, "clip_index": 0})]
    for cmd, params in steps:
        res = remote_script.send_command(cmd, params, timeout=20.0)
        if not res.get("success"):
            return {**res, "message": f"Made track {t} '{new_name}' but {cmd} failed: {res.get('message')}"}
    pitches = [n[0] for n in notes]
    out = {"success": True, "track_index": t, "track_name": new_name, "notes": len(notes),
           "pitch_range": [min(pitches), max(pitches)], "placed_at_beat": float(start), "length_beats": length}
    if key and kind != "hits":
        out["outside_key"] = key_check(pitches, key)
    out["summary"] = (f"{len(notes)} {'hits' if kind == 'hits' else 'notes'} on new track {t} '{new_name}' "
                      f"(pitch {min(pitches)}-{max(pitches)}), no instrument yet")
    return out
