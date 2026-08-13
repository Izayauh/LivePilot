import time
import sys
import os
from pythonosc.udp_client import SimpleUDPClient
from ableton_controls import ableton

# Force UTF-8 output encoding for stdout
sys.stdout.reconfigure(encoding='utf-8')

def main():
    client = SimpleUDPClient("127.0.0.1", 11000)
    print("Connecting to Ableton Live OSC on port 11000...")

    # 1. Rename Track 1 to "BASS - Midi"
    print("Renaming Track 1 to 'BASS - Midi'...")
    ableton.set_track_name(1, "BASS - Midi")
    time.sleep(0.1)

    # 2. Create MIDI track at index 4 (SUB - Midi)
    print("Creating MIDI track at index 4 for SUB...")
    ableton.create_midi_track(4)
    time.sleep(0.5)
    ableton.set_track_name(4, "SUB - Midi")
    time.sleep(0.1)

    # Load Simpler and Saturator on SUB - Midi
    print("Loading Simpler on SUB - Midi...")
    ableton._load_device_osc(4, "Simpler", position=0)
    time.sleep(1.0)
    print("Loading Saturator on SUB - Midi...")
    ableton._load_device_osc(4, "Saturator", position=1)
    time.sleep(1.0)

    # 3. Create Audio track at index 5 (BASS - Audio Loop)
    print("Creating Audio track at index 5 for BASS - Audio Loop...")
    ableton.create_audio_track(5, "BASS - Audio Loop")
    time.sleep(0.5)

    # 4. Create Audio track at index 6 (SUB - Audio Loop)
    print("Creating Audio track at index 6 for SUB - Audio Loop...")
    ableton.create_audio_track(6, "SUB - Audio Loop")
    time.sleep(0.5)

    # Notes definition for SUB - Midi
    bass_notes = []
    for bar in range(8):
        base = bar * 4
        mode = bar % 4
        if mode == 0:
            bass_notes.append({"pitch": 36, "start": base + 0.0, "end": base + 1.5, "velocity": 85})
            bass_notes.append({"pitch": 48, "start": base + 2.0, "end": base + 2.5, "velocity": 75})
            bass_notes.append({"pitch": 43, "start": base + 2.5, "end": base + 3.25, "velocity": 80})
            bass_notes.append({"pitch": 39, "start": base + 3.5, "end": base + 3.75, "velocity": 80})
        elif mode == 1:
            bass_notes.append({"pitch": 32, "start": base + 0.0, "end": base + 1.5, "velocity": 85})
            bass_notes.append({"pitch": 44, "start": base + 2.0, "end": base + 2.5, "velocity": 75})
            bass_notes.append({"pitch": 39, "start": base + 2.5, "end": base + 3.25, "velocity": 80})
            bass_notes.append({"pitch": 36, "start": base + 3.5, "end": base + 3.75, "velocity": 80})
        elif mode == 2:
            bass_notes.append({"pitch": 29, "start": base + 0.0, "end": base + 1.5, "velocity": 85})
            bass_notes.append({"pitch": 41, "start": base + 2.0, "end": base + 2.5, "velocity": 75})
            bass_notes.append({"pitch": 36, "start": base + 2.5, "end": base + 3.25, "velocity": 80})
            bass_notes.append({"pitch": 32, "start": base + 3.25, "end": base + 3.5, "velocity": 75})
            bass_notes.append({"pitch": 34, "start": base + 3.5, "end": base + 3.75, "velocity": 80})
        else:
            bass_notes.append({"pitch": 31, "start": base + 0.0, "end": base + 1.5, "velocity": 85})
            bass_notes.append({"pitch": 43, "start": base + 2.0, "end": base + 2.5, "velocity": 75})
            bass_notes.append({"pitch": 38, "start": base + 2.5, "end": base + 3.25, "velocity": 80})
            bass_notes.append({"pitch": 37, "start": base + 3.5, "end": base + 3.75, "velocity": 80})

    def recreate_midi_clip(track_idx, slot_idx, length_beats):
        client.send_message("/live/clip_slot/delete_clip", [track_idx, slot_idx])
        time.sleep(0.05)
        client.send_message("/live/clip_slot/create_clip", [track_idx, slot_idx, float(length_beats)])
        time.sleep(0.05)

    def push_notes(track_idx, slot_idx, notes):
        chunk_size = 20
        for i in range(0, len(notes), chunk_size):
            chunk = notes[i:i+chunk_size]
            params = [track_idx, slot_idx]
            for note in chunk:
                params.extend([
                    int(note["pitch"]),
                    float(note["start"]),
                    float(note["end"] - note["start"]),
                    int(note.get("velocity", 90)),
                    0
                ])
            client.send_message("/live/clip/add/notes", params)
            time.sleep(0.02)

    def load_audio_loop(track_idx, slot_idx, filepath):
        print(f"Loading loop into Track {track_idx+1} Slot {slot_idx+1}...")
        address = "/jarvis/clip/create_audio"
        import socket
        import struct
        addr_bytes = address.encode('utf-8') + b'\x00'
        addr_padded = addr_bytes + b'\x00' * ((4 - len(addr_bytes) % 4) % 4)
        type_tag = ',isi'
        type_bytes = type_tag.encode('utf-8') + b'\x00'
        type_padded = type_bytes + b'\x00' * ((4 - len(type_bytes) % 4) % 4)
        arg_data = struct.pack('>i', track_idx)
        str_bytes = filepath.encode('utf-8') + b'\x00'
        str_padded = str_bytes + b'\x00' * ((4 - len(str_bytes) % 4) % 4)
        arg_data += str_padded
        arg_data += struct.pack('>i', slot_idx)
        message = addr_padded + type_padded + arg_data
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(message, ('127.0.0.1', 11002))
        sock.close()
        time.sleep(0.2) # wait for clip load

        # Set clip to warp & loop
        client.send_message("/live/clip/set/warp_mode", [track_idx, slot_idx, 0])
        client.send_message("/live/clip/set/warping", [track_idx, slot_idx, 1])
        client.send_message("/live/clip/set/looping", [track_idx, slot_idx, 1])
        client.send_message("/live/clip/set/loop_start", [track_idx, slot_idx, 0.0])
        client.send_message("/live/clip/set/loop_end", [track_idx, slot_idx, 16.0])
        time.sleep(0.05)

    # Write MIDI clips to Track 4 (SUB - Midi)
    print("Writing MIDI notes to Track 4 (SUB - Midi) for Chorus & Verse...")
    recreate_midi_clip(4, 1, 32.0)
    push_notes(4, 1, bass_notes)
    recreate_midi_clip(4, 2, 32.0)
    push_notes(4, 2, bass_notes)

    # 5. Load Audio Loops
    electric_bass_path = r"C:\Users\isaia\Documents\Splice\Samples\packs\Pertes' Electric Bass Tools for the Groove\APERTES_labeled_processed\APERTES_bass\APERTES_bass_raw\APERTES_bass_line_raw_spy_110_Cmin.wav"
    synth_sub_path = r"C:\Users\isaia\Documents\Splice\Samples\packs\Oliver Power Tools Sample Pack III\OLIVER_VOL3_sample_pack\OLIVER_tonal\OLIVER_tonal_loops\OLIVER_cinematic_loops\OLIVER_80_cinematic_loop_alec_maire_night_fighter_bass_Cmin.wav"

    if os.path.exists(electric_bass_path):
        print("Writing electric bass loop to Track 5 (BASS - Audio Loop) for Chorus & Verse...")
        load_audio_loop(5, 1, electric_bass_path)
        load_audio_loop(5, 2, electric_bass_path)
    else:
        print(f"Warning: Electric bass loop not found: {electric_bass_path}")

    if os.path.exists(synth_sub_path):
        print("Writing sub-bass synth loop to Track 6 (SUB - Audio Loop) for Chorus & Verse...")
        load_audio_loop(6, 1, synth_sub_path)
        load_audio_loop(6, 2, synth_sub_path)
    else:
        print(f"Warning: Sub-bass loop not found: {synth_sub_path}")

    # Trigger Scene 1 (Intro) to refresh playback state
    print("Triggering Scene 1 (Intro) to sync playback...")
    client.send_message("/live/scene/fire", [0])

    print("Sub and Bass configuration completed successfully!")

if __name__ == "__main__":
    main()
