"""
Crash-focused test: AbletonOSC query + safe parameter set

Goal:
- Verify AbletonOSC replies are being received on port 11001
- Verify we can fetch device param min/max
- Verify we can safely set parameters (clamped) without triggering AbletonOSC "Invalid value" errors

Prereqs:
- Ableton Live running
- AbletonOSC control surface enabled (port 11000, response port 11001)
- JarvisDeviceLoader control surface enabled (port 11002) for device loading
"""

import time
from ableton_controls import ableton
from discovery.vst_discovery import get_vst_discovery


def main():
    track_index = 0  # Track 1

    print("=== AbletonOSC connection test ===")
    if not ableton.test_connection():
        print("FAIL: AbletonOSC not reachable on port 11000")
        return
    print("OK: AbletonOSC message send works (no guarantee of replies yet).")

    print("\n=== Query num devices (sync) ===")
    nd0 = ableton.get_num_devices_sync(track_index, timeout=2.0)
    print(nd0)
    if not nd0.get("success"):
        print("FAIL: No response on port 11001. Check AbletonOSC response port configuration.")
        return

    print("\n=== Load EQ Eight via JarvisDeviceLoader ===")
    vst = get_vst_discovery()
    load = vst.load_device_on_track(track_index, "EQ Eight", -1)
    print(load)
    if not load.get("success"):
        print("FAIL: Could not load EQ Eight. Check JarvisDeviceLoader is selected in Ableton preferences.")
        return

    time.sleep(2.0)

    nd1 = ableton.get_num_devices_sync(track_index, timeout=2.0)
    print("\n=== Query num devices (after load) ===")
    print(nd1)
    if not nd1.get("success") or nd1.get("count", 0) <= 0:
        print("FAIL: Unexpected device count after load.")
        return

    device_index = nd1["count"] - 1
    print(f"\nAssuming newly loaded device index is {device_index}")

    print("\n=== Fetch param min/max (sync) ===")
    mm = ableton.get_device_parameters_minmax_sync(track_index, device_index, timeout=3.0)
    print({k: (len(v) if isinstance(v, list) else v) for k, v in mm.items()})
    if not mm.get("success"):
        print("FAIL: Could not fetch min/max.")
        return

    mins = mm["mins"]
    maxs = mm["maxs"]
    n = min(len(mins), len(maxs))
    print(f"Param count (min(len(mins), len(maxs))): {n}")

    print("\n=== Safe-set stress test (should clamp and NOT crash Ableton) ===")
    # Try the first few parameters with obviously out-of-range values
    for p in range(min(10, n)):
        target_high = maxs[p] + 9999.0
        target_low = mins[p] - 9999.0

        r1 = ableton.safe_set_device_parameter(track_index, device_index, p, target_high)
        r2 = ableton.safe_set_device_parameter(track_index, device_index, p, target_low)

        print(f"param {p}: hi -> sent={r1.get('sent_value')} clamped={r1.get('clamped')} range=({r1.get('min')},{r1.get('max')})")
        print(f"param {p}: lo -> sent={r2.get('sent_value')} clamped={r2.get('clamped')} range=({r2.get('min')},{r2.get('max')})")

        time.sleep(0.05)

    print("\nDONE. If Ableton stayed open and AbletonOSC logs show no 'Invalid value' errors, this passes.")


if __name__ == "__main__":
    main()








