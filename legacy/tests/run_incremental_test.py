"""
Incremental Chain Test with Crash Recovery

Runs a 3-device test, clears, then runs a 5-device test.
Designed for safe testing after Ableton restarts.
Now includes automatic crash detection and recovery!

Usage:
    python tests/run_incremental_test.py              # Normal mode with auto-recovery
    python tests/run_incremental_test.py --strict     # Fail if track can't be cleared
    python tests/run_incremental_test.py --diagnose   # Test JarvisDeviceLoader connection first
    python tests/run_incremental_test.py --no-recovery  # Disable automatic crash recovery
"""

import argparse
import sys
import time
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.chain_test_utils import (
    run_chain_test, print_chain_report, create_reliable_controller,
    get_device_count, clear_track_devices, print_summary,
    test_jarvis_device_loader_connection, validate_jarvis_device_loader
)
from tests.crash_resilient_wrapper import get_crash_detector, with_crash_recovery
from ableton_controls.process_manager import get_ableton_manager


def get_3_device_chain():
    """Simple 3-device chain: EQ → Compressor → Reverb"""
    return [
        {
            "type": "eq",
            "name": "EQ Eight",
            "settings": {
                "1 Filter On A": 1.0,
                "1 Gain A": 0.0,
            }
        },
        {
            "type": "compressor",
            "name": "Compressor",
            "settings": {
                "Ratio": 0.5,  # Use normalized value (0-1)
                "Dry/Wet": 1.0,
            }
        },
        {
            "type": "reverb",
            "name": "Reverb",
            "settings": {
                "Dry/Wet": 0.25,
            }
        },
    ]


def get_5_device_chain():
    """5-device chain: EQ → Compressor → Saturator → EQ → Reverb"""
    return [
        {
            "type": "eq",
            "name": "EQ Eight",
            "settings": {
                "1 Filter On A": 1.0,
                "3 Gain A": 2.0,  # Gain works with proper range -15 to 15
            }
        },
        {
            "type": "compressor", 
            "name": "Compressor",
            "settings": {
                "Dry/Wet": 1.0,
            }
        },
        {
            "type": "saturation",
            "name": "Saturator",
            "settings": {
                "Drive": 6.0,  # Works with range -36 to 36
                "Dry/Wet": 0.4,
            }
        },
        {
            "type": "eq",
            "name": "EQ Eight",
            "settings": {
                "4 Gain A": 1.5,
            }
        },
        {
            "type": "reverb",
            "name": "Reverb",
            "settings": {
                "Dry/Wet": 0.3,
            }
        },
    ]


@with_crash_recovery("ensure_track_clear")
def ensure_track_clear(track_index: int, reliable, strict: bool = False, 
                       test_name: str = "test", crash_detector=None) -> bool:
    """
    Ensure track is clear before starting a test (with crash recovery).
    
    Args:
        track_index: Track to clear
        reliable: ReliableParameterController instance
        strict: If True, exit on failure; if False, warn and continue
        test_name: Name of the test (for error messages)
        crash_detector: CrashDetector instance (optional)
        
    Returns:
        True if track is clear (0 devices), False otherwise
    """
    current_count = get_device_count(track_index)
    
    if current_count == 0:
        print(f"   ✅ Track {track_index} is already clear")
        return True
    
    print(f"\n🧹 Clearing {current_count} devices from track {track_index}...")
    
    # Check if Ableton is running before clearing
    if crash_detector:
        if not crash_detector.verify_ableton_running():
            print("   ⚠️ Ableton not running! Attempting recovery...")
            if not crash_detector.recover_from_crash():
                print("   ❌ Recovery failed")
                return False
    
    # Use gentle mode to prevent Ableton crashes from rapid OSC messages
    clear_result = clear_track_devices(track_index, reliable, max_attempts=3, 
                                        verbose=True, gentle=True)
    
    # Give Ableton time to stabilize after clearing
    # Longer pause prevents socket errors from occurring during subsequent device loading
    print(f"   ⏳ Waiting for Ableton to stabilize (5 seconds)...")
    time.sleep(5.0)
    
    final_count = get_device_count(track_index)
    
    if final_count == 0:
        print(f"   ✅ Track cleared and stable")
        return True
    
    # Track still has devices
    print(f"\n   ❌ FAILED: Track still has {final_count} devices")
    
    if clear_result.get("errors"):
        print(f"   📋 Errors encountered:")
        for error in clear_result["errors"][:5]:  # Show first 5 errors
            print(f"      - {error}")
    
    if strict:
        print(f"\n   🛑 STRICT MODE: Cannot proceed with {test_name}")
        print(f"   💡 Please manually clear Track {track_index + 1} in Ableton and re-run")
        return False
    else:
        print(f"\n   ⚠️ WARNING: Proceeding with {final_count} existing devices on track")
        print(f"   💡 Run with --strict flag to enforce clean track requirement")
        return True  # Continue anyway in non-strict mode


