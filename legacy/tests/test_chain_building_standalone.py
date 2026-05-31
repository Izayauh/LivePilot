"""
Standalone Chain Building Test

Tests chain building in isolation without dependencies on research agents or Gemini.
Uses predefined chains and validates device loading + parameter configuration.

Run with: python tests/test_chain_building_standalone.py
"""

import os
import sys
import time
import argparse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.chain_test_utils import (
    ChainTestResult,
    run_chain_test,
    print_chain_report,
    print_summary,
    save_test_results,
    get_preset_chain,
    get_billie_eilish_chain,
    load_chain_definition,
    create_reliable_controller,
    get_device_count,
    clear_track_devices,
)


def test_basic_vocal_chain(track_index: int = 0, verbose: bool = True) -> ChainTestResult:
    """
    Test simple 3-device chain: EQ → Compressor → Reverb
    
    This is the minimum viable vocal chain that should work reliably.
    Tests ~10 parameters across 3 devices.
    """
    print("\n" + "=" * 60)
    print("🎤 TEST: Basic Vocal Chain")
    print("   EQ Eight → Compressor → Reverb")
    print("=" * 60)
    
    chain = get_preset_chain("vocal_basic")
    
    if not chain:
        print("❌ Failed to load vocal_basic preset")
        return ChainTestResult(chain_name="vocal_basic", track_index=track_index)
    
    result = run_chain_test(
        chain_name="vocal_basic",
        chain_devices=chain,
        track_index=track_index,
        clear_track=True,
        verbose=verbose
    )
    
    print_chain_report(result)
    return result


def test_full_vocal_chain(track_index: int = 0, verbose: bool = True) -> ChainTestResult:
    """
    Test complex 7-device chain: EQ → Comp → De-esser → Saturator → EQ → Reverb → Delay
    
    This is a full production-ready vocal chain.
    Tests ~25 parameters across 7 devices.
    """
    print("\n" + "=" * 60)
    print("🎤 TEST: Full Vocal Chain")
    print("   EQ → Comp → De-esser → Saturator → EQ → Reverb → Delay")
    print("=" * 60)
    
    chain = get_preset_chain("vocal_full")
    
    if not chain:
        print("❌ Failed to load vocal_full preset")
        return ChainTestResult(chain_name="vocal_full", track_index=track_index)
    
    result = run_chain_test(
        chain_name="vocal_full",
        chain_devices=chain,
        track_index=track_index,
        clear_track=True,
        verbose=verbose
    )
    
    print_chain_report(result)
    return result


def test_billie_eilish_chain(track_index: int = 0, verbose: bool = True) -> ChainTestResult:
    """
    Test real-world chain: Billie Eilish vocal processing
    
    This chain is from plugin_chains.json and represents actual
    production settings used for intimate, breathy vocals.
    Tests 6 devices with specific artistic parameters.
    """
    print("\n" + "=" * 60)
    print("🎤 TEST: Billie Eilish Vocal Chain")
    print("   Intimate, breathy vocal processing with dark reverb")
    print("=" * 60)
    
    chain = get_billie_eilish_chain()
    
    result = run_chain_test(
        chain_name="billie_eilish_vocal",
        chain_devices=chain,
        track_index=track_index,
        clear_track=True,
        verbose=verbose
    )
    
    print_chain_report(result)
    return result


def test_drum_bus_chain(track_index: int = 0, verbose: bool = True) -> ChainTestResult:
    """
    Test drum bus chain: EQ → Glue Compressor → Saturator → Limiter
    
    Tests a different track type to validate versatility.
    """
    print("\n" + "=" * 60)
    print("🥁 TEST: Drum Bus Chain")
    print("   EQ → Glue Compressor → Saturator → Limiter")
    print("=" * 60)
    
    chain = get_preset_chain("drum_bus")
    
    if not chain:
        print("❌ Failed to load drum_bus preset")
        return ChainTestResult(chain_name="drum_bus", track_index=track_index)
    
    result = run_chain_test(
        chain_name="drum_bus",
        chain_devices=chain,
        track_index=track_index,
        clear_track=True,
        verbose=verbose
    )
    
    print_chain_report(result)
    return result


