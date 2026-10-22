"""
Device Parameter Testing Suite

Tests:
1. Parameter setting on native Ableton devices (EQ Eight)
2. Discovering actual parameter indices
3. VST loading capabilities
4. VST parameter access via OSC
"""

from pythonosc.udp_client import SimpleUDPClient
import time
import json

import pytest

IP = "127.0.0.1"
PORT = 11000


@pytest.fixture(name="client")
def client_fixture():
    """Live-Ableton OSC client, or skip.

    This file is a live-integration diagnostic: every test drives a running
    Ableton over AbletonOSC. Under bare pytest the functions previously errored
    with "fixture 'client' not found" (2026-08-21), which read as 4 suite
    failures when nothing was broken. UDP has no handshake, so reachability is
    checked by asking AbletonOSC for a reply on its response port.
    """
    import socket

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.settimeout(1.5)
    try:
        probe.bind((IP, 11001))  # AbletonOSC replies on 11001
    except OSError:
        probe.close()
        pytest.skip("port 11001 busy (another listener owns the OSC reply port)")
    try:
        SimpleUDPClient(IP, PORT).send_message("/live/test", [])
        probe.recvfrom(1024)
    except (socket.timeout, OSError):
        pytest.skip("Ableton (AbletonOSC on :11000) is not running")
    finally:
        probe.close()
    return SimpleUDPClient(IP, PORT)

