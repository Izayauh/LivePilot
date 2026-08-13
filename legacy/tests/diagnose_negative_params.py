"""
Diagnostic Script for Negative-Only Parameter Ranges

Investigates why parameters with negative-only ranges (min < 0, max = 0.0)
like Saturator/Output and Glue Compressor/Threshold are failing.

This script tests:
1. What min/max values are reported by OSC
2. What happens when we send 0.0, 0.5, and 1.0 normalized
3. Whether the normalization is inverted internally

Run with:
    python tests/diagnose_negative_params.py
"""

import sys
import os
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ableton_controls import ableton
from ableton_controls.reliable_params import ReliableParameterController


def log(msg: str, level: str = "INFO"):
    """Print log message with timestamp"""
    from datetime import datetime
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    prefix = {
        "INFO": "ℹ️",
        "WARN": "⚠️",
        "ERROR": "❌",
        "SUCCESS": "✅",
        "TEST": "🧪"
    }.get(level, "")
    print(f"[{timestamp}] {prefix} {msg}")


def diagnose_parameter(reliable: ReliableParameterController, 
                       track: int, device_idx: int,
                       param_name: str, device_name: str):
    """
    Diagnose a specific parameter's normalization behavior.
    
    Tests:
    1. Reported min/max from OSC
    2. Endpoint behavior (send 0.0, 1.0)
    3. Midpoint behavior (send 0.5)
    """
    print(f"\n{'='*60}")
    print(f"DIAGNOSING: {device_name} / {param_name}")
    print(f"{'='*60}")
    
    # Find parameter index
    param_idx = reliable.find_parameter_index(track, device_idx, param_name)
    if param_idx is None:
        log(f"Parameter '{param_name}' not found!", "ERROR")
        return None
    
    log(f"Parameter '{param_name}' at index {param_idx}")
    
    # Get reported range from cache
    info = reliable.get_device_info(track, device_idx)
    if not info:
        log("Could not get device info", "ERROR")
        return None
    
    reported_min = info.param_mins[param_idx]
    reported_max = info.param_maxs[param_idx]
    
    log(f"Reported range from OSC: min={reported_min}, max={reported_max}")
    
    # Check if it's a negative-only range
    is_negative_only = (reported_max <= 0 and reported_min < 0)
    log(f"Is negative-only range: {is_negative_only}")
    
    results = {
        "param_name": param_name,
        "param_index": param_idx,
        "reported_min": reported_min,
        "reported_max": reported_max,
        "is_negative_only": is_negative_only,
        "tests": []
    }
    
    # Test 1: Send 0.0 normalized
    print(f"\n--- Test 1: Send 0.0 normalized ---")
    ableton.set_device_parameter(track, device_idx, param_idx, 0.0)
    time.sleep(0.2)
    readback_0 = reliable.get_parameter_value_sync(track, device_idx, param_idx)
    log(f"Sent: 0.0 normalized → Readback: {readback_0}")
    
    # Denormalize to human value (using reported range)
    if readback_0 is not None:
        human_0 = reported_min + (readback_0 * (reported_max - reported_min))
        log(f"Denormalized (using reported range): {human_0:.2f}")
    
    results["tests"].append({
        "sent": 0.0,
        "readback_normalized": readback_0,
        "expected": "should be 0.0 if consistent"
    })
    
    # Test 2: Send 1.0 normalized
    print(f"\n--- Test 2: Send 1.0 normalized ---")
    ableton.set_device_parameter(track, device_idx, param_idx, 1.0)
    time.sleep(0.2)
    readback_1 = reliable.get_parameter_value_sync(track, device_idx, param_idx)
    log(f"Sent: 1.0 normalized → Readback: {readback_1}")
    
    if readback_1 is not None:
        human_1 = reported_min + (readback_1 * (reported_max - reported_min))
        log(f"Denormalized (using reported range): {human_1:.2f}")
    
    results["tests"].append({
        "sent": 1.0,
        "readback_normalized": readback_1,
        "expected": "should be 1.0 if consistent"
    })
    
    # Test 3: Send 0.5 normalized
    print(f"\n--- Test 3: Send 0.5 normalized ---")
    ableton.set_device_parameter(track, device_idx, param_idx, 0.5)
    time.sleep(0.2)
    readback_05 = reliable.get_parameter_value_sync(track, device_idx, param_idx)
    log(f"Sent: 0.5 normalized → Readback: {readback_05}")
    
    if readback_05 is not None:
        human_05 = reported_min + (readback_05 * (reported_max - reported_min))
        log(f"Denormalized (using reported range): {human_05:.2f}")
    
    results["tests"].append({
        "sent": 0.5,
        "readback_normalized": readback_05,
        "expected": "should be 0.5 if consistent"
    })
    
    # Analysis
    print(f"\n--- Analysis ---")
    
    if readback_0 is not None and readback_1 is not None:
        # Check if read/write is consistent
        if abs(readback_0 - 0.0) < 0.01 and abs(readback_1 - 1.0) < 0.01:
            log("Read/Write is CONSISTENT - values match what we sent", "SUCCESS")
            results["diagnosis"] = "consistent"
        elif abs(readback_0 - 1.0) < 0.01 and abs(readback_1 - 0.0) < 0.01:
            log("Read/Write is INVERTED - 0→1, 1→0", "WARN")
            results["diagnosis"] = "inverted"
        elif readback_0 == readback_1:
            log(f"Read/Write ASYMMETRY - both read as {readback_0}", "ERROR")
            results["diagnosis"] = "asymmetric"
            
            # Check if the value is stuck at one extreme
            if abs(readback_0 - 0.0) < 0.01:
                log("Value stuck at minimum (0.0 normalized)", "ERROR")
                log("This suggests writing doesn't work - it's being ignored!", "ERROR")
            elif abs(readback_0 - 1.0) < 0.01:
                log("Value stuck at maximum (1.0 normalized)", "ERROR")
        else:
            log(f"UNEXPECTED behavior: sent 0.0→got {readback_0}, sent 1.0→got {readback_1}", "WARN")
            results["diagnosis"] = "unexpected"
    
    return results


