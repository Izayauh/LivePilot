"""Loopback capture helpers for spectral comparison."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np


class AudioCaptureError(RuntimeError):
    """Raised when loopback capture cannot be completed."""


@dataclass
class CapturedPair:
    reference_audio: np.ndarray
    user_audio: np.ndarray
    sample_rate: int
    reference_track: int
    user_track: int


def capture_loopback(
    device: str,
    seconds: float,
    sample_rate: int = 48000,
    channels: int = 2,
) -> np.ndarray:
    """Record a short stereo capture from a named input device."""
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise AudioCaptureError(
            "sounddevice is required for loopback capture. Install requirements.txt first."
        ) from exc

    frames = int(round(float(seconds) * sample_rate))
    if frames <= 0:
        raise AudioCaptureError("--capture-seconds must be greater than zero.")

    try:
        recording = sd.rec(
            frames,
            samplerate=sample_rate,
            channels=channels,
            dtype="float32",
            device=device,
        )
        sd.wait()
    except Exception as exc:
        raise AudioCaptureError(f"Could not capture from device {device!r}: {exc}") from exc

    return np.asarray(recording, dtype=np.float32)


def resolve_track(bridge: Any, track_ref: str) -> int:
    """Resolve a 0-based track index or fuzzy track name."""
    try:
        return int(str(track_ref).strip())
    except (TypeError, ValueError):
        pass

    matches = bridge.find_track_by_name(track_ref)
    if not matches:
        raise AudioCaptureError(f"No Ableton track matched {track_ref!r}.")
    return int(matches[0]["index"])


def capture_track(
    bridge: Any,
    track_index: int,
    capture_device: str,
    capture_seconds: float,
    sample_rate: int = 48000,
    channels: int = 2,
    preroll_seconds: float = 0.35,
) -> np.ndarray:
    """Solo one track, play the current loop, and capture loopback audio."""
    _exclusive_solo(bridge, track_index)
    bridge.execute("play", {})
    if preroll_seconds > 0:
        time.sleep(preroll_seconds)
    try:
        return capture_loopback(
            capture_device,
            capture_seconds,
            sample_rate=sample_rate,
            channels=channels,
        )
    finally:
        bridge.execute("stop", {})


def capture_reference_and_user(
    bridge: Any,
    reference_track: int,
    user_track: int,
    capture_device: str,
    capture_seconds: float,
    sample_rate: int = 48000,
    channels: int = 2,
    preroll_seconds: float = 0.35,
) -> CapturedPair:
    """Capture the loaded reference and user's vocal stack from loopback."""
    reference_audio = capture_track(
        bridge,
        reference_track,
        capture_device,
        capture_seconds,
        sample_rate=sample_rate,
        channels=channels,
        preroll_seconds=preroll_seconds,
    )
    user_audio = capture_track(
        bridge,
        user_track,
        capture_device,
        capture_seconds,
        sample_rate=sample_rate,
        channels=channels,
        preroll_seconds=preroll_seconds,
    )
    return CapturedPair(
        reference_audio=reference_audio,
        user_audio=user_audio,
        sample_rate=sample_rate,
        reference_track=reference_track,
        user_track=user_track,
    )


def _exclusive_solo(bridge: Any, track_index: int) -> None:
    tracks = bridge.get_track_list()
    for track in tracks:
        index: Optional[int]
        try:
            index = int(track.get("index"))
        except (TypeError, ValueError):
            index = None
        if index is None:
            continue
        bridge.solo_track(index, index == track_index)

