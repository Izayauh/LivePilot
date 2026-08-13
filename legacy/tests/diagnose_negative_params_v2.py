"""
Diagnostic Script v2 - Test if writes actually work visually

This time we'll:
1. Set parameter to different values using HUMAN values (dB)
2. Pause so you can visually verify in Ableton
3. Try raw OSC sends without any transformation

Run with:
    python tests/diagnose_negative_params_v2.py
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ableton_controls import ableton
from ableton_controls.reliable_params import ReliableParameterController


def test_raw_osc_writes():
    """Test raw OSC writes to see what actually works"""
    
    print("\n" + "=" * 70)
    print("NEGATIVE PARAMETER RAW OSC TEST")
    print("=" * 70)
    
    # Test connection
    print("\nTesting OSC connection...")
    if not ableton.test_connection():
        print("❌ OSC connection failed!")
        return 1
    print("✓ OSC connection OK\n")
    
    reliable = ReliableParameterController(ableton, verbose=True)
    track = 0
    
    # Load Saturator
    print("Loading Saturator...")
    load_result = reliable.load_device_verified(track, "Saturator", position=-1)
    if not load_result.get("success"):
        print(f"Failed to load: {load_result}")
        return 1
    
    device_idx = load_result["device_index"]
    print(f"Device at index {device_idx}")
    
    # Wait for ready
    reliable.wait_for_device_ready(track, device_idx)
    
    # Get Output parameter info
    param_idx = reliable.find_parameter_index(track, device_idx, "Output")
    print(f"\nOutput parameter at index {param_idx}")
    
    # Get reported range
    info = reliable.get_device_info(track, device_idx)
    pmin = info.param_mins[param_idx]  # -36.0
    pmax = info.param_maxs[param_idx]  # 0.0
    print(f"Reported range: [{pmin}, {pmax}]")
    
    # Test 1: Try sending the actual dB value (not normalized)
    print("\n" + "=" * 60)
    print("TEST 1: Send actual dB value (-18.0) directly")
    print("=" * 60)
    print("Watch Ableton's Saturator Output knob...")
    
    # Send -18.0 dB directly (maybe it wants dB, not normalized?)
    ableton.client.send_message("/live/device/set/parameter/value", 
                                [track, device_idx, param_idx, -18.0])
    time.sleep(1.0)
    
    readback = reliable.get_parameter_value_sync(track, device_idx, param_idx)
    print(f"Sent: -18.0 dB → Readback: {readback}")
    input("Press Enter to continue...")
    
    # Test 2: Try with normalized 0.5
    print("\n" + "=" * 60)
    print("TEST 2: Send normalized 0.5")
    print("=" * 60)
    
    ableton.client.send_message("/live/device/set/parameter/value", 
                                [track, device_idx, param_idx, 0.5])
    time.sleep(1.0)
    
    readback = reliable.get_parameter_value_sync(track, device_idx, param_idx)
    print(f"Sent: 0.5 → Readback: {readback}")
    input("Press Enter to continue...")
    
    # Test 3: Try with inverted normalized (1.0 - 0.5 = 0.5 for mid)
    # Actually let's try 0.0833 which should map to -3.0 dB if inverted
    # -3.0 dB: normalized = (-3.0 - (-36.0)) / (0.0 - (-36.0)) = 33/36 = 0.916667
    # inverted = 1.0 - 0.916667 = 0.083333
    print("\n" + "=" * 60)
    print("TEST 3: Send inverted normalized (0.083 for -3 dB)")
    print("=" * 60)
    
    ableton.client.send_message("/live/device/set/parameter/value", 
                                [track, device_idx, param_idx, 0.083333])
    time.sleep(1.0)
    
    readback = reliable.get_parameter_value_sync(track, device_idx, param_idx)
    print(f"Sent: 0.083333 → Readback: {readback}")
    
    # Convert readback to dB
    if readback is not None:
        # Standard: dB = min + readback * (max - min)
        db_standard = pmin + readback * (pmax - pmin)
        print(f"  Standard denorm: {db_standard:.2f} dB")
        
        # Inverted: dB = min + (1 - readback) * (max - min)
        db_inverted = pmin + (1.0 - readback) * (pmax - pmin)
        print(f"  Inverted denorm: {db_inverted:.2f} dB")
    
    input("Press Enter to continue...")
    
    # Test 4: Get current value directly and try setting it
    print("\n" + "=" * 60)
    print("TEST 4: Read current, then set same value back")
    print("=" * 60)
    
    # First, manually move the Output knob in Ableton
    print("MANUALLY move the Saturator Output knob in Ableton to somewhere in the middle.")
    input("Press Enter when done...")
    
    current = reliable.get_parameter_value_sync(track, device_idx, param_idx)
    print(f"Current readback (after manual change): {current}")
    
    if current is not None:
        db_val = pmin + current * (pmax - pmin)
        print(f"  This is: {db_val:.2f} dB")
    
    # Now try setting it to something else
    print("\nNow I'll try to set it to a different value...")
    ableton.client.send_message("/live/device/set/parameter/value", 
                                [track, device_idx, param_idx, 0.75])
    time.sleep(0.5)
    
    new_readback = reliable.get_parameter_value_sync(track, device_idx, param_idx)
    print(f"Sent: 0.75 → Readback: {new_readback}")
    print("Did the knob move in Ableton? (Check visually)")
    
    input("Press Enter to finish...")
    
    return 0


if __name__ == "__main__":
    sys.exit(test_raw_osc_writes())

