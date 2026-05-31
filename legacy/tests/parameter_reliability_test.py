"""
Parameter Reliability Test Suite

Exhaustive testing of parameter operations on stock Ableton devices.
Tests the ReliableParameterController to ensure 95%+ success rate.

Run with:
    python tests/parameter_reliability_test.py

Requirements:
    - Ableton Live running
    - AbletonOSC bridge active on port 11000
    - At least one track available for testing
"""

import sys
import os
import time
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ableton_controls import ableton
from ableton_controls.reliable_params import ReliableParameterController


@dataclass
class TestResult:
    """Result of a single parameter test"""
    test_name: str
    device_name: str
    param_name: str
    target_value: float
    actual_value: Optional[float]
    success: bool
    verified: bool
    attempts: int
    elapsed_time: float
    message: str = ""
    
    def __str__(self):
        status = "✓" if self.success else "✗"
        return (f"{status} {self.device_name}/{self.param_name}: "
                f"target={self.target_value}, actual={self.actual_value}, "
                f"attempts={self.attempts}, time={self.elapsed_time:.2f}s")


@dataclass 
class TestSuiteResults:
    """Results from a complete test suite run"""
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    success_rate: float = 0.0
    total_time: float = 0.0
    results: List[TestResult] = field(default_factory=list)
    
    def add_result(self, result: TestResult):
        self.results.append(result)
        self.total_tests += 1
        if result.success:
            self.passed += 1
        else:
            self.failed += 1
        self.success_rate = (self.passed / self.total_tests * 100) if self.total_tests > 0 else 0.0
        self.total_time += result.elapsed_time
    
    def print_summary(self):
        print("\n" + "=" * 70)
        print("PARAMETER RELIABILITY TEST RESULTS")
        print("=" * 70)
        print(f"\nTotal Tests: {self.total_tests}")
        print(f"Passed: {self.passed}")
        print(f"Failed: {self.failed}")
        print(f"Success Rate: {self.success_rate:.1f}%")
        print(f"Total Time: {self.total_time:.2f}s")
        
        if self.success_rate >= 95.0:
            print("\n✅ SUCCESS: Achieved target 95%+ reliability!")
        else:
            print(f"\n⚠️ WARNING: Below target. Need {95.0 - self.success_rate:.1f}% improvement")
        
        if self.failed > 0:
            print("\nFailed Tests:")
            for result in self.results:
                if not result.success:
                    print(f"  - {result}")
        
        print("=" * 70)


