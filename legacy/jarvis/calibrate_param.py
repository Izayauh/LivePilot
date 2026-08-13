#!/usr/bin/env python
"""
Auto-calibrate Ableton plugin parameters.

Sweep behavior:
  - Sends normalized values 0.0 .. 1.0 in 0.1 increments
  - Waits 50ms between each write/read cycle
  - Reads display strings (e.g. "-12 dB", "500 Hz")
  - Detects linear vs logarithmic relationship
  - Saves learned curves to config/calibration.json

Usage:
  python calibrate_param.py <track_index> <device_index>
  python calibrate_param.py <track_index> <device_index> --param-index 3
  python calibrate_param.py <track_index> <device_index> --param-index 3 --param-index 5
"""

from __future__ import annotations

import argparse
import json
import sys

from calibration_utils import CALIBRATION_DB_PATH, CalibrationSweeper


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auto-calibrate Ableton plugin parameters.")
    parser.add_argument("track_index", type=int, help="0-based track index")
    parser.add_argument("device_index", type=int, help="0-based device index on the track")
    parser.add_argument(
        "--param-index",
        type=int,
        action="append",
        default=None,
        help="Optional parameter index to calibrate (repeatable). If omitted, all params are swept.",
    )
    parser.add_argument(
        "--settle-ms",
        type=int,
        default=50,
        help="Delay between OSC write/read during sweep (default: 50)",
    )
    parser.add_argument(
        "--output",
        default=CALIBRATION_DB_PATH,
        help=f"Calibration database path (default: {CALIBRATION_DB_PATH})",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    from ableton_controls.controller import ableton

    sweeper = CalibrationSweeper(ableton, settle_ms=args.settle_ms)
    try:
        result = sweeper.sweep_and_save(
            track_index=args.track_index,
            device_index=args.device_index,
            param_indices=args.param_index,
            store_path=args.output,
        )
    except Exception as exc:
        print(f"[calibrate] failed: {exc}")
        return 1

    plugin_name = result.get("plugin_name", f"track{args.track_index}_device{args.device_index}")
    params = result.get("parameters", {})
    errors = result.get("errors", [])

    print(f"[calibrate] plugin: {plugin_name}")
    print(f"[calibrate] calibrated parameters: {len(params)}")
    print(f"[calibrate] errors: {len(errors)}")

    for param_name, curve in params.items():
        curve_model = curve.get("curve_model", "LINEAR")
        rng = curve.get("range", {})
        print(
            f"  - {param_name} [{curve.get('param_index')}] "
            f"{curve_model} range=({rng.get('min')} -> {rng.get('max')})"
        )

    if errors:
        print("[calibrate] failed parameters:")
        for err in errors:
            print(f"  - {json.dumps(err)}")

    print(f"[calibrate] wrote: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
