import os
import sys
import time
import subprocess
import sounddevice as sd
import soundfile as sf
import numpy as np
from pythonosc.udp_client import SimpleUDPClient

# Force UTF-8 stdout
sys.stdout.reconfigure(encoding='utf-8')

# Import spectral analysis helpers
sys.path.insert(0, r"C:\Users\isaia\Projects\music\live-pilot")
from analysis import spectral

def main():
    client = SimpleUDPClient("127.0.0.1", 11000)
    
    # Find Loop-back device
    devices = sd.query_devices()
    loopback_idx = None
    
    for idx, d in enumerate(devices):
        if "loop-back" in d["name"].lower() and "wasapi" in sd.query_hostapis(d["hostapi"])["name"].lower():
            loopback_idx = idx
            break
            
    if loopback_idx is None:
        for idx, d in enumerate(devices):
            if "loop-back" in d["name"].lower():
                loopback_idx = idx
                break
                
    if loopback_idx is None:
        print("Error: Could not find Audient Loop-back device.")
        sys.exit(1)
        
    device_info = sd.query_devices(loopback_idx)
    sr = int(device_info.get("default_samplerate", 44100))
    duration = 16.0
    
    print(f"Triggering Scene 2 (Chorus)...")
    client.send_message("/live/scene/fire", [1])
    time.sleep(1.0) # wait for start and pre-roll
    
    print(f"Recording {duration}s from {device_info['name']} (Index {loopback_idx})...")
    audio_data = sd.rec(int(duration * sr), samplerate=sr, channels=2, device=loopback_idx, dtype='float32')
    sd.wait()
    
    print("Stopping playback...")
    client.send_message("/live/song/stop", [])
    
    wav_path = r"C:\Users\isaia\Projects\music\live-pilot\scratch\rendered_beat_pro.wav"
    mp3_path = r"C:\Users\isaia\Projects\music\live-pilot\scratch\rendered_beat_pro.mp3"
    
    sf.write(wav_path, audio_data, sr)
    print(f"Saved WAV to {wav_path}")
    
    # Convert to MP3
    print("Converting to MP3 via FFmpeg...")
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", wav_path,
            "-codec:a", "libmp3lame", "-qscale:a", "2",
            mp3_path
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        print(f"Saved MP3 to {mp3_path}")
    except Exception as e:
        print(f"FFmpeg conversion failed: {e}")
        
    # Analyze
    print("Analyzing audio using spectral library...")
    report = spectral.analyze(audio_data, sr)
    
    print("\n--- NEW REFINED SPECTRAL REPORT ---")
    print(f"Sample Rate: {report.sample_rate} Hz")
    print(f"Duration: {report.duration_seconds:.2f} s")
    print(f"Total Power: {report.total_power_db:.2f} dB")
    print(f"Crest Factor: {report.crest_factor_db:.2f} dB")
    print(f"Centroid (Brightness): {report.spectral_centroid_hz:.1f} Hz")
    print(f"Bandwidth: {report.spectral_bandwidth_hz:.1f} Hz")
    print(f"Mid/Side Ratio (Stereo): {report.mid_side_ratio:.2f}")
    
    print("\nFrequency Bands Power Distribution:")
    for band in report.bands:
        print(f"  {band.label:<12}: {band.power_db:6.1f} dB  (normalized: {band.normalized_db:6.1f} dB)")
        
    print("\n--------------------------------")

if __name__ == "__main__":
    main()