class ParameterReliabilityTest:
    """
    Exhaustive parameter testing on stock Ableton devices.
    
    Tests device loading, parameter discovery, and verified parameter setting
    to ensure reliable operation of the ReliableParameterController.
    """
    
    def __init__(self, track_index: int = 0, verbose: bool = True):
        """
        Initialize the test suite.
        
        Args:
            track_index: Track to use for testing (0-based)
            verbose: Enable verbose output
        """
        self.track_index = track_index
        self.verbose = verbose
        self.reliable = ReliableParameterController(ableton, verbose=verbose)
        self.results = TestSuiteResults()
        
        # Test configurations for each device
        # Format: (device_name, [(param_name, test_value, tolerance, is_percentage), ...])
        # is_percentage: True if we're testing with percentage values (will compare against 0-1 normalized)
        self.device_tests = {
            "EQ Eight": [
                ("1 Frequency A", 0.5, 0.05, False),  # Band 1 Frequency (normalized 0-1)
                ("1 Gain A", -3.0, 0.5, False),        # Band 1 Gain (dB)
                ("2 Frequency A", 0.3, 0.05, False),   # Band 2 Frequency (normalized 0-1) 
                ("2 Gain A", 2.0, 0.5, False),         # Band 2 Gain (dB)
            ],
            "Compressor": [
                ("Threshold", 0.5, 0.05, False),     # Normalized 0-1 parameter
                ("Ratio", 0.4, 0.05, False),         # Normalized 0-1 parameter
                ("Attack", 0.5, 0.05, False),        # Normalized 0-1 parameter
                ("Release", 0.6, 0.05, False),       # Normalized 0-1 parameter
                ("Output Gain", 3.0, 0.5, False),    # Gain in dB
            ],
            "Reverb": [
                ("Decay Time", 0.5, 0.05, False),    # Normalized 0-1
                ("Room Size", 60.0, 5.0, True),      # Percentage (will auto-convert to 0.6)
                ("Predelay", 0.3, 0.05, False),      # Correct param name (no space)
                ("Dry/Wet", 35.0, 2.0, True),        # Percentage (will auto-convert to 0.35)
            ],
            "Saturator": [
                ("Drive", 10.0, 1.0, False),         # dB value
                ("Output", -3.0, 0.5, False),        # dB value
                ("Dry/Wet", 80.0, 2.0, True),        # Percentage (will auto-convert to 0.8)
            ],
            "Glue Compressor": [
                ("Threshold", -15.0, 1.0, False),    # dB value
                ("Makeup", 3.0, 0.5, False),         # dB value
                ("Dry/Wet", 100.0, 2.0, True),       # Percentage (will auto-convert to 1.0)
            ],
        }
    
    def _log(self, msg: str, level: str = "INFO"):
        """Log message if verbose mode enabled"""
        if self.verbose:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            prefix = {
                "INFO": "ℹ️",
                "WARN": "⚠️",
                "ERROR": "❌",
                "SUCCESS": "✅",
                "TEST": "🧪"
            }.get(level, "")
            print(f"[{timestamp}] {prefix} {msg}")
    
    def _clear_track_devices(self) -> bool:
        """Remove all devices from test track"""
        try:
            # Get current device count
            result = ableton.get_num_devices_sync(self.track_index)
            if not result.get("success"):
                return False
            
            count = result.get("count", 0)
            
            # Remove devices from end to start (safer)
            for i in range(count - 1, -1, -1):
                # There's no direct delete device OSC command in standard AbletonOSC
                # We'll just leave devices - tests should still work
                pass
            
            # Invalidate cache for this track
            self.reliable.cache.invalidate_track(self.track_index)
            
            return True
        except Exception as e:
            self._log(f"Error clearing track: {e}", "ERROR")
            return False
    
    def _test_device_parameters(self, device_name: str, 
                                 param_tests: List[tuple],
                                 iterations: int = 3) -> List[TestResult]:
        """
        Test parameters on a single device.
        
        Args:
            device_name: Name of device to test
            param_tests: List of (param_name, test_value, tolerance, is_percentage) tuples
            iterations: Number of times to run each test
            
        Returns:
            List of TestResult objects
        """
        results = []
        
        self._log(f"\n{'='*60}", "TEST")
        self._log(f"Testing: {device_name}", "TEST")
        self._log(f"{'='*60}", "TEST")
        
        # Load the device
        load_result = self.reliable.load_device_verified(
            self.track_index, device_name, position=-1, timeout=5.0
        )
        
        if not load_result.get("success"):
            self._log(f"Failed to load {device_name}: {load_result.get('message')}", "ERROR")
            
            # Record failure for all param tests
            for test_tuple in param_tests:
                param_name, value = test_tuple[0], test_tuple[1]
                for i in range(iterations):
                    results.append(TestResult(
                        test_name=f"{device_name}_{param_name}_{i+1}",
                        device_name=device_name,
                        param_name=param_name,
                        target_value=value,
                        actual_value=None,
                        success=False,
                        verified=False,
                        attempts=0,
                        elapsed_time=0.0,
                        message="Device load failed"
                    ))
            return results
        
        device_index = load_result.get("device_index", 0)
        self._log(f"Device loaded at index {device_index}", "SUCCESS")
        
        # Wait for device to be ready
        if not self.reliable.wait_for_device_ready(self.track_index, device_index):
            self._log(f"Device not ready after timeout", "ERROR")
            return results
        
        # Print available parameters for debugging
        all_params = self.reliable.get_all_parameter_names(self.track_index, device_index)
        self._log(f"Available parameters ({len(all_params)}): {all_params[:15]}...")
        
        # Test each parameter multiple times
        for test_tuple in param_tests:
            # Handle both old format (3 items) and new format (4 items)
            if len(test_tuple) == 4:
                param_name, target_value, tolerance, is_percentage = test_tuple
            else:
                param_name, target_value, tolerance = test_tuple
                is_percentage = False
            
            self._log(f"\n--- Testing: {param_name} = {target_value} ---")
            
            for iteration in range(iterations):
                start_time = time.time()
                
                # Set parameter by name
                set_result = self.reliable.set_parameter_by_name(
                    self.track_index, device_index, param_name, target_value
                )
                
                elapsed = time.time() - start_time
                
                # Determine success with tolerance
                success = set_result.get("success", False)
                actual = set_result.get("actual_value")
                
                if success and actual is not None:
                    # For percentage parameters, compare against normalized value
                    # (e.g., if we sent 80.0%, we expect 0.8 back)
                    if is_percentage:
                        expected_value = target_value / 100.0
                    else:
                        expected_value = target_value
                    
                    # Check tolerance
                    diff = abs(actual - expected_value)
                    if diff > tolerance:
                        success = False
                        set_result["message"] = f"Value outside tolerance: expected={expected_value:.4f}, actual={actual:.4f}, diff={diff:.4f}"
                
                result = TestResult(
                    test_name=f"{device_name}_{param_name}_{iteration+1}",
                    device_name=device_name,
                    param_name=param_name,
                    target_value=target_value,
                    actual_value=actual,
                    success=success,
                    verified=set_result.get("verified", False),
                    attempts=set_result.get("attempts", 0),
                    elapsed_time=elapsed,
                    message=set_result.get("message", "")
                )
                
                results.append(result)
                
                status = "✓" if success else "✗"
                self._log(f"  Iteration {iteration+1}: {status} "
                         f"target={target_value}, actual={actual}, "
                         f"time={elapsed:.2f}s")
                
                # Small delay between iterations
                time.sleep(0.1)
        
        return results
    
    def run_single_device_test(self, device_name: str, iterations: int = 3) -> TestSuiteResults:
        """
        Run tests for a single device.
        
        Args:
            device_name: Device to test
            iterations: Number of test iterations
            
        Returns:
            TestSuiteResults for this device
        """
        if device_name not in self.device_tests:
            self._log(f"No test configuration for device: {device_name}", "ERROR")
            return TestSuiteResults()
        
        param_tests = self.device_tests[device_name]
        results = self._test_device_parameters(device_name, param_tests, iterations)
        
        suite_results = TestSuiteResults()
        for result in results:
            suite_results.add_result(result)
        
        return suite_results
    
    def run_all_tests(self, iterations: int = 3) -> TestSuiteResults:
        """
        Run all device tests.
        
        Args:
            iterations: Number of times to run each parameter test
            
        Returns:
            Complete TestSuiteResults
        """
        print("\n" + "=" * 70)
        print("PARAMETER RELIABILITY TEST SUITE")
        print("=" * 70)
        print(f"\nTrack Index: {self.track_index}")
        print(f"Iterations per test: {iterations}")
        print(f"Devices to test: {list(self.device_tests.keys())}")
        print("\n")
        
        start_time = time.time()
        
        # Test connection first
        if not ableton.test_connection():
            self._log("OSC connection failed. Is Ableton running with AbletonOSC?", "ERROR")
            return self.results
        
        self._log("OSC connection OK", "SUCCESS")
        
        # Run tests for each device
        for device_name in self.device_tests:
            try:
                param_tests = self.device_tests[device_name]
                device_results = self._test_device_parameters(
                    device_name, param_tests, iterations
                )
                
                for result in device_results:
                    self.results.add_result(result)
                
                # Print device summary
                device_passed = sum(1 for r in device_results if r.success)
                device_total = len(device_results)
                pct = (device_passed / device_total * 100) if device_total > 0 else 0
                self._log(f"\n{device_name}: {device_passed}/{device_total} ({pct:.1f}%)")
                
                # Delay between devices
                time.sleep(0.5)
                
            except Exception as e:
                self._log(f"Error testing {device_name}: {e}", "ERROR")
                import traceback
                traceback.print_exc()
        
        total_time = time.time() - start_time
        self.results.total_time = total_time
        
        return self.results
    
    def run_quick_test(self) -> TestSuiteResults:
        """
        Run a quick test with just 1 iteration per parameter.
        Good for rapid verification.
        """
        return self.run_all_tests(iterations=1)
    
    def run_thorough_test(self) -> TestSuiteResults:
        """
        Run a thorough test with 10 iterations per parameter.
        Good for reliability statistics.
        """
        return self.run_all_tests(iterations=10)


