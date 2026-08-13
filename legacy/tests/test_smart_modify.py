from pythonosc.udp_client import SimpleUDPClient
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer
import threading
import time
import socket

# Configuration
SEND_PORT = 11000
LISTEN_PORT = 11001
LOADER_PORT = 11002
TRACK_IDX = 0

# Store for device names
track_devices = {} # {index: "Name"}

def handle_device_name(address, *args):
    # Address: /live/track/get/devices/name
    # Args: (track_idx, device_idx, name)
    if len(args) == 3:
        t_idx, d_idx, name = args
        if t_idx == TRACK_IDX:
            track_devices[d_idx] = name

def get_existing_devices():
    """Queries Ableton for list of devices on the track."""
    track_devices.clear()
    
    dispatcher = Dispatcher()
    dispatcher.map("/live/track/get/devices/name", handle_device_name)
    
    server = BlockingOSCUDPServer(("127.0.0.1", LISTEN_PORT), dispatcher)
    
    # Start server in background
    st = threading.Thread(target=server.serve_forever)
    st.daemon = True
    st.start()
    
    client = SimpleUDPClient("127.0.0.1", SEND_PORT)
    
    # Send query (Requesting devices 0-10 just to be safe)
    # The standard AbletonOSC command usually dumps all if we ask for the count
    # But let's iterate to be robust for this test
    for i in range(10):
        client.send_message("/live/track/get/devices/name", [TRACK_IDX, i])
        
    time.sleep(0.5) # Wait for replies
    server.shutdown()
    st.join()
    
    return track_devices

def smart_eq_control():
    print("--- SMART EQ CONTROL TEST ---")
    
    # 1. Check what's there
    print("1. Scanning Track 0 for devices...")
    devices = get_existing_devices()
    
    eq_index = -1
    for idx, name in devices.items():
        print(f"   Found Device {idx}: {name}")
        if "EQ Eight" in name:
            eq_index = idx
            break # Found the first one
            
    # 2. Load OR Select
    client = SimpleUDPClient("127.0.0.1", SEND_PORT)
    
    if eq_index != -1:
        print(f"2. [SUCCESS] Found existing EQ Eight at Device Index {eq_index}. Using it.")
    else:
        print("2. [WARN] No EQ Eight found. Loading new instance...")
        loader = SimpleUDPClient("127.0.0.1", LOADER_PORT)
        loader.send_message('/jarvis/device/load', [TRACK_IDX, 'EQ Eight'])
        time.sleep(1.0) # Wait for load
        # Re-scan to get the new index (it should be the last one)
        devices = get_existing_devices()
        for idx, name in devices.items():
            if "EQ Eight" in name:
                eq_index = idx # Take the last one found
        print(f"   -> New EQ Eight loaded at Index {eq_index}")

    if eq_index == -1:
        print("[ERROR] Critical Error: Failed to find or load EQ Eight.")
        return

    # 3. Apply Settings to the SPECIFIC Index
    print(f"3. Applying High-Pass Filter to Device {eq_index}...")
    
    # Param 4 (Band 1 On), Param 5 (Type), Param 6 (Freq)
    client.send_message('/live/device/set/parameter/value', [TRACK_IDX, eq_index, 4, 1.0]) # On
    client.send_message('/live/device/set/parameter/value', [TRACK_IDX, eq_index, 5, 0.0]) # Low Cut
    client.send_message('/live/device/set/parameter/value', [TRACK_IDX, eq_index, 6, 0.3]) # ~150Hz
    
    print("   -> Settings applied.")
    print("   [CHECK] Did the EXISTING EQ change? (No new device should appear)")

if __name__ == "__main__":
    smart_eq_control()
