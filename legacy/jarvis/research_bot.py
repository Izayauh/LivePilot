"""
Research Bot - Autonomous Visual Iteration System

Orchestrator that ties together:
- Deep web/YouTube research for precise parameter values
- Parameter application via OSC
- Visual verification via screenshot + Gemini Vision
- Autonomous iteration loop

Usage:
    bot = ResearchBot()
    result = await bot.auto_chain("kanye", "donda", "vocal", track_index=2)
"""

import asyncio
import json
import logging
import math
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from calibration_utils import (
    CALIBRATION_DB_PATH,
    CalibrationStore,
    coerce_target_to_base_value,
    value_to_normalized_from_curve,
)

logger = logging.getLogger("jarvis.research_bot")

# ---------------------------------------------------------------------------
# Lazy imports to avoid circular dependencies / heavy startup cost
# ---------------------------------------------------------------------------

def _get_ableton():
    from ableton_controls.controller import ableton
    return ableton

def _get_micro_kb():
    from knowledge.micro_settings_kb import get_micro_settings_kb
    return get_micro_settings_kb()

def _get_gemini_client():
    from research.llm_client import GeminiClient
    return GeminiClient()

def _get_research_coordinator():
    from research.research_coordinator import ResearchCoordinator
    return ResearchCoordinator()

def _get_youtube_parser():
    from research.youtube_parser import YouTubeSettingsParser
    return YouTubeSettingsParser()


# ============================================================================
# ABLETON DEVICE PARAMETER MAPS
# ============================================================================
# Maps human-readable parameter names → Ableton parameter indices.
# These are for stock Ableton devices.  Indices come from empirical testing
# (see refine_eq_precision.py) and AbletonOSC documentation.

# EQ Eight parameter layout (verified from reliable_params.py SEMANTIC_PARAM_MAPPINGS):
#   Band 1: indices 1-5 (Freq=1, Gain=2, Q=3, Type=4, On=5)
#   Band 2: indices 6-10 (Freq=6, Gain=7, Q=8, Type=9, On=10)
#   Band 3: indices 11-15 (Freq=11, Gain=12, Q=13, Type=14, On=15)
#   Band 4: indices 16-20 (Freq=16, Gain=17, Q=18, Type=19, On=20)
#   Band 5-8 follow same pattern: stride of 5 per band
#
# Pattern: Band N starts at index (N-1)*5 + 1
# Offsets within band: freq=0, gain=1, q=2, type=3, on=4

EQ_EIGHT_BAND_BASE = {1: 1, 2: 6, 3: 11, 4: 16, 5: 21, 6: 26, 7: 31, 8: 36}
EQ_EIGHT_OFFSETS = {"freq": 0, "gain": 1, "q": 2, "type": 3, "on": 4}
# Type values: 0=LP48, 1=LP24, 2=LP12, 3=Notch, 4=HP12, 5=HP24, 6=HP48, 7=Bell, 8=LowShelf, 9=HighShelf

COMPRESSOR_PARAMS = {
    "threshold": 1,    # 0.0-1.0 normalized (calibrated: -70dB to +6dB)
    "ratio": 2,        # 0.0-1.0 normalized (calibrated: 1:1 to inf:1)
    "attack": 4,       # 0.0-1.0 normalized (calibrated: 0.1ms to 1000ms)
    "release": 5,      # 0.0-1.0 normalized (calibrated: 1ms to 3000ms)
    "output_gain": 6,  # Output Gain (verified from reliable_params)
    "dry_wet": 8,      # Dry/Wet (verified from reliable_params)
    "knee": 12,        # Knee (verified from reliable_params)
    "model": 10,       # 0=FF1, 1=FF2, 2=FB
}

GLUE_COMPRESSOR_PARAMS = {
    "threshold": 1,    # Verified from reliable_params
    "ratio": 2,        # Verified from reliable_params
    "attack": 3,       # Verified from reliable_params
    "release": 4,      # Verified from reliable_params
    "makeup": 6,       # Verified from reliable_params
    "dry_wet": 9,      # Verified from reliable_params
}

REVERB_PARAMS = {
    "decay_time": 3,     # Verified from reliable_params
    "predelay": 1,       # Verified from reliable_params
    "room_size": 2,      # Verified from reliable_params
    "dry_wet": 10,       # Verified from reliable_params
    "high_cut": 7,       # HiShelf Freq
    "low_cut": 5,        # LoShelf Freq
}

DELAY_PARAMS = {
    "delay_time": 2,     # L Time - verified from reliable_params
    "feedback": 12,      # Verified from reliable_params
    "dry_wet": 14,       # Verified from reliable_params
    "filter_on": 6,      # Filter on/off
    "filter_freq": 7,    # Filter Freq - verified from reliable_params
}

SATURATOR_PARAMS = {
    "type": 1,       # Shaper Type - verified from reliable_params
    "drive": 2,      # Verified from reliable_params
    "output": 3,     # Verified from reliable_params
    "dry_wet": 6,    # Verified from reliable_params
}

AUTO_FILTER_PARAMS = {
    "frequency": 3,
    "resonance": 4,
    "type": 5,
    "dry_wet": 9,
}

UTILITY_PARAMS = {
    "mute": 1,       # Verified from reliable_params
    "gain": 3,       # Verified from reliable_params
    "pan": 4,        # Panorama - verified from reliable_params
    "width": 6,      # Verified from reliable_params
}

DEVICE_PARAM_MAPS = {
    "EQ Eight": {"type": "eq_eight"},
    "Compressor": {"type": "compressor", "params": COMPRESSOR_PARAMS},
    "Glue Compressor": {"type": "glue_compressor", "params": GLUE_COMPRESSOR_PARAMS},
    "Reverb": {"type": "reverb", "params": REVERB_PARAMS},
    "Delay": {"type": "delay", "params": DELAY_PARAMS},
    "Saturator": {"type": "saturator", "params": SATURATOR_PARAMS},
    "Auto Filter": {"type": "auto_filter", "params": AUTO_FILTER_PARAMS},
    "Utility": {"type": "utility", "params": UTILITY_PARAMS},
}


# ============================================================================
# NORMALIZATION HELPERS
# ============================================================================
# Based on "Technical Analysis of Parameter Normalization and Scaling
# Transformations in the Ableton Live Object Model" (docs/Ableton LOM Parameter
# Scaling Formulas.pdf)
#
# Three primary models:
#   1. LINEAR:      V_norm = (Value - Min) / (Max - Min)
#   2. LOGARITHMIC: V_norm = ln(Value/Min) / ln(Max/Min)
#   3. EXPONENTIAL: V_norm = ((Value - Min) / (Max - Min))^(1/alpha)
#
# Ableton's OSC/LOM uses 0.0-1.0 normalized values for all parameters.


def _freq_to_normalized(freq_hz: float, min_hz: float = 10.0, max_hz: float = 22000.0) -> float:
    """Convert Hz to normalized frequency (0.0-1.0) using LOGARITHMIC scaling.

    From PDF Section 3.2 - Logarithmic Scaling (Frequency Domain):
        V_norm = ln(Value/Min) / ln(Max/Min)

    EQ Eight range: 10 Hz to 22,000 Hz
    Example: 200 Hz → 0.389
    """
    freq_hz = max(min_hz, min(freq_hz, max_hz))
    return math.log(freq_hz / min_hz) / math.log(max_hz / min_hz)


def _db_to_normalized_linear(db_value: float, min_db: float, max_db: float) -> float:
    """Convert dB to normalized (0.0-1.0) using LINEAR scaling.

    From PDF Section 4.1 - Device Gain (Saturator Drive, EQ Gain):
        V_norm = (Value - Min) / (Max - Min)

    Used for bounded dB parameters like:
      - EQ Eight Gain: -15 to +15 dB
      - Saturator Drive: 0 to 36 dB (or -36 to +36 depending on mode)
      - Utility Gain: -35 to +35 dB

    Example: -18 dB with range ±36 dB → 0.25
    """
    db_value = max(min_db, min(db_value, max_db))
    return (db_value - min_db) / (max_db - min_db)


