from pythonosc.udp_client import SimpleUDPClient
import socket
import time

def send_and_wait(client, sock, addr, args, timeout=3.0):
    client.send_message(addr, args)
    sock.settimeout(timeout)
    try:
        data, _ = sock.recvfrom(4096)
        return data
    except socket.timeout:
        return None

# Setup
client = SimpleUDPClient("127.0.0.1", 11002) # Jarvis Loader (for loading)
client_osc = SimpleUDPClient("127.0.0.1", 11000) # AbletonOSC (for control)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("127.0.0.1", 11001)) # Listen on AbletonOSC response port

print("1. Loading EQ Eight on Track 3...")
client.send_message("/jarvis/device/load", [2, "EQ Eight"])
time.sleep(2) # Wait for load

print("2. Getting devices on Track 3...")
resp = send_and_wait(client_osc, sock, "/live/track/get/devices/name", [2])
print(f"Devices: {resp}")

# Assuming EQ Eight is the last device (index 0 if empty before)
# We need to find the device index. Let's assume index 0 for this test.
device_idx = 0

print(f"3. Getting parameters for Device {device_idx}...")
client_osc.send_message("/live/device/get/parameters/name", [2, device_idx])
resp = send_and_wait(client_osc, sock, "/live/device/get/parameters/name", [2, device_idx])
# We can't parse binary OSC easily here without a library, but raw output is useful enough to verify response
print(f"Params Raw: {resp}")

print("4. Setting Parameter 1 (Freq 1 maybe?) to 0.5 (center)...")
# Parameter 0 is usually On/Off. Parameter 1/2 might be Freq.
# Let's try setting parameter 3 (often a frequency or gain)
client_osc.send_message("/live/device/set/parameter/value", [2, device_idx, 3, 0.5])
print("Sent parameter update.")

print("5. Getting Parameter 3 value...")
client_osc.send_message("/live/device/get/parameter/value", [2, device_idx, 3])
resp = send_and_wait(client_osc, sock, "/live/device/get/parameter/value", [2, device_idx, 3])
print(f"Value Raw: {resp}")

sock.close()
