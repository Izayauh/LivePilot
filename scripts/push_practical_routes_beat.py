#!/usr/bin/env python3
import time
import sys
from pythonosc.udp_client import SimpleUDPClient

def main():
    client = SimpleUDPClient("127.0.0.1", 11000)
    print("Connecting to Ableton Live OSC on port 11000...")

    # 1. Set song tempo to 82 BPM
    print("Setting tempo to 82 BPM...")
    client.send_message("/live/song/set/tempo", [82.0])
    time.sleep(0.1)

    # 2. Rhodes Chords (Cm9 - Abmaj7 - Fm9 - G7alt)
    chords = []
    voicings = [
        [48, 55, 58, 62, 63], # Cm9
        [44, 55, 60, 63, 67], # Abmaj7
        [41, 55, 56, 60, 63], # Fm9
        [43, 53, 56, 59, 63]  # G7alt
    ]
    for bar in range(8):
        base = bar * 4
        chord_voicing = voicings[bar % 4]
        for pitch in chord_voicing:
            chords.append({
                "pitch": pitch,
                "start": base,
                "end": base + 3.75,
                "velocity": 60
            })

    # 3. Sub Bass
    bass = []
    root_pitches = [36, 32, 29, 31]
    for bar in range(8):
        base = bar * 4
        root = root_pitches[bar % 4]
        bass.append({"pitch": root, "start": base + 0.0, "end": base + 2.5, "velocity": 85})
        
        if bar % 4 == 0:
            bass.append({"pitch": 39, "start": base + 2.75, "end": base + 3.25, "velocity": 80})
            bass.append({"pitch": 43, "start": base + 3.5, "end": base + 3.75, "velocity": 80})
        elif bar % 4 == 1:
            bass.append({"pitch": 32, "start": base + 3.0, "end": base + 3.75, "velocity": 85})
        elif bar % 4 == 2:
            bass.append({"pitch": 32, "start": base + 2.75, "end": base + 3.25, "velocity": 80})
            bass.append({"pitch": 34, "start": base + 3.5, "end": base + 3.75, "velocity": 80})
        elif bar % 4 == 3:
            bass.append({"pitch": 31, "start": base + 3.0, "end": base + 3.75, "velocity": 85})

    # 4. Drums (Swung boom bap rim & kick & hats)
    drums = []
    for bar in range(8):
        base = bar * 4
        # Snare/Rim on 2 and 4 (beat 1.0 and 3.0)
        drums.append({"pitch": 38, "start": base + 1.0, "end": base + 1.1, "velocity": 95})
        drums.append({"pitch": 38, "start": base + 3.0, "end": base + 3.1, "velocity": 95})

        # Kick
        if bar % 2 == 0:
            drums.append({"pitch": 36, "start": base + 0.0, "end": base + 0.15, "velocity": 105})
            drums.append({"pitch": 36, "start": base + 2.26, "end": base + 2.4, "velocity": 100})
        else:
            drums.append({"pitch": 36, "start": base + 0.0, "end": base + 0.15, "velocity": 105})
            drums.append({"pitch": 36, "start": base + 2.26, "end": base + 2.4, "velocity": 100})
            drums.append({"pitch": 36, "start": base + 3.76, "end": base + 3.9, "velocity": 90})

        # Swung hats
        for step in range(8):
            start_beat = step * 0.5
            if step % 2 == 1:
                start_beat += 0.04
            drums.append({
                "pitch": 42,
                "start": base + start_beat,
                "end": base + start_beat + 0.05,
                "velocity": 50 if step % 2 == 1 else 65
            })

    def recreate_midi_clip(track_idx, clip_idx, length_beats):
        print(f"Creating MIDI clip on track {track_idx + 1}, slot {clip_idx + 1}...")
        client.send_message("/live/clip_slot/delete_clip", [track_idx, clip_idx])
        time.sleep(0.1)
        client.send_message("/live/clip_slot/create_clip", [track_idx, clip_idx, float(length_beats)])
        time.sleep(0.2)

    def push_notes(track_idx, clip_idx, notes):
        print(f"Pushing {len(notes)} notes to track {track_idx + 1}, slot {clip_idx + 1}...")
        chunk_size = 20
        for i in range(0, len(notes), chunk_size):
            chunk = notes[i:i+chunk_size]
            params = [track_idx, clip_idx]
            for note in chunk:
                params.extend([
                    int(note["pitch"]),
                    float(note["start"]),
                    float(note["end"] - note["start"]),
                    int(note.get("velocity", 90)),
                    0 # mute (0 = False)
                ])
            client.send_message("/live/clip/add/notes", params)
            time.sleep(0.05)

    # Recreate and push to Track index 0 (Rhodes Chords)
    recreate_midi_clip(0, 0, 32.0)
    push_notes(0, 0, chords)

    # Recreate and push to Track index 1 (Sub Bass)
    recreate_midi_clip(1, 0, 32.0)
    push_notes(1, 0, bass)

    # Set up Track index 2 (AUDIO - Soul Sample) clip properties
    print("Configuring Audio Clip properties on track 3, slot 1...")
    # Enable warping
    client.send_message("/live/clip/set/warping", [2, 0, 1])
    time.sleep(0.1)
    # Enable looping
    client.send_message("/live/clip/set/looping", [2, 0, 1])
    time.sleep(0.1)
    # Set loop start
    client.send_message("/live/clip/set/loop_start", [2, 0, 0.0])
    time.sleep(0.1)
    # Set loop end to 16.0 beats (4 bars at 63.5 BPM)
    client.send_message("/live/clip/set/loop_end", [2, 0, 16.0])
    time.sleep(0.1)

    # Recreate and push to Track index 3 (DRUMS - Kick Snare Rim)
    recreate_midi_clip(3, 0, 32.0)
    push_notes(3, 0, drums)

    # Start playback of all clips
    print("Firing all clips in Ableton Live...")
    client.send_message("/live/clip/fire", [0, 0])
    client.send_message("/live/clip/fire", [1, 0])
    client.send_message("/live/clip/fire", [2, 0])
    client.send_message("/live/clip/fire", [3, 0])
    time.sleep(0.1)
    
    # Start song playing
    print("Starting global song playback...")
    client.send_message("/live/song/start_playing", [])

    print("Success: Beat successfully loaded and playing inside Ableton Live!")

if __name__ == "__main__":
    main()
