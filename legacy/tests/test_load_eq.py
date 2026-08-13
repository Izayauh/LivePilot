r"""
Test script for JarvisDeviceLoader - Load EQ Eight on Track 1
Run this from Windows PowerShell after Ableton is fully loaded:
  cd C:\Users\isaia\Documents\JarvisAbleton
  python test_load_eq.py
"""
from pythonosc.udp_client import SimpleUDPClient
import socket
import time

def test_jarvis():
    # First test if JarvisDeviceLoader is responding
    print("Testing JarvisDeviceLoader...")
    client = SimpleUDPClient('127.0.0.1', 11002)
    client.send_message('/jarvis/test', [])
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(3.0)
    sock.bind(('127.0.0.1', 11003))
    
    try:
        data, addr = sock.recvfrom(1024)
        print(f"✓ JarvisDeviceLoader is responding!")
    except socket.timeout:
        print("✗ JarvisDeviceLoader not responding. Is it enabled in Ableton Preferences > Link/Tempo/MIDI > Control Surface?")
        sock.close()
        return
    sock.close()
    
    # Now try loading EQ Eight on track 0
    print("\nLoading 'EQ Eight' on Track 1...")
    client.send_message('/jarvis/device/load', [0, 'EQ Eight'])
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(10.0)
    sock.bind(('127.0.0.1', 11003))
    
    try:
        data, addr = sock.recvfrom(4096)
        print(f"Response: {data}")
        if b'success' in data:
            print("✓ Device loaded successfully!")
        elif b'error' in data:
            print("✗ Error loading device - check Ableton Log.txt for details")
    except socket.timeout:
        print("✗ No response (timeout). Check Ableton Log.txt for errors.")
    sock.close()

if __name__ == "__main__":
    test_jarvis()
