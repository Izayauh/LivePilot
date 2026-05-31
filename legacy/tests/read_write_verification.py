"""
Read-Write Verification Test Script

Tests the closed-loop parameter setting system:
  1. Send a normalized value to Ableton.
  2. Read back the display string (e.g., "500 Hz").
  3. Iterate until the readback matches the target.

Usage:
    python tests/read_write_verification.py --track 0
    python tests/read_write_verification.py --track 0 --device 0 --param 1 --target 500
"""

import argparse
import json
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ableton_controls.controller import AbletonController
from ableton_controls.reliable_params import ReliableParameterController


def print_banner(text: str):
    width = 60
    print("\n" + "=" * width)
    print(f"  {text}")
    print("=" * width)


def print_result(result: dict):
    success = result.get("success", False)
    icon = "✅" if success else "❌"
    print(f"\n{icon} Result:")
    print(f"  Target:          {result.get('target_value')}")
    print(f"  Actual Display:  {result.get('actual_display')}")
    print(f"  Actual Parsed:   {result.get('actual_base_value')}")
    print(f"  Final Normalized:{result.get('final_normalized')}")
    print(f"  Iterations:      {result.get('iterations')}")
    print(f"  Method:          {result.get('method')}")
    print(f"  Message:         {result.get('message')}")


def test_single_parameter(reliable, track, device, param_idx, target_value):
    """Test a single parameter with the readback loop."""
    print_banner(f"Testing: Track {track}, Device {device}, Param {param_idx} -> {target_value}")

    result = reliable.set_parameter_with_readback(
        track_index=track,
        device_index=device,
        param_index=param_idx,
        target_display_value=target_value,
        max_iterations=5,
        tolerance_pct=5.0,
        auto_calibrate=True,
    )
    print_result(result)
    return result


def test_eq_eight_frequency(reliable, track, device):
    """Test EQ Eight frequency parameters — the classic logarithmic challenge."""
    print_banner("EQ Eight Frequency Test Suite")

    # Param index 1 = "1 Frequency A" on EQ Eight
    targets = [100, 500, 1000, 5000, 10000]
    results = []
    for hz in targets:
        result = reliable.set_parameter_with_readback(
            track_index=track,
            device_index=device,
            param_index=1,  # 1 Frequency A
            target_display_value=hz,
            max_iterations=5,
            tolerance_pct=5.0,
        )
        print_result(result)
        results.append(result)
        time.sleep(0.3)

    successes = sum(1 for r in results if r["success"])
    total = len(results)
    print(f"\n📊 EQ Frequency Results: {successes}/{total} passed")
    return results


def test_compressor_params(reliable, track, device):
    """Test Compressor threshold and ratio — nonlinear parameters."""
    print_banner("Compressor Parameter Test Suite")
    
    tests = [
        (1, -20.0, "Threshold"),   # Param index 1 = Threshold
        (4, 4.0,   "Ratio"),       # Param index 4 = Ratio
    ]
    results = []
    for param_idx, target, name in tests:
        print(f"\n--- Testing {name} (param {param_idx}) -> {target} ---")
        result = reliable.set_parameter_with_readback(
            track_index=track,
            device_index=device,
            param_index=param_idx,
            target_display_value=target,
            max_iterations=5,
        )
        print_result(result)
        results.append(result)
        time.sleep(0.3)

    successes = sum(1 for r in results if r["success"])
    print(f"\n📊 Compressor Results: {successes}/{len(results)} passed")
    return results


def discover_and_test(reliable, track):
    """Discover all devices on a track and test key parameters."""
    print_banner(f"Device Discovery on Track {track}")

    from ableton_controls.controller import AbletonController
    ableton = reliable.ableton

    devices_result = ableton.get_track_devices_sync(track)
    if not devices_result.get("success"):
        print("❌ Could not get devices. Is Ableton running with AbletonOSC?")
        return

    devices = devices_result.get("devices", [])
    print(f"Found {len(devices)} devices: {devices}")

    # Known test targets per device type
    DEVICE_TESTS = {
        "EQ Eight": [(1, 500, "1 Frequency A"), (2, -3.0, "1 Gain A")],
        "Compressor": [(1, -20.0, "Threshold"), (4, 4.0, "Ratio")],
        "Reverb": [(4, 2000, "Decay Time")],
        "Delay": [(2, 300, "L Time")],
        "Utility": [(3, -6.0, "Gain")],
    }

    all_results = []
    for dev_idx, dev_name in enumerate(devices):
        if dev_name in DEVICE_TESTS:
            print(f"\n--- Testing {dev_name} (device {dev_idx}) ---")
            for param_idx, target, param_label in DEVICE_TESTS[dev_name]:
                print(f"  Setting {param_label} to {target}...")
                result = reliable.set_parameter_with_readback(
                    track_index=track,
                    device_index=dev_idx,
                    param_index=param_idx,
                    target_display_value=target,
                )
                print_result(result)
                all_results.append({
                    "device": dev_name,
                    "param": param_label,
                    "target": target,
                    **result,
                })
                time.sleep(0.3)

    # Summary
    successes = sum(1 for r in all_results if r["success"])
    total = len(all_results)
    print_banner(f"OVERALL: {successes}/{total} parameters set correctly")

    # Save report
    report_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "logs", "readwrite_verification_report.json"
    )
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"📄 Report saved to: {report_path}")


def main():
    parser = argparse.ArgumentParser(description="Read-Write Verification Loop Tester")
    parser.add_argument("--track", type=int, default=0, help="Track index (0-based)")
    parser.add_argument("--device", type=int, default=None, help="Device index (0-based)")
    parser.add_argument("--param", type=int, default=None, help="Parameter index (0-based)")
    parser.add_argument("--target", type=float, default=None, help="Target display value")
    parser.add_argument("--discover", action="store_true", help="Auto-discover and test all devices")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    print_banner("Read-Write Verification Loop")
    print(f"Connecting to AbletonOSC on 127.0.0.1:11000...")

    ableton = AbletonController()
    reliable = ReliableParameterController(ableton, verbose=args.verbose)

    # Test connection
    if not ableton.test_connection():
        print("❌ Cannot connect to AbletonOSC. Is Ableton running?")
        sys.exit(1)
    print("✅ Connected to AbletonOSC")

    if args.discover:
        discover_and_test(reliable, args.track)
    elif args.device is not None and args.param is not None and args.target is not None:
        test_single_parameter(reliable, args.track, args.device, args.param, args.target)
    else:
        print("\nNo specific test specified. Running default test suite...")
        print("Use --discover for auto-discovery, or --device/--param/--target for specific test.\n")

        # Default: try EQ Eight on device 0
        info = reliable.get_device_info(args.track, 0)
        if info:
            print(f"Device 0: {info.device_name}")
            if "EQ" in info.device_name:
                test_eq_eight_frequency(reliable, args.track, 0)
            elif "Compressor" in info.device_name.lower():
                test_compressor_params(reliable, args.track, 0)
            else:
                print(f"Unknown device type: {info.device_name}")
                print("Use --discover for full auto-discovery.")
        else:
            print("Could not get device info. Use --discover to scan track.")


if __name__ == "__main__":
    main()