class ParameterDiscoveryTest:
    """
    Test parameter discovery functionality.
    
    Verifies that we can correctly discover parameter indices by name
    for stock Ableton devices.
    """
    
    def __init__(self, track_index: int = 0, verbose: bool = True):
        self.track_index = track_index
        self.verbose = verbose
        self.reliable = ReliableParameterController(ableton, verbose=verbose)
    
    def _log(self, msg: str):
        if self.verbose:
            print(f"[Discovery] {msg}")
    
    def discover_device_parameters(self, device_name: str) -> Dict[str, Any]:
        """
        Load a device and discover all its parameters.
        
        Returns a dict with parameter info that can be used to update device_kb.py
        """
        result = {
            "device_name": device_name,
            "success": False,
            "parameters": [],
            "message": ""
        }
        
        self._log(f"\n{'='*60}")
        self._log(f"Discovering parameters for: {device_name}")
        self._log(f"{'='*60}")
        
        # Load device
        load_result = self.reliable.load_device_verified(
            self.track_index, device_name, position=-1
        )
        
        if not load_result.get("success"):
            result["message"] = f"Failed to load: {load_result.get('message')}"
            return result
        
        device_index = load_result.get("device_index", 0)
        
        # Wait for ready
        if not self.reliable.wait_for_device_ready(self.track_index, device_index):
            result["message"] = "Device not ready"
            return result
        
        # Get parameter info
        info = self.reliable.get_device_info(self.track_index, device_index, use_cache=False)
        
        if not info or not info.accessible:
            result["message"] = "Parameters not accessible"
            return result
        
        # Build parameter list
        for i, name in enumerate(info.param_names):
            param_info = {
                "index": i,
                "name": name,
                "min": info.param_mins[i] if i < len(info.param_mins) else 0.0,
                "max": info.param_maxs[i] if i < len(info.param_maxs) else 1.0,
            }
            result["parameters"].append(param_info)
        
        result["success"] = True
        result["message"] = f"Found {len(result['parameters'])} parameters"
        
        # Print for reference
        self._log(f"\nParameters for {device_name}:")
        self._log("-" * 60)
        for p in result["parameters"]:
            self._log(f"  [{p['index']:3d}] {p['name']:<40} min={p['min']:.2f}, max={p['max']:.2f}")
        
        return result
    
    def discover_all_devices(self, device_names: List[str]) -> Dict[str, Dict]:
        """
        Discover parameters for multiple devices.
        
        Returns dict of device_name -> parameter info
        """
        results = {}
        
        for device_name in device_names:
            try:
                results[device_name] = self.discover_device_parameters(device_name)
                time.sleep(0.5)  # Delay between devices
            except Exception as e:
                results[device_name] = {
                    "device_name": device_name,
                    "success": False,
                    "message": str(e)
                }
        
        return results


