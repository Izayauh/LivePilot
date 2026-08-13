"""
Parameter Range Diagnostic Tool

Investigates why AbletonOSC returns incorrect parameter ranges (0-1) for some
parameters but correct ranges for others.

Usage:
    python tests/diagnose_parameter_ranges.py

This script will:
1. Load test devices (EQ Eight, Compressor, Saturator)
2. Query their parameter ranges from OSC
3. Compare against expected ranges from device_kb.py
4. Test actual parameter behavior (normalized vs denormalized)
5. Report findings and recommend fixes
"""

import sys
import os
import time
from typing import Dict, List, Tuple, Any

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ableton_controls import ableton
from ableton_controls.reliable_params import ReliableParameterController
from knowledge.device_kb import get_device_kb


class ParameterRangeDiagnostic:
    """Diagnose parameter range issues with AbletonOSC"""
    
    def __init__(self):
        self.reliable = ReliableParameterController(ableton, verbose=False)
        self.device_kb = get_device_kb()
        self.findings = []
        
    def log(self, msg: str, level: str = "INFO"):
        """Log a message"""
        prefix = {
            "INFO": "ℹ️",
            "WARN": "⚠️",
            "ERROR": "❌",
            "SUCCESS": "✅",
            "TEST": "🔬"
        }.get(level, "")
        print(f"{prefix} {msg}")
        
    def diagnose_device(self, device_name: str, track_index: int = 0) -> Dict[str, Any]:
        """
        Diagnose parameter range issues for a specific device.
        
        Returns findings dict with:
        - device_name
        - param_comparisons: list of {name, osc_range, expected_range, issue}
        - behavior_tests: list of test results
        """
        self.log(f"\n{'='*70}")
        self.log(f"Diagnosing: {device_name}", "TEST")
        self.log(f"{'='*70}")
        
        # Load the device
        self.log(f"Loading {device_name}...")
        load_result = self.reliable.load_device_verified(track_index, device_name, position=-1)
        
        if not load_result.get("success"):
            self.log(f"Failed to load {device_name}", "ERROR")
            return {"device_name": device_name, "error": "Failed to load"}
        
        device_index = load_result["device_index"]
        time.sleep(1.0)  # Wait for device to fully initialize
        
        # Wait for device ready
        if not self.reliable.wait_for_device_ready(track_index, device_index, timeout=5.0):
            self.log(f"Device not ready", "ERROR")
            return {"device_name": device_name, "error": "Device not ready"}
        
        # Get device info from OSC (clear cache first)
        self.reliable.cache.invalidate(track_index, device_index)
        ableton._param_range_cache.clear()  # Clear OSC cache
        
        info = self.reliable.get_device_info(track_index, device_index, use_cache=False)
        if not info or not info.accessible:
            self.log(f"Cannot access device parameters", "ERROR")
            return {"device_name": device_name, "error": "Parameters not accessible"}
        
        self.log(f"Found {len(info.param_names)} parameters")
        
        # Get expected ranges from device_kb
        kb_device = self.device_kb.get_device_info(device_name)
        
        findings = {
            "device_name": device_name,
            "param_count": len(info.param_names),
            "comparisons": [],
            "behavior_tests": []
        }
        
        # Compare ranges for known parameters
        self.log(f"\nComparing OSC ranges vs Expected ranges:")
        self.log(f"-" * 70)
        
        for idx, param_name in enumerate(info.param_names):
            if idx >= len(info.param_mins) or idx >= len(info.param_maxs):
                continue
                
            osc_min = info.param_mins[idx]
            osc_max = info.param_maxs[idx]
            osc_range = (osc_min, osc_max)
            
            # Try to find expected range from KB
            expected_range = None
            kb_param = None
            if kb_device:
                for p in kb_device.parameters:
                    if p.name.lower() == param_name.lower():
                        kb_param = p
                        expected_range = (p.min_value, p.max_value)
                        break
            
            # Detect issues
            issue = None
            is_normalized = (osc_min == 0.0 and osc_max == 1.0)
            
            if expected_range and is_normalized and expected_range != (0.0, 1.0):
                # OSC says 0-1 but KB expects wider range
                issue = "OSC_WRONG_RANGE"
                self.log(f"  ⚠️  [{idx:2d}] {param_name:30s} OSC: {osc_range}, Expected: {expected_range}", "WARN")
            elif is_normalized and any(keyword in param_name.lower() for keyword in ["frequency", "freq", "hz", "time", "delay", "ms", "threshold", "ratio"]):
                # Parameter name suggests it shouldn't be 0-1
                issue = "SUSPICIOUS_RANGE"
                self.log(f"  ⚠️  [{idx:2d}] {param_name:30s} OSC: {osc_range} (suspicious for '{param_name}')", "WARN")
            else:
                self.log(f"  ✓  [{idx:2d}] {param_name:30s} OSC: {osc_range}")
            
            findings["comparisons"].append({
                "index": idx,
                "name": param_name,
                "osc_range": osc_range,
                "expected_range": expected_range,
                "kb_param": kb_param,
                "issue": issue
            })
        
        # Test actual parameter behavior on problematic params
        self.log(f"\nTesting parameter behavior:")
        self.log(f"-" * 70)
        
        problematic_params = [c for c in findings["comparisons"] if c["issue"]]
        test_params = problematic_params[:3]  # Test first 3 problematic ones
        
        for comp in test_params:
            self.log(f"\nTesting: {comp['name']} (index {comp['index']})")
            
            behavior = self.test_parameter_behavior(
                track_index, device_index, comp['index'], 
                comp['name'], comp['osc_range'], comp['expected_range']
            )
            findings["behavior_tests"].append(behavior)
        
        return findings
    
    def test_parameter_behavior(self, track: int, device: int, param_idx: int,
                                  param_name: str, osc_range: Tuple[float, float],
                                  expected_range: Tuple[float, float]) -> Dict[str, Any]:
        """
        Test how a parameter actually behaves:
        - Does it accept normalized values?
        - Does it return normalized or denormalized values?
        - What format does it actually work with?
        """
        result = {
            "name": param_name,
            "index": param_idx,
            "osc_range": osc_range,
            "expected_range": expected_range,
            "tests": []
        }
        
        # Test 1: Send normalized 0.5, read back
        self.log(f"  Test 1: Send normalized 0.5")
        try:
            ableton.set_device_parameter(track, device, param_idx, 0.5)
            time.sleep(0.1)
            readback_1 = self.reliable.get_parameter_value_sync(track, device, param_idx)
            
            if readback_1 is not None:
                self.log(f"    → Readback: {readback_1:.6f}")
                if 0.4 <= readback_1 <= 0.6:
                    self.log(f"    ✓ Returns normalized value", "SUCCESS")
                    returns_normalized = True
                else:
                    self.log(f"    ℹ️  Returns denormalized value")
                    returns_normalized = False
                
                result["tests"].append({
                    "test": "send_norm_0.5",
                    "sent": 0.5,
                    "received": readback_1,
                    "returns_normalized": returns_normalized
                })
        except Exception as e:
            self.log(f"    ❌ Error: {e}", "ERROR")
        
        # Test 2: If we have expected range, try sending a denormalized value
        if expected_range and expected_range != (0.0, 1.0):
            exp_min, exp_max = expected_range
            test_value = exp_min + (exp_max - exp_min) * 0.3  # 30% through range
            
            self.log(f"  Test 2: Send denormalized {test_value:.2f} (30% of {expected_range})")
            try:
                ableton.set_device_parameter(track, device, param_idx, test_value)
                time.sleep(0.1)
                readback_2 = self.reliable.get_parameter_value_sync(track, device, param_idx)
                
                if readback_2 is not None:
                    self.log(f"    → Readback: {readback_2:.6f}")
                    
                    # Check if it matches what we sent
                    if abs(readback_2 - test_value) < abs(test_value * 0.05):  # Within 5%
                        self.log(f"    ✓ Accepts denormalized values!", "SUCCESS")
                        accepts_denorm = True
                    else:
                        self.log(f"    ℹ️  Does not match sent value")
                        accepts_denorm = False
                    
                    result["tests"].append({
                        "test": "send_denorm",
                        "sent": test_value,
                        "received": readback_2,
                        "accepts_denormalized": accepts_denorm
                    })
            except Exception as e:
                self.log(f"    ❌ Error: {e}", "ERROR")
        
        # Test 3: Send 0.0 and 1.0 to check endpoints
        self.log(f"  Test 3: Endpoint test (0.0 and 1.0)")
        try:
            ableton.set_device_parameter(track, device, param_idx, 0.0)
            time.sleep(0.05)
            readback_min = self.reliable.get_parameter_value_sync(track, device, param_idx)
            
            ableton.set_device_parameter(track, device, param_idx, 1.0)
            time.sleep(0.05)
            readback_max = self.reliable.get_parameter_value_sync(track, device, param_idx)
            
            if readback_min is not None and readback_max is not None:
                self.log(f"    → Min: {readback_min:.6f}, Max: {readback_max:.6f}")
                
                # These readbacks tell us the actual parameter range!
                actual_range = (readback_min, readback_max)
                self.log(f"    → Actual range appears to be: {actual_range}")
                
                result["tests"].append({
                    "test": "endpoints",
                    "actual_min": readback_min,
                    "actual_max": readback_max,
                    "actual_range": actual_range
                })
                
                result["inferred_actual_range"] = actual_range
        except Exception as e:
            self.log(f"    ❌ Error: {e}", "ERROR")
        
        return result
    
    def print_summary(self, all_findings: List[Dict[str, Any]]):
        """Print summary of all findings"""
        self.log(f"\n\n{'='*70}")
        self.log(f"DIAGNOSTIC SUMMARY", "TEST")
        self.log(f"{'='*70}\n")
        
        total_issues = 0
        osc_wrong_count = 0
        suspicious_count = 0
        
        for finding in all_findings:
            if "error" in finding:
                continue
                
            device_name = finding["device_name"]
            issues = [c for c in finding["comparisons"] if c["issue"]]
            total_issues += len(issues)
            
            osc_wrong = [c for c in issues if c["issue"] == "OSC_WRONG_RANGE"]
            suspicious = [c for c in issues if c["issue"] == "SUSPICIOUS_RANGE"]
            osc_wrong_count += len(osc_wrong)
            suspicious_count += len(suspicious)
            
            if issues:
                self.log(f"{device_name}:")
                self.log(f"  - {len(osc_wrong)} parameters with wrong OSC ranges")
                self.log(f"  - {len(suspicious)} parameters with suspicious ranges")
        
        self.log(f"\nTOTAL ISSUES: {total_issues}")
        self.log(f"  - OSC_WRONG_RANGE: {osc_wrong_count}")
        self.log(f"  - SUSPICIOUS_RANGE: {suspicious_count}")
        
        # Analyze behavior tests
        self.log(f"\nBEHAVIOR ANALYSIS:")
        
        for finding in all_findings:
            if "behavior_tests" not in finding or not finding["behavior_tests"]:
                continue
                
            self.log(f"\n{finding['device_name']}:")
            for test in finding["behavior_tests"]:
                self.log(f"  {test['name']}:")
                
                if "inferred_actual_range" in test:
                    self.log(f"    → Actual range: {test['inferred_actual_range']}")
                    if test['osc_range'] != test['inferred_actual_range']:
                        self.log(f"    ⚠️  OSC LIED! Reported {test['osc_range']}", "WARN")
                
                for t in test["tests"]:
                    if t["test"] == "send_norm_0.5" and "returns_normalized" in t:
                        if t["returns_normalized"]:
                            self.log(f"    ✓ Returns normalized values")
                        else:
                            self.log(f"    ✓ Returns denormalized values")
                    
                    if t["test"] == "send_denorm" and "accepts_denormalized" in t:
                        if t["accepts_denormalized"]:
                            self.log(f"    ✓ Accepts denormalized values")
        
        # Recommendations
        self.log(f"\n\nRECOMMENDATIONS:")
        if osc_wrong_count > 0:
            self.log(f"1. AbletonOSC is returning WRONG ranges (0-1) for parameters that have wider ranges")
            self.log(f"   → Use device_kb.py as source of truth")
            self.log(f"   → Or detect when OSC range is suspicious and fall back to KB")
        
        if suspicious_count > 0:
            self.log(f"2. Some parameters have 0-1 range when their name suggests otherwise")
            self.log(f"   → These might need different OSC queries")
            self.log(f"   → Or KB lookup for actual ranges")
        
        self.log(f"\n3. Test if sending DENORMALIZED values works better:")
        self.log(f"   → If parameters accept denormalized values, skip normalization")
        self.log(f"   → If they return denormalized values, skip denormalization")


def main():
    """Run diagnostics on test devices"""
    print("\n" + "="*70)
    print("PARAMETER RANGE DIAGNOSTIC TOOL")
    print("="*70)
    print()
    
    # Test connection
    if not ableton.test_connection():
        print("❌ OSC connection failed!")
        print("\nMake sure:")
        print("  1. Ableton Live is running")
        print("  2. AbletonOSC is installed and active")
        print("  3. Listening on port 11000")
        return 1
    
    print("✅ OSC connection OK\n")
    
    diagnostic = ParameterRangeDiagnostic()
    
    # Test devices
    test_devices = ["EQ Eight", "Compressor", "Saturator"]
    
    all_findings = []
    for device_name in test_devices:
        try:
            findings = diagnostic.diagnose_device(device_name, track_index=0)
            all_findings.append(findings)
            time.sleep(0.5)
        except Exception as e:
            diagnostic.log(f"Error diagnosing {device_name}: {e}", "ERROR")
            import traceback
            traceback.print_exc()
    
    # Print summary
    diagnostic.print_summary(all_findings)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

