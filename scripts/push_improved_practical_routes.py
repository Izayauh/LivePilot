#!/usr/bin/env python3
import time
import sys
from pythonosc.udp_client import SimpleUDPClient

def main():
    client = SimpleUDPClient("127.0.0.1", 11000)
    print("Connecting to Ableton Live OSC on port 11000...")

    # 1. Ensure Tempo is locked at 82 BPM
    client.send_message("/live/song/set/tempo", [82.0])
    time.sleep(0.05)

    # 2. Rhodes Active Comping MIDI (Cm9 - Abmaj7 - Fm9 - G7alt)
    chords = []
    
    # Chord voicings
    cm9_basic = [48, 55, 58, 62, 63]  # C3, G3, Bb3, D4, Eb4
    cm9_ext   = [48, 58, 62, 63, 67]  # C3, Bb3, D4, Eb4, G4 (Higher voicing)
    
    abmaj7_basic = [44, 55, 60, 63, 67] # Ab2, G3, C4, Eb4, G4
    abmaj7_ext   = [44, 60, 63, 67, 70] # Ab2, C4, Eb4, G4, Bb4 (9th extension)
    
    fm9_basic = [41, 55, 56, 60, 63]  # F2, G3, Ab3, C4, Eb4
    fm9_ext   = [41, 56, 60, 63, 67]  # F2, Ab3, C4, Eb4, G4 (Higher extension)
    
    g7alt_basic = [43, 53, 56, 59, 63] # G2, F3, Ab3, B3, Eb4
    g7alt_ext   = [43, 56, 59, 63, 66] # G2, Ab3, B3, Eb4, Gb4 (Flat 9 / Sharp 9)

    for bar in range(8):
        base = bar * 4
        is_even = (bar % 2 == 0)
        
        # Select voicings dynamically for movement
        if bar % 4 == 0:
            v_main, v_stab = cm9_basic, cm9_ext
        elif bar % 4 == 1:
            v_main, v_stab = abmaj7_basic, abmaj7_ext
        elif bar % 4 == 2:
            v_main, v_stab = fm9_basic, fm9_ext
        else:
            v_main, v_stab = g7alt_basic, g7alt_ext

        # Rhythmic layout
        if is_even:
            # Beat 0.0: Main chord (sustained)
            for p in v_main:
                chords.append({"pitch": p, "start": base + 0.0, "end": base + 1.75, "velocity": 65})
            # Beat 2.0: Dynamic rhythmic stab
            for p in v_stab:
                chords.append({"pitch": p, "start": base + 2.0, "end": base + 2.5, "velocity": 55})
            # Beat 3.5: Anticipation stab into next bar
            for p in v_stab:
                chords.append({"pitch": p, "start": base + 3.5, "end": base + 4.5, "velocity": 60})
        else:
            # Beat 0.5 (offbeat resolution)
            for p in v_main:
                chords.append({"pitch": p, "start": base + 0.5, "end": base + 2.0, "velocity": 62})
            # Beat 2.5: Soft rhythmic stab
            for p in v_stab:
                chords.append({"pitch": p, "start": base + 2.5, "end": base + 3.0, "velocity": 50})
            # Beat 3.75: Very soft transition chord
            for p in v_main:
                chords.append({"pitch": p, "start": base + 3.75, "end": base + 4.0, "velocity": 45})

    # 3. Melodic & Syncopated Sub Bass
    # Uses octaves and 5ths to create melodic movement inspired by alternative pop basslines
    bass = []
    for bar in range(8):
        base = bar * 4
        mode = bar % 4
        
        if mode == 0:  # C Minor
            bass.append({"pitch": 36, "start": base + 0.0, "end": base + 1.5, "velocity": 85}) # C2
            bass.append({"pitch": 48, "start": base + 2.0, "end": base + 2.5, "velocity": 75}) # C3 (Octave jump)
            bass.append({"pitch": 43, "start": base + 2.5, "end": base + 3.25, "velocity": 80}) # G2 (5th)
            bass.append({"pitch": 39, "start": base + 3.5, "end": base + 3.75, "velocity": 80}) # Eb2 (Minor 3rd)
        elif mode == 1:  # Ab Major
            bass.append({"pitch": 32, "start": base + 0.0, "end": base + 1.5, "velocity": 85}) # Ab1
            bass.append({"pitch": 44, "start": base + 2.0, "end": base + 2.5, "velocity": 75}) # Ab2 (Octave jump)
            bass.append({"pitch": 39, "start": base + 2.5, "end": base + 3.25, "velocity": 80}) # Eb2 (5th)
            bass.append({"pitch": 36, "start": base + 3.5, "end": base + 3.75, "velocity": 80}) # C2
        elif mode == 2:  # F Minor
            bass.append({"pitch": 29, "start": base + 0.0, "end": base + 1.5, "velocity": 85}) # F1
            bass.append({"pitch": 41, "start": base + 2.0, "end": base + 2.5, "velocity": 75}) # F2 (Octave jump)
            bass.append({"pitch": 36, "start": base + 2.5, "end": base + 3.25, "velocity": 80}) # C2 (5th)
            # Melodic walk-up to G
            bass.append({"pitch": 32, "start": base + 3.25, "end": base + 3.5, "velocity": 75}) # Ab1
            bass.append({"pitch": 34, "start": base + 3.5, "end": base + 3.75, "velocity": 80}) # Bb1
        else:  # G7alt
            bass.append({"pitch": 31, "start": base + 0.0, "end": base + 1.5, "velocity": 85}) # G1
            bass.append({"pitch": 43, "start": base + 2.0, "end": base + 2.5, "velocity": 75}) # G2 (Octave jump)
            bass.append({"pitch": 38, "start": base + 2.5, "end": base + 3.25, "velocity": 80}) # D2 (5th)
            # Step down to C
            bass.append({"pitch": 37, "start": base + 3.5, "end": base + 3.75, "velocity": 80}) # Db2 (Tritone substitute approach)

    # 4. Drums (Pocket with Ghost Notes, Velocity Dynamics, & Air)
    drums = []
    for bar in range(8):
        base = bar * 4
        is_even = (bar % 2 == 0)

        # Snare/Rim on 2 and 4 (beat 1.0 and 3.0) with slight velocity variation
        drums.append({"pitch": 38, "start": base + 1.0, "end": base + 1.1, "velocity": 98})
        drums.append({"pitch": 38, "start": base + 3.0, "end": base + 3.1, "velocity": 94})

        # --- Ghost Snares (Indie/Alternative Pocket Details) ---
        drums.append({"pitch": 38, "start": base + 1.75, "end": base + 1.85, "velocity": 35})
        drums.append({"pitch": 38, "start": base + 2.5, "end": base + 2.6, "velocity": 28})
        if not is_even:
            drums.append({"pitch": 38, "start": base + 3.75, "end": base + 3.85, "velocity": 40})

        # Kick Drum (Laid-back, syncopated and micro-timed)
        # Downbeat kick (105 velocity)
        drums.append({"pitch": 36, "start": base + 0.0, "end": base + 0.15, "velocity": 105})
        
        # Off-beat kicks
        if is_even:
            # Syncopated kick on the 'and' of 2
            drums.append({"pitch": 36, "start": base + 2.26, "end": base + 2.4, "velocity": 98})
        else:
            drums.append({"pitch": 36, "start": base + 2.26, "end": base + 2.4, "velocity": 98})
            # Anticipation kick before next downbeat
            drums.append({"pitch": 36, "start": base + 3.76, "end": base + 3.9, "velocity": 88})

        # Swung Hats (Humanized velocities)
        for step in range(8):
            start_beat = step * 0.5
            # Swing offset on 16th steps
            if step % 2 == 1:
                start_beat += 0.04
            
            # Skip hat occasionally to let the snare breathe
            if step == 2:  # Hitting right on snare beat 1.0
                continue
                
            drums.append({
                "pitch": 42,
                "start": base + start_beat,
                "end": base + start_beat + 0.05,
                "velocity": 45 if step % 2 == 1 else 68
            })

        # Open Hi-hat for "air" at the end of odd bars
        if not is_even:
            drums.append({"pitch": 46, "start": base + 3.5, "end": base + 3.7, "velocity": 55})

    def recreate_midi_clip(track_idx, clip_idx, length_beats):
        print(f"Clearing and creating MIDI clip on track {track_idx + 1}, slot {clip_idx + 1}...")
        client.send_message("/live/clip_slot/delete_clip", [track_idx, clip_idx])
        time.sleep(0.1)
        client.send_message("/live/clip_slot/create_clip", [track_idx, clip_idx, float(length_beats)])
        time.sleep(0.2)

    def push_notes(track_idx, clip_idx, notes):
        print(f"Injecting {len(notes)} notes into track {track_idx + 1}, slot {clip_idx + 1}...")
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

    # 5. Execute MIDI Updates
    recreate_midi_clip(0, 0, 32.0)
    push_notes(0, 0, chords)

    recreate_midi_clip(1, 0, 32.0)
    push_notes(1, 0, bass)

    recreate_midi_clip(3, 0, 32.0)
    push_notes(3, 0, drums)

    # Trigger clips to refresh playback
    print("Firing updated clips...")
    client.send_message("/live/clip/fire", [0, 0])
    client.send_message("/live/clip/fire", [1, 0])
    client.send_message("/live/clip/fire", [2, 0])
    client.send_message("/live/clip/fire", [3, 0])

    print("Success: Refined, dynamic beat pushed to Ableton Live successfully!")

if __name__ == "__main__":
    main()
