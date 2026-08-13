"""
Comprehensive Test Suite for Jarvis-Ableton OSC Integration

Tests all major control categories using CORRECT OSC paths:
- Playback controls
- Transport controls
- Track controls (with CORRECT parameter format)
- Scene controls
- Clip controls

IMPORTANT: Per AbletonOSC documentation:
- Track/scene/clip IDs are PARAMETERS, not part of the OSC path
- Format: /live/track/set/mute [track_id, mute_value]
- All indices are 0-based (Track 1 = index 0)
"""

from pythonosc.udp_client import SimpleUDPClient
import time

IP = "127.0.0.1"
PORT = 11000


def print_section(title):
    """Print a formatted section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


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


def test_playback_controls(client):
    """Test playback controls"""
    print_section("Testing Playback Controls")
    
    # Metronome
    print("\n1. Testing Metronome...")
    print("   Turning metronome ON...")
    client.send_message("/live/song/set/metronome", [1])
    time.sleep(1)
    print("   [CHECK] Metronome icon should be orange")
    
    time.sleep(1)
    print("   Turning metronome OFF...")
    client.send_message("/live/song/set/metronome", [0])
    time.sleep(1)
    print("   [CHECK] Metronome icon should be white/gray")
    
    # Play/Stop
    print("\n2. Testing Play/Stop...")
    print("   Starting playback...")
    client.send_message("/live/song/start_playing", [])
    time.sleep(2)
    print("   [CHECK] Ableton should be playing")
    
    print("   Stopping playback...")
    client.send_message("/live/song/stop_playing", [])
    time.sleep(1)
    print("   [CHECK] Ableton should be stopped")


def test_transport_controls(client):
    """Test transport controls"""
    print_section("Testing Transport Controls")
    
    print("\n1. Testing Tempo Change...")
    print("   Setting tempo to 128 BPM...")
    client.send_message("/live/song/set/tempo", [128.0])
    time.sleep(1)
    print("   [CHECK] Tempo display should show 128 BPM")
    
    time.sleep(1)
    print("   Setting tempo to 90 BPM...")
    client.send_message("/live/song/set/tempo", [90.0])
    time.sleep(1)
    print("   [CHECK] Tempo display should show 90 BPM")
    
    # Restore to 120
    client.send_message("/live/song/set/tempo", [120.0])
    
    print("\n2. Testing Loop Controls...")
    print("   Enabling loop...")
    client.send_message("/live/song/set/loop", [1])
    time.sleep(1)
    print("   [CHECK] Loop button should be highlighted")
    
    print("   Disabling loop...")
    client.send_message("/live/song/set/loop", [0])
    time.sleep(1)
    print("   [CHECK] Loop button should NOT be highlighted")


def test_track_controls(client):
    """Test track controls with CORRECT parameter format"""
    print_section("Testing Track Controls (CORRECTED FORMAT)")
    
    print("\n" + "-"*50)
    print("  IMPORTANT: Per AbletonOSC documentation:")
    print("  Track ID is a PARAMETER, not part of the path!")
    print("  Format: /live/track/set/mute [track_id, value]")
    print("-"*50)
    
    print("\nREMINDER: Track 1 in Ableton = Index 0 in OSC")
    
    # Test Track 1 (index 0) - MUTE
    print("\n1. Testing Track 1 MUTE (index 0)...")
    print("   Sending: /live/track/set/mute [0, 1]")
    client.send_message("/live/track/set/mute", [0, 1])
    time.sleep(1)
    print("   [CHECK] Track 1 should be MUTED (M button yellow)")
    
    time.sleep(1)
    print("   Sending: /live/track/set/mute [0, 0]")
    client.send_message("/live/track/set/mute", [0, 0])
    time.sleep(1)
    print("   [CHECK] Track 1 should be UNMUTED")
    
    # Test Track 1 - SOLO
    print("\n2. Testing Track 1 SOLO...")
    print("   Sending: /live/track/set/solo [0, 1]")
    client.send_message("/live/track/set/solo", [0, 1])
    time.sleep(1)
    print("   [CHECK] Track 1 should be SOLOED (S button blue)")
    
    time.sleep(1)
    print("   Sending: /live/track/set/solo [0, 0]")
    client.send_message("/live/track/set/solo", [0, 0])
    time.sleep(1)
    print("   [CHECK] Track 1 should be UNSOLOED")
    
    # Test Track 1 - VOLUME
    print("\n3. Testing Track 1 Volume...")
    print("   Sending: /live/track/set/volume [0, 0.5]")
    client.send_message("/live/track/set/volume", [0, 0.5])
    time.sleep(1)
    print("   [CHECK] Track 1 volume fader should be at ~50%")
    
    time.sleep(1)
    print("   Restoring volume to 0.85...")
    client.send_message("/live/track/set/volume", [0, 0.85])
    time.sleep(1)
    print("   [CHECK] Track 1 volume should be back to ~85%")
    
    # Test Track 1 - PAN
    print("\n4. Testing Track 1 Pan...")
    print("   Sending: /live/track/set/panning [0, -0.5] (left)")
    client.send_message("/live/track/set/panning", [0, -0.5])
    time.sleep(1)
    print("   [CHECK] Track 1 pan should be LEFT")
    
    time.sleep(1)
    print("   Restoring pan to center...")
    client.send_message("/live/track/set/panning", [0, 0.0])
    time.sleep(1)
    print("   [CHECK] Track 1 pan should be CENTER")


def test_scene_controls(client):
    """Test scene controls"""
    print_section("Testing Scene Controls")
    
    print("\n  Format: /live/scene/fire [scene_id]")
    print("  Scene 1 = index 0")
    
    print("\n1. Testing Scene 1 (index 0)...")
    print("   Sending: /live/scene/fire [0]")
    client.send_message("/live/scene/fire", [0])
    time.sleep(2)
    print("   [CHECK] Scene 1 (top row) should trigger")
    
    # Stop playback
    print("   Stopping playback...")
    client.send_message("/live/song/stop_playing", [])
    time.sleep(1)


def test_clip_controls(client):
    """Test clip controls"""
    print_section("Testing Clip Controls")
    
    print("\n  Format: /live/clip/fire [track_id, clip_id]")
    print("  Track 1 = index 0, Clip slot 1 = index 0")
    
    print("\n1. Testing Fire Clip (track 0, slot 0)...")
    print("   Sending: /live/clip/fire [0, 0]")
    client.send_message("/live/clip/fire", [0, 0])
    time.sleep(2)
    print("   [CHECK] Clip in Track 1, Slot 1 should play")
    
    print("\n2. Testing Stop Clips on Track...")
    print("   Sending: /live/track/stop_all_clips [0]")
    client.send_message("/live/track/stop_all_clips", [0])
    time.sleep(1)
    print("   [CHECK] All clips on Track 1 should stop")
    
    # Stop everything
    client.send_message("/live/song/stop_playing", [])


def run_all_tests():
    """Run all tests in sequence"""
    print("\n" + "="*60)
    print("  JARVIS-ABLETON COMPREHENSIVE TEST SUITE")
    print("  (Using CORRECTED OSC path format)")
    print("="*60)
    print("\nThis will test all major Ableton OSC controls.")
    print("Watch Ableton Live to verify each action.\n")
    
    # Test connection first
    client = test_connection()
    if not client:
        print("\n✗ Tests aborted - no OSC connection")
        return
    
    # Run all test suites
    try:
        test_playback_controls(client)
        time.sleep(2)
        
        test_transport_controls(client)
        time.sleep(2)
        
        test_track_controls(client)
        time.sleep(2)
        
        test_scene_controls(client)
        time.sleep(1)
        
        test_clip_controls(client)
        
        # Summary
        print_section("Test Suite Complete")
        print("\n✓ All tests executed")
        print("\nReview the checks above to verify each worked correctly.")
        print("\nKey changes from previous version:")
        print("  - Track ID is now a PARAMETER, not in path")
        print("  - Format: /live/track/set/mute [track_id, value]")
        print("\nIf all checks passed, run: python jarvis_engine.py")
        
    except Exception as e:
        print(f"\n✗ Test suite error: {e}")
        print("Check that Ableton Live and AbletonOSC are running properly")


def test_single_function(function_name):
    """Test a single function by name"""
    client = test_connection()
    if not client:
        return
    
    tests = {
        "playback": test_playback_controls,
        "transport": test_transport_controls,
        "tracks": test_track_controls,
        "scenes": test_scene_controls,
        "clips": test_clip_controls,
    }
    
    if function_name in tests:
        tests[function_name](client)
    else:
        print(f"\nUnknown test: {function_name}")
        print(f"Available tests: {', '.join(tests.keys())}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Run specific test
        test_single_function(sys.argv[1])
    else:
        # Run all tests
        run_all_tests()
