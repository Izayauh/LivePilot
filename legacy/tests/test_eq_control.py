from pythonosc.udp_client import SimpleUDPClient
import socket
import time

def test_eq_control():
    print("Testing EQ Eight Control Sequence")
    
    # 1. Load EQ Eight
    print("\n[Step 1] Loading EQ Eight...")
    client = SimpleUDPClient('127.0.0.1', 11002)
    client.send_message('/jarvis/device/load', [0, 'EQ Eight'])

    # Wait for confirmation
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(5.0)
    sock.bind(('127.0.0.1', 11003))

    try:
        data, addr = sock.recvfrom(4096)
        print(f"  Response: {data}")
    except socket.timeout:
        print("  Timeout waiting for load confirmation (assuming loaded for now)")
    finally:
        sock.close()

    # 2. Wait for device to initialize
    print("\n[Step 2] Waiting 1.0s for device init...")
    time.sleep(1.0)

    # 3. Change Parameter (Band 1 Freq is usually Param 3 on EQ Eight, approx)
    # Note: Ableton devices vary. We will try to set Param 3 (Freq) to a high value.
    # Native params are usually 0.0 - 1.0 or direct values depending on config.
    # Sending 0.8 (approx 10kHz)
    
    print("\n[Step 3] Setting Band 1 Freq (Param 3) to 0.8...")
    # Using the standard AbletonOSC address for parameter setting
    # /live/device/set/parameter/value (track, device, param, value)
    client = SimpleUDPClient('127.0.0.1', 11000) # Standard OSC port
    
    # Track 0, Device 0 (First device), Param 3 (Freq 1), Value 0.8
    client.send_message('/live/device/set/parameter/value', [0, 0, 3, 0.8])
    print("  Command sent.")

    print("\n[Step 4] Setting Band 1 Gain (Param 4) to 1.0 (Max boost)...")
    # Track 0, Device 0, Param 4 (Gain 1), Value 1.0
    client.send_message('/live/device/set/parameter/value', [0, 0, 4, 1.0])
    print("  Command sent.")

    print("\nCHECK ABLETON: Did Band 1 on EQ Eight jump up and to the right?")

if __name__ == "__main__":
    test_eq_control()
