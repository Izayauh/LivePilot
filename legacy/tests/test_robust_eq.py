from pythonosc.udp_client import SimpleUDPClient
import socket
import time

def run_robust_test():
    client = SimpleUDPClient('127.0.0.1', 11000) # Standard Port
    loader_client = SimpleUDPClient('127.0.0.1', 11002) # Loader Port

    print("\n[TEST] Starting Robust EQ Eight Configuration...")
    
    # 1. Load (or Reload) EQ Eight
    print("1. Loading EQ Eight on Track 0...")
    loader_client.send_message('/jarvis/device/load', [0, 'EQ Eight'])
    time.sleep(1.0) # Wait for load
    
    # 2. Configure Band 1 as Low Cut (Hi Pass) @ ~100Hz
    print("2. Configuring Band 1: Low Cut (Hi-Pass) @ 100Hz")
    # Param 4: On
    client.send_message('/live/device/set/parameter/value', [0, 0, 4, 1.0])
    # Param 5: Type (0.0 = Low Cut / Hi Pass usually)
    client.send_message('/live/device/set/parameter/value', [0, 0, 5, 0.0])
    # Param 6: Freq (0.2 approx 100Hz)
    client.send_message('/live/device/set/parameter/value', [0, 0, 6, 0.2])
    # Param 8: Q (0.5 for standard slope)
    client.send_message('/live/device/set/parameter/value', [0, 0, 8, 0.5])
    
    # 3. Configure Band 4 as High Shelf Boost
    print("3. Configuring Band 4: High Shelf Boost")
    # Param 34: On
    client.send_message('/live/device/set/parameter/value', [0, 0, 34, 1.0])
    # Param 35: Type - Correct values: 0=LP48, 1=LP24, 2=LP12, 3=Notch, 4=HP12, 5=HP24, 6=HP48, 7=Bell, 8=LowShelf, 9=HighShelf
    # High Shelf = 9.0
    client.send_message('/live/device/set/parameter/value', [0, 0, 35, 9.0])
    # Param 36: Freq (0.8 approx 5kHz)
    client.send_message('/live/device/set/parameter/value', [0, 0, 36, 0.8])
    # Param 37: Gain (0.7 = +6dB approx)
    client.send_message('/live/device/set/parameter/value', [0, 0, 37, 0.7])

    print("\n[DONE] Check Ableton:")
    print("  - Band 1: Should be a Low Cut (curving up from left)")
    print("  - Band 4: Should be a High Shelf (boosted on right)")
    print("  - Both bands should be ACTIVE (yellow squares)")

if __name__ == "__main__":
    run_robust_test()