def main():
    print("\n" + "=" * 70)
    print("NEGATIVE-ONLY PARAMETER DIAGNOSTIC")
    print("=" * 70)
    
    # Test connection
    print("\nTesting OSC connection...")
    if not ableton.test_connection():
        print("❌ OSC connection failed!")
        print("Make sure Ableton Live is running with AbletonOSC.")
        return 1
    print("✓ OSC connection OK\n")
    
    reliable = ReliableParameterController(ableton, verbose=True)
    track = 0
    
    # Parameters to diagnose
    test_cases = [
        ("Saturator", "Output"),
        ("Glue Compressor", "Threshold"),
    ]
    
    all_results = []
    
    for device_name, param_name in test_cases:
        print(f"\n{'#'*60}")
        print(f"# Loading {device_name}...")
        print(f"{'#'*60}")
        
        # Load device
        load_result = reliable.load_device_verified(track, device_name, position=-1)
        
        if not load_result.get("success"):
            log(f"Failed to load {device_name}: {load_result.get('message')}", "ERROR")
            continue
        
        device_idx = load_result["device_index"]
        log(f"Loaded {device_name} at index {device_idx}", "SUCCESS")
        
        # Wait for device to be ready
        if not reliable.wait_for_device_ready(track, device_idx):
            log(f"Device not ready", "ERROR")
            continue
        
        # Diagnose the parameter
        result = diagnose_parameter(reliable, track, device_idx, param_name, device_name)
        if result:
            all_results.append(result)
        
        time.sleep(0.5)
    
    # Summary
    print("\n" + "=" * 70)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 70)
    
    for result in all_results:
        print(f"\n{result['param_name']}:")
        print(f"  Reported range: [{result['reported_min']}, {result['reported_max']}]")
        print(f"  Is negative-only: {result['is_negative_only']}")
        print(f"  Diagnosis: {result.get('diagnosis', 'unknown')}")
        
        for test in result['tests']:
            print(f"    Sent {test['sent']:.1f} → Got {test['readback_normalized']}")
    
    # Recommendation
    print("\n" + "=" * 70)
    print("RECOMMENDATION")
    print("=" * 70)
    
    has_asymmetric = any(r.get('diagnosis') == 'asymmetric' for r in all_results)
    has_inverted = any(r.get('diagnosis') == 'inverted' for r in all_results)
    
    if has_asymmetric:
        print("""
The read/write is ASYMMETRIC for these parameters!

This means:
- We SEND a normalized value (e.g., 0.916667)
- We READ BACK 0.0 (the minimum)

The write seems to be ignored or there's a read-only issue.
This could mean:
1. These parameters don't accept writes via OSC
2. The OSC path for setting is different
3. Ableton silently rejects the value

SUGGESTED FIX:
Since writing doesn't work reliably, we should either:
a) Skip verification for these parameters (accept the write without readback check)
b) Use raw normalized values without transformation and accept what Ableton does
        """)
    elif has_inverted:
        print("""
The normalization is INVERTED for these parameters!

SUGGESTED FIX:
For negative-only ranges (min < 0, max <= 0):
- Send: 1.0 - normalize(value) 
- Read: denormalize(1.0 - readback)
        """)
    else:
        print("Parameters behave consistently - no special handling needed.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

