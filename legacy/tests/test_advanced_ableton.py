"""
Advanced Test Suite for Jarvis-Ableton OSC Integration

Tests all new advanced control categories:
- Track Management (create, delete, duplicate, rename)
- Device Query (list devices, get parameters)
- Device Parameter Control (set values, enable/disable)

IMPORTANT: Per AbletonOSC documentation:
- All indices are 0-based (Track 1 = index 0, Device 1 = index 0)
- Track/device/param IDs are PARAMETERS, not part of the OSC path

WARNING: Some tests will create/delete tracks. Run on a test project!
"""

from pythonosc.udp_client import SimpleUDPClient
import time
import sys

IP = "127.0.0.1"
PORT = 11000


def print_section(title):
    """Print a formatted section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_subsection(title):
    """Print a formatted subsection header"""
    print(f"\n{'-'*50}")
    print(f"  {title}")
    print(f"{'-'*50}")


def test_connection():
    """Test basic OSC connection"""
    print_section("Testing OSC Connection")
    try:
        client = SimpleUDPClient(IP, PORT)
        client.send_message("/live/test", [])
        print("✓ OSC connection established")
        return client
    except Exception as e:
        print(f"✗ OSC connection failed: {e}")
        print("\nMake sure:")
        print("  1. Ableton Live is running")
        print("  2. AbletonOSC is installed and selected in Control Surfaces")
        print("  3. OSC server is listening on port 11000")
        return None


# ==================== TRACK MANAGEMENT TESTS ====================

def test_create_audio_track(client):
    """Test creating audio tracks"""
    print_subsection("Create Audio Track")
    
    print("1. Creating audio track at end (-1)...")
    print("   Sending: /live/song/create_audio_track [-1]")
    client.send_message("/live/song/create_audio_track", [-1])
    time.sleep(1)
    print("   [CHECK] A new audio track should appear at the end")
    
    return True


def test_create_midi_track(client):
    """Test creating MIDI tracks"""
    print_subsection("Create MIDI Track")
    
    print("1. Creating MIDI track at end (-1)...")
    print("   Sending: /live/song/create_midi_track [-1]")
    client.send_message("/live/song/create_midi_track", [-1])
    time.sleep(1)
    print("   [CHECK] A new MIDI track should appear at the end")
    
    return True


def test_create_return_track(client):
    """Test creating return tracks"""
    print_subsection("Create Return Track")
    
    print("1. Creating return track...")
    print("   Sending: /live/song/create_return_track []")
    client.send_message("/live/song/create_return_track", [])
    time.sleep(1)
    print("   [CHECK] A new return track should appear")
    
    return True


def test_rename_track(client):
    """Test renaming a track"""
    print_subsection("Rename Track")
    
    print("1. Renaming Track 1 to 'Test Track'...")
    print("   Sending: /live/track/set/name [0, 'Test Track']")
    client.send_message("/live/track/set/name", [0, "Test Track"])
    time.sleep(1)
    print("   [CHECK] Track 1 should now be named 'Test Track'")
    
    return True


def test_duplicate_track(client):
    """Test duplicating a track"""
    print_subsection("Duplicate Track")
    
    print("1. Duplicating Track 1...")
    print("   Sending: /live/song/duplicate_track [0]")
    client.send_message("/live/song/duplicate_track", [0])
    time.sleep(1)
    print("   [CHECK] Track 1 should be duplicated")
    
    return True


def test_set_track_color(client):
    """Test setting track color"""
    print_subsection("Set Track Color")
    
    print("1. Setting Track 1 color to index 10 (orange/red)...")
    print("   Sending: /live/track/set/color_index [0, 10]")
    client.send_message("/live/track/set/color_index", [0, 10])
    time.sleep(1)
    print("   [CHECK] Track 1 color should change")
    
    return True


def test_delete_track(client):
    """Test deleting a track"""
    print_subsection("Delete Track")
    
    print("1. Getting track count first...")
    client.send_message("/live/song/get/num_tracks", [])
    time.sleep(0.5)
    
    print("2. Deleting the LAST track (to clean up)...")
    print("   NOTE: We'll delete index 3 (Track 4) if it exists")
    print("   Sending: /live/song/delete_track [3]")
    client.send_message("/live/song/delete_track", [3])
    time.sleep(1)
    print("   [CHECK] The track should be deleted")
    
    return True


def run_track_management_tests(client):
    """Run all track management tests"""
    print_section("TRACK MANAGEMENT TESTS")
    print("\n⚠️  WARNING: These tests CREATE and DELETE tracks!")
    print("   Run on a test project, not your production work!")
    
    input("\nPress ENTER to continue or Ctrl+C to abort...")
    
    test_create_audio_track(client)
    time.sleep(1)
    
    test_create_midi_track(client)
    time.sleep(1)
    
    test_create_return_track(client)
    time.sleep(1)
    
    test_rename_track(client)
    time.sleep(1)
    
    test_set_track_color(client)
    time.sleep(1)
    
    test_duplicate_track(client)
    time.sleep(1)
    
    # Optionally delete test tracks
    print("\n\n⚠️  Would you like to DELETE the test tracks created?")
    response = input("   Type 'yes' to delete: ")
    if response.lower() == 'yes':
        test_delete_track(client)


# ==================== DEVICE QUERY TESTS ====================

def test_get_num_devices(client):
    """Test getting device count"""
    print_subsection("Get Number of Devices")
    
    print("1. Querying device count on Track 1...")
    print("   Sending: /live/track/get/num_devices [0]")
    client.send_message("/live/track/get/num_devices", [0])
    time.sleep(0.5)
    print("   [CHECK] Response will be sent to /live/track/get/num_devices on port 11001")
    print("   NOTE: OSC responses are async - check Ableton logs or OSC monitor")
    
    return True


def test_get_device_names(client):
    """Test getting device names"""
    print_subsection("Get Device Names")
    
    print("1. Querying device names on Track 1...")
    print("   Sending: /live/track/get/devices/name [0]")
    client.send_message("/live/track/get/devices/name", [0])
    time.sleep(0.5)
    print("   [CHECK] Response includes list of device names on track")
    
    return True


def test_get_device_class_name(client):
    """Test getting device class name"""
    print_subsection("Get Device Class Name")
    
    print("1. Querying class name for Device 1 on Track 1...")
    print("   Sending: /live/device/get/class_name [0, 0]")
    client.send_message("/live/device/get/class_name", [0, 0])
    time.sleep(0.5)
    print("   [CHECK] Response includes class like 'Reverb', 'Compressor', etc.")
    
    return True


def test_get_device_parameters_names(client):
    """Test getting device parameter names"""
    print_subsection("Get Device Parameter Names")
    
    print("1. Querying parameter names for Device 1 on Track 1...")
    print("   Sending: /live/device/get/parameters/name [0, 0]")
    client.send_message("/live/device/get/parameters/name", [0, 0])
    time.sleep(0.5)
    print("   [CHECK] Response includes list of parameter names")
    
    return True


def test_get_device_parameter_value(client):
    """Test getting a specific parameter value"""
    print_subsection("Get Device Parameter Value")
    
    print("1. Querying parameter 0 value for Device 1 on Track 1...")
    print("   Sending: /live/device/get/parameter/value [0, 0, 0]")
    client.send_message("/live/device/get/parameter/value", [0, 0, 0])
    time.sleep(0.5)
    print("   [CHECK] Response includes the parameter value")
    
    return True


def run_device_query_tests(client):
    """Run all device query tests"""
    print_section("DEVICE QUERY TESTS")
    print("\nNOTE: These tests require at least one device on Track 1.")
    print("      Add a Reverb, Compressor, or any effect to Track 1 first.")
    
    input("\nPress ENTER to continue...")
    
    test_get_num_devices(client)
    time.sleep(1)
    
    test_get_device_names(client)
    time.sleep(1)
    
    test_get_device_class_name(client)
    time.sleep(1)
    
    test_get_device_parameters_names(client)
    time.sleep(1)
    
    test_get_device_parameter_value(client)
    time.sleep(1)


# ==================== DEVICE PARAMETER CONTROL TESTS ====================

def test_set_device_parameter(client):
    """Test setting a device parameter"""
    print_subsection("Set Device Parameter")
    
    print("1. Setting parameter 1 (often a main control) to 0.5...")
    print("   Sending: /live/device/set/parameter/value [0, 0, 1, 0.5]")
    client.send_message("/live/device/set/parameter/value", [0, 0, 1, 0.5])
    time.sleep(1)
    print("   [CHECK] Device parameter should change visually")
    
    print("\n2. Restoring parameter 1 to 0.7...")
    client.send_message("/live/device/set/parameter/value", [0, 0, 1, 0.7])
    time.sleep(1)
    print("   [CHECK] Device parameter should be restored")
    
    return True


def test_device_enable_disable(client):
    """Test enabling/disabling a device"""
    print_subsection("Enable/Disable Device")
    
    print("1. Disabling Device 1 on Track 1 (param 0 = on/off)...")
    print("   Sending: /live/device/set/parameter/value [0, 0, 0, 0]")
    client.send_message("/live/device/set/parameter/value", [0, 0, 0, 0])
    time.sleep(1)
    print("   [CHECK] Device should be bypassed (grayed out)")
    
    print("\n2. Re-enabling Device 1...")
    print("   Sending: /live/device/set/parameter/value [0, 0, 0, 1]")
    client.send_message("/live/device/set/parameter/value", [0, 0, 0, 1])
    time.sleep(1)
    print("   [CHECK] Device should be active again")
    
    return True


def run_device_parameter_tests(client):
    """Run all device parameter control tests"""
    print_section("DEVICE PARAMETER CONTROL TESTS")
    print("\nNOTE: These tests require at least one device on Track 1.")
    print("      The device will be modified during testing.")
    
    input("\nPress ENTER to continue...")
    
    test_device_enable_disable(client)
    time.sleep(1)
    
    test_set_device_parameter(client)
    time.sleep(1)


# ==================== MAIN TEST RUNNER ====================

def run_all_tests():
    """Run all advanced tests"""
    print("\n" + "="*60)
    print("  JARVIS-ABLETON ADVANCED TEST SUITE")
    print("  (Track Management, Device Query, Parameter Control)")
    print("="*60)
    print("\nThis will test all advanced Ableton OSC controls.")
    print("Watch Ableton Live to verify each action.\n")
    
    # Test connection first
    client = test_connection()
    if not client:
        print("\n✗ Tests aborted - no OSC connection")
        return
    
    # Menu for test selection
    print("\n" + "-"*50)
    print("  SELECT TEST SUITE")
    print("-"*50)
    print("  1. Track Management (create, delete, duplicate)")
    print("  2. Device Query (list devices, parameters)")
    print("  3. Device Parameter Control (set values)")
    print("  4. All tests")
    print("  5. Quick smoke test (non-destructive)")
    print("-"*50)
    
    choice = input("\nEnter choice (1-5): ").strip()
    
    if choice == "1":
        run_track_management_tests(client)
    elif choice == "2":
        run_device_query_tests(client)
    elif choice == "3":
        run_device_parameter_tests(client)
    elif choice == "4":
        run_track_management_tests(client)
        run_device_query_tests(client)
        run_device_parameter_tests(client)
    elif choice == "5":
        run_quick_smoke_test(client)
    else:
        print("Invalid choice. Running quick smoke test...")
        run_quick_smoke_test(client)
    
    # Summary
    print_section("Test Suite Complete")
    print("\n✓ All tests executed")
    print("\nReview the checks above to verify each worked correctly.")
    print("\nIf all checks passed, run: python jarvis_engine.py")


def run_quick_smoke_test(client):
    """Run a quick non-destructive smoke test"""
    print_section("QUICK SMOKE TEST (Non-Destructive)")
    
    print("\n1. Testing track name query...")
    client.send_message("/live/song/get/track_names", [])
    time.sleep(0.5)
    print("   ✓ Track names query sent")
    
    print("\n2. Testing device query on Track 1...")
    client.send_message("/live/track/get/devices/name", [0])
    time.sleep(0.5)
    print("   ✓ Device names query sent")
    
    print("\n3. Testing tempo query...")
    client.send_message("/live/song/get/tempo", [])
    time.sleep(0.5)
    print("   ✓ Tempo query sent")
    
    print("\n4. Testing scene count query...")
    client.send_message("/live/song/get/num_scenes", [])
    time.sleep(0.5)
    print("   ✓ Scene count query sent")
    
    print("\n✓ Smoke test complete - no changes made to your project")


def run_specific_test(test_name):
    """Run a specific test by name"""
    client = test_connection()
    if not client:
        return
    
    tests = {
        "create_audio": test_create_audio_track,
        "create_midi": test_create_midi_track,
        "create_return": test_create_return_track,
        "rename": test_rename_track,
        "duplicate": test_duplicate_track,
        "delete": test_delete_track,
        "color": test_set_track_color,
        "num_devices": test_get_num_devices,
        "device_names": test_get_device_names,
        "device_class": test_get_device_class_name,
        "param_names": test_get_device_parameters_names,
        "param_value": test_get_device_parameter_value,
        "set_param": test_set_device_parameter,
        "enable_disable": test_device_enable_disable,
    }
    
    if test_name in tests:
        tests[test_name](client)
    else:
        print(f"\nUnknown test: {test_name}")
        print(f"Available tests: {', '.join(tests.keys())}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Run specific test
        run_specific_test(sys.argv[1])
    else:
        # Run all tests interactively
        run_all_tests()

