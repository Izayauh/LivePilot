"""
Audio Analyst Module

Analyzes reference audio tracks to extract sonic characteristics and suggest
processing chains based on spectral and dynamic analysis.
"""

import os
import logging
import numpy as np
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

# Get logger
logger = logging.getLogger("jarvis.research.audio_analyst")

@dataclass
class AudioFeatures:
    """Extracted audio features"""
    tempo: float
    spectral_centroid_mean: float  # Brightness
    spectral_bandwidth_mean: float # Width of spectrum
    rms_mean: float               # Loudness
    rms_std: float                # Dynamic range (higher = more dynamic)
    zero_crossing_rate_mean: float # Noisiness/Sibilance
    duration: float

class AudioAnalyst:
    """
    Analyzes audio files to suggest production techniques.
    """
    
    def __init__(self):
        self._librosa = None
        
    def _ensure_librosa(self):
        """Lazily import librosa as it's heavy"""
        if self._librosa is None:
            import librosa
            self._librosa = librosa
            
    def analyze_track(self, file_path: str) -> Dict[str, Any]:
        """
        Analyze an audio track and return features and suggestions.
        
        Args:
            file_path: Path to audio file
            
        Returns:
            Dict containing features and chain suggestions
        """
        if not os.path.exists(file_path):
            return {"success": False, "message": f"File not found: {file_path}"}
            
        try:
            self._ensure_librosa()
            y, sr = self._librosa.load(file_path, duration=30) # Analyze first 30s
            
            features = self._extract_features(y, sr)
            suggestions = self._generate_suggestions(features)
            
            return {
                "success": True,
                "features": features.__dict__,
                "suggestions": suggestions,
                "chain_spec": self._suggestions_to_chain_spec(suggestions)
            }
            
        except Exception as e:
            logger.error(f"Audio analysis failed: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "message": str(e)}

    def _extract_features(self, y, sr) -> AudioFeatures:
        """Extract technical audio features"""
        librosa = self._librosa
        
        # Spectral
        centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
        bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)
        
        # Dynamics
        rms = librosa.feature.rms(y=y)
        
        # Temporal
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        zcr = librosa.feature.zero_crossing_rate(y)
        
        return AudioFeatures(
            tempo=float(tempo),
            spectral_centroid_mean=float(np.mean(centroid)),
            spectral_bandwidth_mean=float(np.mean(bandwidth)),
            rms_mean=float(np.mean(rms)),
            rms_std=float(np.std(rms)),
            zero_crossing_rate_mean=float(np.mean(zcr)),
            duration=librosa.get_duration(y=y, sr=sr)
        )

    def _generate_suggestions(self, features: AudioFeatures) -> List[Dict]:
        """Generate processing suggestions based on features"""
        suggestions = []
        
        # 1. EQ Suggestions
        if features.spectral_centroid_mean < 1500:
            suggestions.append({
                "type": "eq",
                "name": "EQ Eight",
                "reason": "Tracking is dark (Low Centroid). Consider high-shelf boost.",
                "settings": {"High Shelf Gain": 3.0, "High Shelf Freq": 5000}
            })
        elif features.spectral_centroid_mean > 3500:
            suggestions.append({
                "type": "eq",
                "name": "EQ Eight",
                "reason": "Tracking is bright (High Centroid). Watch for harshness.",
                "settings": {"High Cut Freq": 18000}
            })
            
        # 2. Dynamics Suggestions
        # High RMS std dev means high dynamic range -> needs compression
        if features.rms_std > 0.05:
            suggestions.append({
                "type": "compressor",
                "name": "Compressor",
                "reason": "High dynamic range detected. Use compression to glue.",
                "settings": {"Ratio": 4.0, "Threshold": -20.0}
            })
        else:
            suggestions.append({
                "type": "compressor",
                "name": "Compressor",
                "reason": "Consistent dynamics. Light compression for color.",
                "settings": {"Ratio": 2.0, "Threshold": -15.0}
            })
            
        # 3. Sibilance/De-essing
        if features.zero_crossing_rate_mean > 0.1:
             suggestions.append({
                "type": "dynamics",
                "name": "De-Esser", # Or MB compression
                "reason": "High zero-crossing rate suggests sibilance.",
                "settings": {"Threshold": -25.0}
            })
            
        return suggestions

    def _suggestions_to_chain_spec(self, suggestions: List[Dict]) -> Dict:
        """Convert suggestions to a simple chain format"""
        # Mapping to jarvis chain format
        chain = []
        for s in suggestions:
            chain.append({
                "plugin_name": s["name"],
                "category": s["type"],
                "purpose": s["reason"],
                "parameters": s["settings"],
                "confidence": 0.7
            })
        return chain

# Singleton instance
_analyst = None

def get_audio_analyst():
    global _analyst
    if _analyst is None:
        _analyst = AudioAnalyst()
    return _analyst
