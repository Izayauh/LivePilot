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
    resolve_track,
)
from analysis.spectral import analyze, compare, format_report  # noqa: E402
from scripts import setup_comparison  # noqa: E402


DEFAULT_TARGET_LUFS = -18.0


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
        required=True,
        help='Input device name for loopback capture, e.g. "Loop-back 1/2"',
    )
    parser.add_argument("--capture-seconds", type=float, default=6.0)
    parser.add_argument("--target-lufs", type=float, default=DEFAULT_TARGET_LUFS)
    parser.add_argument("--sample-rate", type=int, default=48000)
    parser.add_argument("--channels", type=int, default=2)
    parser.add_argument("--output-dir", default=str(_REPO_ROOT / "logs"))
    return parser


def run(args: argparse.Namespace) -> tuple[str, Path]:
    bridge = setup_comparison.AbletonBridgeClient()
    reference_track = resolve_track(bridge, args.reference_track)
    user_track = resolve_track(bridge, args.my_vocal_group)

    reference_path = bridge.get_clip_audio_path(reference_track, 0)
    setup_comparison.setup_comparison(
        reference_path,
        my_vocal_track=user_track,
        reference_track=reference_track,
        target_lufs=args.target_lufs,
        bridge=bridge,
    )

    captured = capture_reference_and_user(
        bridge,
        reference_track=reference_track,
        user_track=user_track,
        capture_device=args.capture_device,
        capture_seconds=args.capture_seconds,
        sample_rate=args.sample_rate,
        channels=args.channels,
    )
    reference_report = analyze(captured.reference_audio, captured.sample_rate)
    user_report = analyze(captured.user_audio, captured.sample_rate)
    comparison = compare(
        user_report,
        reference_report,
        matched_lufs=args.target_lufs,
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
