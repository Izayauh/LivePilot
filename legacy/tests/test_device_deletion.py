"""
Device Deletion Diagnostic Test

Tests the device deletion functionality in isolation to diagnose issues
with clearing devices from tracks.

Usage:
    python tests/test_device_deletion.py           # Run all diagnostics
    python tests/test_device_deletion.py --quick   # Quick connection test only
"""

import argparse
import sys
import time
import os
import socket

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.chain_test_utils import (
    create_reliable_controller, get_device_count, delete_device_via_osc,
    clear_track_devices, test_jarvis_device_loader_connection
)


def test_port_accessibility():
    """Test if port 11002 is accessible"""
    print("\n🔌 Testing port 11002 accessibility...")
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1.0)
        sock.sendto(b"test", ('127.0.0.1', 11002))
        sock.close()
        print("   ✅ Can send UDP to port 11002")
        return True
    except Exception as e:
        print(f"   ❌ Cannot access port 11002: {e}")
        return False


def test_jarvis_connection():
    """Test JarvisDeviceLoader connection"""
    print("\n📡 Testing JarvisDeviceLoader connection...")
    
    result = test_jarvis_device_loader_connection(timeout=3.0)
    
    if result["connected"]:
        print(f"   ✅ JarvisDeviceLoader responding ({result['response_time_ms']}ms)")
        return True
    else:
        print(f"   ❌ {result['message']}")
        return False


def test_load_single_device(track_index: int = 0):
    """Test loading a single device to have something to delete"""
    print(f"\n📦 Loading test device on track {track_index}...")
    
    reliable = create_reliable_controller(verbose=True)
    
    # Try to load EQ Eight (a common Ableton device)
    try:
        result = reliable.load_device_verified(
            track_index=track_index,
            device_name="EQ Eight",
            timeout=5.0
        )
        
        if result.get("success"):
            print(f"   ✅ EQ Eight loaded at index {result.get('device_index')}")
            return result.get("device_index", -1)
        else:
            print(f"   ❌ Failed to load device: {result.get('message')}")
            return -1
    except Exception as e:
        print(f"   ❌ Error loading device: {e}")
        return -1


def test_delete_single_device(track_index: int = 0, device_index: int = 0):
    """Test deleting a single device"""
    print(f"\n🗑️ Testing device deletion (track={track_index}, device={device_index})...")
    
    # Get device count before
    before = get_device_count(track_index)
    print(f"   Devices before: {before}")
    
    if device_index >= before:
        print(f"   ⚠️ No device at index {device_index} (only {before} devices)")
        return False
    
    # Try to delete
    result = delete_device_via_osc(track_index, device_index, timeout=3.0, verbose=True)
    
    print(f"   Result: {result}")
    
    # Wait for deletion to complete
    time.sleep(1.0)
    
    # Check count after
    after = get_device_count(track_index)
    print(f"   Devices after: {after}")
    
    if after < before:
        print(f"   ✅ Device deleted! ({before} -> {after})")
        return True
    else:
        print(f"   ❌ Device NOT deleted (count unchanged: {before})")
        return False


def test_clear_all_devices(track_index: int = 0):
    """Test clearing all devices from track"""
    print(f"\n🧹 Testing full track clear (track={track_index})...")
    
    reliable = create_reliable_controller(verbose=False)
    before = get_device_count(track_index)
    
    print(f"   Devices before: {before}")
    
    if before == 0:
        print("   ⚠️ Track already empty - nothing to clear")
        return True
    
    result = clear_track_devices(track_index, reliable, max_attempts=5, verbose=True)
    
    # Wait for operations to complete
    time.sleep(0.5)
    
    after = get_device_count(track_index)
    print(f"\n   Devices after: {after}")
    print(f"   Deletion result: {result}")
    
    if result.get("success") and after == 0:
        print(f"   ✅ Track cleared successfully!")
        return True
    elif after < before:
        print(f"   ⚠️ Partial success: {before - after} deleted, {after} remaining")
        return False
    else:
        print(f"   ❌ Failed to clear track")
        return False


