#!/usr/bin/env python3
import sys
import os

# Force UTF-8 output encoding for stdout
sys.stdout.reconfigure(encoding='utf-8')

import numpy as np
import librosa

# Krumhansl-Schmuckler key profiles
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

def estimate_key(y, sr):
    # Compute chroma representation
    chromagram = librosa.feature.chroma_cqt(y=y, sr=sr)
    # Sum chroma over time
    chroma_mean = np.mean(chromagram, axis=1)
    
    # Normalize chroma vector
    chroma_mean = (chroma_mean - np.mean(chroma_mean)) / (np.std(chroma_mean) + 1e-6)
    
    best_corr = -1.0
    best_key = ""
    
    for i in range(12):
        # Shift profiles to match key starting on i
        shifted_major = np.roll(MAJOR_PROFILE, i)
        shifted_minor = np.roll(MINOR_PROFILE, i)
        
        # Normalize profiles
        shifted_major = (shifted_major - np.mean(shifted_major)) / (np.std(shifted_major) + 1e-6)
        shifted_minor = (shifted_minor - np.mean(shifted_minor)) / (np.std(shifted_minor) + 1e-6)
        
        # Calculate Pearson correlation
        corr_major = np.corrcoef(chroma_mean, shifted_major)[0, 1]
        corr_minor = np.corrcoef(chroma_mean, shifted_minor)[0, 1]
        
        if corr_major > best_corr:
            best_corr = corr_major
            best_key = f"{NOTE_NAMES[i]} Major"
            
        if corr_minor > best_corr:
            best_corr = corr_minor
            best_key = f"{NOTE_NAMES[i]} Minor"
            
    return best_key, best_corr

def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_audio.py <path_to_audio_file>")
        sys.exit(1)
        
    filepath = sys.argv[1]
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        sys.exit(1)
        
    print(f"Loading and analyzing: {os.path.basename(filepath)}...")
    
    # Load first 60 seconds of audio to speed up analysis
    y, sr = librosa.load(filepath, duration=60.0)
    
    duration = librosa.get_duration(y=y, sr=sr)
    print(f"Duration analyzed: {duration:.2f} seconds")
    
    # Estimate Tempo
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    # tempo could be scalar or array in newer librosa versions
    bpm = tempo[0] if hasattr(tempo, "__len__") else tempo
    print(f"Estimated Tempo: {bpm:.1f} BPM")
    
    # Estimate Key
    key, confidence = estimate_key(y, sr)
    print(f"Estimated Key: {key} (confidence: {confidence:.2f})")
    
    # Calculate RMS Energy (Average Loudness)
    rms = librosa.feature.rms(y=y)
    mean_rms = np.mean(rms)
    max_rms = np.max(rms)
    print(f"Loudness (RMS) - Mean: {mean_rms:.3f}, Peak: {max_rms:.3f}")
    
    print("\nAnalysis Complete!")

if __name__ == "__main__":
    main()
