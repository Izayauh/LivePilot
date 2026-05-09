#!/usr/bin/env python3
"""Objective spectral comparison between a vocal stack and a reference."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from analysis.audio_capture import (  # noqa: E402
    AudioCaptureError,
    capture_reference_and_user,
    resolve_capture_device,
    resolve_track,
)
from analysis.spectral import analyze, compare, format_report  # noqa: E402
from scripts import setup_comparison  # noqa: E402


DEFAULT_SILENCE_THRESHOLD_DB = -60.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture and compare a vocal stack against a reference track."
    )
    parser.add_argument(
        "--reference-track",
        required=True,
        help="0-based Ableton track index or fuzzy name for the loaded reference track",
    )
    parser.add_argument(
        "--my-vocal-group",
        required=True,
        help="0-based Ableton track index or fuzzy name for the user's vocal group/stack",
    )
    parser.add_argument(
        "--capture-device",
        help=(
            "Input device name for loopback capture. Prefer --capture-device-index "
            "when multiple host APIs expose the same name."
        ),
    )
    parser.add_argument(
        "--capture-device-index",
        type=int,
        help="Exact sounddevice input index for loopback capture; overrides --capture-device",
    )
    parser.add_argument("--capture-seconds", type=float, default=6.0)
    parser.add_argument(
        "--target-lufs",
        type=float,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        help="Capture sample rate. Defaults to the selected device's reported sample rate.",
    )
    parser.add_argument("--channels", type=int, default=2)
    parser.add_argument(
        "--silence-threshold",
        type=float,
        default=DEFAULT_SILENCE_THRESHOLD_DB,
        help="Abort if either capture RMS is below this dBFS threshold; default: -60",
    )
    parser.add_argument("--output-dir", default=str(_REPO_ROOT / "logs"))
    return parser


def run(args: argparse.Namespace) -> tuple[str, Path]:
    bridge = setup_comparison.AbletonBridgeClient()
    reference_track = resolve_track(bridge, args.reference_track)
    user_track = resolve_track(bridge, args.my_vocal_group)
    capture_device = resolve_capture_device(
        capture_device=args.capture_device,
        capture_device_index=args.capture_device_index,
        sample_rate=args.sample_rate,
    )

    captured = capture_reference_and_user(
        bridge,
        reference_track=reference_track,
        user_track=user_track,
        capture_device=capture_device.device,
        capture_seconds=args.capture_seconds,
        sample_rate=capture_device.sample_rate,
        channels=args.channels,
        silence_threshold_db=args.silence_threshold,
    )
    reference_report = analyze(captured.reference_audio, captured.sample_rate)
    user_report = analyze(captured.user_audio, captured.sample_rate)
    comparison = compare(
        user_report,
        reference_report,
        matched_lufs=None,
        capture_seconds=args.capture_seconds,
    )

    output_path = _write_json_report(comparison, Path(args.output_dir))
    return format_report(comparison), output_path


def _write_json_report(comparison, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    safe_timestamp = timestamp.replace("+00:00", "Z").replace(":", "-")
    output_path = output_dir / f"spectral_compare_{safe_timestamp}.json"
    comparison.saved_to = str(output_path)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(comparison.to_dict(), f, indent=2)
        f.write("\n")
    return output_path


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report, _ = run(args)
    except (AudioCaptureError, setup_comparison.ComparisonSetupError, ValueError) as exc:
        parser.exit(2, f"ERROR: {exc}\n")

    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
