"""
Quick test for the fixed get_track_list function
"""

import sys
sys.path.insert(0, '.')

from ableton_controls.controller import AbletonController

def test_track_list():
    print("="*80)
    print("TESTING GET_TRACK_LIST FIX")
    print("="*80)

    # Initialize controller
    print("\n1. Initializing Ableton controller...")
    ableton = AbletonController()

    # Test connection
    print("\n2. Testing OSC connection...")
    if ableton.test_connection():
        print("   [OK] Connected to Ableton OSC")
    else:
        print("   [FAIL] Failed to connect - make sure Ableton is running with AbletonOSC")
        return False

    # Test get_track_names
    print("\n3. Testing get_track_names()...")
    result = ableton.get_track_names()
    print(f"   Result: {result}")

    if result['success']:
        print(f"   [OK] Got track names: {result['track_names']}")
    else:
        print(f"   [FAIL] Failed: {result['message']}")
        return False

    # Test get_track_list
    print("\n4. Testing get_track_list()...")
    result = ableton.get_track_list()
    print(f"   Result: {result}")

    if result['success']:
        print(f"   [OK] Got {len(result['tracks'])} tracks:")
        for track in result['tracks']:
            print(f"      Track {track['display_index']} (index {track['index']}): {track['name']}")
    else:
        print(f"   [FAIL] Failed: {result['message']}")
        return False

    print("\n" + "="*80)
    print("[OK] ALL TESTS PASSED")
    print("="*80)
    return True

if __name__ == "__main__":
    success = test_track_list()
    sys.exit(0 if success else 1)
