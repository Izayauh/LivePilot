from ableton_controls import ableton
import os
import time
from pythonosc.udp_client import SimpleUDPClient

def main():
    client = SimpleUDPClient("127.0.0.1", 11000)
    print("Connecting to Ableton Live OSC on port 11000...")

    loops = [
        # (track_idx, slot_idx, filepath, loop_end)
        (2, 0, r"C:\Users\isaia\Documents\Ableton\User Library\Samples\Processed\Freeze\Freeze 1-Komplete Kontrol [2025-12-11 065557]-2.wav", 16.0),
        (2, 1, r"C:\Users\isaia\Documents\Ableton\User Library\Samples\Processed\Freeze\Freeze 1-Komplete Kontrol [2025-12-11 065557]-2.wav", 16.0),
        (2, 2, r"C:\Users\isaia\Documents\Ableton\User Library\Samples\Processed\Freeze\Freeze 1-Komplete Kontrol [2025-12-11 065557]-2.wav", 16.0),
        (5, 1, r"C:\Users\isaia\Documents\Splice\Samples\packs\Pertes' Electric Bass Tools for the Groove\APERTES_labeled_processed\APERTES_bass\APERTES_bass_raw\APERTES_bass_line_raw_spy_110_Cmin.wav", 16.0),
        (5, 2, r"C:\Users\isaia\Documents\Splice\Samples\packs\Pertes' Electric Bass Tools for the Groove\APERTES_labeled_processed\APERTES_bass\APERTES_bass_raw\APERTES_bass_line_raw_spy_110_Cmin.wav", 16.0),
        (6, 1, r"C:\Users\isaia\Documents\Splice\Samples\packs\Oliver Power Tools Sample Pack III\OLIVER_VOL3_sample_pack\OLIVER_tonal\OLIVER_tonal_loops\OLIVER_cinematic_loops\OLIVER_80_cinematic_loop_alec_maire_night_fighter_bass_Cmin.wav", 16.0),
        (6, 2, r"C:\Users\isaia\Documents\Splice\Samples\packs\Oliver Power Tools Sample Pack III\OLIVER_VOL3_sample_pack\OLIVER_tonal\OLIVER_tonal_loops\OLIVER_cinematic_loops\OLIVER_80_cinematic_loop_alec_maire_night_fighter_bass_Cmin.wav", 16.0)
    ]

    for track_idx, slot_idx, filepath, loop_end in loops:
        if not os.path.exists(filepath):
            print(f"Warning: File not found: {filepath}")
            continue

        print(f"Loading to Track {track_idx} Slot {slot_idx}...")
        ableton._last_response.clear()
        res = ableton.set_clip_path(track_idx, slot_idx, filepath)
        
        if res.get("success"):
            print(f"  Success: {res.get('message')}")
            # Configure clip properties via OSC client
            client.send_message("/live/clip/set/warp_mode", [track_idx, slot_idx, 0])
            client.send_message("/live/clip/set/warping", [track_idx, slot_idx, 1])
            client.send_message("/live/clip/set/looping", [track_idx, slot_idx, 1])
            client.send_message("/live/clip/set/loop_start", [track_idx, slot_idx, 0.0])
            client.send_message("/live/clip/set/loop_end", [track_idx, slot_idx, float(loop_end)])
            time.sleep(0.05)
        else:
            print(f"  Failed: {res.get('message')}")

    # Trigger Intro to refresh arrangement
    print("Syncing playback by firing Intro...")
    client.send_message("/live/scene/fire", [0])
    print("Loops loaded and configured successfully!")

if __name__ == "__main__":
    main()