def print_section(title):
    """Print a formatted section header"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


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
        return None


def discover_device_parameters(client, track_index, device_index):
    """
    Discover all parameters for a device.
    
    Note: This sends a query but doesn't receive the response directly.
    The response goes back to AbletonOSC's callback system.
    We need to use the listener approach or check ableton_controls.
    """
    print(f"\n  Querying parameters for device {device_index} on track {track_index}...")
    
    # Send queries
    client.send_message("/live/device/get/name", [track_index, device_index])
    time.sleep(0.1)
    client.send_message("/live/device/get/class_name", [track_index, device_index])
    time.sleep(0.1)
    client.send_message("/live/device/get/parameters/name", [track_index, device_index])
    time.sleep(0.1)
    client.send_message("/live/device/get/parameters/value", [track_index, device_index])
    
    print("  Query messages sent. Check Ableton's OSC log for parameter names.")
    print("  NOTE: AbletonOSC returns data via callbacks, not in this script.")


def load_device_manual(client, track_index, device_name):
    """
    Attempt to load a device using direct browser control.
    
    Note: Standard AbletonOSC doesn't have device loading.
    This requires the JarvisDeviceLoader Remote Script.
    """
    print(f"\n  Loading '{device_name}' on track {track_index}...")
    
    # Try using ableton_controls module which has device loading
    try:
        from ableton_controls import ableton
        result = ableton.load_device(track_index, device_name, -1)
        
        if result.get("success"):
            print(f"  ✓ Device load request sent: {result.get('message')}")
            return True
        else:
            print(f"  ✗ Device load failed: {result.get('message')}")
            return False
    except Exception as e:
        print(f"  ✗ Error loading device: {e}")
        return False


def test_native_device_params(client, track_index=0, device_index=0):
    """
    Test parameter setting on a native Ableton device.
    
    PREREQUISITE: Make sure there's an EQ Eight (or any device) already 
    loaded on the specified track at the specified device slot.
    """
    print_section("TEST 1: Native Device Parameter Setting")
    
    print("\n  PREREQUISITE: Load an EQ Eight on Track 1 BEFORE running this test")
    print("  (Manually drag EQ Eight onto Track 1 in Ableton)")
    
    input("\n  Press ENTER when EQ Eight is loaded on Track 1...")
    
    # First, discover the device
    print_subsection("Step 1: Discovering Device Info")
    discover_device_parameters(client, track_index, device_index)
    
    print_subsection("Step 2: Testing Parameter Setting")
    
    # EQ Eight Parameter Tests
    # Based on observation, EQ Eight parameters include:
    # - Band frequencies, gains, Qs, types, and enable states
    # We'll test a few and see what happens
    
    test_params = [
        (1, 500.0, "Param 1 (may be Band 1 Freq or similar)"),
        (2, 0.5, "Param 2"),
        (3, 1.0, "Param 3"),
        (5, 1000.0, "Param 5"),
        (9, 2000.0, "Param 9"),
    ]
    
    print("\n  Setting parameters on EQ Eight (device 0, track 0):")
    
    for param_idx, value, description in test_params:
        try:
            client.send_message(
                "/live/device/set/parameter/value",
                [track_index, device_index, param_idx, float(value)]
            )
            print(f"  → Set param {param_idx} = {value} ({description})")
            time.sleep(0.2)
        except Exception as e:
            print(f"  ✗ Error setting param {param_idx}: {e}")
    
    print("\n  [CHECK] Look at EQ Eight in Ableton - did any parameters change?")
    print("  [CHECK] If yes, note which parameter indices moved which controls.")


def test_eq_eight_specific(client, track_index=0, device_index=0):
    """
    Test specific EQ Eight parameters based on known structure.
    
    EQ Eight structure (typical - may vary by Ableton version):
    - Param 0: Device On
    - Param 1: Band 1 On
    - Param 2: Band 1 Type (0-7)
    - Param 3: Band 1 Freq
    - Param 4: Band 1 Gain  
    - Param 5: Band 1 Q
    ... repeats for bands 2-8 ...
    - Plus global Scale, Output, etc.
    """
    print_section("TEST 2: EQ Eight Specific Parameters")
    
    print("\n  Testing EQ Eight parameters with known structure...")
    print("  (Make sure EQ Eight is on Track 1, Device slot 1)")
    
    # Test Band 1 Frequency (param 3 if structure is correct)
    print("\n  Test A: Setting Band 1 Frequency to 100 Hz (param 3)")
    client.send_message("/live/device/set/parameter/value", 
                       [track_index, device_index, 3, 100.0])
    time.sleep(0.5)
    print("  [CHECK] Did Band 1 frequency change to ~100 Hz?")
    
    # Test Band 1 Gain (param 4 if structure is correct)
    print("\n  Test B: Setting Band 1 Gain to -6 dB (param 4)")
    client.send_message("/live/device/set/parameter/value",
                       [track_index, device_index, 4, -6.0])
    time.sleep(0.5)
    print("  [CHECK] Did Band 1 gain change to -6 dB?")
    
    # Test Band 1 Q (param 5 if structure is correct)
    print("\n  Test C: Setting Band 1 Q to 2.0 (param 5)")
    client.send_message("/live/device/set/parameter/value",
                       [track_index, device_index, 5, 2.0])
    time.sleep(0.5)
    print("  [CHECK] Did Band 1 Q change?")
    
    # Test Band 1 Type (param 2 if structure is correct)
    print("\n  Test D: Setting Band 1 Type to Low Cut (param 2, value 0)")
    client.send_message("/live/device/set/parameter/value",
                       [track_index, device_index, 2, 0.0])
    time.sleep(0.5)
    print("  [CHECK] Did Band 1 become a Low Cut filter?")
    
    # Reset to Peak
    print("\n  Test E: Setting Band 1 Type back to Peak (param 2, value 2)")
    client.send_message("/live/device/set/parameter/value",
                       [track_index, device_index, 2, 2.0])
    time.sleep(0.5)
    print("  [CHECK] Did Band 1 become a Peak filter?")


def test_param_range_discovery(client, track_index=0, device_index=0, max_params=50):
    """
    Try setting each parameter to see which ones exist and what they control.
    """
    print_section("TEST 3: Parameter Range Discovery")
    
    print(f"\n  Testing params 0-{max_params-1} with value 0.5...")
    print("  Watch Ableton to see which parameters respond.\n")
    
    for i in range(max_params):
        try:
            # Set to 0.5 (middle value for normalized params)
            client.send_message(
                "/live/device/set/parameter/value",
                [track_index, device_index, i, 0.5]
            )
            print(f"  Param {i:2d}: sent value 0.5")
            time.sleep(0.1)
        except Exception as e:
            print(f"  Param {i:2d}: error - {e}")
    
    print("\n  [CHECK] Note which parameter indices caused visible changes")
    print("  Write down the indices and what controls moved!")


def test_vst_discovery():
    """Test if VST Discovery finds third-party plugins"""
    print_section("TEST 4: VST Discovery")
    
    try:
        from discovery.vst_discovery import get_vst_discovery
        vst = get_vst_discovery()
        
        print("\n  Loading plugin cache...")
        all_plugins = vst.get_all_plugins()
        
        print(f"\n  Found {len(all_plugins)} plugins in cache:")
        
        # Group by type
        by_type = {}
        for plugin in all_plugins:
            ptype = plugin.plugin_type
            if ptype not in by_type:
                by_type[ptype] = []
            by_type[ptype].append(plugin.name)
        
        for ptype, names in by_type.items():
            print(f"\n  {ptype.upper()} ({len(names)}):")
            for name in names[:10]:  # Show first 10
                print(f"    - {name}")
            if len(names) > 10:
                print(f"    ... and {len(names) - 10} more")
        
        # Check for common third-party plugins
        print("\n  Checking for common third-party plugins:")
        third_party = ["FabFilter", "Waves", "iZotope", "Soundtoys", "UAD"]
        for vendor in third_party:
            matches = [p.name for p in all_plugins if vendor.lower() in p.name.lower()]
            if matches:
                print(f"    ✓ {vendor}: {len(matches)} plugins found")
                for m in matches[:3]:
                    print(f"      - {m}")
            else:
                print(f"    ✗ {vendor}: No plugins found")
        
        return True
        
    except Exception as e:
        print(f"\n  ✗ VST Discovery Error: {e}")
        return False


def test_vst_loading():
    """Test loading a third-party VST"""
    print_section("TEST 5: VST Loading")
    
    try:
        from discovery.vst_discovery import get_vst_discovery
        vst = get_vst_discovery()
        
        # First check if we have any VSTs
        plugins = vst.get_all_plugins()
        
        if not plugins:
            print("\n  No plugins in cache. Attempting refresh...")
            vst.refresh_plugins()
            plugins = vst.get_all_plugins()
        
        if not plugins:
            print("\n  ✗ No plugins available. JarvisDeviceLoader may not be responding.")
            return False
        
        # Try to load the first VST plugin (not native)
        vst_plugins = [p for p in plugins if 'plugin' in p.plugin_type.lower()]
        
        if vst_plugins:
            test_plugin = vst_plugins[0].name
            print(f"\n  Attempting to load VST: {test_plugin}")
            
            result = vst.load_device_on_track(0, test_plugin, -1)
            
            if result.get('success'):
                print(f"  ✓ Load request sent: {result}")
                print("\n  [CHECK] Did the VST appear on Track 1 in Ableton?")
                return True
            else:
                print(f"  ✗ Load failed: {result}")
                return False
        else:
            # Try loading a native device
            print("\n  No VST plugins found, testing with native device...")
            
            from ableton_controls import ableton
            result = ableton.load_device(0, "Compressor", -1)
            
            print(f"\n  Load result: {result}")
            print("\n  [CHECK] Did a Compressor appear on Track 1?")
            return result.get('success', False)
            
    except Exception as e:
        print(f"\n  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_vst_params(client, track_index=0, device_index=0):
    """Test setting parameters on a VST"""
    print_section("TEST 6: VST Parameter Access")
    
    print("\n  PREREQUISITE: Make sure a third-party VST is loaded on Track 1")
    print("  (e.g., FabFilter Pro-Q, Waves plugin, etc.)")
    
    input("\n  Press ENTER when a VST is loaded on Track 1, device slot 1...")
    
    print("\n  Testing parameter access on the VST:")
    
    # Try setting a few parameters
    for i in range(10):
        try:
            client.send_message(
                "/live/device/set/parameter/value",
                [track_index, device_index, i, 0.5]
            )
            print(f"  → Set param {i} = 0.5")
            time.sleep(0.2)
        except Exception as e:
            print(f"  ✗ Error setting param {i}: {e}")
    
    print("\n  [CHECK] Did any VST parameters change?")
    print("  If YES, then OSC CAN control third-party VSTs!")
    print("  If NO, VST parameter control may require extension to Remote Script")


def test_loading_with_delay():
    """Test loading multiple devices with increased delay"""
    print_section("TEST 7: Device Loading with Increased Delay")
    
    print("\n  This test will load 3 devices with 2-second delays between each.")
    print("  Watch Ableton to verify stability.\n")
    
    try:
        from ableton_controls import ableton
        
        devices = ["EQ Eight", "Compressor", "Limiter"]
        
        for i, device in enumerate(devices):
            print(f"\n  Loading {device} (device {i+1}/3)...")
            result = ableton.load_device(0, device, -1)
            
            if result.get('success'):
                print(f"  ✓ {device} load request sent")
            else:
                print(f"  ✗ {device} failed: {result.get('message')}")
            
            print(f"  Waiting 2 seconds before next device...")
            time.sleep(2.0)
        
        print("\n  [CHECK] Did all 3 devices load without crashing Ableton?")
        print("  If YES, 2-second delay is sufficient.")
        return True
        
    except Exception as e:
        print(f"\n  ✗ Error: {e}")
        return False


def test_param_after_load():
    """Test setting parameters immediately after loading a device"""
    print_section("TEST 8: Parameter Setting After Device Load")
    
    print("\n  This test loads EQ Eight then immediately tries to set parameters.")
    print("  Testing different delay values.\n")
    
    try:
        from ableton_controls import ableton
        client = SimpleUDPClient(IP, PORT)
        
        # Delete existing devices first (manual step)
        print("  Please clear all devices from Track 1 before continuing.")
        input("  Press ENTER when Track 1 has no devices...")
        
        # Test with 0.5s delay
        print("\n  Test A: Load + 0.5s delay + set param")
        result = ableton.load_device(0, "EQ Eight", -1)
        print(f"  Load result: {result.get('success')}")
        time.sleep(0.5)
        client.send_message("/live/device/set/parameter/value", [0, 0, 3, 200.0])
        print("  Set Band 1 Freq to 200Hz")
        print("  [CHECK] Did it work?")
        time.sleep(1.0)
        
        # Test with 1.5s delay
        print("\n  Test B: Load + 1.5s delay + set param")
        result = ableton.load_device(0, "Compressor", -1)
        print(f"  Load result: {result.get('success')}")
        time.sleep(1.5)
        client.send_message("/live/device/set/parameter/value", [0, 1, 1, -20.0])
        print("  Set Threshold to -20dB (param 1)")
        print("  [CHECK] Did it work?")
        time.sleep(1.0)
        
        # Test with 2.5s delay
        print("\n  Test C: Load + 2.5s delay + set param")
        result = ableton.load_device(0, "Limiter", -1)
        print(f"  Load result: {result.get('success')}")
        time.sleep(2.5)
        client.send_message("/live/device/set/parameter/value", [0, 2, 1, -3.0])
        print("  Set Ceiling to -3dB (param 1)")
        print("  [CHECK] Did it work?")
        
        print("\n  Summary: Which delay value worked best?")
        print("  - 0.5s: Device may not be ready")
        print("  - 1.5s: Should be safe for most devices")
        print("  - 2.5s: Very safe, but slower")
        
        return True
        
    except Exception as e:
        print(f"\n  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all tests in sequence"""
    print("\n" + "="*70)
    print("  DEVICE PARAMETER & VST TESTING SUITE")
    print("="*70)
    print("\nThis will test device parameter setting and VST access.")
    print("Watch Ableton Live to verify each action.\n")
    
    client = test_connection()
    if not client:
        print("\n✗ Tests aborted - no OSC connection")
        return
    
    print("\nSelect which tests to run:")
    print("  1. Native Device Parameter Setting (EQ Eight)")
    print("  2. EQ Eight Specific Parameters")
    print("  3. Parameter Range Discovery (0-50)")
    print("  4. VST Discovery Check")
    print("  5. VST Loading Test")
    print("  6. VST Parameter Access")
    print("  7. Device Loading with Delay")
    print("  8. Parameter Setting After Load")
    print("  a. Run ALL tests")
    print("  q. Quit")
    
    while True:
        choice = input("\nEnter test number (or 'a' for all, 'q' to quit): ").strip().lower()
        
        if choice == 'q':
            break
        elif choice == '1':
            test_native_device_params(client)
        elif choice == '2':
            test_eq_eight_specific(client)
        elif choice == '3':
            test_param_range_discovery(client)
        elif choice == '4':
            test_vst_discovery()
        elif choice == '5':
            test_vst_loading()
        elif choice == '6':
            test_vst_params(client)
        elif choice == '7':
            test_loading_with_delay()
        elif choice == '8':
            test_param_after_load()
        elif choice == 'a':
            test_native_device_params(client)
            test_eq_eight_specific(client)
            test_vst_discovery()
            test_vst_loading()
            test_loading_with_delay()
            test_param_after_load()
        else:
            print("  Invalid choice. Enter a number 1-8, 'a', or 'q'")
    
    print("\n" + "="*70)
    print("  Testing Complete")
    print("="*70)


if __name__ == "__main__":
    run_all_tests()