def _threshold_to_normalized(threshold_db: float) -> float:
    """Convert compressor threshold dB to Ableton normalized 0.0-1.0.

    EMPIRICALLY CALIBRATED using calibrate_param.py:
        Normalized → Display
        0.0  → -inf dB (use -70 as practical minimum)
        0.2  → -34.4 dB
        0.5  → -14.0 dB
        0.75 → -4.0 dB
        1.0  → +6.0 dB

    Uses lookup table with linear interpolation between calibrated points.
    NOTE: Threshold range goes POSITIVE to +6 dB, not 0 dB!
    """
    _LUT = [(-70.0, 0.0), (-34.4, 0.2), (-14.0, 0.5), (-4.0, 0.75), (6.0, 1.0)]
    if threshold_db <= _LUT[0][0]:
        return _LUT[0][1]
    if threshold_db >= _LUT[-1][0]:
        return _LUT[-1][1]
    for i in range(len(_LUT) - 1):
        db0, x0 = _LUT[i]
        db1, x1 = _LUT[i + 1]
        if db0 <= threshold_db <= db1:
            t = (threshold_db - db0) / (db1 - db0)
            return x0 + t * (x1 - x0)
    return 0.5


def _ratio_to_normalized(ratio: float) -> float:
    """Convert compression ratio to Ableton normalized 0.0-1.0.

    EMPIRICALLY CALIBRATED using calibrate_param.py:
        Normalized → Display
        0.0  → 1:1
        0.2  → 1.25:1
        0.5  → 2.00:1
        0.75 → 4.00:1
        1.0  → inf:1 (use 100 as practical maximum)

    Uses lookup table with linear interpolation between calibrated points.
    """
    _LUT = [(1.0, 0.0), (1.25, 0.2), (2.0, 0.5), (4.0, 0.75), (100.0, 1.0)]
    if ratio <= _LUT[0][0]:
        return _LUT[0][1]
    if ratio >= _LUT[-1][0]:
        return _LUT[-1][1]
    for i in range(len(_LUT) - 1):
        r0, x0 = _LUT[i]
        r1, x1 = _LUT[i + 1]
        if r0 <= ratio <= r1:
            t = (ratio - r0) / (r1 - r0)
            return x0 + t * (x1 - x0)
    return 0.5


def _attack_to_normalized(attack_ms: float) -> float:
    """Convert Compressor attack time in ms to Ableton normalized (0.0-1.0).

    EMPIRICALLY CALIBRATED using calibrate_param.py:
        Normalized → Display
        0.0  → 0.1 ms
        0.5  → 3.16 ms
        0.66 → 20 ms
        0.75 → 56.2 ms
        1.0  → 1000 ms

    The curve is: display = 10^(4 * normalized^1.414 - 1)
    Inverse:      normalized = ((log10(attack_ms) + 1) / 4) ^ 0.707

    Range: 0.1 ms to 1000 ms
    """
    attack_ms = max(0.1, min(attack_ms, 1000.0))
    log_val = math.log10(attack_ms)
    normalized = ((log_val + 1.0) / 4.0) ** 0.707
    return max(0.0, min(1.0, normalized))


def _release_to_normalized(release_ms: float) -> float:
    """Convert Compressor release time in ms to Ableton normalized (0.0-1.0).

    EMPIRICALLY CALIBRATED using calibrate_param.py:
        Normalized → Display
        0.0  → 1 ms
        0.2  → 50 ms
        0.5  → 459 ms
        0.75 → 1360 ms (1.36 s)
        1.0  → 3000 ms (3.0 s)

    Uses lookup table with linear interpolation between calibrated points.
    Range: 1 ms to 3000 ms
    """
    _LUT = [(1.0, 0.0), (50.0, 0.2), (459.0, 0.5), (1360.0, 0.75), (3000.0, 1.0)]
    if release_ms <= _LUT[0][0]:
        return _LUT[0][1]
    if release_ms >= _LUT[-1][0]:
        return _LUT[-1][1]
    for i in range(len(_LUT) - 1):
        ms0, x0 = _LUT[i]
        ms1, x1 = _LUT[i + 1]
        if ms0 <= release_ms <= ms1:
            t = (release_ms - ms0) / (ms1 - ms0)
            return x0 + t * (x1 - x0)
    return 0.5


def _percent_to_normalized(pct: float) -> float:
    """Convert 0-100% to normalized 0.0-1.0 using LINEAR scaling.

    From PDF Section 3.1 - Linear Scaling:
        V_norm = (Value - Min) / (Max - Min) = Value / 100

    Used for Dry/Wet, Mix, Feedback, etc.
    """
    return max(0.0, min(pct / 100.0, 1.0))


def _q_to_normalized(q: float, min_q: float = 0.1, max_q: float = 18.0) -> float:
    """Convert Q/Resonance to normalized (0.0-1.0).

    From PDF Section 3.3 and Table 1: Q uses EXPONENTIAL scaling.
    However, it may also use logarithmic. Needs calibration.

    EQ Eight Q range: 0.1 to 18.0 (approximately)

    TODO: Calibrate with calibrate_param.py
    """
    q = max(min_q, min(q, max_q))
    # Using log scaling as approximation (common for Q parameters)
    return math.log(q / min_q) / math.log(max_q / min_q)


def _decay_to_normalized(decay_ms: float) -> float:
    """Convert reverb decay time to normalized using LOGARITHMIC scaling.

    Ableton Reverb Decay Time range: ~200 ms to ~60000 ms (estimated)

    TODO: Calibrate with calibrate_param.py
    """
    min_ms, max_ms = 200.0, 60000.0
    decay_ms = max(min_ms, min(decay_ms, max_ms))
    return math.log(decay_ms / min_ms) / math.log(max_ms / min_ms)


def _predelay_to_normalized(predelay_ms: float) -> float:
    """Convert reverb predelay to normalized using LINEAR scaling.

    Ableton Reverb Predelay range: 0 to 250 ms
    """
    return max(0.0, min(predelay_ms / 250.0, 1.0))


def _drive_to_normalized(drive_db: float, min_db: float = 0.0, max_db: float = 36.0) -> float:
    """Convert Saturator drive dB to normalized using LINEAR scaling.

    From PDF Section 4.1 - Device Gain uses linear-in-dB:
        V_norm = (Value - Min) / (Max - Min)

    Saturator Drive range: 0 dB to 36 dB
    """
    return _db_to_normalized_linear(drive_db, min_db, max_db)


def _gain_to_normalized(gain_db: float, min_db: float = -15.0, max_db: float = 15.0) -> float:
    """Convert EQ/device gain dB to normalized using LINEAR scaling.

    From PDF Section 4.1 - Device Gain uses linear-in-dB:
        V_norm = (Value - Min) / (Max - Min)

    EQ Eight Gain range: -15 dB to +15 dB
    Example: 0 dB → 0.5, -15 dB → 0.0, +15 dB → 1.0
    """
    return _db_to_normalized_linear(gain_db, min_db, max_db)


# Legacy alias for compatibility
def _gain_to_raw(gain_db: float, min_db: float = -15.0, max_db: float = 15.0) -> float:
    """DEPRECATED: Use _gain_to_normalized or _db_to_normalized_linear instead.

    This function now returns normalized values, not raw dB.
    Kept for backward compatibility.
    """
    return _db_to_normalized_linear(gain_db, min_db, max_db)


# Map of EQ Eight filter type names → numeric values
# Correct EQ Eight types: 0=LP48, 1=LP24, 2=LP12, 3=Notch, 4=HP12, 5=HP24, 6=HP48, 7=Bell, 8=LowShelf, 9=HighShelf
EQ_TYPE_MAP = {
    "low_pass": 0,      # LP48 - cuts high frequencies
    "low_pass_48": 0,
    "low_pass_24": 1,   # LP24
    "low_pass_12": 2,   # LP12
    "notch": 3,
    "high_pass": 4,     # HP12 - cuts low frequencies (aka "low cut")
    "high_pass_12": 4,
    "low_cut": 4,       # Same as high pass - cuts lows
    "high_pass_24": 5,  # HP24
    "high_pass_48": 6,  # HP48
    "bell": 7,
    "peak": 7,
    "parametric": 7,
    "low_shelf": 8,
    "high_shelf": 9,
    "high_cut": 0,      # Same as low pass - cuts highs
}

SATURATOR_TYPE_MAP = {
    "analog_clip": 0,
    "soft_sine": 1,
    "soft_curve": 1,
    "medium_curve": 2,
    "hard_curve": 3,
    "sinoid_fold": 4,
    "digital_clip": 5,
}


# ============================================================================
# RESEARCH BOT
# ============================================================================

