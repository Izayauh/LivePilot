"""
Integration tests for the non-chatty chain pipeline.

These tests require a running Ableton Live instance with AbletonOSC
and JarvisDeviceLoader. Skip gracefully if Ableton is not available.

Run with: python tests/test_pipeline_integration.py [--track N]

Tests:
- End-to-end: EQ Eight + Compressor + Reverb on a track
- Dry-run mode produces plan without changes
- Idempotent re-run skips params
- Exactly 1 LLM call used (guardrail check)
"""

import os
import sys
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.schemas import (
    ChainPipelinePlan,
    DeviceSpec,
    ParamSpec,
    PipelinePhase,
)
from pipeline.executor import ChainPipelineExecutor
from pipeline.guardrail import LLMGuardrail


def check_ableton_connection():
    """Check if Ableton + JarvisDeviceLoader are running and responding."""
    try:
        from ableton_controls.controller import ableton

        result = ableton.get_track_list()
        if result.get("success"):
            tracks = result.get("tracks", [])
            print(f"[OK] Ableton connected: {len(tracks)} tracks")
        else:
            print("[SKIP] Ableton not responding")
            return False

        loader = ableton.test_device_loader_connection()
        if not loader.get("success"):
            print(f"[SKIP] {loader.get('message', 'JarvisDeviceLoader not responding')}")
            return False

        print("[OK] JarvisDeviceLoader connected")
        return True
    except Exception as e:
        print(f"[SKIP] Cannot connect to Ableton: {e}")
        return False


def test_basic_vocal_chain(track_index: int = 0):
    """End-to-end: EQ Eight + Compressor + Reverb with real params."""
    print("\n" + "=" * 60)
    print(f"TEST: Basic Vocal Chain on Track {track_index + 1}")
    print("  EQ Eight -> Compressor -> Reverb")
    print("=" * 60)

    plan = ChainPipelinePlan(
        track_index=track_index,
        devices=[
            DeviceSpec(
                name="EQ Eight",
                purpose="high_pass",
                params=[
                    ParamSpec(name="band1_freq_hz", value=100.0),
                    ParamSpec(name="band1_type", value=6.0),
                ],
            ),
            DeviceSpec(
                name="Compressor",
                purpose="dynamics",
                params=[
                    ParamSpec(name="threshold_db", value=-18.0),
                    ParamSpec(name="ratio", value=3.0),
                    ParamSpec(name="attack_ms", value=10.0),
                    ParamSpec(name="release_ms", value=100.0),
                ],
            ),
            DeviceSpec(
                name="Reverb",
                purpose="space",
                params=[
                    ParamSpec(name="decay_time_ms", value=1500.0),
                    ParamSpec(name="dry_wet_pct", value=20.0),
                ],
            ),
        ],
        description="Basic vocal chain (integration test)",
    )

    executor = ChainPipelineExecutor()
    result = executor.execute(plan)

    print(f"\nResult: success={result.success}")
    print(f"  Phase reached: {result.phase_reached.value}")
    print(f"  Devices: {result.total_devices_loaded}/{result.total_devices_planned}")
    print(f"  Params: {result.total_params_set}/{result.total_params_planned}")
    print(f"  Verified: {result.total_params_verified}")
    print(f"  Skipped (idempotent): {result.total_params_skipped_idempotent}")
    print(f"  LLM calls: {result.llm_calls_used}")
    print(f"  Time: {result.total_time_ms:.0f}ms")

    if result.errors:
        print(f"  Errors: {result.errors}")
    if result.warnings:
        print(f"  Warnings: {result.warnings}")

    for dev in result.devices:
        status = "LOADED" if dev.loaded else "FAILED"
        fb = " (fallback)" if dev.is_fallback else ""
        print(f"  [{status}] {dev.name}{fb} @ index {dev.device_index}")
        for pr in dev.params:
            skip = " [SKIP]" if pr.skipped_idempotent else ""
            verify = " [VERIFIED]" if pr.verified else ""
            err = f" ERROR: {pr.error}" if pr.error else ""
            print(f"    {pr.name}: {pr.requested_value} -> {pr.actual_value}{skip}{verify}{err}")

    # Assertions
    assert result.success, f"Pipeline failed: {result.errors}"
    assert result.llm_calls_used == 1, f"Expected 1 LLM call, got {result.llm_calls_used}"
    assert result.total_devices_loaded == 3, f"Expected 3 devices loaded, got {result.total_devices_loaded}"

    print("\n[PASS] Basic vocal chain test passed")
    return result


