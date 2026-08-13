"""
Diagnostic script for problematic parameters.

Specifically tests Saturator Output and Glue Compressor Threshold
to understand why they reject normalized values.
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ableton_controls import ableton
from ableton_controls.reliable_params import ReliableParameterController

def diagnose_parameter(reliable, track_idx, device_name, param_name, test_values):
    """Diagnose a single problematic parameter"""
    
    print(f"\n{'='*70}")
    print(f"DIAGNOSING: {device_name} / {param_name}")
    print(f"{'='*70}\n")
    
    # Load device
    load_result = reliable.load_device_verified(track_idx, device_name, timeout=5.0)
    
    if not load_result.get("success"):
        print(f"❌ Failed to load {device_name}")
        return
    
    device_idx = load_result["device_index"]
    print(f"✅ Device loaded at index {device_idx}")
    
    # Wait for ready
    if not reliable.wait_for_device_ready(track_idx, device_idx):
        print("❌ Device not ready")
        return
    
    # Get parameter info
    info = reliable.get_device_info(track_idx, device_idx)
    param_idx = reliable.find_parameter_index(track_idx, device_idx, param_name)
    
    if param_idx is None:
        print(f"❌ Parameter '{param_name}' not found")
        return
    
    print(f"✅ Parameter found at index {param_idx}")
    print(f"   Range from OSC: {info.param_mins[param_idx]} to {info.param_maxs[param_idx]}")
    
    pmin, pmax = info.param_mins[param_idx], info.param_maxs[param_idx]
    
    print(f"\n--- Testing different approaches ---\n")
    
    for test_val in test_values:
        print(f"\n🧪 Test: Trying to set {param_name} = {test_val}")
        
        # Approach 1: Try with normalized value (current approach)
        print(f"\n  Approach 1: Send NORMALIZED value")
        normalized = (test_val - pmin) / (pmax - pmin) if pmax != pmin else 0.0
        print(f"    Calculated normalized: {normalized:.6f}")
        
        result = ableton.set_device_parameter(track_idx, device_idx, param_idx, normalized)
        time.sleep(0.2)
        
        readback = reliable.get_parameter_value_sync(track_idx, device_idx, param_idx)
        if readback is not None:
            readback_human = pmin + (readback * (pmax - pmin))
            print(f"    ✓ Set command: {result.get('success')}")
            print(f"    📊 Readback normalized: {readback:.6f}")
            print(f"    📊 Readback human units: {readback_human:.2f}")
            if abs(readback - normalized) < 0.01:
                print(f"    ✅ SUCCESS - Value matched!")
            else:
                print(f"    ❌ FAILED - Readback doesn't match (diff={abs(readback - normalized):.6f})")
        
        time.sleep(0.3)
        
        # Approach 2: Try with DENORMALIZED value (direct human value)
        print(f"\n  Approach 2: Send DENORMALIZED (raw human) value")
        print(f"    Sending raw value: {test_val}")
        
        result = ableton.set_device_parameter(track_idx, device_idx, param_idx, test_val)
        time.sleep(0.2)
        
        readback = reliable.get_parameter_value_sync(track_idx, device_idx, param_idx)
        if readback is not None:
            readback_human = pmin + (readback * (pmax - pmin))
            print(f"    ✓ Set command: {result.get('success')}")
            print(f"    📊 Readback normalized: {readback:.6f}")
            print(f"    📊 Readback human units: {readback_human:.2f}")
            if abs(readback_human - test_val) < 1.0:
                print(f"    ✅ SUCCESS - Value matched!")
            else:
                print(f"    ❌ FAILED - Readback doesn't match (diff={abs(readback_human - test_val):.2f})")
        
        time.sleep(0.3)
        
        # Approach 3: Try setting to 0.0 first, then the target
        print(f"\n  Approach 3: Reset to min first, then set target")
        
        # Reset to minimum
        ableton.set_device_parameter(track_idx, device_idx, param_idx, 0.0)
        time.sleep(0.2)
        
        # Now set target
        ableton.set_device_parameter(track_idx, device_idx, param_idx, normalized)
        time.sleep(0.2)
        
        readback = reliable.get_parameter_value_sync(track_idx, device_idx, param_idx)
        if readback is not None:
            readback_human = pmin + (readback * (pmax - pmin))
            print(f"    📊 Readback normalized: {readback:.6f}")
            print(f"    📊 Readback human units: {readback_human:.2f}")
            if abs(readback - normalized) < 0.01:
                print(f"    ✅ SUCCESS - Value matched!")
            else:
                print(f"    ❌ FAILED - Readback doesn't match")

def main():
    """Run diagnostics on problematic parameters"""
    
    print("\n" + "="*70)
    print("PARAMETER DIAGNOSIS - Problem Parameters")
    print("="*70)
    
    # Test connection
    if not ableton.test_connection():
        print("❌ OSC connection failed!")
        return
    
    print("✅ OSC connection OK\n")
    
    reliable = ReliableParameterController(ableton, verbose=False)
    track_idx = 0
    
    # Test Saturator Output
    diagnose_parameter(
        reliable, track_idx, 
        "Saturator", "Output",
        [-3.0, -6.0, -12.0, 0.0]
    )
    
    time.sleep(1.0)
    
    # Test Glue Compressor Threshold
    diagnose_parameter(
        reliable, track_idx,
        "Glue Compressor", "Threshold",
        [-15.0, -20.0, -30.0, 0.0]
    )
    
    print("\n" + "="*70)
    print("DIAGNOSIS COMPLETE")
    print("="*70)

if __name__ == "__main__":
    main()