class ResearchBot:
    """
    Autonomous orchestrator: research → apply parameters → verify visually → iterate.
    """

    def __init__(self):
        self._ableton = None
        self._micro_kb = None
        self._gemini = None
        self._coordinator = None
        self._calibration_store = None

    @property
    def ableton(self):
        if self._ableton is None:
            self._ableton = _get_ableton()
        return self._ableton

    @property
    def micro_kb(self):
        if self._micro_kb is None:
            self._micro_kb = _get_micro_kb()
        return self._micro_kb

    @property
    def gemini(self):
        if self._gemini is None:
            self._gemini = _get_gemini_client()
        return self._gemini

    @property
    def coordinator(self):
        if self._coordinator is None:
            self._coordinator = _get_research_coordinator()
        return self._coordinator

    @property
    def calibration_store(self):
        if self._calibration_store is None:
            self._calibration_store = CalibrationStore(CALIBRATION_DB_PATH)
        return self._calibration_store

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_device_names_on_track(self, track_index: int) -> Dict[int, str]:
        """Query Ableton for the actual device names on a track.

        Uses a sequential approach: loads each device one at a time, and records
        the number of loaded devices from the load_device result.
        Since the OSC name query can return interleaved responses, we use
        the parameter name signature (first 6 params) as a fingerprint.

        Returns:
            Dict mapping device_index -> device_name
        """
        import time as _time
        devices = {}

        # We know devices were loaded in order by the pipeline.
        # Query them one at a time with generous delays.
        for i in range(30):
            _time.sleep(0.25)
            names = self.ableton.get_device_parameters_name_sync(track_index, i, timeout=3.0)
            if not names.get("success") or not names.get("names"):
                break

            param_names = names["names"]
            device_name = self._identify_device_from_params(param_names)
            devices[i] = device_name

        return devices

    @staticmethod
    def _identify_device_from_params(param_names: List[str]) -> str:
        """Identify an Ableton device by its parameter names."""
        if not param_names:
            return "Unknown"
        # Check for distinctive parameter names
        names_set = set(param_names[:10])
        if "Threshold" in names_set and "Ratio" in names_set:
            if "Range" in names_set:
                return "Glue Compressor"
            return "Compressor"
        if "1 Frequency A" in names_set or "Adaptive Q" in names_set:
            return "EQ Eight"
        if "Drive" in names_set and ("Dry/Wet" in names_set or "Output" in names_set):
            return "Saturator"
        if "Delay Mode" in names_set or "Ping Pong" in names_set:
            return "Delay"
        if "Predelay" in names_set and "Diffuse Level" in param_names:
            return "Reverb"
        if "Predelay" in names_set:
            return "Reverb"
        if "Frequency" in names_set and "Resonance" in names_set:
            return "Auto Filter"
        if "Width" in names_set and "Gain" in names_set and len(param_names) < 8:
            return "Utility"
        # Fallback: use the first non-generic param name
        return "Unknown"

    def _find_last_device_index(self, track_index: int) -> int:
        """Find the index of the last device on a track by probing param names."""
        import time as _time
        last_valid = -1
        for i in range(30):
            _time.sleep(0.1)
            names = self.ableton.get_device_parameters_name_sync(track_index, i, timeout=2.0)
            if names.get("success") and names.get("names"):
                last_valid = i
            else:
                break
        return max(last_valid, 0)

    # ------------------------------------------------------------------
    # A. Deep Research Pipeline
    # ------------------------------------------------------------------

    async def research_micro_settings(
        self, artist: str, style: str = "", track_type: str = "vocal"
    ) -> Dict[str, Any]:
        """
        Research precise numeric parameter values for an artist/style.

        Pipeline:
        1. Check micro_settings_kb (exact values)
        2. Web + YouTube research via ResearchCoordinator
        3. LLM extraction of exact values from scraped content
        4. Merge and return with confidence score

        Returns:
            {
                "devices": { "device_key": { "device": str, "parameters": {...} } },
                "confidence": float,
                "sources": [str],
            }
        """
        logger.info(f"Researching micro settings: {artist} / {style} / {track_type}")

        # 1. Check knowledge base first
        kb_settings = self.micro_kb.get_settings(artist, style, track_type)
        if kb_settings:
            logger.info("Found settings in micro_settings_kb")
            return {
                "devices": kb_settings.get("devices", {}),
                "description": kb_settings.get("description", ""),
                "confidence": 0.9,
                "sources": ["micro_settings_kb"],
            }

        # 2. Web + YouTube research
        query = f"{artist} {style} {track_type} chain".strip()
        try:
            chain_spec = await self.coordinator.research_vocal_chain(
                query, use_youtube=True, use_web=True
            )
            if chain_spec and chain_spec.devices:
                # 3. Convert ChainSpec devices to micro_settings format
                devices = {}
                for i, dev in enumerate(chain_spec.devices):
                    key = f"{dev.category}_{i}"
                    devices[key] = {
                        "device": dev.plugin_name,
                        "purpose": dev.purpose,
                        "parameters": dev.parameters,
                    }

                result = {
                    "devices": devices,
                    "description": chain_spec.style_description,
                    "confidence": chain_spec.confidence,
                    "sources": chain_spec.sources,
                }

                # Cache if high confidence
                if chain_spec.confidence >= 0.7:
                    self.micro_kb.store_researched_settings(
                        artist, style, track_type,
                        {"devices": devices, "description": chain_spec.style_description},
                        chain_spec.confidence,
                        chain_spec.sources,
                    )

                return result

        except Exception as e:
            logger.warning(f"Web research failed: {e}")

        # 4. Fallback: no results
        return {
            "devices": {},
            "confidence": 0.0,
            "sources": [],
        }

    async def _research_with_llm(self, scraped_content: str, artist: str,
                                  style: str, track_type: str) -> Dict[str, Any]:
        """Use Gemini to extract exact numeric values from scraped articles."""
        prompt = f"""You are an expert mixing engineer. Extract EXACT numeric parameter values
from this content for a {track_type} chain in the style of {artist} ({style}).

Return JSON with this structure:
{{
    "devices": [
        {{
            "name": "EQ Eight",
            "category": "eq",
            "parameters": {{
                "band1_freq_hz": 100,
                "band1_gain_db": 0,
                "band1_type": "high_pass",
                "band2_freq_hz": 3500,
                "band2_gain_db": 4.5
            }}
        }}
    ],
    "confidence": 0.8
}}

Only include values explicitly mentioned or strongly implied in the content.
Content:
{scraped_content[:4000]}"""

        response = await self.gemini.generate(prompt)
        if not response.success:
            return {"devices": [], "confidence": 0.0}

        try:
            # Extract JSON from response
            text = response.content
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
        except (json.JSONDecodeError, ValueError):
            pass

        return {"devices": [], "confidence": 0.0}

    # ------------------------------------------------------------------
    # B. Parameter Application Engine
    # ------------------------------------------------------------------

    # Waves plugins with known parameter names in WAVES_MICRO_SETTINGS.
    # When settings use these DAW-native names, we can skip both the stock
    # normalization layer and the LLM-based dynamic discovery, and instead
    # call reliable_params.set_parameter_by_name() directly.
    WAVES_PLUGINS_WITH_KNOWN_PARAMS = {
        "CLA-76", "CLA-2A", "SSL E-Channel",
        "SSL G-Master Buss Compressor", "H-Reverb",
    }

    def apply_parameters(
        self, track_index: int, device_index: int,
        device_name: str, settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Apply parameter settings to a device via OSC.

        Args:
            track_index: 0-based track index
            device_index: 0-based device index on track
            device_name: Name of the Ableton device (e.g., "EQ Eight")
            settings: Dict of parameter_name → value in human-readable units

        Returns:
            {"success": bool, "applied": [...], "failed": [...]}
        """
        # Waves-aware path: settings already use DAW parameter names,
        # so we can set them by name without normalization or LLM discovery.
        if device_name in self.WAVES_PLUGINS_WITH_KNOWN_PARAMS:
            return self._apply_parameters_by_name(
                track_index, device_index, device_name, settings
            )

        applied = []
        failed = []

        param_list = self._settings_to_osc_params(device_name, settings)

        # If param_list is None, this is an unknown/3rd-party plugin —
        # delegate to async dynamic discovery (caller must handle).
        if param_list is None:
            return {
                "success": False,
                "applied": [],
                "failed": [],
                "device": device_name,
                "track": track_index,
                "device_index": device_index,
                "needs_dynamic_discovery": True,
            }

        for param_index, value, param_name in param_list:
            # Log what we're sending (value is already normalized by _settings_to_osc_params)
            print(f"  [OSC] {device_name} param[{param_index}] ({param_name}) = {value:.4f} (normalized)")
            result = self.ableton.safe_set_device_parameter(
                track_index, device_index, param_index, value
            )
            entry = {"param": param_name, "index": param_index, "value": value}
            if result.get("success"):
                applied.append(entry)
            else:
                entry["error"] = result.get("message", "unknown")
                failed.append(entry)
            # Small delay between parameters to avoid overwhelming OSC
            time.sleep(0.02)

        return {
            "success": len(failed) == 0,
            "applied": applied,
            "failed": failed,
            "device": device_name,
            "track": track_index,
            "device_index": device_index,
        }

    def _apply_parameters_by_name(
        self, track_index: int, device_index: int,
        device_name: str, settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Apply parameters using DAW-native parameter names via
        reliable_params.set_parameter_by_name().

        Used for Waves plugins whose WAVES_MICRO_SETTINGS already contain
        the exact parameter names as exposed to the DAW, so no normalization
        or LLM discovery is needed.
        """
        from ableton_controls.reliable_params import get_reliable_controller

        applied = []
        failed = []

        try:
            rpc = get_reliable_controller()
        except Exception as e:
            logger.error(f"[apply_by_name] Could not get reliable_params controller: {e}")
            return {
                "success": False,
                "applied": [],
                "failed": [],
                "device": device_name,
                "track": track_index,
                "device_index": device_index,
                "needs_dynamic_discovery": True,
            }

        for param_name, value in settings.items():
            if not isinstance(value, (int, float)):
                continue

            result = rpc.set_parameter_by_name(
                track_index, device_index, param_name, float(value)
            )
            entry = {"param": param_name, "value": value}
            if result.get("success"):
                entry["index"] = result.get("param_index")
                applied.append(entry)
            else:
                entry["error"] = result.get("message", "unknown")
                failed.append(entry)
            time.sleep(0.02)

        logger.info(
            f"[apply_by_name] {device_name}: {len(applied)} applied, "
            f"{len(failed)} failed"
        )

        return {
            "success": len(failed) == 0,
            "applied": applied,
            "failed": failed,
            "device": device_name,
            "track": track_index,
            "device_index": device_index,
        }

    def apply_parameters_batch(
        self, track_index: int, device_index: int,
        device_name: str, settings: Dict[str, Any],
        inter_param_delay: float = 0.03
    ) -> Dict[str, Any]:
        """
        Same as apply_parameters but with configurable delay between params.
        Useful for avoiding OSC message flooding.
        """
        applied = []
        failed = []

        param_list = self._settings_to_osc_params(device_name, settings)

        for param_index, value, param_name in param_list:
            result = self.ableton.safe_set_device_parameter(
                track_index, device_index, param_index, value
            )
            entry = {"param": param_name, "index": param_index, "value": value}
            if result.get("success"):
                applied.append(entry)
            else:
                entry["error"] = result.get("message", "unknown")
                failed.append(entry)
            time.sleep(inter_param_delay)

        return {
            "success": len(failed) == 0,
            "applied": applied,
            "failed": failed,
        }

    def _settings_to_osc_params(
        self, device_name: str, settings: Dict[str, Any]
    ) -> List[Tuple[int, float, str]]:
        """
        Convert human-readable settings dict into a list of
        (param_index, normalized_value, param_name) tuples.
        """
        results = []

        if device_name == "EQ Eight":
            results = self._eq_eight_settings_to_params(settings)
        elif device_name in ("Compressor", "Glue Compressor"):
            results = self._compressor_settings_to_params(device_name, settings)
        elif device_name == "Saturator":
            results = self._saturator_settings_to_params(settings)
        elif device_name == "Reverb":
            results = self._reverb_settings_to_params(settings)
        elif device_name == "Delay":
            results = self._delay_settings_to_params(settings)
        elif device_name == "Utility":
            results = self._utility_settings_to_params(settings)
        else:
            logger.info(f"No hardcoded parameter map for device: {device_name} — use dynamic VST discovery")
            return None  # Signal: caller should use _discover_and_map_vst_params

        return results

    def _eq_eight_settings_to_params(
        self, settings: Dict[str, Any]
    ) -> List[Tuple[int, float, str]]:
        """Convert EQ Eight human settings to OSC params."""
        params = []

        for band_num in range(1, 9):
            prefix = f"band{band_num}_"
            base = EQ_EIGHT_BAND_BASE.get(band_num)
            if base is None:
                # Bands 6-8 follow the same pattern
                base = 1 + (band_num - 1) * 9
                if base > 65:
                    continue

            # Band On/Off
            on_key = f"{prefix}on"
            if on_key in settings:
                val = 1.0 if settings[on_key] else 0.0
                params.append((base + EQ_EIGHT_OFFSETS["on"], val, on_key))

            # Band Type
            type_key = f"{prefix}type"
            if type_key in settings:
                type_val = settings[type_key]
                if isinstance(type_val, str):
                    type_val = EQ_TYPE_MAP.get(type_val.lower(), 3)  # Default bell
                params.append((base + EQ_EIGHT_OFFSETS["type"], float(type_val), type_key))

            # Frequency
            freq_key = f"{prefix}freq_hz"
            if freq_key in settings:
                norm = _freq_to_normalized(float(settings[freq_key]))
                params.append((base + EQ_EIGHT_OFFSETS["freq"], norm, freq_key))

            # Gain - EQ Eight takes RAW dB values (-15 to +15), NOT normalized!
            # Calibration confirmed: send 5.0 → displays 5.0 dB
            gain_key = f"{prefix}gain_db"
            if gain_key in settings:
                raw_db = max(-15.0, min(float(settings[gain_key]), 15.0))
                params.append((base + EQ_EIGHT_OFFSETS["gain"], raw_db, gain_key))

            # Q
            q_key = f"{prefix}q"
            if q_key in settings:
                norm = _q_to_normalized(float(settings[q_key]))
                params.append((base + EQ_EIGHT_OFFSETS["q"], norm, q_key))

        return params

    def _compressor_settings_to_params(
        self, device_name: str, settings: Dict[str, Any]
    ) -> List[Tuple[int, float, str]]:
        """Convert compressor human settings to OSC params."""
        params = []
        pmap = COMPRESSOR_PARAMS if device_name == "Compressor" else GLUE_COMPRESSOR_PARAMS

        if "threshold_db" in settings:
            idx = pmap.get("threshold", 3)
            params.append((idx, _threshold_to_normalized(settings["threshold_db"]), "threshold_db"))

        if "ratio" in settings:
            idx = pmap.get("ratio", 5)
            params.append((idx, _ratio_to_normalized(settings["ratio"]), "ratio"))

        if "attack_ms" in settings:
            idx = pmap.get("attack", 6)
            params.append((idx, _attack_to_normalized(settings["attack_ms"]), "attack_ms"))

        if "release_ms" in settings:
            idx = pmap.get("release", 7)
            params.append((idx, _release_to_normalized(settings["release_ms"]), "release_ms"))

        output_key = "output_gain" if device_name == "Compressor" else "makeup"
        for label in ("output_gain_db", "makeup_gain_db"):
            if label in settings:
                idx = pmap.get(output_key, 9)
                params.append((idx, _gain_to_raw(settings[label], -36.0, 36.0), label))
                break

        if "dry_wet_pct" in settings:
            idx = pmap.get("dry_wet", 10)
            params.append((idx, _percent_to_normalized(settings["dry_wet_pct"]), "dry_wet_pct"))

        if "knee_db" in settings and "knee" in pmap:
            params.append((pmap["knee"], _gain_to_raw(settings["knee_db"], 0.0, 24.0), "knee_db"))

        return params

    def _saturator_settings_to_params(
        self, settings: Dict[str, Any]
    ) -> List[Tuple[int, float, str]]:
        """Convert Saturator human settings to OSC params."""
        params = []

        if "drive_db" in settings:
            # Saturator Drive: 0 to 36 dB, LINEAR scaling
            params.append((SATURATOR_PARAMS["drive"],
                          _drive_to_normalized(settings["drive_db"]), "drive_db"))

        if "type" in settings:
            t = settings["type"]
            if isinstance(t, str):
                t = SATURATOR_TYPE_MAP.get(t.lower(), 2)
            params.append((SATURATOR_PARAMS["type"], float(t), "type"))

        if "output_db" in settings:
            # Saturator Output: -36 to 0 dB, LINEAR scaling
            params.append((SATURATOR_PARAMS["output"],
                          _db_to_normalized_linear(settings["output_db"], -36.0, 0.0), "output_db"))

        if "dry_wet_pct" in settings:
            params.append((SATURATOR_PARAMS["dry_wet"],
                          _percent_to_normalized(settings["dry_wet_pct"]), "dry_wet_pct"))

        return params

    def _reverb_settings_to_params(
        self, settings: Dict[str, Any]
    ) -> List[Tuple[int, float, str]]:
        """Convert Reverb human settings to OSC params."""
        params = []

        if "decay_time_ms" in settings:
            params.append((REVERB_PARAMS["decay_time"],
                          _decay_to_normalized(settings["decay_time_ms"]), "decay_time_ms"))

        if "predelay_ms" in settings:
            params.append((REVERB_PARAMS["predelay"],
                          _predelay_to_normalized(settings["predelay_ms"]), "predelay_ms"))

        if "room_size" in settings:
            # Already 0-1
            params.append((REVERB_PARAMS["room_size"],
                          max(0.0, min(float(settings["room_size"]), 1.0)), "room_size"))

        if "dry_wet_pct" in settings:
            params.append((REVERB_PARAMS["dry_wet"],
                          _percent_to_normalized(settings["dry_wet_pct"]), "dry_wet_pct"))

        if "high_cut_hz" in settings:
            params.append((REVERB_PARAMS["high_cut"],
                          _freq_to_normalized(settings["high_cut_hz"]), "high_cut_hz"))

        return params

    def _delay_settings_to_params(
        self, settings: Dict[str, Any]
    ) -> List[Tuple[int, float, str]]:
        """Convert Delay human settings to OSC params."""
        params = []

        if "delay_time_ms" in settings:
            # Map 1-2000ms log scale
            t = max(1.0, min(float(settings["delay_time_ms"]), 2000.0))
            norm = math.log(t) / math.log(2000.0)
            params.append((DELAY_PARAMS["delay_time"], norm, "delay_time"))

        if "feedback_pct" in settings:
            params.append((DELAY_PARAMS["feedback"],
                          _percent_to_normalized(settings["feedback_pct"]), "feedback_pct"))

        if "dry_wet_pct" in settings:
            params.append((DELAY_PARAMS["dry_wet"],
                          _percent_to_normalized(settings["dry_wet_pct"]), "dry_wet_pct"))

        if "filter_freq_hz" in settings:
            params.append((DELAY_PARAMS["filter_freq"],
                          _freq_to_normalized(settings["filter_freq_hz"]), "filter_freq_hz"))

        return params

    def _utility_settings_to_params(
        self, settings: Dict[str, Any]
    ) -> List[Tuple[int, float, str]]:
        """Convert Utility settings to OSC params."""
        params = []

        if "gain_db" in settings:
            params.append((UTILITY_PARAMS["gain"],
                          _gain_to_raw(settings["gain_db"], -35.0, 35.0), "gain_db"))

        if "width_pct" in settings:
            # Width: 0=mono, 100=stereo, 200=wide
            params.append((UTILITY_PARAMS["width"],
                          max(0.0, min(settings["width_pct"] / 200.0, 1.0)), "width_pct"))

        return params

    # ------------------------------------------------------------------
    # C. Visual Verification Loop
    # ------------------------------------------------------------------

    def capture_monitor(self, monitor_index: int = 3) -> Optional[str]:
        """
        Capture a screenshot of the specified monitor.

        Args:
            monitor_index: MSS monitor index (3 = typically Ableton display)

        Returns:
            File path to saved PNG, or None on failure.
        """
        try:
            import mss
            import mss.tools

            with mss.mss() as sct:
                monitors = sct.monitors
                if monitor_index >= len(monitors):
                    logger.warning(f"Monitor {monitor_index} not found (have {len(monitors)-1})")
                    # Fall back to last available monitor
                    monitor_index = len(monitors) - 1

                monitor = monitors[monitor_index]
                timestamp = int(time.time())
                screenshots_dir = os.path.join(os.getcwd(), "screenshots")
                os.makedirs(screenshots_dir, exist_ok=True)
                filepath = os.path.join(screenshots_dir, f"research_bot_capture_{timestamp}.png")

                sct_img = sct.grab(monitor)
                mss.tools.to_png(sct_img.rgb, sct_img.size, output=filepath)

                logger.info(f"Captured monitor {monitor_index} → {filepath}")
                return filepath

        except Exception as e:
            logger.error(f"Screenshot capture failed: {e}")
            return None

    async def analyze_screenshot(
        self, image_path: str, analysis_prompt: str
    ) -> Dict[str, Any]:
        """
        Send a screenshot to Gemini Vision for analysis.

        Args:
            image_path: Path to the PNG file
            analysis_prompt: What to look for (e.g., "What are the EQ settings?")

        Returns:
            {"success": bool, "analysis": str, "adjustments": [...]}
        """
        if not os.path.exists(image_path):
            return {"success": False, "analysis": "Image not found"}

        try:
            import google.generativeai as genai

            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                return {"success": False, "analysis": "GOOGLE_API_KEY not set"}

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")

            # Upload image
            with open(image_path, "rb") as f:
                image_data = f.read()

            import PIL.Image
            import io
            img = PIL.Image.open(io.BytesIO(image_data))

            response = await model.generate_content_async([analysis_prompt, img])

            return {
                "success": True,
                "analysis": response.text,
            }

        except Exception as e:
            logger.error(f"Screenshot analysis failed: {e}")
            return {"success": False, "analysis": str(e)}

    async def capture_and_analyze(
        self, prompt: str = "Describe the current plugin settings visible in Ableton Live.",
        monitor_index: int = 3
    ) -> Dict[str, Any]:
        """Capture monitor screenshot and analyze with Gemini Vision."""
        filepath = self.capture_monitor(monitor_index)
        if not filepath:
            return {"success": False, "analysis": "Capture failed"}

        result = await self.analyze_screenshot(filepath, prompt)

        # Clean up screenshot
        try:
            os.remove(filepath)
        except OSError:
            pass

        return result

    async def iterate_until_correct(
        self,
        track_index: int,
        device_index: int,
        device_name: str,
        target_settings: Dict[str, Any],
        max_iterations: int = 5,
        monitor_index: int = 3,
    ) -> Dict[str, Any]:
        """
        Autonomous visual iteration loop:
        1. Apply parameters via OSC
        2. Wait for UI update
        3. Capture screenshot
        4. Ask Gemini Vision to compare to target
        5. Parse corrections
        6. Apply corrections
        7. Repeat until match or max iterations

        Returns:
            {"success": bool, "iterations": int, "final_analysis": str}
        """
        iteration_log = []

        for i in range(max_iterations):
            logger.info(f"Visual iteration {i+1}/{max_iterations} for {device_name}")

            # 1. Apply current settings
            if i == 0:
                apply_result = self.apply_parameters(
                    track_index, device_index, device_name, target_settings
                )
                if not apply_result["success"]:
                    logger.warning(f"Parameter apply had failures: {apply_result['failed']}")

            # 2. Wait for UI update
            await asyncio.sleep(0.5)

            # 3. Capture + analyze
            target_desc = json.dumps(target_settings, indent=2)
            prompt = f"""Look at this Ableton Live screenshot. Focus on the {device_name} plugin.

Target settings:
{target_desc}

1. Describe what you see in the plugin UI (current values).
2. Compare to the target settings above.
3. If they match (within reasonable tolerance), say "MATCH_CONFIRMED".
4. If they don't match, list the specific adjustments needed as JSON:
   {{"adjustments": [{{"param": "param_name", "current": value, "target": value, "direction": "increase/decrease"}}]}}
"""
            analysis = await self.capture_and_analyze(prompt, monitor_index)

            iteration_log.append({
                "iteration": i + 1,
                "analysis": analysis.get("analysis", ""),
                "success": analysis.get("success", False),
            })

            if not analysis.get("success"):
                logger.warning(f"Analysis failed on iteration {i+1}")
                continue

            response_text = analysis["analysis"]

            # 4. Check for match
            if "MATCH_CONFIRMED" in response_text.upper():
                logger.info(f"Settings confirmed after {i+1} iterations")
                return {
                    "success": True,
                    "iterations": i + 1,
                    "final_analysis": response_text,
                    "log": iteration_log,
                }

            # 5. Parse and apply corrections
            corrections = self._parse_corrections(response_text, device_name, target_settings)
            if corrections:
                logger.info(f"Applying {len(corrections)} corrections")
                corr_result = self.apply_parameters(
                    track_index, device_index, device_name, corrections
                )
                # Update target_settings with corrections for next iteration reference
            else:
                logger.info("No parseable corrections found, retrying")

        return {
            "success": False,
            "iterations": max_iterations,
            "final_analysis": "Max iterations reached",
            "log": iteration_log,
        }

    def _parse_corrections(
        self, analysis_text: str, device_name: str, target_settings: Dict
    ) -> Dict[str, Any]:
        """Parse Gemini's correction suggestions into parameter updates."""
        # Try to extract JSON from the analysis
        try:
            start = analysis_text.find('{"adjustments"')
            if start < 0:
                start = analysis_text.find('"adjustments"')
                if start >= 0:
                    start = analysis_text.rfind("{", 0, start)
            if start < 0:
                return {}

            end = analysis_text.find("}", start)
            # Find matching closing brace (handle nested)
            depth = 0
            for j in range(start, len(analysis_text)):
                if analysis_text[j] == "{":
                    depth += 1
                elif analysis_text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        end = j + 1
                        break

            data = json.loads(analysis_text[start:end])
            adjustments = data.get("adjustments", [])

            corrections = {}
            for adj in adjustments:
                param = adj.get("param", "")
                target = adj.get("target")
                if param and target is not None:
                    corrections[param] = target

            return corrections

        except (json.JSONDecodeError, ValueError):
            return {}

    # ------------------------------------------------------------------
    # D. Dynamic VST Parameter Discovery
    # ------------------------------------------------------------------

    VST_PARAM_CACHE_PATH = os.path.join(
        os.path.dirname(__file__), "config", "vst_param_cache.json"
    )

    def _load_vst_param_cache(self) -> Dict[str, Any]:
        """Load cached VST parameter mappings from disk."""
        if os.path.exists(self.VST_PARAM_CACHE_PATH):
            try:
                with open(self.VST_PARAM_CACHE_PATH, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def _save_vst_param_cache(self, cache: Dict[str, Any]):
        """Persist VST parameter cache to disk."""
        os.makedirs(os.path.dirname(self.VST_PARAM_CACHE_PATH), exist_ok=True)
        with open(self.VST_PARAM_CACHE_PATH, "w") as f:
            json.dump(cache, f, indent=2)

    def _get_calibrated_normalized_value(
        self,
        plugin_name: str,
        param_name: str,
        desired_value: Any,
        param_index: Optional[int] = None,
    ) -> Optional[float]:
        """
        If calibration data exists for plugin/parameter, convert desired value
        to normalized 0..1 using the learned curve.
        """
        curve = self.calibration_store.get_curve(
            plugin_name=plugin_name,
            param_name=param_name,
            param_index=param_index,
        )
        if not curve:
            return None

        target_base_value = coerce_target_to_base_value(
            desired_value, expected_unit=curve.get("unit")
        )
        if target_base_value is None:
            logger.info(
                f"[calibration] Could not parse value '{desired_value}' for "
                f"{plugin_name}:{param_name}"
            )
            return None

        normalized = value_to_normalized_from_curve(target_base_value, curve)
        if normalized is None:
            logger.info(
                f"[calibration] Curve conversion failed for {plugin_name}:{param_name} "
                f"value={desired_value}"
            )
            return None

        normalized = max(0.0, min(float(normalized), 1.0))
        logger.info(
            f"[calibration] {plugin_name}:{param_name} {desired_value} -> {normalized:.4f} "
            f"({curve.get('curve_model', 'LINEAR')})"
        )
        return normalized

    async def _discover_and_map_vst_params(
        self,
        track_index: int,
        device_index: int,
        plugin_name: str,
        desired_settings: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Use LLM to map human-readable desired settings to actual VST parameter
        names and normalized values.

        1. Query all param names + min/max via reliable_params
        2. Check cache for existing mapping
        3. If not cached, ask Gemini to produce a JSON mapping
        4. Cache the result
        5. Apply via set_parameter_by_name

        Returns:
            {"success": bool, "applied": [...], "failed": [...], "mapping": {...}}
        """
        from ableton_controls.reliable_params import get_reliable_controller

        rpc = get_reliable_controller()

        # 1. Query param info
        info = rpc.get_device_info(track_index, device_index, use_cache=False)
        if not info or not info.param_names:
            return {"success": False, "applied": [], "failed": [],
                    "message": "Could not read device parameters"}

        param_names = info.param_names
        param_mins = info.param_mins
        param_maxs = info.param_maxs
        param_count = len(param_names)

        # 2. Check cache
        cache_key = f"{plugin_name}|{param_count}"
        cache = self._load_vst_param_cache()
        cached_entry = cache.get(cache_key)

        if cached_entry and cached_entry.get("param_map"):
            param_map = cached_entry["param_map"]
            logger.info(f"[vst_discover] Using cached mapping for {cache_key}")
        else:
            # 3. Ask Gemini
            param_info_list = []
            for i, name in enumerate(param_names):
                low = param_mins[i] if i < len(param_mins) else 0.0
                high = param_maxs[i] if i < len(param_maxs) else 1.0
                param_info_list.append({"index": i, "name": name, "min": low, "max": high})

            prompt = (
                f"You are a VST plugin parameter expert. The plugin is '{plugin_name}'.\n"
                f"Here are all its parameters:\n{json.dumps(param_info_list, indent=2)}\n\n"
                f"The user wants these settings applied:\n{json.dumps(desired_settings, indent=2)}\n\n"
                "For each desired setting, find the matching VST parameter and compute the "
                "correct normalized value (0.0-1.0) based on the parameter's min/max range.\n\n"
                "Return ONLY valid JSON in this exact format:\n"
                '{"mappings": [{"desired_key": "<key>", "param_name": "<vst_param_name>", '
                '"param_index": <int>, "normalized_value": <float>, "reasoning": "<short>"}]}'
            )

            try:
                import google.generativeai as genai
                api_key = os.getenv("GOOGLE_API_KEY")
                if not api_key:
                    return {"success": False, "applied": [], "failed": [],
                            "message": "GOOGLE_API_KEY not set"}
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel("gemini-2.0-flash")
                response = await model.generate_content_async(prompt)
                response_text = response.text

                # Extract JSON from response
                start = response_text.find("{")
                end = response_text.rfind("}") + 1
                if start < 0 or end <= start:
                    return {"success": False, "applied": [], "failed": [],
                            "message": f"LLM returned no JSON: {response_text[:200]}"}

                mapping_data = json.loads(response_text[start:end])
                mappings = mapping_data.get("mappings", [])

                param_map = {}
                for m in mappings:
                    param_map[m["desired_key"]] = {
                        "param_name": m["param_name"],
                        "param_index": m["param_index"],
                        "normalized_value": m["normalized_value"],
                    }

                # 4. Cache
                cache[cache_key] = {
                    "param_map": param_map,
                    "plugin_name": plugin_name,
                    "param_count": param_count,
                    "discovered_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                self._save_vst_param_cache(cache)
                logger.info(f"[vst_discover] Cached mapping for {cache_key}: {len(param_map)} params")

            except Exception as e:
                logger.error(f"[vst_discover] LLM mapping failed: {e}")
                return {"success": False, "applied": [], "failed": [],
                        "message": f"LLM mapping failed: {e}"}

        # 5. Apply via set_parameter_by_name
        applied = []
        failed = []
        for desired_key, value in desired_settings.items():
            mapping = param_map.get(desired_key)
            if not mapping:
                failed.append({"param": desired_key, "error": "No mapping found"})
                continue

            try:
                normalized_to_send = mapping.get("normalized_value")
                source = "llm_mapping"

                calibrated = self._get_calibrated_normalized_value(
                    plugin_name=plugin_name,
                    param_name=mapping.get("param_name", desired_key),
                    desired_value=value,
                    param_index=mapping.get("param_index"),
                )
                if calibrated is not None:
                    normalized_to_send = calibrated
                    source = "calibration"

                try:
                    normalized_to_send = float(normalized_to_send)
                except (TypeError, ValueError):
                    failed.append(
                        {
                            "param": desired_key,
                            "error": f"Invalid normalized value: {normalized_to_send}",
                        }
                    )
                    continue

                result = rpc.set_parameter_by_name(
                    track_index, device_index,
                    mapping["param_name"], normalized_to_send
                )
                if result.get("success"):
                    applied.append(
                        {
                            "param": desired_key,
                            "mapped_to": mapping["param_name"],
                            "value": normalized_to_send,
                            "source": source,
                        }
                    )
                else:
                    failed.append({"param": desired_key, "error": result.get("message", "unknown")})
            except Exception as e:
                failed.append({"param": desired_key, "error": str(e)})

            time.sleep(0.03)

        return {
            "success": len(failed) == 0,
            "applied": applied,
            "failed": failed,
            "mapping": param_map,
        }

    # ------------------------------------------------------------------
    # E. License / Health Detection
    # ------------------------------------------------------------------

    HEALTH_SUSPECT_KEYWORDS = [
        "demo", "trial", "unregistered", "activate", "license",
        "register", "expired", "buy", "purchase",
    ]

    def _check_plugin_health(
        self, track_index: int, device_index: int, expected_name: str
    ) -> Dict[str, Any]:
        """
        Check whether a loaded plugin is healthy (licensed, functional).

        Checks:
        1. Device readiness (wait_for_device_ready)
        2. Parameter count (< 3 = likely stub)
        3. Device name for demo/trial keywords
        4. Parameter names for registration-related params

        Returns:
            {"healthy": bool, "reason": str, "details": {...}}
        """
        from ableton_controls.reliable_params import get_reliable_controller

        rpc = get_reliable_controller()

        # 1. Wait for ready
        try:
            ready = rpc.wait_for_device_ready(track_index, device_index, timeout=8.0)
            if not ready:
                return {"healthy": False, "reason": "Device not ready (timeout)",
                        "details": {"check": "readiness"}}
        except Exception as e:
            return {"healthy": False, "reason": f"Readiness check failed: {e}",
                    "details": {"check": "readiness"}}

        # 2. Parameter count
        info = rpc.get_device_info(track_index, device_index, use_cache=False)
        if not info or not info.param_names:
            return {"healthy": False, "reason": "No parameters found",
                    "details": {"check": "param_count", "count": 0}}

        param_count = len(info.param_names)
        if param_count < 3:
            return {"healthy": False,
                    "reason": f"Only {param_count} params (likely unlicensed stub)",
                    "details": {"check": "param_count", "count": param_count}}

        # 3. Device name check
        name_result = self.ableton.get_device_name_sync(track_index, device_index)
        device_name = name_result.get("name", "") if name_result.get("success") else ""
        name_lower = device_name.lower()
        for kw in self.HEALTH_SUSPECT_KEYWORDS:
            if kw in name_lower:
                return {"healthy": False,
                        "reason": f"Device name contains '{kw}': {device_name}",
                        "details": {"check": "name_keyword", "name": device_name}}

        # 4. Parameter name scan
        param_names_lower = [p.lower() for p in info.param_names]
        suspect_params = [p for p in param_names_lower
                          if any(kw in p for kw in self.HEALTH_SUSPECT_KEYWORDS)]
        if len(suspect_params) >= 2:
            return {"healthy": False,
                    "reason": f"Multiple suspect params: {suspect_params}",
                    "details": {"check": "param_keywords", "suspects": suspect_params}}

        return {"healthy": True, "reason": "All checks passed",
                "details": {"param_count": param_count, "device_name": device_name}}

    async def _load_with_fallback(
        self,
        track_index: int,
        plugin_name: str,
        category: str,
        fallbacks: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Load a plugin with health check and automatic fallback.

        1. Load desired plugin
        2. Run health check
        3. If unhealthy → delete → try next fallback
        4. If all fail → use stock Ableton device for category

        Args:
            track_index: 0-based track index
            plugin_name: Desired plugin name
            category: Plugin category (eq, compressor, reverb, etc.)
            fallbacks: Ordered list of fallback plugin names

        Returns:
            {"success": bool, "loaded_plugin": str, "is_fallback": bool, "device_index": int}
        """
        # Build fallback chain
        if fallbacks is None:
            fallbacks = []

        # Load category → stock fallback mapping
        stock_fallbacks = {
            "eq": "EQ Eight",
            "compressor": "Compressor",
            "reverb": "Reverb",
            "delay": "Delay",
            "saturator": "Saturator",
            "limiter": "Limiter",
            "multiband": "Multiband Dynamics",
        }

        candidates = [plugin_name] + fallbacks
        stock = stock_fallbacks.get(category.lower())
        if stock and stock not in candidates:
            candidates.append(stock)

        for i, candidate in enumerate(candidates):
            is_fallback = (i > 0)
            logger.info(f"[fallback] Trying: {candidate} (fallback={is_fallback})")

            load_result = self.ableton.load_device(track_index, candidate)
            if not load_result.get("success"):
                logger.warning(f"[fallback] Failed to load {candidate}: {load_result.get('message')}")
                continue

            await asyncio.sleep(1.0)
            device_idx = self._find_last_device_index(track_index)

            # Health check (skip for known stock devices)
            is_stock = candidate in DEVICE_PARAM_MAPS
            if not is_stock:
                health = self._check_plugin_health(track_index, device_idx, candidate)
                if not health["healthy"]:
                    logger.warning(f"[fallback] {candidate} unhealthy: {health['reason']}")
                    # Delete the broken device
                    self.ableton.client.send_message(
                        "/live/device/delete", [track_index, device_idx]
                    )
                    await asyncio.sleep(0.5)
                    continue

            return {
                "success": True,
                "loaded_plugin": candidate,
                "is_fallback": is_fallback,
                "device_index": device_idx,
                "is_stock": is_stock,
            }

        return {
            "success": False,
            "loaded_plugin": None,
            "is_fallback": True,
            "device_index": -1,
            "message": f"All candidates failed: {candidates}",
        }

    # ------------------------------------------------------------------
    # F. Plugin GUI Display + Screenshot
    # ------------------------------------------------------------------

    def show_plugin_gui(self, track_index: int, device_index: int) -> Dict[str, Any]:
        """
        Select a device in Detail View and attempt to open its floating plugin window.

        1. Send /jarvis/device/select to show in Detail View
        2. Use pyautogui to click the wrench/spanner icon to open the floating VST window

        Returns:
            {"success": bool, "message": str}
        """
        # Step 1: Select device in Detail View
        select_result = self.ableton.select_device(track_index, device_index)
        if not select_result.get("success"):
            return {"success": False, "message": f"Could not select device: {select_result.get('message')}"}

        time.sleep(0.5)

        # Step 2: Try to open the floating VST window via the wrench icon
        try:
            import pyautogui
            pyautogui.FAILSAFE = True

            # Capture current screen to find the wrench icon via Gemini Vision
            screenshot_path = self.capture_monitor(monitor_index=0)
            if not screenshot_path:
                return {"success": True,
                        "message": "Device selected in Detail View, but couldn't capture screen for wrench icon"}

            # Use Gemini to locate the wrench/plugin edit button
            import google.generativeai as genai
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                return {"success": True,
                        "message": "Device selected in Detail View (no API key for wrench detection)"}

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")

            import PIL.Image
            img = PIL.Image.open(screenshot_path)
            width, height = img.size

            prompt = (
                "Look at this Ableton Live screenshot. Find the wrench/spanner icon "
                "in the Detail View (bottom panel) that opens the floating plugin window. "
                "Return ONLY JSON: {\"x\": <pixel_x>, \"y\": <pixel_y>, \"found\": true/false}"
            )

            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, run synchronously via thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    response = pool.submit(
                        lambda: model.generate_content([prompt, img])
                    ).result(timeout=15)
            else:
                response = model.generate_content([prompt, img])

            text = response.text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                coords = json.loads(text[start:end])
                if coords.get("found"):
                    x, y = coords["x"], coords["y"]
                    pyautogui.click(x, y)
                    time.sleep(0.5)

                    # Clean up
                    try:
                        os.remove(screenshot_path)
                    except OSError:
                        pass

                    return {"success": True,
                            "message": f"Opened plugin window (clicked wrench at {x},{y})"}

            # Clean up
            try:
                os.remove(screenshot_path)
            except OSError:
                pass

            return {"success": True,
                    "message": "Device selected in Detail View, wrench icon not found"}

        except ImportError:
            return {"success": True,
                    "message": "Device selected in Detail View (pyautogui not available for GUI automation)"}
        except Exception as e:
            logger.error(f"[show_gui] Error opening plugin window: {e}")
            return {"success": True,
                    "message": f"Device selected in Detail View, couldn't open floating window: {e}"}

    async def capture_plugin_screenshot(
        self, track_index: int, device_index: int, monitor_index: int = 0
    ) -> Optional[str]:
        """
        Select a plugin, open its GUI, and capture a screenshot.

        Returns:
            Path to the screenshot PNG, or None on failure.
        """
        gui_result = self.show_plugin_gui(track_index, device_index)
        if not gui_result.get("success"):
            logger.warning(f"[capture_plugin] GUI show failed: {gui_result.get('message')}")
            return None

        # Wait for the floating window to render
        time.sleep(1.0)

        return self.capture_monitor(monitor_index)

    # ------------------------------------------------------------------
    # G. Full Autonomous Pipeline
    # ------------------------------------------------------------------

    async def auto_chain(
        self,
        artist: str,
        style: str,
        track_type: str,
        track_index: int,
        visual_verify: bool = True,
        max_visual_iterations: int = 3,
        monitor_index: int = 3,
    ) -> Dict[str, Any]:
        """
        Full autonomous pipeline:
        1. Research micro settings
        2. Check available plugins
        3. Build + load chain
        4. Apply parameters to each device
        5. Visual verify + iterate each device
        6. Return summary

        Args:
            artist: Artist name (e.g., "kanye")
            style: Style/era (e.g., "donda")
            track_type: Track type (e.g., "vocal")
            track_index: 0-based Ableton track index
            visual_verify: Whether to run visual verification loop
            max_visual_iterations: Max iterations per device
            monitor_index: Monitor to capture for visual verification

        Returns:
            Summary dict with results for each step.
        """
        report = {
            "artist": artist,
            "style": style,
            "track_type": track_type,
            "track_index": track_index,
            "steps": {},
        }

        # Step 1: Research
        logger.info(f"[auto_chain] Step 1: Researching {artist}/{style}/{track_type}")
        research = await self.research_micro_settings(artist, style, track_type)
        report["steps"]["research"] = {
            "confidence": research["confidence"],
            "sources": research["sources"],
            "device_count": len(research.get("devices", {})),
        }

        if not research.get("devices"):
            report["success"] = False
            report["message"] = "No settings found for this artist/style"
            return report

        devices_config = research["devices"]

        # Merge 3rd party plugin preferences into device configs
        plugin_prefs = self.micro_kb.get_plugin_preferences(artist, style, track_type)
        for slot_key, prefs in plugin_prefs.items():
            if slot_key in devices_config:
                # Add preference metadata without overwriting existing params
                devices_config[slot_key].setdefault("preferred_plugin", prefs.get("preferred_plugin"))
                devices_config[slot_key].setdefault("category", prefs.get("category", slot_key))
                devices_config[slot_key].setdefault("fallbacks", prefs.get("fallbacks", []))

        # Fetch Waves-specific micro settings (used when a Waves plugin loads)
        waves_settings = self.micro_kb.get_waves_settings(artist, style, track_type)
        waves_devices = waves_settings.get("devices", {}) if waves_settings else {}

        # Step 2: Check available plugins
        logger.info("[auto_chain] Step 2: Checking available plugins")
        available = self.ableton.get_available_plugins()
        report["steps"]["plugin_check"] = {"available": bool(available)}

        # Step 3: Load devices on track AND apply parameters immediately
        # We apply params right after each device loads, using the device count
        # to determine the correct index. This avoids OSC response interleaving
        # issues that make post-hoc device index queries unreliable.
        logger.info("[auto_chain] Step 3+4: Loading devices and applying parameters")
        loaded_devices = []
        apply_results = []

        for key, dev_config in devices_config.items():
            device_name = dev_config.get("device", "")
            if not device_name:
                continue

            # Determine category and fallbacks from config
            category = dev_config.get("category", key)  # e.g. "eq", "compressor"
            fallbacks = dev_config.get("fallbacks", [])
            preferred = dev_config.get("preferred_plugin")

            target_plugin = preferred if preferred else device_name

            # Use _load_with_fallback for health-checked loading
            load_result = await self._load_with_fallback(
                track_index, target_plugin, category, fallbacks
            )

            if load_result.get("success"):
                actual_plugin = load_result["loaded_plugin"]
                device_idx = load_result["device_index"]
                is_stock = load_result.get("is_stock", actual_plugin in DEVICE_PARAM_MAPS)

                loaded_devices.append({
                    "key": key,
                    "device": actual_plugin,
                    "config": dev_config,
                    "device_index": device_idx,
                    "is_fallback": load_result.get("is_fallback", False),
                    "is_stock": is_stock,
                })
                logger.info(
                    f"  Loaded: {actual_plugin} at index {device_idx}"
                    f"{' (fallback)' if load_result.get('is_fallback') else ''}"
                )

                # Apply parameters immediately
                # If the loaded plugin is a Waves device, use Waves-specific
                # parameters from WAVES_MICRO_SETTINGS instead of stock settings.
                settings = dev_config.get("parameters", {})
                if not is_stock and waves_devices:
                    for ws_key, ws_dev in waves_devices.items():
                        if ws_dev.get("device") == actual_plugin:
                            waves_params = ws_dev.get("parameters", {})
                            if waves_params:
                                logger.info(
                                    f"    Using WAVES_MICRO_SETTINGS for {actual_plugin} "
                                    f"(slot: {ws_key}, {len(waves_params)} params)"
                                )
                                settings = waves_params
                            break
                if settings and device_idx is not None:
                    result = self.apply_parameters(
                        track_index, device_idx, actual_plugin, settings
                    )

                    # If apply_parameters signals dynamic discovery needed (3rd party)
                    if result.get("needs_dynamic_discovery") and not is_stock:
                        logger.info(f"    Using dynamic VST param discovery for {actual_plugin}")
                        result = await self._discover_and_map_vst_params(
                            track_index, device_idx, actual_plugin, settings
                        )

                    apply_results.append({
                        "device": actual_plugin,
                        "device_index": device_idx,
                        "applied": len(result.get("applied", [])),
                        "failed": len(result.get("failed", [])),
                    })
                    logger.info(
                        f"    Applied {len(result.get('applied', []))} params "
                        f"({len(result.get('failed', []))} failed)"
                    )
            else:
                logger.warning(
                    f"  Failed to load: {device_name} - {load_result.get('message')}"
                )

            await asyncio.sleep(0.5)

        report["steps"]["load"] = {
            "loaded": len(loaded_devices),
            "total": len(devices_config),
        }

        if not loaded_devices:
            report["success"] = False
            report["message"] = "Failed to load any devices"
            return report

        report["steps"]["apply"] = apply_results

        # Step 5: Visual verification (optional)
        if visual_verify:
            logger.info("[auto_chain] Step 5: Visual verification")
            verify_results = []
            # Re-use the device indices from the apply step
            apply_idx_map = {r["device"]: r["device_index"] for r in apply_results}
            for loaded in loaded_devices:
                device_name = loaded["device"]
                settings = loaded["config"].get("parameters", {})
                if not settings or device_name not in apply_idx_map:
                    continue

                device_idx = apply_idx_map[device_name]

                vresult = await self.iterate_until_correct(
                    track_index, device_idx, device_name, settings,
                    max_iterations=max_visual_iterations,
                    monitor_index=monitor_index,
                )
                verify_results.append({
                    "device": device_name,
                    "verified": vresult["success"],
                    "iterations": vresult["iterations"],
                })

            report["steps"]["visual_verify"] = verify_results

        report["success"] = True
        report["message"] = (
            f"Chain applied: {len(loaded_devices)} devices loaded with "
            f"{sum(r['applied'] for r in apply_results)} parameters set"
        )

        logger.info(f"[auto_chain] Complete: {report['message']}")
        return report


# ============================================================================
# Module-level convenience
# ============================================================================
_bot_instance: Optional[ResearchBot] = None


def get_research_bot() -> ResearchBot:
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = ResearchBot()
    return _bot_instance
