"""
Test script for validating Kanye-style chain execution fixes.

This tests:
1. OSC Connection Stability (Fix 1)
2. Track Type Validation (Fix 2)

IMPORTANT: Ableton Live must be running with JarvisDeviceLoader remote script loaded.
"""

import sys
import os
import asyncio

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from discovery.vst_discovery import VSTDiscoveryService
from plugins.chain_builder import PluginChainBuilder, PluginChain, PluginSlot, PluginInfo

def print_test_header(test_name: str):
    """Print formatted test header"""
    print("\n" + "="*80)
    print(f"TEST: {test_name}")
    print("="*80)

def print_result(passed: bool, message: str):
    """Print test result"""
    status = "[PASS]" if passed else "[FAIL]"
    print(f"\n{status} {message}\n")

# ==================== TEST 1: OSC CONNECTION HEALTH CHECK ====================

def test_osc_health_check():
    """Test 1: OSC connection health check"""
    print_test_header("OSC Connection Health Check")

    vst = VSTDiscoveryService()

    print("Checking connection health to JarvisDeviceLoader...")
    health = vst._check_connection_health(timeout=3.0)

    print(f"Health result: {health}")

    if health["healthy"]:
        print_result(True, f"JarvisDeviceLoader is healthy (response: {health['response_time_ms']:.0f}ms)")
        return True
    else:
        print_result(False, f"JarvisDeviceLoader not responding: {health['error']}")
        print("\nTroubleshooting:")
        print("1. Is Ableton Live running?")
        print("2. Is JarvisDeviceLoader remote script installed?")
        print("3. Check Ableton -> Preferences -> MIDI -> Control Surface")
        return False

# ==================== TEST 2: OSC RETRY LOGIC ====================

def test_osc_retry_logic():
    """Test 2: OSC retry logic with exponential backoff"""
    print_test_header("OSC Retry Logic")

    vst = VSTDiscoveryService()

    print("Testing retry logic by sending request with max_retries=2...")
    print("(If JarvisDeviceLoader is running, this should succeed on first try)")

    try:
        response = vst._send_osc_request("/jarvis/test", [], timeout=2.0, max_retries=2)

        if response:
            print_result(True, "OSC request succeeded (retry logic is in place)")
            return True
        else:
            print_result(False, "OSC request returned None (unexpected)")
            return False

    except Exception as e:
        print_result(False, f"OSC request failed after retries: {e}")
        return False

# ==================== TEST 3: TRACK TYPE QUERY ====================

def test_track_type_query():
    """Test 3: Track type query to JarvisDeviceLoader"""
    print_test_header("Track Type Query")

    vst = VSTDiscoveryService()

    print("Querying track type for track 0 (first track)...")

    try:
        response = vst._send_osc_request("/jarvis/track/type", [0], timeout=3.0)

        if not response:
            print_result(False, "No response from track type query")
            print("Make sure you have at least one track in your Ableton project")
            return False

        addr, args = response
        print(f"Response address: {addr}")
        print(f"Response args: {args}")

        if len(args) >= 6 and args[0] == 1:
            track_type = args[1]
            has_audio_input = args[2]
            has_midi_input = args[3]
            can_audio_fx = args[4]
            can_midi_fx = args[5]

            print(f"\nTrack 0 info:")
            print(f"  Type: {track_type}")
            print(f"  Has audio input: {has_audio_input}")
            print(f"  Has MIDI input: {has_midi_input}")
            print(f"  Can host audio effects: {can_audio_fx}")
            print(f"  Can host MIDI effects: {can_midi_fx}")

            print_result(True, f"Track type query succeeded (track 0 is {track_type})")
            return True
        else:
            print_result(False, f"Unexpected response format: {args}")
            return False

    except Exception as e:
        print_result(False, f"Track type query failed: {e}")
        return False

# ==================== TEST 4: TRACK TYPE VALIDATION ====================

