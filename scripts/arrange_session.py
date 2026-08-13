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

    # 1. Ensure scene count is at least 4
    # Query num scenes via AbletonController sync helper if available
    # Or just try to create scenes 1, 2, 3
    print("Ensuring 4 scenes exist in session...")
    for _ in range(5): # Create extra scenes to be safe
        client.send_message("/live/song/create_scene", [-1])
        time.sleep(0.05)

    # Name the scenes
    time.sleep(0.2)
    client.send_message("/live/scene/set/name", [0, "1. Intro (Vibe Setup)"])
    client.send_message("/live/scene/set/name", [1, "2. Chorus (Full Vibe)"])
    client.send_message("/live/scene/set/name", [2, "3. Verse (Vocal Pocket)"])
    client.send_message("/live/scene/set/name", [3, "4. Outro (Ethereal Out)"])
    time.sleep(0.1)

    # WAV sample path for track 2 (Soul Sample)
    wav_path = r"C:\Users\isaia\Documents\Ableton\User Library\Samples\Processed\Freeze\Freeze 1-Komplete Kontrol [2025-12-11 065557]-2.wav"
    if not os.path.exists(wav_path):
        print(f"Warning: Audio sample path not found: {wav_path}")

    # Chords, Bass, Drums definitions (exactly the same as v2 refined version)
    # Chord voicings
    cm9_basic = [48, 55, 58, 62, 63]  # C3, G3, Bb3, D4, Eb4
    cm9_ext   = [48, 58, 62, 63, 67]  # C3, Bb3, D4, Eb4, G4 (Higher voicing)
    abmaj7_basic = [44, 55, 60, 63, 67] # Ab2, G3, C4, Eb4, G4
    abmaj7_ext   = [44, 60, 63, 67, 70] # Ab2, C4, Eb4, G4, Bb4 (9th extension)
    fm9_basic = [41, 55, 56, 60, 63]  # F2, G3, Ab3, C4, Eb4
    fm9_ext   = [41, 56, 60, 63, 67]  # F2, Ab3, C4, Eb4, G4 (Higher extension)
    g7alt_basic = [43, 53, 56, 59, 63] # G2, F3, Ab3, B3, Eb4
    g7alt_ext   = [43, 56, 59, 63, 66] # G2, Ab3, B3, Eb4, Gb4

    chords = []
    for bar in range(8):
        base = bar * 4
        is_even = (bar % 2 == 0)
        if bar % 4 == 0:
            v_main, v_stab = cm9_basic, cm9_ext
        elif bar % 4 == 1:
            v_main, v_stab = abmaj7_basic, abmaj7_ext
        elif bar % 4 == 2:
            v_main, v_stab = fm9_basic, fm9_ext
        else:
            v_main, v_stab = g7alt_basic, g7alt_ext

        if is_even:
            for p in v_main: chords.append({"pitch": p, "start": base + 0.0, "end": base + 1.75, "velocity": 65})
            for p in v_stab: chords.append({"pitch": p, "start": base + 2.0, "end": base + 2.5, "velocity": 55})
            for p in v_stab: chords.append({"pitch": p, "start": base + 3.5, "end": base + 4.5, "velocity": 60})
        else:
            for p in v_main: chords.append({"pitch": p, "start": base + 0.5, "end": base + 2.0, "velocity": 62})
            for p in v_stab: chords.append({"pitch": p, "start": base + 2.5, "end": base + 3.0, "velocity": 50})
            for p in v_main: chords.append({"pitch": p, "start": base + 3.75, "end": base + 4.0, "velocity": 45})

    bass = []
    for bar in range(8):
        base = bar * 4
        mode = bar % 4
        if mode == 0:
            bass.append({"pitch": 36, "start": base + 0.0, "end": base + 1.5, "velocity": 85})
            bass.append({"pitch": 48, "start": base + 2.0, "end": base + 2.5, "velocity": 75})
            bass.append({"pitch": 43, "start": base + 2.5, "end": base + 3.25, "velocity": 80})
            bass.append({"pitch": 39, "start": base + 3.5, "end": base + 3.75, "velocity": 80})
        elif mode == 1:
            bass.append({"pitch": 32, "start": base + 0.0, "end": base + 1.5, "velocity": 85})
            bass.append({"pitch": 44, "start": base + 2.0, "end": base + 2.5, "velocity": 75})
            bass.append({"pitch": 39, "start": base + 2.5, "end": base + 3.25, "velocity": 80})
            bass.append({"pitch": 36, "start": base + 3.5, "end": base + 3.75, "velocity": 80})
        elif mode == 2:
            bass.append({"pitch": 29, "start": base + 0.0, "end": base + 1.5, "velocity": 85})
            bass.append({"pitch": 41, "start": base + 2.0, "end": base + 2.5, "velocity": 75})
            bass.append({"pitch": 36, "start": base + 2.5, "end": base + 3.25, "velocity": 80})
            bass.append({"pitch": 32, "start": base + 3.25, "end": base + 3.5, "velocity": 75})
            bass.append({"pitch": 34, "start": base + 3.5, "end": base + 3.75, "velocity": 80})
        else:
            bass.append({"pitch": 31, "start": base + 0.0, "end": base + 1.5, "velocity": 85})
            bass.append({"pitch": 43, "start": base + 2.0, "end": base + 2.5, "velocity": 75})
            bass.append({"pitch": 38, "start": base + 2.5, "end": base + 3.25, "velocity": 80})
            bass.append({"pitch": 37, "start": base + 3.5, "end": base + 3.75, "velocity": 80})

    drums = []
    for bar in range(8):
        base = bar * 4
        is_even = (bar % 2 == 0)
        drums.append({"pitch": 38, "start": base + 1.0, "end": base + 1.1, "velocity": 98})
        drums.append({"pitch": 38, "start": base + 3.0, "end": base + 3.1, "velocity": 94})
        drums.append({"pitch": 38, "start": base + 1.75, "end": base + 1.85, "velocity": 35})
        drums.append({"pitch": 38, "start": base + 2.5, "end": base + 2.6, "velocity": 28})
        if not is_even:
            drums.append({"pitch": 38, "start": base + 3.75, "end": base + 3.85, "velocity": 40})
        drums.append({"pitch": 36, "start": base + 0.0, "end": base + 0.15, "velocity": 105})
        if is_even:
            drums.append({"pitch": 36, "start": base + 2.26, "end": base + 2.4, "velocity": 98})
        else:
            drums.append({"pitch": 36, "start": base + 2.26, "end": base + 2.4, "velocity": 98})
            drums.append({"pitch": 36, "start": base + 3.76, "end": base + 3.9, "velocity": 88})
        for step in range(8):
            start_beat = step * 0.5
            if step % 2 == 1: start_beat += 0.04
            if step == 2: continue
            drums.append({
                "pitch": 42, "start": base + start_beat, "end": base + start_beat + 0.05,
                "velocity": 45 if step % 2 == 1 else 68
            })
        if not is_even:
            drums.append({"pitch": 46, "start": base + 3.5, "end": base + 3.7, "velocity": 55})

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

    def load_audio_clip(track_idx, slot_idx, filepath):
        # Calls JarvisDeviceLoader
        print(f"Loading audio loop into Track {track_idx+1} Slot {slot_idx+1}...")
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

        # Set clip to warp & loop (length 16.0 beats)
        client.send_message("/live/clip/set/warp_mode", [track_idx, slot_idx, 0])
        client.send_message("/live/clip/set/warping", [track_idx, slot_idx, 1])
        client.send_message("/live/clip/set/looping", [track_idx, slot_idx, 1])
        client.send_message("/live/clip/set/loop_start", [track_idx, slot_idx, 0.0])
        client.send_message("/live/clip/set/loop_end", [track_idx, slot_idx, 16.0])
        time.sleep(0.05)

    # Clear slots 0, 1, 2, 3 on all tracks
    print("Clearing clip slots...")
    for t in [0, 1, 2, 3]:
        for s in [0, 1, 2, 3]:
            client.send_message("/live/clip_slot/delete_clip", [t, s])
            time.sleep(0.02)

    # Write Intro (Scene 0)
    print("\nWriting Scene 1: Intro...")
    recreate_midi_clip(0, 0, 32.0)
    push_notes(0, 0, chords)
    load_audio_clip(2, 0, wav_path)

    # Write Chorus (Scene 1)
    print("\nWriting Scene 2: Chorus...")
    recreate_midi_clip(0, 1, 32.0)
    push_notes(0, 1, chords)
    recreate_midi_clip(1, 1, 32.0)
    push_notes(1, 1, bass)
    load_audio_clip(2, 1, wav_path)
    recreate_midi_clip(3, 1, 32.0)
    push_notes(3, 1, drums)

    # Write Verse (Scene 2)
    print("\nWriting Scene 3: Verse...")
    # Rhodes left empty for vocal space!
    recreate_midi_clip(1, 2, 32.0)
    push_notes(1, 2, bass)
    load_audio_clip(2, 2, wav_path)
    recreate_midi_clip(3, 2, 32.0)
    push_notes(3, 2, drums)

    # Write Outro (Scene 3)
    print("\nWriting Scene 4: Outro...")
    recreate_midi_clip(0, 3, 32.0)
    push_notes(0, 3, chords)
    # Bass, Sample, and Drums left empty for fading out

    # Trigger playback of Scene 1 (Intro) to start
    print("\nFiring Scene 1 (Intro) to start playback...")
    client.send_message("/live/scene/fire", [0])

    print("Success: 4-scene R&B instrumental arrangement constructed and active!")

if __name__ == "__main__":
    main()