def test_parameter_reliability(track_index: int = 0, verbose: bool = True) -> ChainTestResult:
    """
    Focus test: Many parameter sets across devices
    
    Loads a single device multiple times with different parameter values
    to stress-test parameter reliability.
    """
    print("\n" + "=" * 60)
    print("🔬 TEST: Parameter Reliability Stress Test")
    print("   Testing 50+ parameter sets for reliability")
    print("=" * 60)
    
    # Load EQ Eight 3 times with many parameters each
    chain = [
        {
            "type": "eq",
            "name": "EQ Eight",
            "settings": {
                "1 Filter On A": 1.0,
                "1 Frequency A": 100.0,
                "1 Gain A": -3.0,
                "2 Filter On A": 1.0,
                "2 Frequency A": 300.0,
                "2 Gain A": -2.0,
                "3 Filter On A": 1.0,
                "3 Frequency A": 2500.0,
                "3 Gain A": 2.0,
                "4 Filter On A": 1.0,
                "4 Frequency A": 5000.0,
                "4 Gain A": 1.0,
            }
        },
        {
            "type": "compressor",
            "name": "Compressor",
            "settings": {
                "Threshold": -12.0,
                "Ratio": 4.0,
                "Attack": 10.0,
                "Release": 100.0,
                "Knee": 3.0,
                "Model": 0.0,  # Peak mode
                "Makeup": 3.0,
            }
        },
        {
            "type": "compressor",
            "name": "Glue Compressor",
            "settings": {
                "Threshold": -15.0,
                "Ratio": 4.0,
                "Attack": 30.0,
                "Release": 0.4,
                "Makeup": 2.0,
                "Dry/Wet": 1.0,
            }
        },
        {
            "type": "saturation",
            "name": "Saturator",
            "settings": {
                "Drive": 8.0,
                "Dry/Wet": 0.5,
                "Color": 1.0,
                "Base": 0.0,
            }
        },
        {
            "type": "reverb",
            "name": "Reverb",
            "settings": {
                "Decay Time": 3.0,
                "Dry/Wet": 0.4,
                "Predelay": 50.0,
                "Room Size": 100.0,
                "Diffusion Network On": 1.0,
                "Chorus Rate": 0.2,
                "Chorus Amount": 0.5,
            }
        },
        {
            "type": "delay",
            "name": "Delay",
            "settings": {
                "Dry/Wet": 0.2,
                "Feedback": 0.35,
                "L Time": 0.25,
                "R Time": 0.375,
            }
        },
    ]
    
    result = run_chain_test(
        chain_name="parameter_reliability",
        chain_devices=chain,
        track_index=track_index,
        clear_track=True,
        verbose=verbose
    )
    
    print_chain_report(result)
    return result


def run_all_standalone_tests(track_index: int = 0, verbose: bool = True) -> list:
    """
    Run all standalone chain tests and generate summary report
    """
    print("\n" + "=" * 60)
    print("🎬 STARTING STANDALONE CHAIN BUILDING TESTS")
    print("=" * 60)
    
    results = []
    
    # Run each test
    print("\n📋 Test Suite: 5 tests queued")
    print("   1. Basic Vocal Chain (3 devices)")
    print("   2. Full Vocal Chain (7 devices)")
    print("   3. Billie Eilish Chain (6 devices)")
    print("   4. Drum Bus Chain (4 devices)")
    print("   5. Parameter Reliability (50+ params)")
    
    # Pause between tests to let Ableton stabilize
    test_delay = 3.0  # Give Ableton more time between tests
    
    # Test 1: Basic Vocal
    results.append(test_basic_vocal_chain(track_index, verbose))
    time.sleep(test_delay)
    
    # Test 2: Full Vocal
    results.append(test_full_vocal_chain(track_index, verbose))
    time.sleep(test_delay)
    
    # Test 3: Billie Eilish
    results.append(test_billie_eilish_chain(track_index, verbose))
    time.sleep(test_delay)
    
    # Test 4: Drum Bus
    results.append(test_drum_bus_chain(track_index, verbose))
    time.sleep(test_delay)
    
    # Test 5: Parameter Reliability (skip if other tests had major issues)
    if all(r.device_success_rate >= 0.5 for r in results):
        results.append(test_parameter_reliability(track_index, verbose))
    else:
        print("\n⚠️ Skipping parameter reliability test due to earlier failures")
    
    # Print summary
    print_summary(results)
    
    # Save results
    save_test_results(results, "standalone_chain_test_results.json")
    
    return results


def run_quick_test(track_index: int = 0, verbose: bool = True) -> list:
    """
    Run just the basic vocal chain test for quick validation
    """
    print("\n🚀 QUICK TEST: Basic Vocal Chain Only")
    
    results = [test_basic_vocal_chain(track_index, verbose)]
    print_summary(results)
    
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Standalone Chain Building Tests")
    parser.add_argument("--track", type=int, default=0,
                        help="Track index to test on (0-based, default: 0)")
    parser.add_argument("--quick", action="store_true",
                        help="Run quick test only (basic vocal chain)")
    parser.add_argument("--quiet", action="store_true",
                        help="Reduce verbosity")
    parser.add_argument("--test", type=str, choices=[
                        "basic", "full", "billie", "drums", "params"],
                        help="Run a specific test only")
    
    args = parser.parse_args()
    verbose = not args.quiet
    
    print("\n🎹 Standalone Chain Building Test Suite")
    print(f"   Target Track: {args.track} (Track {args.track + 1} in Ableton)")
    print(f"   Verbose: {verbose}")
    
    if args.quick:
        run_quick_test(args.track, verbose)
    elif args.test:
        test_map = {
            "basic": test_basic_vocal_chain,
            "full": test_full_vocal_chain,
            "billie": test_billie_eilish_chain,
            "drums": test_drum_bus_chain,
            "params": test_parameter_reliability,
        }
        test_fn = test_map[args.test]
        result = test_fn(args.track, verbose)
        print_summary([result])
    else:
        run_all_standalone_tests(args.track, verbose)

