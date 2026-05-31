"""
Test if the AbletonController's response listener is working
"""

import sys
sys.path.insert(0, '.')
import time

from ableton_controls.controller import AbletonController

print("Testing AbletonController response listener...")
print("=" * 80)

# Initialize controller
print("\n1. Initializing controller...")
controller = AbletonController()

# Check if response listener started
print(f"\n2. Response listener status:")
print(f"   _resp_sock: {controller._resp_sock}")
print(f"   _resp_running: {controller._resp_running}")
print(f"   _resp_thread: {controller._resp_thread}")
print(f"   _resp_thread.is_alive(): {controller._resp_thread.is_alive() if controller._resp_thread else 'N/A'}")

if not controller._resp_sock:
    print("\n   [WARN] Response socket not initialized!")
    print("   This means responses won't be received.")
else:
    print("\n   [OK] Response listener appears to be running")

# Give it a moment to settle
print("\n3. Waiting 1 second for listener to fully start...")
time.sleep(1)

# Try to get track names
print("\n4. Testing _send_and_wait directly...")
response = controller._send_and_wait("/live/song/get/track_names", [], timeout=3.0)

if response:
    print(f"   [OK] Got response: {response}")
else:
    print(f"   [FAIL] No response received")

    # Check response cache
    print(f"\n5. Checking _last_response cache:")
    print(f"   Cache contents: {controller._last_response}")

print("\n" + "=" * 80)
print("Test complete")