def diagnose_connection():
    """Run diagnostics to check JarvisDeviceLoader connection"""
    print("\n" + "=" * 60)
    print("🔍 DIAGNOSTICS: Testing JarvisDeviceLoader Connection")
    print("=" * 60)
    
    print("\n📡 Testing OSC connection to port 11002...")
    result = test_jarvis_device_loader_connection(timeout=3.0)
    
    if result["connected"]:
        print(f"   ✅ Connected! Response time: {result['response_time_ms']}ms")
        return True
    else:
        print(f"   ❌ {result['message']}")
        print("\n   💡 Troubleshooting:")
        print("      1. Is Ableton Live running?")
        print("      2. Is JarvisDeviceLoader selected in Preferences > MIDI > Control Surface?")
        print("      3. Check Ableton's Log.txt for JarvisDeviceLoader messages")
        print("      4. Remote Script path: C:\\ProgramData\\Ableton\\Live 11\\Resources\\MIDI Remote Scripts\\JarvisDeviceLoader\\")
        return False


def main():
    parser = argparse.ArgumentParser(description="Run incremental chain building tests with crash recovery")
    parser.add_argument("--strict", action="store_true", 
                       help="Fail immediately if track cannot be cleared")
    parser.add_argument("--diagnose", action="store_true",
                       help="Test JarvisDeviceLoader connection before running tests")
    parser.add_argument("--track", type=int, default=0,
                       help="Track index to use for tests (default: 0)")
    parser.add_argument("--no-recovery", action="store_true",
                       help="Disable automatic crash recovery")
    args = parser.parse_args()
    
    track_index = args.track
    strict = args.strict
    results = []
    
    # Initialize crash recovery system
    if not args.no_recovery:
        print("\n" + "=" * 60)
        print("🛡️  CRASH RECOVERY ENABLED")
        print("=" * 60)
        print("  - Ableton crashes will be automatically detected")
        print("  - System will restart Ableton and resume tests")
        print("  - Recovery dialogs will be handled automatically")
        print("  - Use --no-recovery to disable this feature")
        print("=" * 60 + "\n")
        
        crash_detector = get_crash_detector(
            auto_recover=True,
            max_recovery_attempts=3,
            recovery_wait=20.0,
            verbose=True
        )
        
        # Ensure Ableton is running
        ableton_manager = get_ableton_manager(verbose=True)
        if not ableton_manager.ensure_ableton_running():
            print("\n❌ Failed to start Ableton. Cannot proceed.")
            sys.exit(1)
        
        print("\n✅ Ableton is ready\n")
        time.sleep(2)
    else:
        crash_detector = None
        print("\n⚠️  Crash recovery disabled\n")
    
    # Run diagnostics if requested
    if args.diagnose:
        if not diagnose_connection():
            print("\n❌ Diagnostics failed. Fix connection issues before running tests.")
            sys.exit(1)
        print("\n✅ Diagnostics passed. Proceeding with tests...\n")
        time.sleep(1)
    
    # CRITICAL: Validate JarvisDeviceLoader Remote Script is loaded
    print("\n" + "=" * 60)
    print("📡 VALIDATING JARVISDEVICELOADER REMOTE SCRIPT")
    print("=" * 60)
    
    validation = validate_jarvis_device_loader(timeout=3.0)
    
    if not validation.get("loaded"):
        print(f"\n❌ {validation.get('message', 'JarvisDeviceLoader not responding')}")
        print("\n" + "=" * 60)
        print("🔧 ACTION REQUIRED: JarvisDeviceLoader Remote Script is NOT loaded!")
        print("=" * 60)
        print("""
The tests require JarvisDeviceLoader to be configured in Ableton.

To fix this:
1. Open Ableton Live
2. Go to Preferences (Ctrl+,) > Link/Tempo/MIDI
3. Under 'Control Surface', find an empty slot (shows 'None')
4. Click the dropdown and select 'JarvisDeviceLoader'
5. Click 'Close' and the script will start automatically

The Remote Script should be installed at:
Windows: C:\\ProgramData\\Ableton\\Live 11\\Resources\\MIDI Remote Scripts\\JarvisDeviceLoader\\
""")
        print("=" * 60)
        
        # Ask if user wants to continue anyway
        try:
            response = input("\n⚠️  Continue anyway? Tests will likely fail. (y/N): ")
            if response.lower() != 'y':
                print("\n👋 Exiting. Please configure JarvisDeviceLoader and try again.")
                sys.exit(1)
            print("\n⚠️  Continuing without JarvisDeviceLoader - expect failures\n")
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Exiting. Please configure JarvisDeviceLoader and try again.")
            sys.exit(1)
    else:
        print(f"\n✅ {validation.get('message', 'JarvisDeviceLoader is responding')}")
        print("=" * 60 + "\n")
    
    reliable = create_reliable_controller(verbose=False)
    
    # Check initial state
    initial = get_device_count(track_index)
    print(f"\n📊 Initial state: {initial} devices on track {track_index}")
    
    if strict:
        print("🔒 STRICT MODE: Tests will fail if track cannot be cleared")
    
    # === TEST 1: 3-Device Chain ===
    print("\n" + "=" * 60)
    print("🎯 TEST 1: 3-Device Chain")
    print("   EQ Eight → Compressor → Reverb")
    print("=" * 60)
    
    # Ensure track is clear
    if not ensure_track_clear(track_index, reliable, strict=strict, 
                              test_name="Test 1", crash_detector=crash_detector):
        sys.exit(1)
    
    before_test1 = get_device_count(track_index)
    print(f"\n   📋 Devices before test: {before_test1}")
    
    if strict and before_test1 != 0:
        print(f"   ❌ ASSERTION FAILED: Expected 0 devices, found {before_test1}")
        sys.exit(1)
    
    # Run test
    chain_3 = get_3_device_chain()
    result_3 = run_chain_test(
        chain_name="3_device_test",
        chain_devices=chain_3,
        track_index=track_index,
        clear_track=False,  # We already cleared
        verbose=True
    )
    results.append(result_3)
    print_chain_report(result_3)
    
    after_test1 = get_device_count(track_index)
    expected_devices_1 = len(chain_3)
    print(f"📊 Devices after Test 1: {after_test1} (expected: {expected_devices_1})")
    
    if after_test1 != before_test1 + expected_devices_1:
        print(f"   ⚠️ Device count mismatch!")
    
    # Pause between tests
    print("\n⏳ Pausing 3 seconds before next test...")
    time.sleep(3)
    
    # === TEST 2: 5-Device Chain ===
    print("\n" + "=" * 60)
    print("🎯 TEST 2: 5-Device Chain")
    print("   EQ → Compressor → Saturator → EQ → Reverb")
    print("=" * 60)
    
    # Ensure track is clear
    if not ensure_track_clear(track_index, reliable, strict=strict, 
                              test_name="Test 2", crash_detector=crash_detector):
        sys.exit(1)
    
    before_test2 = get_device_count(track_index)
    print(f"\n   📋 Devices before test: {before_test2}")
    
    if strict and before_test2 != 0:
        print(f"   ❌ ASSERTION FAILED: Expected 0 devices, found {before_test2}")
        sys.exit(1)
    
    # Run test
    chain_5 = get_5_device_chain()
    result_5 = run_chain_test(
        chain_name="5_device_test",
        chain_devices=chain_5,
        track_index=track_index,
        clear_track=False,  # We already cleared
        verbose=True
    )
    results.append(result_5)
    print_chain_report(result_5)
    
    after_test2 = get_device_count(track_index)
    expected_devices_2 = len(chain_5)
    print(f"📊 Devices after Test 2: {after_test2} (expected: {expected_devices_2})")
    
    # Final summary
    print_summary(results)
    
    # Final cleanup
    print("\n🧹 Final cleanup...")
    clear_result = clear_track_devices(track_index, reliable, max_attempts=5, verbose=True)
    
    time.sleep(0.5)
    final = get_device_count(track_index)
    print(f"\n📊 Final device count: {final}")
    
    if final == 0:
        print("✅ Track cleaned up successfully")
    else:
        print(f"⚠️ {final} devices remain on track (manual cleanup may be needed)")
    
    # Exit code based on test results
    all_passed = all(r.overall_success for r in results)
    if all_passed:
        print("\n🎉 ALL TESTS PASSED!")
        sys.exit(0)
    else:
        print("\n❌ SOME TESTS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
