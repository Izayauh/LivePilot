import os
import sys
import time
from pythonosc.udp_client import SimpleUDPClient
from ableton_controls import ableton
from ableton_controls.reliable_params import ReliableParameterController, smart_normalize_parameter
from discovery.vst_discovery import get_vst_discovery

# Force UTF-8 stdout
sys.stdout.reconfigure(encoding='utf-8')

def main():
    discovery = get_vst_discovery()
    reliable = ReliableParameterController(ableton, verbose=True)
    
    print("\n=== STEP 1: CONFIGURE TRACK MUTES ===")
    # Mute Track 1 (MIDI Electric Bass) and Track 6 (Audio Sub Loop)
    # 1 = muted, 0 = unmuted
    print("Muting Track 1 (BASS - Midi)...")
    ableton.mute_track(1, 1)
    time.sleep(0.2)
    print("Muting Track 6 (SUB - Audio Loop)...")
    ableton.mute_track(6, 1)
    time.sleep(0.2)
    
    # Ensure active tracks are unmuted
    print("Unmuting active tracks...")
    for t in [0, 2, 3, 4, 5]:
        ableton.mute_track(t, 0)
        time.sleep(0.1)

    print("\n=== STEP 2: LOAD EQ EIGHT DEVICES ===")
    
    def ensure_eq_eight(track_idx):
        ableton._last_response.clear()
        time.sleep(0.2)
        res = ableton.get_track_devices_sync(track_idx)
        print(f"  Track {track_idx} current devices: {res.get('devices')}")
        
        if res.get("success") and "EQ Eight" in res.get("devices", []):
            dev_idx = res["devices"].index("EQ Eight")
            print(f"  Track {track_idx} already has EQ Eight at index {dev_idx}")
            return dev_idx
        else:
            print(f"  Loading EQ Eight on Track {track_idx}...")
            discovery.load_device_on_track(track_idx, "EQ Eight")
            time.sleep(1.0) # Give Ableton time to load the device
            
            # Recheck
            ableton._last_response.clear()
            res = ableton.get_track_devices_sync(track_idx)
            if res.get("success") and "EQ Eight" in res.get("devices", []):
                dev_idx = res["devices"].index("EQ Eight")
                print(f"  Track {track_idx} now has EQ Eight at index {dev_idx}")
                return dev_idx
            else:
                # If still not found, try one more time
                time.sleep(1.0)
                ableton._last_response.clear()
                res = ableton.get_track_devices_sync(track_idx)
                if res.get("success") and "EQ Eight" in res.get("devices", []):
                    dev_idx = res["devices"].index("EQ Eight")
                    return dev_idx
                raise Exception(f"Failed to load EQ Eight on Track {track_idx}")

    # Track 0: Has EQ Eight at index 1
    t0_eq = 1
    print(f"Track 0 EQ Eight at index {t0_eq}")
    
    # Track 2: Has EQ Eight
    t2_eq = ensure_eq_eight(2)
    
    # Track 3: Load EQ Eight
    t3_eq = ensure_eq_eight(3)
    
    # Track 4: Load EQ Eight
    t4_eq = ensure_eq_eight(4)
    
    # Track 5: Has EQ Eight
    t5_eq = ensure_eq_eight(5)

    print("\n=== STEP 3: CONFIGURE EQ CURVES ===")

    # Helper to set EQ Eight Band parameters
    def set_eq_band(track_idx, dev_idx, band_num, on=True, filter_type=2.0, freq=1000.0, gain=0.0, q=0.707):
        a_base = 4 + (band_num - 1) * 10
        b_base = 9 + (band_num - 1) * 10
        
        # 1. On/Off
        on_val = 1.0 if on else 0.0
        ableton.set_device_parameter(track_idx, dev_idx, a_base, on_val)
        time.sleep(0.05)
        ableton.set_device_parameter(track_idx, dev_idx, b_base, on_val)
        time.sleep(0.05)
        
        # 2. Filter Type
        ableton.set_device_parameter(track_idx, dev_idx, a_base + 1, float(filter_type))
        time.sleep(0.05)
        ableton.set_device_parameter(track_idx, dev_idx, b_base + 1, float(filter_type))
        time.sleep(0.05)
        
        # 3. Frequency
        norm_freq, _ = smart_normalize_parameter(f"{band_num} Frequency A", freq, "EQ Eight")
        ableton.set_device_parameter(track_idx, dev_idx, a_base + 2, norm_freq)
        time.sleep(0.05)
        ableton.set_device_parameter(track_idx, dev_idx, b_base + 2, norm_freq)
        time.sleep(0.05)
        
        # 4. Gain
        ableton.set_device_parameter(track_idx, dev_idx, a_base + 3, float(gain))
        time.sleep(0.05)
        ableton.set_device_parameter(track_idx, dev_idx, b_base + 3, float(gain))
        time.sleep(0.05)
        
        # 5. Resonance / Q
        norm_q, _ = smart_normalize_parameter(f"{band_num} Resonance A", q, "EQ Eight")
        ableton.set_device_parameter(track_idx, dev_idx, a_base + 4, norm_q)
        time.sleep(0.05)
        ableton.set_device_parameter(track_idx, dev_idx, b_base + 4, norm_q)
        time.sleep(0.05)
        
        print(f"  Track {track_idx} Band {band_num} Configured: Type={filter_type}, Freq={freq}Hz, Gain={gain}dB, Q={q}")

    # Track 0 (Rhodes):
    # - Band 1: HPF at 100 Hz
    # - Band 2: Bell cut at 200 Hz (-2.0 dB, Q=1.0)
    print("\nConfiguring Track 0 (Rhodes) EQ...")
    set_eq_band(0, t0_eq, band_num=1, on=True, filter_type=0.0, freq=100.0)
    set_eq_band(0, t0_eq, band_num=2, on=True, filter_type=2.0, freq=200.0, gain=-2.0, q=1.0)

    # Track 2 (Soul Sample):
    # - Band 1: HPF at 120 Hz
    # - Band 2: Bell boost at 2500 Hz (+1.5 dB, Q=1.0)
    print("\nConfiguring Track 2 (Soul Sample) EQ...")
    set_eq_band(2, t2_eq, band_num=1, on=True, filter_type=0.0, freq=120.0)
    set_eq_band(2, t2_eq, band_num=2, on=True, filter_type=2.0, freq=2500.0, gain=1.5, q=1.0)

    # Track 3 (Drums):
    # - Band 1: Bell cut at 250 Hz (-2.0 dB, Q=1.0)
    # - Band 3: High Shelf boost at 8000 Hz (+3.5 dB, Q=0.707)
    print("\nConfiguring Track 3 (Drums) EQ...")
    set_eq_band(3, t3_eq, band_num=1, on=True, filter_type=2.0, freq=250.0, gain=-2.0, q=1.0)
    set_eq_band(3, t3_eq, band_num=3, on=True, filter_type=4.0, freq=8000.0, gain=3.5, q=0.707)

    # Track 4 (Sub MIDI):
    # - Band 8: LPF at 90 Hz (Q=0.707)
    print("\nConfiguring Track 4 (Sub MIDI) EQ...")
    set_eq_band(4, t4_eq, band_num=8, on=True, filter_type=3.0, freq=90.0, q=0.707)

    # Track 5 (Bass Audio Loop):
    # - Band 1: HPF at 90 Hz
    print("\nConfiguring Track 5 (Bass Audio Loop) EQ...")
    set_eq_band(5, t5_eq, band_num=1, on=True, filter_type=0.0, freq=90.0)

    print("\nMix refinement complete!")

if __name__ == "__main__":
    main()