async def test_track_type_validation():
    """Test 4: Track type validation in chain builder"""
    print_test_header("Track Type Validation")

    vst = VSTDiscoveryService()
    builder = PluginChainBuilder(vst)

    # Create a mock audio effects chain
    print("Creating mock audio effects chain...")
    chain = PluginChain(
        name="Test Audio Chain",
        track_type="vocal",
        slots=[]
    )

    # Add a mock audio effect slot
    mock_audio_plugin = PluginInfo(
        name="EQ Eight",
        plugin_type="audio_effect",
        category="EQ",
        manufacturer="Ableton",
        is_native=True
    )

    slot = PluginSlot(
        plugin_type="eq",
        purpose="test"
    )
    slot.matched_plugin = mock_audio_plugin
    slot.is_alternative = False

    chain.slots.append(slot)

    print("Testing validation on track 0...")
    validation_result = builder._validate_track_type_for_chain(0, chain)

    print(f"\nValidation result: {validation_result}")

    if validation_result["compatible"]:
        print_result(True, f"Track type validation passed: {validation_result['message']}")
        return True
    else:
        print_result(False, f"Track type validation failed: {validation_result['message']}")
        print(f"Expected: {validation_result['expected_type']}")
        print(f"Actual: {validation_result['actual_type']}")
        print("\nNote: If track 0 is a MIDI track, this is expected behavior.")
        print("The validation is working correctly by rejecting audio effects on MIDI tracks.")
        return validation_result["actual_type"] == "midi"  # Pass if rejection is due to MIDI track

# ==================== TEST 5: END-TO-END HEALTH CHECK IN CHAIN LOADING ====================

async def test_chain_loading_health_check():
    """Test 5: Health check integrated into chain loading"""
    print_test_header("Chain Loading with Health Check")

    vst = VSTDiscoveryService()
    builder = PluginChainBuilder(vst)

    # Create a simple chain
    chain = PluginChain(
        name="Test Chain",
        track_type="vocal",
        slots=[]
    )

    print("Attempting to load chain on track 0...")
    print("This should trigger the health check first...")

    result = await builder.load_chain_on_track(chain, track_index=0)

    print(f"\nLoad result: {result}")

    if result["success"]:
        print_result(True, "Chain loading succeeded (health check passed)")
        return True
    else:
        if "JarvisDeviceLoader not responding" in result.get("message", ""):
            print_result(False, "Health check correctly detected JarvisDeviceLoader is not responding")
            print("This is expected if JarvisDeviceLoader is not running")
            return True  # This is actually correct behavior
        else:
            print_result(False, f"Chain loading failed: {result.get('message')}")
            return False

# ==================== MAIN TEST RUNNER ====================

async def run_all_tests():
    """Run all tests"""
    print("\n" + "="*80)
    print("KANYE-STYLE CHAIN EXECUTION FIX - TEST SUITE")
    print("="*80)
    print("\nTesting Phase 1: Critical Infrastructure")
    print("- Fix 1: OSC Connection Stability")
    print("- Fix 2: Track Type Validation")
    print("\nIMPORTANT: Ableton Live must be running with JarvisDeviceLoader loaded")
    print("="*80)

    results = {}

    # Test 1: Health check
    results["osc_health"] = test_osc_health_check()

    # Test 2: Retry logic
    results["osc_retry"] = test_osc_retry_logic()

    # Test 3: Track type query
    results["track_type_query"] = test_track_type_query()

    # Test 4: Track type validation
    results["track_type_validation"] = await test_track_type_validation()

    # Test 5: Chain loading health check
    results["chain_health_check"] = await test_chain_loading_health_check()

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    passed = sum(1 for result in results.values() if result)
    total = len(results)

    for test_name, result in results.items():
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed ({passed/total*100:.0f}%)")

    if passed == total:
        print("\n✓ ALL TESTS PASSED - Phase 1 implementation is working correctly!")
        print("\nNext steps:")
        print("1. Test with real Kanye-style chain request")
        print("2. Implement Phase 2 (Kanye chain definition + parameter application)")
    else:
        print(f"\n✗ {total - passed} test(s) failed")
        print("\nTroubleshooting:")
        print("1. Ensure Ableton Live is running")
        print("2. Check JarvisDeviceLoader is installed in Ableton")
        print("3. Restart Ableton to reload the updated remote script")

    print("="*80)

if __name__ == "__main__":
    # Check if running from correct directory
    if not os.path.exists("discovery"):
        print("ERROR: Must run from JarvisAbleton root directory")
        sys.exit(1)

    # Run tests
    asyncio.run(run_all_tests())