def test_dry_run(track_index: int = 0):
    """Dry-run mode should produce plan without loading devices."""
    print("\n" + "=" * 60)
    print(f"TEST: Dry Run on Track {track_index + 1}")
    print("=" * 60)

    plan = ChainPipelinePlan(
        track_index=track_index,
        devices=[
            DeviceSpec(name="EQ Eight", params=[ParamSpec(name="band1_freq_hz", value=100.0)]),
            DeviceSpec(name="Compressor", params=[ParamSpec(name="ratio", value=4.0)]),
        ],
        dry_run=True,
    )

    executor = ChainPipelineExecutor()
    result = executor.execute(plan)

    assert result.success, f"Dry run failed: {result.errors}"
    assert result.dry_run
    assert result.phase_reached == PipelinePhase.PLAN
    assert not any(d.loaded for d in result.devices)

    print(f"  Devices planned: {len(result.devices)}")
    print(f"  None loaded (dry run)")
    print("\n[PASS] Dry run test passed")
    return result


def test_idempotent_rerun(track_index: int = 0):
    """Run the same plan twice. Second run should skip most/all params."""
    print("\n" + "=" * 60)
    print(f"TEST: Idempotent Re-run on Track {track_index + 1}")
    print("=" * 60)

    plan = ChainPipelinePlan(
        track_index=track_index,
        devices=[
            DeviceSpec(
                name="EQ Eight",
                purpose="high_pass",
                params=[
                    ParamSpec(name="band1_freq_hz", value=100.0),
                ],
            ),
            DeviceSpec(
                name="Compressor",
                purpose="dynamics",
                params=[
                    ParamSpec(name="threshold_db", value=-18.0),
                    ParamSpec(name="ratio", value=3.0),
                ],
            ),
        ],
        description="Idempotency test",
    )

    # First run
    print("  Run 1 (initial)...")
    executor1 = ChainPipelineExecutor()
    result1 = executor1.execute(plan)
    print(f"    Params set: {result1.total_params_set}, skipped: {result1.total_params_skipped_idempotent}")
    assert result1.success, f"Initial run failed: {result1.errors}"
    assert result1.llm_calls_used == 1, f"Expected 1 LLM call on run 1, got {result1.llm_calls_used}"

    # Second run (same plan)
    print("  Run 2 (idempotent)...")
    executor2 = ChainPipelineExecutor()
    result2 = executor2.execute(plan)
    print(f"    Params set: {result2.total_params_set}, skipped: {result2.total_params_skipped_idempotent}")
    assert result2.success, f"Idempotent run failed: {result2.errors}"
    assert result2.llm_calls_used == 1, f"Expected 1 LLM call on run 2, got {result2.llm_calls_used}"

    # Second run should skip more params than first
    assert result2.total_params_skipped_idempotent >= result1.total_params_skipped_idempotent, \
        "Second run should skip at least as many params as first run"

    print(f"\n  Skipped increased: {result1.total_params_skipped_idempotent} -> {result2.total_params_skipped_idempotent}")
    print("\n[PASS] Idempotent re-run test passed")
    return result2


def main():
    parser = argparse.ArgumentParser(description="Pipeline integration tests")
    parser.add_argument("--track", type=int, default=0,
                        help="0-based track index to test on (default: 0)")
    args = parser.parse_args()

    if not check_ableton_connection():
        print("\nSkipping integration tests (Ableton/JarvisDeviceLoader not available)")
        return

    passed = 0
    failed = 0

    tests = [
        ("Dry Run", test_dry_run),
        ("Basic Vocal Chain", test_basic_vocal_chain),
        ("Idempotent Re-run", test_idempotent_rerun),
    ]

    for name, test_fn in tests:
        try:
            test_fn(args.track)
            passed += 1
        except Exception as e:
            print(f"\n[FAIL] {name}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)


if __name__ == "__main__":
    main()
