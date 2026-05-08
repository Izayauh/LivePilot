#!/usr/bin/env python3
"""
Setup Comparison - deterministic A/B setup against a local reference track.

Loudness path:
  1. Preferred: read the backing audio file for the user's first clip via
     ableton_bridge.get_clip_audio_path and measure it directly with pyloudnorm.
  2. Fallback: load Waves WLM Plus on the user's track, play the current loop,
     and read a short-term LUFS parameter when that device exposes one.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


REFERENCE_LIBRARY_PATH = _REPO_ROOT / "config" / "reference_library.json"
DEFAULT_TARGET_LUFS = -10.0
SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a"}


class ComparisonSetupError(RuntimeError):
    """Raised when comparison setup cannot be completed safely."""


class AbletonBridgeClient:
    """Small in-process wrapper around ableton_bridge dispatch."""

    def execute(self, func_name: str, args: dict) -> dict:
        import ableton_bridge

        dispatch = ableton_bridge._build_dispatch(args)
        if func_name not in dispatch:
            return {"success": False, "message": f"Unknown bridge function: {func_name}"}
        try:
            result = dispatch[func_name]()
        except Exception as exc:
            return {"success": False, "message": str(exc)}
        if isinstance(result, dict):
            return result
        return {"success": True, "result": result}

    def create_audio_track(self, name: str) -> int:
        result = self.execute("create_audio_track", {"name": name, "index": -1})
        _require_success(result, f"create audio track {name!r}")
        track_index = result.get("track_index")
        if track_index is None:
            raise ComparisonSetupError(
                "Bridge created an audio track but did not return track_index."
            )
        return int(track_index)

    def set_clip_path(self, track_index: int, clip_index: int, audio_path: str) -> None:
        result = self.execute(
            "set_clip_path",
            {"track_index": track_index, "clip_index": clip_index, "audio_path": audio_path},
        )
        _require_success(result, f"load clip {audio_path!r}")

    def get_clip_audio_path(self, track_index: int, clip_index: int = 0) -> str:
        result = self.execute(
            "get_clip_audio_path",
            {"track_index": track_index, "clip_index": clip_index},
        )
        _require_success(result, f"read clip path for track {track_index}")
        audio_path = result.get("audio_path") or result.get("path")
        if not audio_path:
            raise ComparisonSetupError(
                f"Bridge did not return audio_path for track {track_index}, clip {clip_index}."
            )
        return str(audio_path)

    def add_utility_device(self, track_index: int, gain_db: float, name: str) -> dict:
        result = self.execute(
            "add_utility_device",
            {"track_index": track_index, "gain_db": gain_db, "name": name},
        )
        _require_success(result, f"add Utility to track {track_index}")
        return result

    def set_track_pan(self, track_index: int, pan: float) -> None:
        result = self.execute("set_track_pan", {"track_index": track_index, "pan": pan})
        _require_success(result, f"set pan on track {track_index}")

    def solo_track(self, track_index: int, soloed: bool) -> None:
        result = self.execute(
            "solo_track",
            {"track_index": track_index, "soloed": 1 if soloed else 0},
        )
        _require_success(result, f"set solo on track {track_index}")

    def set_clip_detune(self, track_index: int, clip_index: int, cents: float) -> dict:
        return self.execute(
            "set_clip_detune",
            {"track_index": track_index, "clip_index": clip_index, "cents": cents},
        )


def _require_success(result: dict, action: str) -> None:
    if result.get("success"):
        return
    message = result.get("message") or result.get("error") or "unknown error"
    raise ComparisonSetupError(f"Could not {action}: {message}")


def measure_lufs(audio_path: str) -> float:
    """Measure integrated loudness for a local audio file."""
    try:
        import pyloudnorm as pyln
        import soundfile as sf
    except ImportError as exc:
        raise ComparisonSetupError(
            "pyloudnorm and soundfile are required. Install requirements.txt first."
        ) from exc

    try:
        samples, sample_rate = sf.read(audio_path, always_2d=True)
    except Exception as exc:
        raise ComparisonSetupError(f"Could not read audio file {audio_path!r}: {exc}") from exc

    meter = pyln.Meter(sample_rate)
    return float(meter.integrated_loudness(samples))


def load_reference_library(library_path: Path = REFERENCE_LIBRARY_PATH) -> dict:
    if not library_path.exists():
        return {"schemaVersion": "live-pilot/reference-library.v1", "entries": {}}
    with library_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_reference(
    reference: Optional[str],
    reference_key: Optional[str],
    library_path: Path = REFERENCE_LIBRARY_PATH,
) -> dict:
    if reference:
        return {"path": str(Path(reference).expanduser()), "lufs": None, "key": None}

    library = load_reference_library(library_path)
    entries = library.get("entries", {})
    if not reference_key or reference_key not in entries:
        available = ", ".join(sorted(entries)) or "none registered"
        raise ComparisonSetupError(
            f"Unknown reference key {reference_key!r}. Available keys: {available}."
        )

    entry = entries[reference_key]
    return {
        "path": str(Path(entry["path"]).expanduser()),
        "lufs": entry.get("lufs"),
        "key": reference_key,
        "title": entry.get("title"),
        "artist": entry.get("artist"),
    }


def _validate_reference_path(reference_path: str) -> Path:
    path = Path(reference_path).expanduser()
    if not path.exists():
        raise ComparisonSetupError(f"Reference file does not exist: {path}")
    if path.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_AUDIO_EXTENSIONS))
        raise ComparisonSetupError(f"Unsupported reference type {path.suffix!r}; use {allowed}.")
    return path


def _measure_user_track_lufs(
    bridge: AbletonBridgeClient,
    track_index: int,
    measure_func: Callable[[str], float],
) -> tuple[float, Optional[str], List[str]]:
    warnings: List[str] = []
    try:
        user_audio_path = bridge.get_clip_audio_path(track_index, 0)
        return measure_func(user_audio_path), user_audio_path, warnings
    except ComparisonSetupError as exc:
        warnings.append(
            "Direct user clip measurement unavailable; trying Waves WLM Plus fallback. "
            f"Reason: {exc}"
        )

    return _measure_user_track_with_wlm(bridge, track_index), None, warnings


def _measure_user_track_with_wlm(bridge: AbletonBridgeClient, track_index: int) -> float:
    bridge.execute(
        "add_plugin_to_track",
        {"track_index": track_index, "plugin_name": "Waves WLM Plus", "position": -1},
    )
    bridge.execute("play", {})
    time.sleep(6)

    devices = bridge.execute("get_track_devices", {"track_index": track_index})
    _require_success(devices, f"read devices on track {track_index}")
    device_names = devices.get("devices", [])
    device_index = next(
        (i for i, name in enumerate(device_names) if "wlm" in str(name).lower()),
        len(device_names) - 1,
    )

    params = bridge.execute(
        "get_device_parameters",
        {"track_index": track_index, "device_index": device_index},
    )
    _require_success(params, f"read WLM Plus parameters on track {track_index}")
    names = params.get("names", [])
    param_index = next(
        (
            i
            for i, name in enumerate(names)
            if "short" in str(name).lower() and "lufs" in str(name).lower()
        ),
        None,
    )
    if param_index is None:
        raise ComparisonSetupError(
            "WLM Plus fallback could not find a short-term LUFS parameter."
        )

    value = bridge.execute(
        "get_device_parameter_value",
        {"track_index": track_index, "device_index": device_index, "param_index": param_index},
    )
    _require_success(value, "read WLM Plus short-term LUFS")
    if value.get("value") is None:
        raise ComparisonSetupError("WLM Plus returned no LUFS value.")
    return float(value["value"])


def _run_apply_vocal_preset(track_index: int) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(_REPO_ROOT / "scripts" / "apply_vocal_preset.py"),
            "--style",
            "cla_modern_pop",
            "--track",
            str(track_index),
        ],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ComparisonSetupError(
            f"apply_vocal_preset.py failed for track {track_index}: {result.stderr or result.stdout}"
        )


def _setup_doubles(
    bridge: AbletonBridgeClient,
    user_audio_path: str,
    warnings: List[str],
) -> List[dict]:
    doubles = [
        {"name": "MY VOX (Double L)", "pan": -0.30, "detune": 5.0},
        {"name": "MY VOX (Double R)", "pan": 0.30, "detune": -5.0},
    ]
    created = []
    for spec in doubles:
        track_index = bridge.create_audio_track(spec["name"])
        bridge.set_clip_path(track_index, 0, user_audio_path)
        bridge.set_track_pan(track_index, spec["pan"])
        detune = bridge.set_clip_detune(track_index, 0, spec["detune"])
        if not detune.get("success"):
            warnings.append(
                f"Clip detune for {spec['name']} was not applied: "
                f"{detune.get('message') or detune.get('error') or 'bridge function unavailable'}"
            )
        bridge.add_utility_device(track_index, -7.0, "DOUBLE LEVEL (-7 dB)")
        _run_apply_vocal_preset(track_index)
        created.append({"track_index": track_index, **spec})
    return created


def setup_comparison(
    reference_path: str,
    my_vocal_track: int,
    simulate_doubles: bool = False,
    reference_lufs: Optional[float] = None,
    target_lufs: float = DEFAULT_TARGET_LUFS,
    bridge: Optional[AbletonBridgeClient] = None,
    measure_func: Callable[[str], float] = measure_lufs,
) -> dict:
    reference = _validate_reference_path(reference_path)
    bridge = bridge or AbletonBridgeClient()
    warnings: List[str] = []

    ref_lufs = float(reference_lufs) if reference_lufs is not None else measure_func(str(reference))
    user_lufs, user_audio_path, user_warnings = _measure_user_track_lufs(
        bridge, my_vocal_track, measure_func
    )
    warnings.extend(user_warnings)

    user_gain_db = target_lufs - user_lufs
    reference_gain_db = target_lufs - ref_lufs

    ref_track_name = f"REF: {reference.name}"
    ref_track = bridge.create_audio_track(ref_track_name)
    bridge.set_clip_path(ref_track, 0, str(reference))
    bridge.add_utility_device(
        my_vocal_track,
        user_gain_db,
        "LOUDNESS-MATCH (do not adjust)",
    )
    bridge.add_utility_device(
        ref_track,
        reference_gain_db,
        "REF LOUDNESS-MATCH (do not adjust)",
    )
    try:
        bridge.solo_track(my_vocal_track, True)
    except ComparisonSetupError as exc:
        warnings.append(f"Could not pre-solo user vocal track: {exc}")

    doubles = []
    if simulate_doubles:
        if not user_audio_path:
            raise ComparisonSetupError(
                "--simulate-doubles requires direct access to the user's clip audio path."
            )
        doubles = _setup_doubles(bridge, user_audio_path, warnings)

    return {
        "reference_path": str(reference),
        "reference_track": ref_track,
        "reference_gain_db": reference_gain_db,
        "reference_lufs": ref_lufs,
        "my_vocal_track": my_vocal_track,
        "my_vocal_lufs": user_lufs,
        "my_vocal_gain_db": user_gain_db,
        "target_lufs": target_lufs,
        "doubles": doubles,
        "warnings": warnings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Set up deterministic loudness-matched A/B comparison in Ableton.",
        epilog=(
            "The user's vocal is measured from clip audio via get_clip_audio_path when "
            "available. If there are multiple clips or no backing file, the command "
            "falls back to Waves WLM Plus short-term LUFS over the current loop."
        ),
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--reference", help="Local reference audio file (.wav, .mp3, .flac, .m4a)")
    source.add_argument("--reference-key", help="Slug from config/reference_library.json")
    parser.add_argument("--my-vocal-track", type=int, required=True, help="0-based Ableton track index")
    parser.add_argument("--simulate-doubles", action="store_true", help="Create cheap L/R fake doubles")
    parser.add_argument("--target-lufs", type=float, default=DEFAULT_TARGET_LUFS,
                        help="Common playback target loudness; default: -10 LUFS")
    parser.add_argument("--library", default=str(REFERENCE_LIBRARY_PATH),
                        help=argparse.SUPPRESS)
    return parser


def _print_summary(summary: dict) -> None:
    ref_name = Path(summary["reference_path"]).name
    print("Comparison setup complete.")
    print(
        f"  Reference:   {ref_name} -> track {summary['reference_track']}, "
        f"gain {summary['reference_gain_db']:+.1f} dB -> "
        f"loudness-matched at {summary['target_lufs']:.0f} LUFS"
    )
    print(
        f"  My vocal:    track {summary['my_vocal_track']} -> "
        f"loudness-match utility added ({summary['my_vocal_gain_db']:+.1f} dB)"
    )
    print(f"  Doubles:     {'yes' if summary['doubles'] else 'no'}")
    for warning in summary["warnings"]:
        print(f"  Warning:     {warning}")
    print("To A/B: alt+click solo on either track to toggle exclusive.")


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        resolved = resolve_reference(
            args.reference,
            args.reference_key,
            Path(args.library),
        )
        summary = setup_comparison(
            resolved["path"],
            args.my_vocal_track,
            simulate_doubles=args.simulate_doubles,
            reference_lufs=resolved.get("lufs"),
            target_lufs=args.target_lufs,
        )
    except ComparisonSetupError as exc:
        parser.exit(2, f"ERROR: {exc}\n")

    _print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