def run_reliability_tests():
    """Run the standard reliability test suite"""
    tester = ParameterReliabilityTest(track_index=0, verbose=True)
    results = tester.run_all_tests(iterations=3)
    results.print_summary()
    return results.success_rate >= 95.0


def run_quick_test():
    """Run a quick single-iteration test"""
    tester = ParameterReliabilityTest(track_index=0, verbose=True)
    results = tester.run_quick_test()
    results.print_summary()
    return results.success_rate >= 95.0


def run_thorough_test():
    """Run a thorough 10-iteration test"""
    tester = ParameterReliabilityTest(track_index=0, verbose=True)
    results = tester.run_thorough_test()
    results.print_summary()
    return results.success_rate >= 95.0


def discover_parameters():
    """Discover parameters for all stock devices"""
    devices = ["EQ Eight", "Compressor", "Reverb", "Saturator", 
               "Glue Compressor", "Limiter", "Delay", "Utility"]
    
    discovery = ParameterDiscoveryTest(track_index=0, verbose=True)
    results = discovery.discover_all_devices(devices)
    
    # Print summary
    print("\n" + "=" * 70)
    print("PARAMETER DISCOVERY SUMMARY")
    print("=" * 70)
    
    for device_name, info in results.items():
        status = "✓" if info.get("success") else "✗"
        param_count = len(info.get("parameters", []))
        print(f"{status} {device_name}: {param_count} parameters - {info.get('message')}")
    
    return results


