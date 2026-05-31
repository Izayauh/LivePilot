"""
Test JarvisDeviceLoader Remote Script Connection

This script tests the OSC connection to JarvisDeviceLoader on port 11002/11003
"""

import socket
import struct
import time

def build_osc_message(address, args):
    """Build an OSC message"""
    # Address (null-terminated, padded)
    addr_bytes = address.encode('utf-8') + b'\x00'
    addr_padded = addr_bytes + b'\x00' * ((4 - len(addr_bytes) % 4) % 4)

    # Type tag
    type_tag = ','
    arg_data = b''

    for arg in args:
        if isinstance(arg, int):
            type_tag += 'i'
            arg_data += struct.pack('>i', arg)
        elif isinstance(arg, float):
            type_tag += 'f'
            arg_data += struct.pack('>f', arg)
        elif isinstance(arg, str):
            type_tag += 's'
            str_bytes = arg.encode('utf-8') + b'\x00'
            str_padded = str_bytes + b'\x00' * ((4 - len(str_bytes) % 4) % 4)
            arg_data += str_padded

    type_bytes = type_tag.encode('utf-8') + b'\x00'
    type_padded = type_bytes + b'\x00' * ((4 - len(type_bytes) % 4) % 4)

    return addr_padded + type_padded + arg_data

def parse_osc_message(data):
    """Parse an OSC message"""
    # Get address
    null_idx = data.index(b'\x00')
    address = data[:null_idx].decode('utf-8')

    # Calculate padding
    addr_size = (null_idx + 4) & ~3

    if len(data) <= addr_size:
        return address, []

    # Find type tag
    type_start = addr_size
    if data[type_start:type_start+1] != b',':
        return address, []

    type_null = data.index(b'\x00', type_start)
    type_tag = data[type_start+1:type_null].decode('utf-8')
    type_size = ((type_null - type_start) + 4) & ~3

    # Parse arguments
    args = []
    offset = type_start + type_size

    for tag in type_tag:
        if tag == 'i':
            val = struct.unpack('>i', data[offset:offset+4])[0]
            args.append(val)
            offset += 4
        elif tag == 'f':
            val = struct.unpack('>f', data[offset:offset+4])[0]
            args.append(val)
            offset += 4
        elif tag == 's':
            str_null = data.index(b'\x00', offset)
            val = data[offset:str_null].decode('utf-8')
            args.append(val)
            offset = ((str_null + 1) + 3) & ~3

    return address, args

def test_jarvis_device_loader():
    """Test connection to JarvisDeviceLoader"""
    print("="*80)
    print("TESTING JARVISDEVICELOADER CONNECTION")
    print("="*80)

    # Create sockets
    send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    recv_sock.bind(('127.0.0.1', 11003))
    recv_sock.settimeout(2.0)

    try:
        # Test 1: Ping test
        print("\n1. Testing connection with /jarvis/test...")
        message = build_osc_message("/jarvis/test", [])
        send_sock.sendto(message, ('127.0.0.1', 11002))

        try:
            data, addr = recv_sock.recvfrom(4096)
            response_addr, response_args = parse_osc_message(data)
            print(f"   [OK] Response: {response_addr} {response_args}")
        except socket.timeout:
            print("   [FAIL] No response (timeout)")
            return False

        # Test 2: Get available plugins
        print("\n2. Testing plugin query...")
        message = build_osc_message("/jarvis/plugins/get", [""])
        send_sock.sendto(message, ('127.0.0.1', 11002))

        try:
            data, addr = recv_sock.recvfrom(65536)
            response_addr, response_args = parse_osc_message(data)
            print(f"   [OK] Response: {response_addr}")
            if len(response_args) >= 3:
                success = response_args[0]
                status = response_args[1]
                total = response_args[2]
                print(f"   Status: {status}")
                print(f"   Total plugins found: {total}")
        except socket.timeout:
            print("   [FAIL] No response (timeout)")

        print("\n" + "="*80)
        print("[OK] JARVISDEVICELOADER IS WORKING!")
        print("="*80)
        print("\nYou can now use device loading commands like:")
        print("  - Load 'EQ Eight' on track 0")
        print("  - Query available compressors")
        print("  - Create plugin chains")

        return True

    except Exception as e:
        print(f"\n[ERROR] {e}")
        return False
    finally:
        send_sock.close()
        recv_sock.close()

if __name__ == "__main__":
    test_jarvis_device_loader()
