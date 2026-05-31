"""
Reference Track Analyzer

Extends the existing AudioAnalyst with the ability to:
1. Extract a detailed spectral profile from a reference track
2. Compare reference vs. current track spectra
3. Suggest concrete EQ/compressor/etc. parameter values to match the reference
"""

import os
import logging
import math
import numpy as np
from typing import Dict, List, Any, Optional

from research.audio_analyst import AudioAnalyst, AudioFeatures, get_audio_analyst

logger = logging.getLogger("jarvis.research.reference_analyzer")


class ReferenceAnalyzer:
    """Analyzes reference tracks and suggests concrete device settings."""

    def __init__(self):
        self._analyst = get_audio_analyst()
        self._librosa = None

    def _ensure_librosa(self):
        if self._librosa is None:
            import librosa
            self._librosa = librosa

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_reference(self, audio_path: str) -> Dict[str, Any]:
        """
        Full spectral + dynamics analysis of a reference track.

        Returns:
            {
                "success": bool,
                "features": AudioFeatures dict,
                "spectral_profile": { "bands": [...] },
                "dynamics_profile": { ... },
                "stereo_width": float | None
            }
        """
        if not os.path.exists(audio_path):
            return {"success": False, "message": f"File not found: {audio_path}"}

        try:
            self._ensure_librosa()
            librosa = self._librosa
            y, sr = librosa.load(audio_path, duration=30)

            features = self._analyst._extract_features(y, sr)
            spectral = self._spectral_profile(y, sr)
            dynamics = self._dynamics_profile(y, sr)

            # Stereo width (if stereo file)
            stereo_width = None
            try:
                y_stereo, _ = librosa.load(audio_path, duration=30, mono=False)
                if y_stereo.ndim == 2 and y_stereo.shape[0] == 2:
                    stereo_width = self._stereo_width(y_stereo)
            except Exception:
                pass

            return {
                "success": True,
                "features": features.__dict__,
                "spectral_profile": spectral,
                "dynamics_profile": dynamics,
                "stereo_width": stereo_width,
            }

        except Exception as e:
            logger.error(f"Reference analysis failed: {e}")
            return {"success": False, "message": str(e)}

    def suggest_settings_from_reference(
        self, analysis: Dict[str, Any], device_type: str
    ) -> Dict[str, Any]:
        """
        Convert a reference analysis into concrete parameter suggestions for a
        given device type.

        Args:
            analysis: Output of analyze_reference()
            device_type: 'eq', 'compressor', 'reverb', etc.

        Returns:
            Dict of suggested parameter values in human-readable units.
        """
        if not analysis.get("success"):
            return {}

        if device_type == "eq":
            return self._suggest_eq(analysis)
        elif device_type == "compressor":
            return self._suggest_compressor(analysis)
        else:
            return {}

    def compare_tracks(
        self, reference_path: str, current_path: str
    ) -> Dict[str, Any]:
        """
        Compare a reference track to the current track and suggest EQ moves.

        Returns:
            List of EQ band suggestions to make current sound like reference.
        """
        ref = self.analyze_reference(reference_path)
        cur = self.analyze_reference(current_path)
        if not ref.get("success") or not cur.get("success"):
            return {"success": False, "message": "Analysis failed for one or both tracks"}

        ref_bands = ref["spectral_profile"]["bands"]
        cur_bands = cur["spectral_profile"]["bands"]

        eq_moves = []
        for rb, cb in zip(ref_bands, cur_bands):
            diff_db = rb["energy_db"] - cb["energy_db"]
            if abs(diff_db) > 1.5:  # Only suggest meaningful moves
                eq_moves.append({
                    "freq_hz": rb["center_freq_hz"],
                    "gain_db": round(diff_db, 1),
                    "q": 1.0,
                    "type": "bell",
                    "reason": f"Reference is {'+' if diff_db > 0 else ''}{diff_db:.1f}dB at {rb['center_freq_hz']}Hz",
                })

        return {"success": True, "eq_moves": eq_moves}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _spectral_profile(self, y, sr) -> Dict[str, Any]:
        """Compute average energy in octave bands."""
        librosa = self._librosa

        # Standard octave center frequencies
        centers = [63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
        S = np.abs(librosa.stft(y))
        freqs = librosa.fft_frequencies(sr=sr)

        bands = []
        for center in centers:
            lo = center / math.sqrt(2)
            hi = center * math.sqrt(2)
            mask = (freqs >= lo) & (freqs < hi)
            if mask.any():
                energy = np.mean(S[mask, :])
                energy_db = 20 * np.log10(energy + 1e-10)
            else:
                energy_db = -60.0
            bands.append({
                "center_freq_hz": center,
                "energy_db": round(float(energy_db), 1),
            })

        return {"bands": bands}

    def _dynamics_profile(self, y, sr) -> Dict[str, Any]:
        """Compute dynamics info useful for compressor suggestions."""
        librosa = self._librosa
        rms = librosa.feature.rms(y=y)[0]
        rms_db = 20 * np.log10(rms + 1e-10)

        return {
            "rms_mean_db": round(float(np.mean(rms_db)), 1),
            "rms_max_db": round(float(np.max(rms_db)), 1),
            "rms_min_db": round(float(np.min(rms_db)), 1),
            "dynamic_range_db": round(float(np.max(rms_db) - np.min(rms_db)), 1),
            "crest_factor_db": round(float(np.max(np.abs(y)) / (np.mean(rms) + 1e-10)), 1),
        }

    def _stereo_width(self, y_stereo) -> float:
        """Estimate stereo width as correlation between L and R (0=wide, 1=mono)."""
        left = y_stereo[0]
        right = y_stereo[1]
        correlation = float(np.corrcoef(left, right)[0, 1])
        # Invert so 1.0 = very wide, 0.0 = mono
        return round(1.0 - correlation, 2)

    def _suggest_eq(self, analysis: Dict) -> Dict[str, Any]:
        """Suggest EQ settings based on spectral profile."""
        bands = analysis["spectral_profile"]["bands"]
        features = analysis["features"]

        params = {}
        # High pass based on low-end energy
        low_energy = next((b for b in bands if b["center_freq_hz"] == 63), None)
        if low_energy and low_energy["energy_db"] < -30:
            params["band1_type"] = "high_pass"
            params["band1_freq_hz"] = 80
            params["band1_on"] = True

        # Brightness boost/cut
        centroid = features.get("spectral_centroid_mean", 2000)
        if centroid < 1500:
            params["high_shelf_freq_hz"] = 8000
            params["high_shelf_gain_db"] = 3.0
        elif centroid > 3500:
            params["high_shelf_freq_hz"] = 10000
            params["high_shelf_gain_db"] = -2.0

        return params

    def _suggest_compressor(self, analysis: Dict) -> Dict[str, Any]:
        """Suggest compressor settings based on dynamics profile."""
        dyn = analysis["dynamics_profile"]
        dr = dyn["dynamic_range_db"]

        if dr > 20:
            return {
                "threshold_db": -18.0,
                "ratio": 6.0,
                "attack_ms": 5.0,
                "release_ms": 80.0,
                "reason": f"High dynamic range ({dr:.0f}dB) - heavy compression",
            }
        elif dr > 12:
            return {
                "threshold_db": -14.0,
                "ratio": 4.0,
                "attack_ms": 10.0,
                "release_ms": 100.0,
                "reason": f"Moderate dynamic range ({dr:.0f}dB) - medium compression",
            }
        else:
            return {
                "threshold_db": -10.0,
                "ratio": 2.0,
                "attack_ms": 15.0,
                "release_ms": 150.0,
                "reason": f"Low dynamic range ({dr:.0f}dB) - gentle leveling",
            }


# Singleton
_ref_analyzer: Optional[ReferenceAnalyzer] = None


def get_reference_analyzer() -> ReferenceAnalyzer:
    global _ref_analyzer
    if _ref_analyzer is None:
        _ref_analyzer = ReferenceAnalyzer()
    return _ref_analyzer