def run_full_diagnostic(track_index: int = 0):
    """Run full diagnostic sequence"""
    print("\n" + "=" * 70)
    print("🔍 DEVICE DELETION DIAGNOSTIC TEST")
    print("=" * 70)
    
    results = {}
    
    # Test 1: Port accessibility
    results["port"] = test_port_accessibility()
    
    # Test 2: JarvisDeviceLoader connection
    results["connection"] = test_jarvis_connection()
    
    if not results["connection"]:
        print("\n" + "=" * 70)
        print("❌ DIAGNOSTIC FAILED: JarvisDeviceLoader not responding")
        print("=" * 70)
        print("\n💡 TROUBLESHOOTING STEPS:")
        print("   1. Ensure Ableton Live is running")
        print("   2. Go to Preferences > Link/Tempo/MIDI > Control Surface")
        print("   3. Set a Control Surface slot to 'JarvisDeviceLoader'")
        print("   4. Check Ableton's Log.txt for initialization messages")
        print(f"   5. Verify script exists at:")
        print("      C:\\ProgramData\\Ableton\\Live 11\\Resources\\MIDI Remote Scripts\\JarvisDeviceLoader\\")
        return False
    
    # Test 3: Get current device count
    print(f"\n📊 Current device count on track {track_index}...")
    current = get_device_count(track_index)
    print(f"   Found {current} devices")
    
    # Test 4: If devices exist, try to delete one
    if current > 0:
        results["delete_single"] = test_delete_single_device(track_index, current - 1)
    else:
        print("\n🧪 Loading a test device to verify deletion works...")
        device_idx = test_load_single_device(track_index)
        if device_idx >= 0:
            time.sleep(1)
            results["delete_single"] = test_delete_single_device(track_index, device_idx)
        else:
            results["delete_single"] = None
            print("   ⚠️ Could not load test device - skipping deletion test")
    
    # Test 5: Test full clear
    current = get_device_count(track_index)
    if current > 0:
        results["clear_all"] = test_clear_all_devices(track_index)
    else:
        results["clear_all"] = True
        print("\n   ℹ️ Track already empty - clearing not needed")
    
    # Summary
    print("\n" + "=" * 70)
    print("📋 DIAGNOSTIC SUMMARY")
    print("=" * 70)
    
    all_passed = True
    for test_name, passed in results.items():
        if passed is None:
            status = "⚠️ SKIPPED"
        elif passed:
            status = "✅ PASS"
        else:
            status = "❌ FAIL"
            all_passed = False
        print(f"   {test_name}: {status}")
    
    print("=" * 70)
    
    if all_passed:
        print("\n🎉 ALL DIAGNOSTICS PASSED!")
        print("   Device deletion is working correctly.")
        print("   You can now run the full chain tests with confidence.")
        return True
    else:
        print("\n❌ SOME DIAGNOSTICS FAILED")
        print("   Device deletion may not be working correctly.")
        print("\n💡 NEXT STEPS:")
        if not results.get("connection"):
            print("   - Ensure JarvisDeviceLoader Remote Script is installed and active")
        if results.get("delete_single") is False:
            print("   - Check Ableton's Log.txt for deletion error messages")
            print("   - Verify track is not in a state that prevents device deletion")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test device deletion functionality")
    parser.add_argument("--quick", action="store_true",
                       help="Quick connection test only")
    parser.add_argument("--track", type=int, default=0,
                       help="Track index to test on (default: 0)")
    parser.add_argument("--delete-only", action="store_true",
                       help="Only test deleting devices (skip loading)")
    args = parser.parse_args()
    
    if args.quick:
        print("\n🔍 Quick Diagnostic Mode")
        if test_jarvis_connection():
            print("\n✅ JarvisDeviceLoader is connected and responding!")
            sys.exit(0)
        else:
            print("\n❌ JarvisDeviceLoader not responding!")
            sys.exit(1)
    
    if args.delete_only:
        print(f"\n🗑️ Delete-Only Mode (track {args.track})")
        if test_clear_all_devices(args.track):
            sys.exit(0)
        else:
            sys.exit(1)
    
    # Full diagnostic
    if run_full_diagnostic(args.track):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

