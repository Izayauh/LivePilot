"""
Direct OSC test to see what responses we're getting
"""

import socket
import struct
import time

def build_osc(address, args=[]):
    """Build OSC message"""
    addr_bytes = address.encode('utf-8') + b'\x00'
    addr_padded = addr_bytes + b'\x00' * ((4 - len(addr_bytes) % 4) % 4)

    type_tag = ','
    arg_data = b''

    for arg in args:
        if isinstance(arg, int):
            type_tag += 'i'
            arg_data += struct.pack('>i', arg)

    type_bytes = type_tag.encode('utf-8') + b'\x00'
    type_padded = type_bytes + b'\x00' * ((4 - len(type_bytes) % 4) % 4)

    return addr_padded + type_padded + arg_data

print("Testing direct OSC communication...")
print("=" * 80)

# Test 1: Send test message
print("\n1. Sending /live/test message...")
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
msg = build_osc("/live/test")
sock.sendto(msg, ('127.0.0.1', 11000))
print("   Sent!")

# Test 2: Request track names (fire-and-forget style)
print("\n2. Requesting track names (fire-and-forget)...")
msg = build_osc("/live/song/get/track_names")
sock.sendto(msg, ('127.0.0.1', 11000))
print("   Request sent!")

# Test 3: Listen for any responses on 11001
print("\n3. Listening for responses on port 11001...")
recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    recv_sock.bind(('127.0.0.1', 11001))
    recv_sock.settimeout(3.0)
    print("   Bound to port 11001, waiting 3 seconds for responses...")

    start = time.time()
    responses = []

    while time.time() - start < 3.0:
        try:
            data, addr = recv_sock.recvfrom(65536)
            responses.append(data)
            print(f"   [OK] Got response ({len(data)} bytes)")

            # Try to parse first part
            try:
                null_idx = data.index(b'\x00')
                response_addr = data[:null_idx].decode('utf-8')
                print(f"        Address: {response_addr}")
            except:
                print(f"        Raw: {data[:50]}...")

        except socket.timeout:
            continue

    if responses:
        print(f"\n   Total responses received: {len(responses)}")
    else:
        print("\n   [WARN] No responses received")

except Exception as e:
    print(f"   [ERROR] {e}")
finally:
    recv_sock.close()
    sock.close()

print("\n" + "=" * 80)
print("Test complete")