def test_existing_devices(track_index: int = 0, verbose: bool = True) -> TestSuiteResults:
    """
    Test parameter operations on devices ALREADY loaded in Ableton.
    
    This mode doesn't require the JarvisDeviceLoader Remote Script.
    Just manually load some devices in Ableton first, then run this test.
    
    Returns:
        TestSuiteResults with success rate
    """
    reliable = ReliableParameterController(ableton, verbose=verbose)
    results = TestSuiteResults()
    
    print("\n" + "=" * 70)
    print("EXISTING DEVICE PARAMETER TEST")
    print("=" * 70)
    print("\nThis test works on devices already loaded in Ableton.")
    print("Make sure you have devices on the specified track before running.\n")
    
    # Get number of devices on track
    num_result = ableton.get_num_devices_sync(track_index)
    if not num_result.get("success"):
        print(f"❌ Could not query devices on track {track_index}")
        return results
    
    device_count = num_result.get("count", 0)
    print(f"Found {device_count} devices on track {track_index + 1}\n")
    
    if device_count == 0:
        print("⚠️ No devices found. Please add some devices to the track first.")
        return results
    
    # Get device names
    devices_result = ableton.get_track_devices_sync(track_index)
    device_names = devices_result.get("devices", [])
    
    for device_index in range(device_count):
        device_name = device_names[device_index] if device_index < len(device_names) else f"Device {device_index}"
        
        print(f"\n--- Testing: {device_name} (device {device_index}) ---")
        
        # Wait for device ready
        if not reliable.wait_for_device_ready(track_index, device_index, timeout=3.0):
            print(f"  ⚠️ Device not accessible")
            continue
        
        # Get parameters
        info = reliable.get_device_info(track_index, device_index, use_cache=False)
        if not info or not info.accessible:
            print(f"  ⚠️ Parameters not accessible")
            continue
        
        print(f"  Found {len(info.param_names)} parameters")
        
        # Test first few parameters (skip Device On at index 0)
        test_params = [(1, 0.5), (2, 0.5)] if len(info.param_names) > 2 else [(0, 0.5)]
        
        for param_idx, test_value in test_params:
            if param_idx >= len(info.param_names):
                continue
            
            param_name = info.param_names[param_idx]
            pmin, pmax = info.param_mins[param_idx], info.param_maxs[param_idx]
            
            # Adjust test value to be within range
            test_value_scaled = pmin + (pmax - pmin) * test_value
            
            start_time = time.time()
            result = reliable.set_parameter_verified(
                track_index, device_index, param_idx, test_value_scaled
            )
            elapsed = time.time() - start_time
            
            test_result = TestResult(
                test_name=f"{device_name}_{param_name}",
                device_name=device_name,
                param_name=param_name,
                target_value=test_value_scaled,
                actual_value=result.get("actual_value"),
                success=result.get("success", False),
                verified=result.get("verified", False),
                attempts=result.get("attempts", 0),
                elapsed_time=elapsed,
                message=result.get("message", "")
            )
            
            results.add_result(test_result)
            
            status = "✓" if test_result.success else "✗"
            print(f"  {status} {param_name}: target={test_value_scaled:.2f}, "
                  f"actual={test_result.actual_value}, time={elapsed:.2f}s")
    
    results.print_summary()
    return results


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Parameter Reliability Test Suite")
    parser.add_argument("--mode", choices=["quick", "standard", "thorough", "discover", "existing"],
                       default="existing",
                       help="Test mode: quick/standard/thorough (require Remote Script), discover (find params), existing (test loaded devices)")
    parser.add_argument("--track", type=int, default=0,
                       help="Track index to use for testing (default: 0)")
    parser.add_argument("--device", type=str, default=None,
                       help="Single device to test (e.g., 'EQ Eight')")
    parser.add_argument("--quiet", action="store_true",
                       help="Reduce output verbosity")
    
    args = parser.parse_args()
    
    print("\n" + "=" * 70)
    print("JARVIS ABLETON - PARAMETER RELIABILITY TEST")
    print("=" * 70)
    print(f"\nMode: {args.mode}")
    print(f"Track: {args.track}")
    if args.device:
        print(f"Device: {args.device}")
    print()
    
    # Test connection first
    print("Testing OSC connection...")
    if not ableton.test_connection():
        print("❌ OSC connection failed!")
        print("\nMake sure:")
        print("  1. Ableton Live is running")
        print("  2. AbletonOSC is installed and active")
        print("  3. Listening on port 11000")
        sys.exit(1)
    print("✓ OSC connection OK\n")
    
    success = False
    
    if args.mode == "discover":
        discover_parameters()
        success = True
        
    elif args.mode == "existing":
        # Test on existing devices - doesn't require Remote Script
        results = test_existing_devices(track_index=args.track, verbose=not args.quiet)
        success = results.success_rate >= 95.0 if results.total_tests > 0 else False
        
    elif args.mode == "quick":
        success = run_quick_test()
        
    elif args.mode == "thorough":
        success = run_thorough_test()
        
    elif args.mode == "standard":
        if args.device:
            tester = ParameterReliabilityTest(track_index=args.track, verbose=not args.quiet)
            results = tester.run_single_device_test(args.device, iterations=3)
            results.print_summary()
            success = results.success_rate >= 95.0
        else:
            success = run_reliability_tests()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

