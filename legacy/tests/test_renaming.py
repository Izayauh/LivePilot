from pythonosc.udp_client import SimpleUDPClient
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer
import threading
import time

# Configuration
SEND_PORT = 11000
LISTEN_PORT = 11001
TRACK_IDX = 0

# Store for device info
track_devices = {} # {index: name}

def handle_device_name(address, *args):
    # Debug print to see exactly what we get
    # print(f"DEBUG: {address} {args}")
    
    # Standard AbletonOSC behavior:
    # If we ask /live/track/get/devices/name, it might reply with a bundle
    # args might be (track_idx, device_idx, name)
    
    if len(args) == 3:
        t_idx = args[0]
        d_idx = args[1]
        name = args[2]
        
        # FIX: Check if d_idx is actually an int or if the args are shifted
        # Sometimes libraries behave oddly.
        if isinstance(d_idx, int):
             if t_idx == TRACK_IDX:
                track_devices[d_idx] = name
        else:
            # Fallback for weird parsing
             pass

def scan_devices():
    print("Scanning devices...")
    track_devices.clear()
    
    dispatcher = Dispatcher()
    dispatcher.map("/live/track/get/devices/name", handle_device_name)
    
    server = BlockingOSCUDPServer(("127.0.0.1", LISTEN_PORT), dispatcher)
    st = threading.Thread(target=server.serve_forever)
    st.daemon = True
    st.start()
    
    client = SimpleUDPClient("127.0.0.1", SEND_PORT)
    
    # Query range 0-4
    for i in range(5):
        client.send_message("/live/track/get/devices/name", [TRACK_IDX, i])
        time.sleep(0.02)
        
    time.sleep(0.5)
    server.shutdown()
    st.join()
    return track_devices

def rename_strategy():
    print("\n--- RENAMING STRATEGY TEST ---")
    
    # 1. Scan
    devices = scan_devices()
    print(f"Found devices: {devices}")
    
    client = SimpleUDPClient("127.0.0.1", SEND_PORT)
    
    # 2. Rename Logic
    # We will try to rename the FIRST EQ Eight to "Subtractive"
    # and the SECOND EQ Eight to "Additive"
    
    eq_count = 0
    
    sorted_indices = sorted(devices.keys())
    
    for idx in sorted_indices:
        name = devices[idx]
        if "EQ Eight" in name:
            eq_count += 1
            new_name = ""
            if eq_count == 1:
                new_name = "Subtractive"
            elif eq_count == 2:
                new_name = "Additive"
            else:
                new_name = f"EQ {eq_count}"
            
            print(f"Refitting Device {idx} ('{name}') -> '{new_name}'")
            
            # Send Rename Command
            # command: /live/device/set/name (track, device, name)
            client.send_message("/live/device/set/name", [TRACK_IDX, idx, new_name])
            time.sleep(0.1)

    print("\nCheck Ableton: Did the EQ Eight names change to 'Subtractive' and 'Additive'?")

if __name__ == "__main__":
    rename_strategy()
