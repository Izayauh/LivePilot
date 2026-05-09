"""Loopback capture helpers for spectral comparison."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

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


@dataclass
class CaptureDevice:
    device: Any
    sample_rate: int
    label: str


def capture_loopback(
    device: Any,
    seconds: float,
    sample_rate: int,
    channels: int = 2,
) -> np.ndarray:
    """Record a short stereo capture from an input device."""
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


def resolve_capture_device(
    capture_device: Optional[str] = None,
    capture_device_index: Optional[int] = None,
    sample_rate: Optional[int] = None,
    query_devices: Optional[Callable[..., Any]] = None,
    query_hostapis: Optional[Callable[..., Any]] = None,
) -> CaptureDevice:
    """Resolve a sounddevice input and sample rate for loopback capture."""
    if query_devices is None or query_hostapis is None:
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise AudioCaptureError(
                "sounddevice is required for loopback capture. Install requirements.txt first."
            ) from exc
        query_devices = query_devices or sd.query_devices
        query_hostapis = query_hostapis or sd.query_hostapis

    if capture_device_index is not None:
        device_info = _device_info(query_devices, capture_device_index)
        _require_input_device(device_info, capture_device_index)
        return CaptureDevice(
            device=int(capture_device_index),
            sample_rate=_resolve_sample_rate(device_info, sample_rate),
            label=_device_label(device_info, capture_device_index, query_hostapis),
        )

    if not capture_device:
        raise AudioCaptureError(
            "Specify --capture-device-index for reliable loopback capture, "
            "or provide --capture-device when the device name is unique."
        )

    matches = []
    for index, device_info in enumerate(query_devices()):
        if int(device_info.get("max_input_channels") or 0) <= 0:
            continue
        if capture_device.lower() in str(device_info.get("name", "")).lower():
            matches.append((index, device_info))

    if not matches:
        raise AudioCaptureError(f"No input capture device matched {capture_device!r}.")
    if len(matches) > 1:
        options = "\n".join(
            f"  [{index}] {_device_label(device_info, index, query_hostapis)}"
            for index, device_info in matches
        )
        raise AudioCaptureError(
            f"Capture device name {capture_device!r} is ambiguous. "
            "Use --capture-device-index with one of:\n"
            f"{options}"
        )

    index, device_info = matches[0]
    return CaptureDevice(
        device=index,
        sample_rate=_resolve_sample_rate(device_info, sample_rate),
        label=_device_label(device_info, index, query_hostapis),
    )


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
    capture_device: Any,
    capture_seconds: float,
    sample_rate: int,
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
    capture_device: Any,
    capture_seconds: float,
    sample_rate: int,
    channels: int = 2,
    preroll_seconds: float = 0.35,
    silence_threshold_db: Optional[float] = None,
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
    if silence_threshold_db is not None:
        ensure_not_silent(reference_audio, "Reference", silence_threshold_db)

    user_audio = capture_track(
        bridge,
        user_track,
        capture_device,
        capture_seconds,
        sample_rate=sample_rate,
        channels=channels,
        preroll_seconds=preroll_seconds,
    )
    if silence_threshold_db is not None:
        ensure_not_silent(user_audio, "Your vocal group", silence_threshold_db)

    return CapturedPair(
        reference_audio=reference_audio,
        user_audio=user_audio,
        sample_rate=sample_rate,
        reference_track=reference_track,
        user_track=user_track,
    )


def rms_dbfs(audio_array: np.ndarray) -> float:
    audio = np.asarray(audio_array, dtype=np.float64)
    if audio.size == 0:
        return float("-inf")
    rms = float(np.sqrt(np.mean(np.square(audio))))
    if rms <= 1e-12:
        return float("-inf")
    return float(20.0 * np.log10(rms))


def ensure_not_silent(audio_array: np.ndarray, label: str, threshold_db: float) -> None:
    dbfs = rms_dbfs(audio_array)
    if dbfs >= float(threshold_db):
        return
    readable = "-inf" if dbfs == float("-inf") else f"{dbfs:.1f}"
    raise AudioCaptureError(
        f"{label} capture is silent or too quiet ({readable} dBFS; "
        f"threshold {float(threshold_db):.1f} dBFS). Check clips firing, "
        "solo/mute state, track routing, and loopback input selection."
    )


def _exclusive_solo(bridge: Any, track_index: int) -> None:
    tracks = bridge.get_track_list()
    seen_target = False
    for track in tracks:
        index: Optional[int]
        try:
            index = int(track.get("index"))
        except (TypeError, ValueError):
            index = None
        if index is None:
            continue
        seen_target = seen_target or index == track_index
        bridge.solo_track(index, False)

    if not seen_target:
        raise AudioCaptureError(f"Track index {track_index} was not found in Ableton track list.")

    bridge.solo_track(track_index, True)
    _log_solo_status_best_effort(bridge, track_index)


def _device_info(query_devices: Callable[..., Any], index: int) -> dict:
    try:
        return dict(query_devices(int(index)))
    except Exception as exc:
        raise AudioCaptureError(f"Could not query capture device index {index}: {exc}") from exc


def _require_input_device(device_info: dict, index: int) -> None:
    if int(device_info.get("max_input_channels") or 0) <= 0:
        raise AudioCaptureError(f"Capture device index {index} has no input channels.")


def _resolve_sample_rate(device_info: dict, sample_rate: Optional[int]) -> int:
    if sample_rate is not None:
        return int(sample_rate)
    default = device_info.get("default_samplerate")
    if not default:
        raise AudioCaptureError(
            f"Capture device {device_info.get('name', '<unknown>')!r} did not report a default sample rate."
        )
    return int(round(float(default)))


def _device_label(
    device_info: dict,
    index: int,
    query_hostapis: Optional[Callable[..., Any]],
) -> str:
    host_api = ""
    if query_hostapis is not None:
        try:
            host_api = str(query_hostapis(device_info.get("hostapi", -1)).get("name", ""))
        except Exception:
            host_api = ""
    suffix = f", {host_api}" if host_api else ""
    return f"{index}: {device_info.get('name', '<unknown>')}{suffix}"


def _log_solo_status_best_effort(bridge: Any, track_index: int) -> None:
    execute = getattr(bridge, "execute", None)
    if not callable(execute):
        return
    try:
        execute("get_track_status", {"track_index": track_index})
    except Exception:
        return

