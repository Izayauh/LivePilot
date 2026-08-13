"""
Reliable Parameter Controller for Ableton Live

Provides robust parameter control with:
- Device readiness detection (no more timing guesses)
- Parameter discovery by name (no more hardcoded indices)
- Verified parameter setting with retry logic
- Parameter caching for performance
- Graceful handling of third-party VSTs

Usage:
    from ableton_controls import ableton
    from ableton_controls.reliable_params import ReliableParameterController
    
    reliable = ReliableParameterController(ableton)
    
    # Wait for device to be ready after loading
    if reliable.wait_for_device_ready(track_index=0, device_index=0):
        # Find parameter by name
        param_idx = reliable.find_parameter_index(0, 0, "Band 1 Frequency")
        if param_idx is not None:
            # Set and verify
            result = reliable.set_parameter_verified(0, 0, param_idx, 100.0)
            print(f"Success: {result['success']}, Value: {result['actual_value']}")
"""

import time
import threading
import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field


# ============================================================================
# PARAMETER-SPECIFIC NORMALIZATION FUNCTIONS
# ============================================================================
# Based on "Technical Analysis of Parameter Normalization and Scaling
# Transformations in the Ableton Live Object Model"
# (docs/Ableton LOM Parameter Scaling Formulas.pdf)
#
# Three primary models:
#   1. LINEAR:      V_norm = (Value - Min) / (Max - Min)
#   2. LOGARITHMIC: V_norm = ln(Value/Min) / ln(Max/Min)
#   3. EXPONENTIAL: V_norm = ((Value - Min) / (Max - Min))^(1/alpha)


def _freq_to_normalized(freq_hz: float, min_hz: float = 10.0, max_hz: float = 22000.0) -> float:
    """Convert Hz to normalized frequency using LOGARITHMIC scaling.

    From PDF Section 3.2:
        V_norm = ln(Value/Min) / ln(Max/Min)

    EQ Eight range: 10 Hz to 22,000 Hz
    Example: 200 Hz → 0.389
    """
    freq_hz = max(min_hz, min(freq_hz, max_hz))
    return math.log(freq_hz / min_hz) / math.log(max_hz / min_hz)


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


def _glue_ratio_to_enum(ratio: float) -> float:
    """Map Glue Compressor ratio choices to the local Ableton enum index."""
    choices = [(2.0, 0.0), (4.0, 1.0), (10.0, 2.0)]
    return min(choices, key=lambda item: abs(item[0] - ratio))[1]


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


def _glue_attack_to_enum(attack_ms: float) -> float:
    """Map Glue Compressor attack choices to the local Ableton enum index."""
    choices = [0.01, 0.1, 0.3, 1.0, 3.0, 10.0, 30.0]
    return float(min(range(len(choices)), key=lambda index: abs(choices[index] - attack_ms)))


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


def _glue_release_to_enum(release_ms: float) -> float:
    """Map Glue Compressor release choices to the local Ableton enum index."""
    choices = [100.0, 300.0, 600.0, 1200.0, 2400.0, 4800.0, 10000.0]
    return float(min(range(len(choices)), key=lambda index: abs(choices[index] - release_ms)))


def _q_to_normalized(q: float) -> float:
    """Convert Q value to Ableton EQ Eight normalized (approx log scale 0.1-18)."""
    q = max(0.1, min(q, 18.0))
    return math.log(q / 0.1) / math.log(18.0 / 0.1)


def _decay_to_normalized(decay_ms: float) -> float:
    """Convert reverb decay time to Ableton Reverb normalized (0.0-1.0).

    Ableton Reverb decay: roughly 200ms to 60000ms (logarithmic scale).
    """
    decay_ms = max(200.0, min(decay_ms, 60000.0))
    return math.log(decay_ms / 200.0) / math.log(60000.0 / 200.0)


def _predelay_to_normalized(predelay_ms: float) -> float:
    """Convert reverb predelay to normalized (0-250ms range, linear)."""
    return max(0.0, min(predelay_ms / 250.0, 1.0))


def _delay_time_to_normalized(delay_ms: float) -> float:
    """Convert delay time to Ableton Delay normalized (1-2000ms log scale)."""
    delay_ms = max(1.0, min(delay_ms, 2000.0))
    return math.log(delay_ms) / math.log(2000.0)


def _drive_to_normalized(drive_db: float) -> float:
    """Convert Saturator drive (0-36dB) to normalized (0.0-1.0)."""
    return max(0.0, min(drive_db, 36.0)) / 36.0


def _percent_to_normalized(pct: float) -> float:
    """Convert 0-100% to 0.0-1.0."""
    return max(0.0, min(pct / 100.0, 1.0))


def _gain_db_to_normalized(gain_db: float, min_db: float = -15.0, max_db: float = 15.0) -> float:
    """Convert gain in dB to normalized 0.0-1.0 (linear mapping within range)."""
    gain_db = max(min_db, min(gain_db, max_db))
    return (gain_db - min_db) / (max_db - min_db)


def smart_normalize_parameter(param_name: str, value: float, device_name: str = "",
                               min_val: float = 0.0, max_val: float = 1.0) -> Tuple[float, str]:
    """
    Intelligently normalize a parameter value based on its name and device context.

    Args:
        param_name: Parameter name (e.g., "Threshold", "1 Frequency A", "ratio")
        value: Human-readable value to convert
        device_name: Device name for context (e.g., "Compressor", "EQ Eight")
        min_val: Parameter's reported min value (used for fallback linear)
        max_val: Parameter's reported max value (used for fallback linear)

    Returns:
        Tuple of (normalized_value, conversion_method_used)
    """
    name_lower = param_name.lower()
    device_lower = device_name.lower() if device_name else ""

    # === GLUE COMPRESSOR DISCRETE CONTROLS ===
    # Glue exposes Ratio/Attack/Release as local enum-style values, not the
    # regular Compressor's continuous normalized curves.
    if 'glue compressor' in device_lower:
        if 'threshold' in name_lower and value <= 0 and max_val > min_val:
            if min_val < 0.0 and max_val <= 0.0:
                return (max(min_val, min(value, max_val)), "glue_threshold_raw_db")
            normalized = (value - min_val) / (max_val - min_val)
            return (max(0.0, min(1.0, normalized)), "glue_threshold_linear")
        if 'ratio' in name_lower and value >= 1.0:
            return (_glue_ratio_to_enum(value), "glue_ratio_enum")
        if 'attack' in name_lower and value > 0:
            return (_glue_attack_to_enum(value), "glue_attack_enum")
        if 'release' in name_lower and value > 0:
            return (_glue_release_to_enum(value), "glue_release_enum")

    # === EQ FILTER TYPE ENUMS (raw integer values, not normalized) ===
    # EQ Eight filter type params are discrete enums (0..7). Sending normalized
    # fractions (e.g., 0.285) causes failed writes/snap-back. For these params,
    # send raw enum values so verification can denormalize correctly.
    if 'filter type' in name_lower and ('eq eight' in device_lower or 'eq' in device_lower):
        enum_val = int(round(value))
        enum_val = int(max(min_val, min(enum_val, max_val)))
        return (float(enum_val), "enum_raw")

    # === FREQUENCY parameters (logarithmic) ===
    if any(kw in name_lower for kw in ['frequency', 'freq', ' hz', 'filter', 'cut']):
        # EQ bands, filter frequencies
        if value > 1.0:  # Only convert if it looks like Hz (not already normalized)
            return (_freq_to_normalized(value), "freq_log")

    # === COMPRESSOR THRESHOLD (piecewise lookup) ===
    if 'threshold' in name_lower and 'compressor' in device_lower:
        if value <= 0:  # Threshold is typically negative dB
            return (_threshold_to_normalized(value), "threshold_lut")

    # === COMPRESSOR RATIO (piecewise lookup) ===
    if 'ratio' in name_lower and value >= 1.0:
        return (_ratio_to_normalized(value), "ratio_lut")

    # === ATTACK TIME (logarithmic) ===
    if 'attack' in name_lower:
        if value > 0 and value <= 1000:  # Looks like milliseconds
            return (_attack_to_normalized(value), "attack_log")

    # === RELEASE TIME (logarithmic) ===
    if 'release' in name_lower:
        if value > 0 and value <= 10000:  # Looks like milliseconds
            return (_release_to_normalized(value), "release_log")

    # === Q / RESONANCE (logarithmic) ===
    if any(kw in name_lower for kw in ['resonance', ' q', '_q']):
        if 0.1 <= value <= 18.0:
            return (_q_to_normalized(value), "q_log")

    # === DECAY TIME (logarithmic) ===
    if 'decay' in name_lower and 'reverb' in device_lower:
        if value > 100:  # Looks like milliseconds
            return (_decay_to_normalized(value), "decay_log")
        elif 0.1 < value <= 100:  # Looks like seconds, convert to ms
            return (_decay_to_normalized(value * 1000), "decay_log")

    # === PREDELAY (linear 0-250ms) ===
    if 'predelay' in name_lower:
        if value > 1:  # Looks like milliseconds
            return (_predelay_to_normalized(value), "predelay_linear")

    # === DELAY TIME (logarithmic) ===
    if 'time' in name_lower and 'delay' in device_lower:
        if value > 1:  # Looks like milliseconds
            return (_delay_time_to_normalized(value), "delay_log")

    # === DRIVE (linear 0-36dB) ===
    if 'drive' in name_lower and 'saturator' in device_lower:
        if value > 1:  # Looks like dB
            return (_drive_to_normalized(value), "drive_linear")
    
    # === SATURATOR BASE (bipolar dB-style: -36 to +36) ===
    if 'base' in name_lower and 'saturator' in device_lower:
        # Base is a bipolar gain-like parameter affecting low frequencies
        if -36 <= value <= 36:
            return ((value + 36) / 72.0, "base_linear")

    # === DRY/WET, MIX (percentage) ===
    if any(kw in name_lower for kw in ['dry/wet', 'dry_wet', 'mix', 'wet']):
        if value > 1:  # Looks like percentage
            return (_percent_to_normalized(value), "percent")


    # === GAIN parameters (dB) ===
    if any(kw in name_lower for kw in ['gain', 'output']):
        # EQ Eight gain handling can vary by exposed OSC range depending on device state.
        # Prefer raw dB only when reported range looks like true dB (about -15..+15).
        if 'eq eight' in device_lower or 'eq' in device_lower:
            if -20.0 <= min_val <= -10.0 and 10.0 <= max_val <= 20.0:
                clamped = max(min_val, min(value, max_val))
                return (clamped, "eq_gain_raw")
            # Fallback: if range is broader/odd (e.g. -100..100), treat incoming value
            # as dB and normalize into the reported range to avoid huge boosts/cuts.
            return (_gain_db_to_normalized(value, min_val, max_val), "eq_gain_db_fallback")

        # Other devices: normalize dB to 0-1
        if -50 <= value <= 50 and value != 0:
            if min_val < 0 or max_val > 1:  # Has a dB range
                return (_gain_db_to_normalized(value, min_val, max_val), "gain_db")

    # === FEEDBACK (percentage) ===
    if 'feedback' in name_lower:
        if value > 1:  # Looks like percentage
            return (_percent_to_normalized(value), "percent")

    # === UTILITY WIDTH (percentage: 0-200% mapped to [0,2]) ===
    if 'width' in name_lower and 'utility' in device_lower:
        if value > 1:  # Looks like percentage
            return (value / 100.0, "utility_width_percent")
    
    # === UTILITY BASS MONO (frequency in Hz) ===
    if 'bass mono' in name_lower or 'bass_mono' in name_lower:
        if value > 1:  # Looks like Hz
            return (_freq_to_normalized(value), "freq_log")
    
    # === ROOM SIZE (already 0-1 typically) ===
    if 'room' in name_lower and 'size' in name_lower:
        if 0 <= value <= 1:
            return (value, "passthrough")

    # === FALLBACK: Linear normalization ===
    # Only apply linear if the value seems out of 0-1 range
    if max_val > min_val and (value < min_val or value > max_val or max_val > 1):
        normalized = (value - min_val) / (max_val - min_val)
        normalized = max(0.0, min(1.0, normalized))
        return (normalized, "linear_fallback")

    # Value already in 0-1 range, pass through
    return (max(0.0, min(1.0, value)), "passthrough")


@dataclass
class CachedDeviceInfo:
    """Cached information about a device's parameters"""
    device_name: str
    param_names: List[str]
    param_mins: List[float]
    param_maxs: List[float]
    timestamp: float
    ttl: float = 300.0  # 5 minutes default
    accessible: bool = True
    is_vst: bool = False
    
    def is_expired(self) -> bool:
        """Check if cache entry is expired"""
        return time.time() - self.timestamp > self.ttl
    
    @property
    def param_count(self) -> int:
        return len(self.param_names)

    def get_param_index(self, name: str) -> Optional[int]:
        """Find parameter index by name (case-insensitive)"""
        name_lower = name.lower()
        
        # Exact match first
        for i, param_name in enumerate(self.param_names):
            if param_name.lower() == name_lower:
                return i
        
        # Partial match (name contains search term)
        for i, param_name in enumerate(self.param_names):
            if name_lower in param_name.lower():
                return i
        
        # Reverse partial match (search term contains param name)
        for i, param_name in enumerate(self.param_names):
            if param_name.lower() in name_lower:
                return i
        
        return None


class ParameterCache:
    """
    Thread-safe cache for device parameter information.
    
    Caches parameter names, min/max values to avoid repeated OSC queries.
    Automatically expires entries after TTL.
    """
    
    def __init__(self, default_ttl: float = 300.0):
        self._cache: Dict[Tuple[int, int], CachedDeviceInfo] = {}
        self._lock = threading.Lock()
        self.default_ttl = default_ttl
    
    def get(self, track_index: int, device_index: int) -> Optional[CachedDeviceInfo]:
        """Get cached device info, returns None if not cached or expired"""
        key = (track_index, device_index)
        with self._lock:
            if key in self._cache:
                info = self._cache[key]
                if not info.is_expired():
                    return info
                else:
                    # Remove expired entry
                    del self._cache[key]
        return None
    
    def set(self, track_index: int, device_index: int, 
            device_name: str, param_names: List[str],
            param_mins: List[float], param_maxs: List[float],
            accessible: bool = True, is_vst: bool = False) -> CachedDeviceInfo:
        """Cache device parameter information"""
        key = (track_index, device_index)
        info = CachedDeviceInfo(
            device_name=device_name,
            param_names=param_names,
            param_mins=param_mins,
            param_maxs=param_maxs,
            timestamp=time.time(),
            ttl=self.default_ttl,
            accessible=accessible,
            is_vst=is_vst
        )
        with self._lock:
            self._cache[key] = info
        return info
    
    def invalidate(self, track_index: int, device_index: int) -> bool:
        """Invalidate a specific cache entry"""
        key = (track_index, device_index)
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
        return False
    
    def invalidate_track(self, track_index: int) -> int:
        """Invalidate all cache entries for a track"""
        count = 0
        with self._lock:
            keys_to_remove = [k for k in self._cache if k[0] == track_index]
            for key in keys_to_remove:
                del self._cache[key]
                count += 1
        return count
    
    def clear(self) -> int:
        """Clear all cache entries"""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self._lock:
            expired = sum(1 for info in self._cache.values() if info.is_expired())
            return {
                "total_entries": len(self._cache),
                "expired_entries": expired,
                "active_entries": len(self._cache) - expired
            }


class ReliableParameterController:
    """
    Reliable parameter control for Ableton Live devices.
    
    Features:
    - Wait for device readiness before parameter operations
    - Find parameters by name instead of hardcoded indices
    - Verify parameter changes with retry logic
    - Cache parameter info to avoid repeated queries
    - Graceful handling of inaccessible VST parameters
    """
    
    def __init__(self, ableton_controller, verbose: bool = False):
        """
        Initialize the reliable parameter controller.
        
        Args:
            ableton_controller: The AbletonController instance from ableton_controls.py
            verbose: Enable verbose logging for debugging
        """
        self.ableton = ableton_controller
        self.cache = ParameterCache()
        self.verbose = verbose
        
        # Configuration - INCREASED DELAYS for state synchronization reliability
        self.default_ready_timeout = 8.0  # seconds (increased from 5.0)
        self.default_verify_delay = 0.5   # seconds (increased from 0.2 - Ableton needs time)
        self.default_max_retries = 4      # retries (increased from 3)
        self.poll_interval = 0.15         # 150ms between polls (increased from 100ms)
        self.value_tolerance = 0.01       # tolerance for value verification
        self.device_load_delay = 0.5      # 500ms minimum delay after device load
    
    def _log(self, msg: str, level: str = "DEBUG"):
        """Log message if verbose mode is enabled"""
        if self.verbose:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            prefix = {
                "DEBUG": "🔍",
                "INFO": "ℹ️",
                "WARN": "⚠️",
                "ERROR": "❌",
                "SUCCESS": "✅"
            }.get(level, "")
            print(f"[{timestamp}] {prefix} [ReliableParams] {msg}")
    
    # ==================== DEVICE READINESS ====================
    
    def wait_for_device_ready(self, track_index: int, device_index: int,
                               timeout: float = None) -> bool:
        """
        Wait for a device to be ready (parameters accessible).
        
        Polls the device until parameters can be fetched or timeout.
        
        Args:
            track_index: Track index (0-based)
            device_index: Device index on the track (0-based)
            timeout: Timeout in seconds (default: 5.0)
            
        Returns:
            True if device is ready, False if timeout
        """
        timeout = timeout or self.default_ready_timeout
        start_time = time.time()
        attempts = 0
        
        self._log(f"wait_for_device_ready: track={track_index}, device={device_index}, timeout={timeout}s")
        
        while time.time() - start_time < timeout:
            attempts += 1
            
            try:
                # Try to fetch parameter names
                result = self.ableton.get_device_parameters_name_sync(
                    track_index, device_index, timeout=1.0
                )
                
                if result.get("success") and result.get("names"):
                    elapsed = time.time() - start_time
                    param_count = len(result["names"])
                    self._log(f"wait_for_device_ready: got {param_count} parameters, "
                             f"device ready ({elapsed:.2f}s, {attempts} attempts)", "SUCCESS")
                    return True
                    
            except Exception as e:
                self._log(f"wait_for_device_ready: attempt {attempts} failed: {e}", "WARN")
            
            # Wait before next poll
            time.sleep(self.poll_interval)
        
        elapsed = time.time() - start_time
        self._log(f"wait_for_device_ready: TIMEOUT after {elapsed:.2f}s, {attempts} attempts", "ERROR")
        return False
    
    # ==================== PARAMETER DISCOVERY ====================
    
    def _fetch_device_info(self, track_index: int, device_index: int,
                           timeout: float = 3.0) -> Optional[CachedDeviceInfo]:
        """
        Fetch and cache device parameter information.
        
        Args:
            track_index: Track index
            device_index: Device index
            timeout: Query timeout
            
        Returns:
            CachedDeviceInfo or None if failed
        """
        try:
            # Fetch parameter names
            names_result = self.ableton.get_device_parameters_name_sync(
                track_index, device_index, timeout=timeout
            )
            
            if not names_result.get("success") or not names_result.get("names"):
                # Device might be a VST with locked parameters
                self._log(f"_fetch_device_info: Could not fetch params for "
                         f"track={track_index}, device={device_index}", "WARN")
                
                # Cache as inaccessible
                return self.cache.set(
                    track_index, device_index,
                    device_name="Unknown",
                    param_names=[],
                    param_mins=[],
                    param_maxs=[],
                    accessible=False,
                    is_vst=True
                )
            
            param_names = names_result["names"]
            
            # Fetch min/max values
            minmax_result = self.ableton.get_device_parameters_minmax_sync(
                track_index, device_index, timeout=timeout
            )
            
            mins = minmax_result.get("mins", [0.0] * len(param_names))
            maxs = minmax_result.get("maxs", [1.0] * len(param_names))
            
            # Try to get device name
            device_name = "Unknown"
            try:
                devices_result = self.ableton.get_track_devices_sync(track_index)
                if devices_result.get("success") and devices_result.get("devices"):
                    devices = devices_result["devices"]
                    if device_index < len(devices):
                        device_name = devices[device_index]
            except Exception:
                pass
            
            # Cache the info
            info = self.cache.set(
                track_index, device_index,
                device_name=device_name,
                param_names=param_names,
                param_mins=mins,
                param_maxs=maxs,
                accessible=True,
                is_vst=False
            )
            
            self._log(f"_fetch_device_info: Cached {len(param_names)} params for "
                     f"'{device_name}' (track={track_index}, device={device_index})", "INFO")
            
            return info
            
        except Exception as e:
            self._log(f"_fetch_device_info: Error: {e}", "ERROR")
            return None
    
    def get_device_info(self, track_index: int, device_index: int,
                        use_cache: bool = True) -> Optional[CachedDeviceInfo]:
        """
        Get device parameter information (from cache or fresh fetch).
        
        Args:
            track_index: Track index
            device_index: Device index
            use_cache: Whether to use cached info (default: True)
            
        Returns:
            CachedDeviceInfo or None
        """
        if use_cache:
            cached = self.cache.get(track_index, device_index)
            if cached:
                self._log(f"get_device_info: Using cached info for "
                         f"track={track_index}, device={device_index}")
                return cached
        
        return self._fetch_device_info(track_index, device_index)
    
    # Semantic parameter name mappings for common Ableton devices
    # Maps chain builder semantic names -> Ableton parameter names/indices
    SEMANTIC_PARAM_MAPPINGS = {
        "EQ Eight": {
            # Band 1 parameters (indices 1-5)
            "band1_on": ("1 Filter On A", 5), "band1_active": ("1 Filter On A", 5),
            "band1_freq_hz": ("1 Frequency A", 1), "band1_frequency": ("1 Frequency A", 1),
            "band1_gain_db": ("1 Gain A", 2), "band1_gain": ("1 Gain A", 2),
            "band1_q": ("1 Resonance A", 3),
            "band1_type": ("1 Filter Type A", 4),
            # Band 2 parameters (indices 6-10)
            "band2_on": ("2 Filter On A", 10), "band2_active": ("2 Filter On A", 10),
            "band2_freq_hz": ("2 Frequency A", 6), "band2_frequency": ("2 Frequency A", 6),
            "band2_gain_db": ("2 Gain A", 7), "band2_gain": ("2 Gain A", 7),
            "band2_q": ("2 Resonance A", 8),
            "band2_type": ("2 Filter Type A", 9),
            # Band 3 parameters (indices 11-15)
            "band3_on": ("3 Filter On A", 15), "band3_active": ("3 Filter On A", 15),
            "band3_freq_hz": ("3 Frequency A", 11), "band3_frequency": ("3 Frequency A", 11),
            "band3_gain_db": ("3 Gain A", 12), "band3_gain": ("3 Gain A", 12),
            "band3_q": ("3 Resonance A", 13),
            "band3_type": ("3 Filter Type A", 14),
            # Band 4 parameters (indices 16-20)
            "band4_on": ("4 Filter On A", 20), "band4_active": ("4 Filter On A", 20),
            "band4_freq_hz": ("4 Frequency A", 16), "band4_frequency": ("4 Frequency A", 16),
            "band4_gain_db": ("4 Gain A", 17), "band4_gain": ("4 Gain A", 17),
            "band4_q": ("4 Resonance A", 18),
            "band4_type": ("4 Filter Type A", 19),
            # Band 5 parameters (indices 21-25)
            "band5_on": ("5 Filter On A", 25), "band5_active": ("5 Filter On A", 25),
            "band5_freq_hz": ("5 Frequency A", 21), "band5_frequency": ("5 Frequency A", 21),
            "band5_gain_db": ("5 Gain A", 22), "band5_gain": ("5 Gain A", 22),
            "band5_q": ("5 Resonance A", 23),
            "band5_type": ("5 Filter Type A", 24),
            # Band 8 parameters (indices 36-40)
            "band8_on": ("8 Filter On A", 40), "band8_active": ("8 Filter On A", 40),
            "band8_freq_hz": ("8 Frequency A", 36), "band8_frequency": ("8 Frequency A", 36),
            "band8_gain_db": ("8 Gain A", 37), "band8_gain": ("8 Gain A", 37),
            "band8_q": ("8 Resonance A", 38),
            "band8_type": ("8 Filter Type A", 39),
            
            "band_1_filter_type": ("1 Filter Type A", 4),
            "band_1_frequency": ("1 Frequency A", 1),
            "band_1_gain": ("1 Gain A", 2),
            "band_1_q": ("1 Resonance A", 3),
            "band_1_on": ("1 Filter On A", 5),
            
            "band_2_filter_type": ("2 Filter Type A", 9),
            "band_2_frequency": ("2 Frequency A", 6),
            "band_2_gain": ("2 Gain A", 7),
            "band_2_q": ("2 Resonance A", 8),
            "band_2_on": ("2 Filter On A", 10),
            
            "band_5_filter_type": ("5 Filter Type A", 24),
            "band_5_frequency": ("5 Frequency A", 21),
            "band_5_gain": ("5 Gain A", 22),
            "band_5_q": ("5 Resonance A", 23),
            "band_5_on": ("5 Filter On A", 25),
            
            "band_8_filter_type": ("8 Filter Type A", 39),
            "band_8_frequency": ("8 Frequency A", 36),
            "band_8_gain": ("8 Gain A", 37),
            "band_8_q": ("8 Resonance A", 38),
            "band_8_on": ("8 Filter On A", 40),
            
            "output_gain": ("Output Gain", 0),  # Usually index 0 or similar, checking needed. often global gain is last but check
        },
        "Multiband Dynamics": {
            # High Band (Above = compression, Below = upward expansion)
            "high_threshold": ("Above Threshold (High)", 19),
            "high_ratio": ("Above Ratio (High)", 25),
            "high_attack": ("Attack Time (High)", 31),
            "high_release": ("Release Time (High)", 34),
            "high_gain": ("Output Gain (High)", 10),
            # Mid Band
            "mid_threshold": ("Above Threshold (Mid)", 18),
            "mid_ratio": ("Above Ratio (Mid)", 24),
            "mid_attack": ("Attack Time (Mid)", 30),
            "mid_release": ("Release Time (Mid)", 33),
            "mid_gain": ("Output Gain (Mid)", 9),
            # Low Band
            "low_threshold": ("Above Threshold (Low)", 17),
            "low_ratio": ("Above Ratio (Low)", 23),
            "low_attack": ("Attack Time (Low)", 29),
            "low_release": ("Release Time (Low)", 32),
            "low_gain": ("Output Gain (Low)", 8),
            # Global
            "amount": ("Amount", 6),
            "master_output": ("Master Output", 5),
            "dry_wet": ("Amount", 6),
            "output_gain": ("Master Output", 5),
        },
        "Compressor": {
            "threshold_db": ("Threshold", 1), "threshold": ("Threshold", 1),
            "ratio": ("Ratio", 2),
            "attack_ms": ("Attack", 4), "attack": ("Attack", 4),
            "release_ms": ("Release", 5), "release": ("Release", 5),
            "output_gain_db": ("Output Gain", 6), "makeup_gain": ("Output Gain", 6),
            "knee_db": ("Knee", 12), "knee": ("Knee", 12),
            "dry_wet_pct": ("Dry/Wet", 8), "dry_wet": ("Dry/Wet", 8), "mix": ("Dry/Wet", 8),
        },
        "Glue Compressor": {
            "threshold_db": ("Threshold", 1), "threshold": ("Threshold", 1),
            # Local Ableton exposes Glue Compressor as:
            # Device On, Threshold, Range, Makeup, Attack, Ratio, Release, Dry/Wet.
            # Keep fallback indices aligned so capped vocal-template runs do not
            # write Range/Makeup/Attack when OSC name lookup is incomplete.
            "range": ("Range", 2),
            "makeup_db": ("Makeup", 3), "makeup": ("Makeup", 3),
            "attack_ms": ("Attack", 4), "attack": ("Attack", 4),
            "ratio": ("Ratio", 5),
            "release_ms": ("Release", 6), "release": ("Release", 6),
            "dry_wet_pct": ("Dry/Wet", 7), "dry_wet": ("Dry/Wet", 7), "mix": ("Dry/Wet", 7),
        },
        "Saturator": {
            "drive_db": ("Drive", 2), "drive": ("Drive", 2),
            "output_db": ("Output", 3), "output": ("Output", 3),
            "dry_wet_pct": ("Dry/Wet", 6), "dry_wet": ("Dry/Wet", 6), "mix": ("Dry/Wet", 6),
            "type": ("Shaper Type", 1),
        },
        "Reverb": {
            "decay_time_ms": ("Decay Time", 3), "decay_time": ("Decay Time", 3), "decay": ("Decay Time", 3),
            "predelay_ms": ("Predelay", 1), "predelay": ("Predelay", 1),
            "dry_wet_pct": ("Dry/Wet", 10), "dry_wet": ("Dry/Wet", 10), "mix": ("Dry/Wet", 10),
            "room_size": ("Room Size", 2), "size": ("Room Size", 2),
            "high_cut_hz": ("HiShelf Freq", 7), "high_cut": ("HiShelf Freq", 7),
            "low_cut_hz": ("LoShelf Freq", 5), "low_cut": ("LoShelf Freq", 5),
            "stereo": ("Stereo Image", 4), "stereo_image": ("Stereo Image", 4),
            "output_gain": ("Reflect Level", 8), # Best guess for output/gain if not Global. Or "Diffuse Level" (9).
                                                 # Actually Reverb usually has "Input Filter" (0), "Predelay" (1)...
                                                 # Let's try to map to "Dry/Wet" if gain is not standard, or just leave it.
                                                 # Wait, standard Reverb has "Global Gain"? No.
                                                 # For now, let's map Output Gain to Dry/Wet if it's 0dB (unity) or just ignore?
                                                 # Better: "Reflect Level" or "Diffuse Level" are gains.
                                                 # BUT, "Output Gain" in the preset might just be a placeholder.
                                                 # Let's check if there is a "Gain" or "Volume".
                                                 # Reverb Device in 11: Input Processing, Early Reflections, Global.
                                                 # "Input Processing" > "Lo Cut", "Hi Cut".
                                                 # "Global" > "Stereo", "Dry/Wet", "Chorusing".
                                                 # There is no master output gain on stock Reverb other than Dry/Wet mix?
                                                 # checking... actually "Reflect Level" and "Diffuse Level" are the closest.
                                                 # I will map output_gain to nothing for now to avoid breaking things, or maybe "Diffuse Level"?
                                                 # Let's just add "Stereo" for now as that was the explicit failure.
        },
        "Delay": {
            "delay_time_ms": ("L Time", 2), "delay_time": ("L Time", 2), "time": ("L Time", 2),
            "feedback_pct": ("Feedback", 12), "feedback": ("Feedback", 12),
            "dry_wet_pct": ("Dry/Wet", 14), "dry_wet": ("Dry/Wet", 14), "mix": ("Dry/Wet", 14),
            "filter_on": ("Filter", 6),
            "filter_freq_hz": ("Filter Freq", 7), "filter_freq": ("Filter Freq", 7),
            
            # Semantic mappings for Travis Scott JSON
            "sync": ("L Sync", 0), # Or "Delay Mode"
            "time_left": ("L Time", 2),
            "time_right": ("R Time", 4),
            "filter_low": ("Filter Freq", 7), # Delay filter is bandpass? Or High/Low?
            "filter_high": ("Filter Width", 8), # Assuming bandpass width/freq or similar. Check KB.
            "ping_pong": ("Ping Pong", 1),
            "output_gain": ("Output Gain", 0),
        },
        "Utility": {
            "gain_db": ("Gain", 3), "gain": ("Gain", 3),
            "pan": ("Panorama", 4), "panorama": ("Panorama", 4),
            "width_pct": ("Width", 6), "width": ("Width", 6),
            "mute": ("Mute", 1),
        },
    }

    def find_parameter_index(self, track_index: int, device_index: int,
                             param_name: str, use_cache: bool = True) -> Optional[int]:
        """
        Find a parameter index by name.

        Uses semantic name mapping first, then case-insensitive matching with
        fallback to partial matching.

        Args:
            track_index: Track index
            device_index: Device index
            param_name: Parameter name to search for
            use_cache: Whether to use cached info

        Returns:
            Parameter index or None if not found
        """
        self._log(f"find_parameter_index: searching for '{param_name}' "
                 f"on track={track_index}, device={device_index}")

        info = self.get_device_info(track_index, device_index, use_cache)
        if not info:
            self._log(f"find_parameter_index: Could not get device info", "WARN")
            return None

        if not info.accessible:
            self._log(f"find_parameter_index: Device params not accessible", "WARN")
            return None

        # First, try semantic name mapping for known devices
        device_name = info.device_name
        if device_name in self.SEMANTIC_PARAM_MAPPINGS:
            device_mapping = self.SEMANTIC_PARAM_MAPPINGS[device_name]
            param_key = param_name.lower().replace(" ", "_").replace("-", "_")
            if param_key in device_mapping:
                ableton_name, fallback_index = device_mapping[param_key]
                self._log(f"find_parameter_index: semantic mapping '{param_name}' -> '{ableton_name}' (fallback idx: {fallback_index})")
                # Try to find by the mapped Ableton name first
                index = info.get_param_index(ableton_name)
                if index is not None:
                    self._log(f"find_parameter_index: found via semantic mapping at index {index}", "SUCCESS")
                    return index
                # Fall back to hardcoded index
                if fallback_index < info.param_count:
                    self._log(f"find_parameter_index: using fallback index {fallback_index}", "SUCCESS")
                    return fallback_index

        # Standard lookup
        index = info.get_param_index(param_name)

        if index is not None:
            actual_name = info.param_names[index] if index < len(info.param_names) else "?"
            self._log(f"find_parameter_index: found '{param_name}' at index {index} "
                     f"(actual name: '{actual_name}')", "SUCCESS")
        else:
            self._log(f"find_parameter_index: '{param_name}' NOT FOUND", "WARN")
            self._log(f"  Available params: {info.param_names[:10]}...", "DEBUG")
        
        return index
    
    def get_all_parameter_names(self, track_index: int, device_index: int,
                                use_cache: bool = True) -> List[str]:
        """
        Get all parameter names for a device.
        
        Args:
            track_index: Track index
            device_index: Device index
            use_cache: Whether to use cached info
            
        Returns:
            List of parameter names
        """
        info = self.get_device_info(track_index, device_index, use_cache)
        if info and info.accessible:
            return info.param_names
        return []
    
    # ==================== PARAMETER VALUE ACCESS ====================
    
    def get_parameter_value_sync(self, track_index: int, device_index: int,
                                  param_index: int, timeout: float = 2.0) -> Optional[float]:
        """
        Get current value of a parameter (synchronous with response wait).
        
        Args:
            track_index: Track index
            device_index: Device index
            param_index: Parameter index
            timeout: Query timeout
            
        Returns:
            Current parameter value or None if failed
        """
        try:
            # Use the request/response mechanism
            resp = self.ableton._send_and_wait(
                "/live/device/get/parameter/value",
                [track_index, device_index, param_index],
                timeout=timeout
            )
            
            if resp:
                _addr, args = resp
                # Response format: [track_id, device_id, param_id, value]
                # or just [value]
                if len(args) >= 4:
                    return float(args[3])
                elif len(args) >= 1:
                    # Try to find the float value
                    for arg in reversed(args):
                        if isinstance(arg, (int, float)):
                            return float(arg)
                            
            return None
            
        except Exception as e:
            self._log(f"get_parameter_value_sync: Error: {e}", "ERROR")
            return None
    
    def get_parameter_range(self, track_index: int, device_index: int,
                            param_index: int) -> Tuple[float, float]:
        """
        Get min/max range for a parameter.
        
        Args:
            track_index: Track index
            device_index: Device index
            param_index: Parameter index
            
        Returns:
            Tuple of (min_value, max_value)
        """
        info = self.get_device_info(track_index, device_index)
        if info and info.accessible and param_index < len(info.param_mins):
            return (info.param_mins[param_index], info.param_maxs[param_index])
        return (0.0, 1.0)  # Default range
    
    # ==================== VALUE NORMALIZATION ====================
    
    def normalize_value(self, value: float, min_val: float, max_val: float) -> float:
        """
        Convert human-readable value to normalized 0.0-1.0 range.
        
        AbletonOSC expects normalized values for most parameters.
        For example, a frequency of 100 Hz with range 20-20000 Hz becomes:
        (100 - 20) / (20000 - 20) ≈ 0.004
        
        Args:
            value: Human value (e.g., 100 Hz, 4.0 ratio)
            min_val: Parameter minimum value
            max_val: Parameter maximum value
            
        Returns:
            Normalized value in range 0.0-1.0
        """
        if max_val == min_val:
            return 0.0
        
        # Clamp to range first
        clamped = max(min_val, min(max_val, value))
        
        # Normalize
        normalized = (clamped - min_val) / (max_val - min_val)
        
        return normalized
    
    def denormalize_value(self, normalized: float, min_val: float, max_val: float) -> float:
        """
        Convert normalized 0.0-1.0 value back to human-readable range.
        
        Used to convert Ableton's normalized readback values to human units
        for comparison and display.
        
        Args:
            normalized: Normalized value (0.0-1.0)
            min_val: Parameter minimum value
            max_val: Parameter maximum value
            
        Returns:
            Human-readable value in original units
        """
        return min_val + (normalized * (max_val - min_val))
    
    # ==================== VERIFIED PARAMETER SETTING ====================
    
    def set_parameter_verified(self, track_index: int, device_index: int,
                               param_index: int, value: float,
                               max_retries: int = None,
                               verify_delay: float = None,
                               tolerance: float = None) -> Dict[str, Any]:
        """
        Set a parameter and verify it was actually set.
        
        Automatically normalizes human-readable values (e.g., 100 Hz, 4:1 ratio)
        to Ableton's 0.0-1.0 range before sending, and denormalizes readbacks
        for accurate verification.
        
        Retries if verification fails.
        
        Args:
            track_index: Track index
            device_index: Device index
            param_index: Parameter index
            value: Value to set (in human-readable units, e.g., Hz, dB, ms)
            max_retries: Maximum retry attempts (default: 3)
            verify_delay: Delay before verification (default: 0.2s)
            tolerance: Value tolerance for verification (default: 0.01)
            
        Returns:
            Dict with:
            - success: bool
            - requested_value: float (original human value)
            - actual_value: float or None (in human units)
            - attempts: int
            - message: str
            - verified: bool
            - normalized_sent: float (what was actually sent to Ableton)
        """
        max_retries = max_retries or self.default_max_retries
        verify_delay = verify_delay or self.default_verify_delay
        tolerance = tolerance or self.value_tolerance
        
        self._log(f"set_parameter_verified: track={track_index}, device={device_index}, "
                 f"param={param_index}, value={value}")
        
        result = {
            "success": False,
            "requested_value": value,
            "actual_value": None,
            "attempts": 0,
            "message": "",
            "verified": False,
            "clamped": False,
            "min": None,
            "max": None,
            "normalized_sent": None
        }
        
        # Get parameter range for normalization
        pmin, pmax = self.get_parameter_range(track_index, device_index, param_index)
        result["min"] = pmin
        result["max"] = pmax

        # Check if parameter is already in normalized range (0.0-1.0)
        is_normalized_param = (pmin == 0.0 and pmax == 1.0)

        # Get parameter name AND device name for intelligent conversion
        info = self.get_device_info(track_index, device_index)
        param_name = ""
        device_name = ""
        if info and info.accessible:
            if param_index < len(info.param_names):
                param_name = info.param_names[param_index]  # Keep original case
            device_name = info.device_name
        
        # Prepare the target value in human units
        target_value = value
        
        # INTELLIGENT auto-percentage conversion:
        # Only convert if it's a NORMALIZED parameter (0-1) AND looks like a percentage
        # DON'T convert frequency, time, ratio, or other non-percentage parameters
        if is_normalized_param and value > 1.0 and value <= 100.0:
            # Check if this is actually a percentage parameter
            percentage_keywords = ['dry/wet', 'dry', 'wet', 'mix', 'blend', 'amount', 
                                    'depth', 'intensity', 'level', 'volume', 'pan']
            
            # Check if this is NOT a percentage (frequency, time, ratio, etc.)
            non_percentage_keywords = ['frequency', 'freq', 'hz', 'time', 'delay', 
                                        'attack', 'release', 'decay', 'ratio', 
                                        'threshold', 'gain', 'drive', 'output',
                                        'filter', 'base', 'attack', 'release']
            
            param_name_lower = param_name.lower()
            is_percentage = any(kw in param_name_lower for kw in percentage_keywords)
            is_not_percentage = any(kw in param_name_lower for kw in non_percentage_keywords)
            
            # Only convert if it looks like a percentage param and doesn't look like something else
            if is_percentage and not is_not_percentage:
                target_value = value / 100.0
                result["clamped"] = True
                self._log(f"  Auto-converted percentage: {value}% -> {target_value}", "INFO")
            elif not is_percentage and not is_not_percentage:
                # Ambiguous - if value is very close to 0-1 range already, don't convert
                # Otherwise convert as percentage (safer default for 0-1 params)
                if value > 10.0:  # Definitely meant as percentage
                    target_value = value / 100.0
                    result["clamped"] = True
                    self._log(f"  Auto-converted percentage: {value}% -> {target_value}", "INFO")
        
        # NORMALIZATION-FIRST STRATEGY:
        # For parameters where smart_normalize knows the mapping (freq, time, ratio,
        # etc.), we must normalize BEFORE clamping. Otherwise, a human value like
        # "300 Hz" gets clamped to 1.0 (the max of a [0,1] normalized range) before
        # the log formula can convert it to ~0.44.
        #
        # We probe smart_normalize once to see if it would apply a known conversion.
        # If so, we use its output directly (already in 0-1 space).
        # If not (passthrough/linear_fallback), we clamp in human space first.
        
        probe_normalized, probe_method = smart_normalize_parameter(
            param_name, target_value, device_name, pmin, pmax
        )
        
        # Methods that indicate smart_normalize understood the parameter semantics
        _SMART_METHODS = {
            "freq_log", "threshold_lut", "ratio_lut", "attack_log",
            "release_log", "q_log", "decay_log", "predelay_linear",
            "delay_log", "drive_linear", "percent", "gain_db",
            "eq_gain_raw", "eq_gain_db_fallback", "enum_raw",
            "utility_width_percent", "base_linear",
            "glue_threshold_linear", "glue_threshold_raw_db",
            "glue_ratio_enum", "glue_attack_enum", "glue_release_enum",
        }
        
        if probe_method in _SMART_METHODS:
            # smart_normalize handled it — value is already normalized.
            # Clamp the NORMALIZED result to [0, 1] (safe for all params).
            clamped_value = target_value  # Preserve human value for logging
            pre_normalized = True
            self._log(
                f"  Smart conversion ({probe_method}): {target_value} -> "
                f"{probe_normalized:.6f} (pre-normalized)", "INFO"
            )
        else:
            # Fallback: clamp in human space, normalize later
            pre_normalized = False
            clamped_value = target_value
            if target_value < pmin:
                clamped_value = pmin
                result["clamped"] = True
                self._log(f"  Clamped {target_value} to min {pmin}", "INFO")
            elif target_value > pmax:
                clamped_value = pmax
                result["clamped"] = True
                self._log(f"  Clamped {target_value} to max {pmax}", "INFO")
        
        # Calculate appropriate tolerance based on parameter range
        param_range = abs(pmax - pmin)
        if param_range > 100:
            # Large range (e.g., frequency 20-20000): use relative tolerance
            effective_tolerance = max(abs(clamped_value) * 0.02, 1.0)  # 2% or at least 1.0
        elif param_range > 10:
            # Medium range: slightly larger absolute tolerance
            effective_tolerance = max(tolerance, 0.1)
        else:
            # Small range: use default tolerance
            effective_tolerance = tolerance
        
        # SPECIAL CASE: Negative-only range parameters (e.g., Saturator Output -36 to 0,
        # Glue Compressor Threshold -40 to 0) have read/write asymmetry in AbletonOSC.
        # Readback always returns 0.0 regardless of the value set.
        # For these parameters, we skip verification and trust the write succeeded.
        is_negative_only_range = (pmax <= 0.0 and pmin < 0.0)
        
        if is_negative_only_range:
            self._log(f"  Negative-only range [{pmin}, {pmax}] - skipping verification "
                     f"(OSC readback unreliable for these parameters)", "INFO")
            
            # Normalize and send the value (using smart normalization)
            if pre_normalized:
                normalized_value, conversion_method = probe_normalized, probe_method
            else:
                normalized_value, conversion_method = smart_normalize_parameter(
                    param_name, clamped_value, device_name, pmin, pmax
                )
            result["normalized_sent"] = normalized_value
            result["conversion_method"] = conversion_method
            result["attempts"] = 1

            self._log(f"  Sending param={param_index} ({param_name}) human={clamped_value} -> "
                     f"normalized={normalized_value:.6f} (via {conversion_method})")
            
            # STRATEGY: Double send for robustness even without verification
            self.ableton.set_device_parameter(
                track_index, device_index, param_index, normalized_value
            )
            time.sleep(0.01) # Small gap
            set_result = self.ableton.set_device_parameter(
                track_index, device_index, param_index, normalized_value
            )
            
            if set_result.get("success"):
                result["success"] = True
                result["verified"] = False  # Not verified but accepted
                result["actual_value"] = clamped_value  # Assume it worked
                result["message"] = "Set without verification (negative-only range OSC limitation)"
                self._log(f"  Set without verification - trusting write succeeded", "SUCCESS")
                return result
            else:
                result["message"] = f"Failed to set: {set_result.get('message')}"
                self._log(f"  Set failed: {result['message']}", "ERROR")
                return result
        
        for attempt in range(1, max_retries + 1):
            result["attempts"] = attempt
            
            try:
                # === NORMALIZE the value using smart parameter-specific conversion ===
                if pre_normalized:
                    normalized_value, conversion_method = probe_normalized, probe_method
                else:
                    normalized_value, conversion_method = smart_normalize_parameter(
                        param_name, clamped_value, device_name, pmin, pmax
                    )
                result["normalized_sent"] = normalized_value
                result["conversion_method"] = conversion_method

                self._log(f"  Attempt {attempt}: Setting param={param_index} ({param_name}) "
                         f"human={clamped_value} -> normalized={normalized_value:.6f} "
                         f"(via {conversion_method}, range: {pmin} - {pmax})")
                
                # STRATEGY: DOUBLE SEND
                # Send the OSC command twice with a small gap to overcome UDP packet loss
                self.ableton.set_device_parameter(
                    track_index, device_index, param_index, normalized_value
                )
                time.sleep(0.01) # 10ms gap
                set_result = self.ableton.set_device_parameter(
                    track_index, device_index, param_index, normalized_value
                )
                
                if not set_result.get("success"):
                    self._log(f"  Attempt {attempt}: set failed: {set_result.get('message')}", "WARN")
                    time.sleep(verify_delay)
                    continue
                
                # Wait for change to take effect
                time.sleep(verify_delay)
                
                # Verify the value
                actual_readback = self.get_parameter_value_sync(track_index, device_index, param_index)
                
                if actual_readback is not None:
                    # AbletonOSC returns values in NORMALIZED form (0-1) for all parameters.
                    # We need to denormalize to get the human-readable value.
                    # 
                    # IMPORTANT: The readback is compared to what we sent (normalized_value),
                    # not the human value. But we report in human units for the user.
                    
                    # Check if the NORMALIZED value we sent matches the NORMALIZED readback
                    normalized_diff = abs(actual_readback - normalized_value)
                    normalized_tolerance = 0.01  # 1% tolerance in normalized space
                    
                    # Denormalize for human-readable reporting.
                    # For enum_raw writes (e.g., EQ filter type), readback is already
                    # in raw enum space, so do not denormalize again.
                    if result.get("conversion_method") in {"enum_raw", "eq_gain_raw"}:
                        actual_human = actual_readback
                    else:
                        actual_human = self.denormalize_value(actual_readback, pmin, pmax)
                    result["actual_value"] = actual_human
                    
                    # Compare in NORMALIZED space first (more reliable)
                    # Then also check human units with tolerance
                    is_close_normalized = normalized_diff <= normalized_tolerance
                    
                    # Also compare in human units for sanity check
                    human_diff = abs(actual_human - clamped_value)
                    is_close_human = human_diff <= effective_tolerance
                    
                    # Accept if either comparison passes (normalized is more reliable)
                    is_close = is_close_normalized or is_close_human
                    
                    if is_close:
                        result["success"] = True
                        result["verified"] = True
                        result["message"] = f"Parameter set and verified (attempt {attempt})"
                        self._log(f"  Attempt {attempt}: SUCCESS - requested {clamped_value:.4f}, "
                                 f"got {actual_human:.4f} (sent normalized: {normalized_value:.6f}, "
                                 f"read normalized: {actual_readback:.6f})", "SUCCESS")
                        return result
                    else:
                        self._log(f"  Attempt {attempt}: Verification failed - "
                                 f"human: expected {clamped_value:.4f}, got {actual_human:.4f} (diff={human_diff:.4f}) | "
                                 f"normalized: sent {normalized_value:.6f}, read {actual_readback:.6f} (diff={normalized_diff:.6f})", "WARN")
                else:
                    self._log(f"  Attempt {attempt}: Could not read back value", "WARN")
                
            except Exception as e:
                self._log(f"  Attempt {attempt}: Exception: {e}", "ERROR")
            
            # Small delay before retry
            if attempt < max_retries:
                time.sleep(0.1)
        
        # All normal attempts failed - try fallback strategies
        
        # FALLBACK 1: For negative-only ranges (e.g., -36 to 0, -40 to 0)
        # These parameters sometimes need special handling - try sending raw value
        is_negative_only_range = (pmax <= 0 and pmin < 0)
        
        if is_negative_only_range:
            self._log(f"  Trying FALLBACK for negative-range parameter...", "INFO")
            
            # Some negative-range parameters want the raw normalized value sent differently
            # Try: invert the normalized value (some parameters are inverted internally)
            inverted_normalized = 1.0 - normalized_value
            
            try:
                # Fallback: Single send, hope for the best
                set_result = self.ableton.set_device_parameter(
                    track_index, device_index, param_index, inverted_normalized
                )
                time.sleep(verify_delay)
                
                actual_readback = self.get_parameter_value_sync(track_index, device_index, param_index)
                if actual_readback is not None:
                    actual_human = self.denormalize_value(actual_readback, pmin, pmax)
                    result["actual_value"] = actual_human
                    
                    human_diff = abs(actual_human - clamped_value)
                    if human_diff <= effective_tolerance:
                        result["success"] = True
                        result["verified"] = True
                        result["message"] = f"Parameter set with inverted normalization"
                        self._log(f"  FALLBACK SUCCESS with inverted normalization", "SUCCESS")
                        return result
            except Exception as e:
                self._log(f"  FALLBACK failed: {e}", "WARN")
        
        # FALLBACK 2: Accept partial success for parameters that are known to be tricky
        # If we got close enough in human units, consider it acceptable
        if result.get("actual_value") is not None:
            final_human_diff = abs(result["actual_value"] - clamped_value)
            param_range = abs(pmax - pmin)
            
            # For large range params, if we're within 10% of the range, accept it
            if param_range > 10 and final_human_diff <= param_range * 0.1:
                result["success"] = True
                result["verified"] = False  # Not perfectly verified but acceptable
                result["message"] = f"Accepted with relaxed tolerance (diff={final_human_diff:.2f})"
                self._log(f"  Accepted with relaxed tolerance", "INFO")
                return result
        
        # All attempts failed
        result["message"] = f"Failed after {max_retries} attempts"
        self._log(f"set_parameter_verified: FAILED after {max_retries} attempts", "ERROR")
        return result
    
    def set_parameter_by_name(self, track_index: int, device_index: int,
                              param_name: str, value: float,
                              **kwargs) -> Dict[str, Any]:
        """
        Set a parameter by name (finds index automatically).
        
        Args:
            track_index: Track index
            device_index: Device index
            param_name: Parameter name
            value: Value to set
            **kwargs: Additional args passed to set_parameter_verified
            
        Returns:
            Result dict (same as set_parameter_verified)
        """
        param_index = self.find_parameter_index(track_index, device_index, param_name)
        
        if param_index is None:
            return {
                "success": False,
                "message": f"Parameter '{param_name}' not found",
                "requested_value": value,
                "actual_value": None,
                "attempts": 0,
                "verified": False
            }
        
        result = self.set_parameter_verified(
            track_index, device_index, param_index, value, **kwargs
        )
        result["param_name"] = param_name
        result["param_index"] = param_index
        return result
    
    # ==================== DEVICE LOADING WITH VERIFICATION ====================
    
    def load_device_verified(self, track_index: int, device_name: str,
                             position: int = -1,
                             timeout: float = 8.0,
                             min_delay: float = 0.5) -> Dict[str, Any]:
        """
        Load a device and verify it was actually loaded.

        Args:
            track_index: Track index
            device_name: Name of device to load
            position: Position in chain (-1 = end)
            timeout: Timeout for verification (default: 8s, increased for reliability)
            min_delay: Minimum delay after load (default: 500ms - Ableton needs time)
            
        Returns:
            Dict with:
            - success: bool
            - device_index: int (index of loaded device)
            - device_name: str
            - message: str
        """
        self._log(f"load_device_verified: Loading '{device_name}' on track {track_index}")
        
        result = {
            "success": False,
            "device_index": None,
            "device_name": device_name,
            "message": ""
        }
        
        try:
            # Get current device count
            before_result = self.ableton.get_num_devices_sync(track_index)
            count_before = before_result.get("count", 0) if before_result.get("success") else 0
            
            # Load the device
            load_result = self.ableton.load_device(track_index, device_name, position)

            # If the loader returns timeout/no-response, the device may still have loaded.
            # Continue into verification polling instead of failing immediately.
            if not load_result.get("success"):
                msg = str(load_result.get("message", "")).lower()
                recoverable = (
                    "timeout" in msg
                    or "no response" in msg
                    or "not responding" in msg
                )
                if not recoverable:
                    result["message"] = f"Load failed: {load_result.get('message')}"
                    return result
                self._log(
                    f"load_device_verified: recoverable load failure '{load_result.get('message')}', checking device count anyway",
                    "WARN",
                )

            # Wait minimum delay
            time.sleep(min_delay)
            
            # Poll for device count increase
            start_time = time.time()
            while time.time() - start_time < timeout:
                after_result = self.ableton.get_num_devices_sync(track_index)
                count_after = after_result.get("count", 0) if after_result.get("success") else 0
                
                if count_after > count_before:
                    # Device loaded - it's at the end (or at position)
                    device_index = count_after - 1 if position == -1 else position
                    result["success"] = True
                    result["device_index"] = device_index
                    result["message"] = f"Device loaded at index {device_index}"
                    
                    # Invalidate cache for this position since device is new
                    self.cache.invalidate(track_index, device_index)
                    
                    self._log(f"load_device_verified: SUCCESS - '{device_name}' "
                             f"loaded at index {device_index}", "SUCCESS")
                    return result
                
                time.sleep(self.poll_interval)
            
            result["message"] = f"Timeout waiting for device to load"
            self._log(f"load_device_verified: TIMEOUT", "ERROR")
            return result
            
        except Exception as e:
            result["message"] = f"Error: {e}"
            self._log(f"load_device_verified: ERROR: {e}", "ERROR")
            return result
    
    # ==================== BATCH OPERATIONS ====================
    
    def set_multiple_parameters(self, track_index: int, device_index: int,
                                params: Dict[int, float],
                                delay_between: float = 0.05) -> Dict[str, Any]:
        """
        Set multiple parameters on a device.
        
        Args:
            track_index: Track index
            device_index: Device index
            params: Dict of {param_index: value}
            delay_between: Delay between parameter sets
            
        Returns:
            Dict with overall results and per-parameter results
        """
        results = {
            "success": True,
            "total": len(params),
            "succeeded": 0,
            "failed": 0,
            "details": []
        }
        
        for param_index, value in params.items():
            result = self.set_parameter_verified(
                track_index, device_index, param_index, value
            )
            
            results["details"].append({
                "param_index": param_index,
                "value": value,
                **result
            })
            
            if result["success"]:
                results["succeeded"] += 1
            else:
                results["failed"] += 1
                results["success"] = False
            
            time.sleep(delay_between)
        
        results["message"] = f"Set {results['succeeded']}/{results['total']} parameters"
        return results
    
    def set_parameters_by_name(self, track_index: int, device_index: int,
                               params: Dict[str, float],
                               delay_between: float = 0.05) -> Dict[str, Any]:
        """
        Set multiple parameters by name.
        
        Args:
            track_index: Track index
            device_index: Device index
            params: Dict of {param_name: value}
            delay_between: Delay between parameter sets
            
        Returns:
            Dict with overall results and per-parameter results
        """
        results = {
            "success": True,
            "total": len(params),
            "succeeded": 0,
            "failed": 0,
            "not_found": 0,
            "details": []
        }
        
        for param_name, value in params.items():
            result = self.set_parameter_by_name(
                track_index, device_index, param_name, value
            )
            
            results["details"].append({
                "param_name": param_name,
                "value": value,
                **result
            })
            
            if result["success"]:
                results["succeeded"] += 1
            else:
                results["failed"] += 1
                results["success"] = False
                if "not found" in result.get("message", "").lower():
                    results["not_found"] += 1
            
            time.sleep(delay_between)
        
        results["message"] = (f"Set {results['succeeded']}/{results['total']} parameters "
                             f"({results['not_found']} not found)")
        return results
    
    # ==================== RETRY WITH EXPONENTIAL BACKOFF ====================

    def _retry_with_backoff(self, operation, max_retries: int = 3,
                            base_delay: float = 0.3,
                            max_delay: float = 2.0) -> Any:
        """
        Retry an operation with exponential backoff.

        Args:
            operation: Callable to retry
            max_retries: Maximum number of retries
            base_delay: Initial delay in seconds
            max_delay: Maximum delay between retries

        Returns:
            Result of operation or None if all retries failed
        """
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                result = operation()
                if result is not None:
                    return result
            except Exception as e:
                last_error = e
                self._log(f"Retry attempt {attempt + 1} failed: {e}", "WARN")

            if attempt < max_retries:
                # Exponential backoff: base_delay * 2^attempt
                delay = min(base_delay * (2 ** attempt), max_delay)
                self._log(f"Retrying in {delay:.2f}s...", "DEBUG")
                time.sleep(delay)

        self._log(f"All {max_retries + 1} attempts failed. Last error: {last_error}", "ERROR")
        return None

    def get_device_count_with_retry(self, track_index: int,
                                     expected_count: int = None,
                                     max_retries: int = 3) -> Dict[str, Any]:
        """
        Get device count with retry logic for state synchronization.

        If expected_count is provided, retries until the count matches or
        max retries exceeded. This helps with the race condition where
        device load completes but OSC query still returns old state.

        Args:
            track_index: Track index
            expected_count: Expected device count (optional)
            max_retries: Maximum retries

        Returns:
            Dict with success, count, and whether expected count was matched
        """
        result = {
            "success": False,
            "count": 0,
            "expected_matched": False,
            "attempts": 0,
            "message": ""
        }

        for attempt in range(max_retries + 1):
            result["attempts"] = attempt + 1

            try:
                count_result = self.ableton.get_num_devices_sync(track_index)

                if count_result.get("success"):
                    count = count_result.get("count", 0)
                    result["count"] = count
                    result["success"] = True

                    # If no expected count, return immediately
                    if expected_count is None:
                        result["message"] = f"Got device count: {count}"
                        return result

                    # Check if expected count matched
                    if count >= expected_count:
                        result["expected_matched"] = True
                        result["message"] = f"Device count matches expected: {count}"
                        self._log(f"Device count matched expected {expected_count} "
                                 f"on attempt {attempt + 1}", "SUCCESS")
                        return result
                    else:
                        self._log(f"Device count {count} < expected {expected_count}, "
                                 f"retrying...", "DEBUG")

            except Exception as e:
                self._log(f"get_device_count_with_retry attempt {attempt + 1} failed: {e}", "WARN")

            if attempt < max_retries:
                # Exponential backoff
                delay = min(0.3 * (2 ** attempt), 2.0)
                time.sleep(delay)

        result["message"] = f"Expected count {expected_count} not reached after {max_retries + 1} attempts"
        self._log(result["message"], "WARN")
        return result

    def get_track_devices_with_retry(self, track_index: int,
                                      expected_device: str = None,
                                      max_retries: int = 3) -> Dict[str, Any]:
        """
        Get track devices with retry logic for state synchronization.

        If expected_device is provided, retries until the device is found
        or max retries exceeded.

        Args:
            track_index: Track index
            expected_device: Expected device name to find (optional)
            max_retries: Maximum retries

        Returns:
            Dict with success, devices list, and whether expected device was found
        """
        result = {
            "success": False,
            "devices": [],
            "expected_found": False,
            "attempts": 0,
            "message": ""
        }

        for attempt in range(max_retries + 1):
            result["attempts"] = attempt + 1

            try:
                devices_result = self.ableton.get_track_devices_sync(track_index)

                if devices_result.get("success"):
                    devices = devices_result.get("devices", [])
                    result["devices"] = devices
                    result["success"] = True

                    # If no expected device, return immediately
                    if expected_device is None:
                        result["message"] = f"Got {len(devices)} devices"
                        return result

                    # Check if expected device found (case-insensitive)
                    expected_lower = expected_device.lower()
                    for device in devices:
                        if expected_lower in device.lower():
                            result["expected_found"] = True
                            result["message"] = f"Found expected device: {device}"
                            self._log(f"Found expected device '{expected_device}' "
                                     f"on attempt {attempt + 1}", "SUCCESS")
                            return result

                    self._log(f"Expected device '{expected_device}' not found in {devices}, "
                             f"retrying...", "DEBUG")

            except Exception as e:
                self._log(f"get_track_devices_with_retry attempt {attempt + 1} failed: {e}", "WARN")

            if attempt < max_retries:
                # Exponential backoff
                delay = min(0.3 * (2 ** attempt), 2.0)
                time.sleep(delay)

        result["message"] = f"Expected device '{expected_device}' not found after {max_retries + 1} attempts"
        self._log(result["message"], "WARN")
        return result

    # ==================== READ-WRITE FEEDBACK LOOP ====================

    def set_parameter_with_readback(
        self,
        track_index: int,
        device_index: int,
        param_index: int,
        target_display_value: float,
        max_iterations: int = 5,
        tolerance_pct: float = 5.0,
        auto_calibrate: bool = True,
    ) -> Dict[str, Any]:
        """
        Set a parameter using a closed Read-Write feedback loop.

        Instead of blindly sending a normalized float, this method:
        1. Estimates an initial normalized value (from calibration DB or smart_normalize).
        2. Sends it to Ableton.
        3. Reads back the display string (e.g., "1.2 kHz").
        4. Compares the readback to the target.
        5. If wrong, adjusts via binary search and retries.

        Args:
            track_index: Track index (0-based)
            device_index: Device index (0-based)
            param_index: Parameter index (0-based)
            target_display_value: Target value in human units (e.g., 500 for 500 Hz)
            max_iterations: Maximum correction iterations
            tolerance_pct: Acceptable error as % of target value (default 5%)
            auto_calibrate: If True, trigger a calibration sweep on first encounter

        Returns:
            Dict with success, iterations, target, actual_display, final_normalized, etc.
        """
        from calibration_utils import (
            CalibrationStore,
            CalibrationSweeper,
            parse_display_value,
            value_to_normalized_from_curve,
        )

        result = {
            "success": False,
            "target_value": target_display_value,
            "actual_display": None,
            "actual_base_value": None,
            "final_normalized": None,
            "iterations": 0,
            "method": None,
            "message": "",
        }

        # --- Step 0: Get device + param info ---
        info = self.get_device_info(track_index, device_index)
        if not info or not info.accessible:
            result["message"] = "Device not accessible"
            self._log(f"set_parameter_with_readback: device not accessible", "ERROR")
            return result

        device_name = info.device_name
        param_name = info.param_names[param_index] if param_index < len(info.param_names) else f"param_{param_index}"
        pmin, pmax = self.get_parameter_range(track_index, device_index, param_index)

        self._log(
            f"set_parameter_with_readback: device={device_name}, param={param_name} "
            f"(idx={param_index}), target={target_display_value}, range=[{pmin}, {pmax}]"
        )

        # --- Step 1: Get initial guess from CalibrationStore ---
        store = CalibrationStore()
        curve = store.get_curve(device_name, param_name, param_index=param_index)

        guess = None
        if curve:
            guess = value_to_normalized_from_curve(float(target_display_value), curve)
            if guess is not None:
                result["method"] = "calibration_curve"
                self._log(f"  Initial guess from calibration: {guess:.6f}", "INFO")

        # --- Step 2: Fall back to smart_normalize ---
        if guess is None:
            guess_val, method = smart_normalize_parameter(
                param_name, float(target_display_value), device_name, pmin, pmax
            )
            guess = guess_val
            result["method"] = f"smart_normalize ({method})"
            self._log(f"  Initial guess from smart_normalize: {guess:.6f} ({method})", "INFO")

        # --- Step 3: Auto-calibrate if no curve exists ---
        if curve is None and auto_calibrate:
            self._log(f"  No calibration curve found. Running auto-calibration sweep...", "INFO")
            try:
                sweeper = CalibrationSweeper(self.ableton)
                sweep_result = sweeper.sweep_and_save(
                    track_index, device_index, param_indices=[param_index]
                )
                # Reload curve
                curve = store.get_curve(device_name, param_name, param_index=param_index)
                if curve:
                    new_guess = value_to_normalized_from_curve(float(target_display_value), curve)
                    if new_guess is not None:
                        guess = new_guess
                        result["method"] = "auto_calibrated_curve"
                        self._log(f"  Updated guess from auto-calibration: {guess:.6f}", "INFO")
            except Exception as e:
                self._log(f"  Auto-calibration failed: {e}", "WARN")

        # --- Step 4: Send + Read + Correct loop ---
        low = 0.0
        high = 1.0
        current_guess = max(0.0, min(1.0, guess))

        for iteration in range(1, max_iterations + 1):
            result["iterations"] = iteration

            # Send
            self.ableton.set_device_parameter(
                track_index, device_index, param_index, current_guess
            )
            time.sleep(self.default_verify_delay)

            # Read back display string
            readback = self.ableton.get_device_parameter_value_string_sync(
                track_index, device_index, param_index
            )
            display_str = readback.get("value_string", "") if readback.get("success") else ""
            result["actual_display"] = display_str

            parsed = parse_display_value(display_str)
            actual_base = parsed.get("base_value")
            result["actual_base_value"] = actual_base
            result["final_normalized"] = current_guess

            self._log(
                f"  Iteration {iteration}: sent={current_guess:.6f}, "
                f"readback=\"{display_str}\", parsed={actual_base}"
            )

            if actual_base is None:
                self._log(f"  Could not parse readback - accepting current guess", "WARN")
                result["success"] = True
                result["message"] = f"Set to {current_guess:.6f}, readback unparseable: \"{display_str}\""
                return result

            # Compare
            target_f = float(target_display_value)
            diff = abs(actual_base - target_f)
            threshold = abs(target_f) * (tolerance_pct / 100.0) if target_f != 0 else 1.0

            if diff <= threshold:
                result["success"] = True
                result["message"] = (
                    f"Converged in {iteration} iteration(s): "
                    f"target={target_f}, actual={actual_base} "
                    f"(diff={diff:.2f}, threshold={threshold:.2f})"
                )
                self._log(f"  SUCCESS: {result['message']}", "SUCCESS")
                return result

            # Adjust via binary search
            if actual_base < target_f:
                # Need to go higher
                low = current_guess
            else:
                # Need to go lower
                high = current_guess
            current_guess = (low + high) / 2.0

            self._log(
                f"  Adjusting: actual={actual_base}, target={target_f}, "
                f"new_guess={current_guess:.6f} (range [{low:.6f}, {high:.6f}])"
            )

        # Exhausted iterations
        result["message"] = (
            f"Did not converge after {max_iterations} iterations. "
            f"Last readback: \"{result['actual_display']}\" "
            f"(parsed={result['actual_base_value']})"
        )
        self._log(f"  FAILED: {result['message']}", "ERROR")
        return result

    # ==================== UTILITIES ====================

    def clear_cache(self) -> int:
        """Clear all cached device info"""
        count = self.cache.clear()
        self._log(f"Cleared {count} cache entries")
        return count
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return self.cache.stats()
    
    def test_device_accessibility(self, track_index: int, device_index: int) -> Dict[str, Any]:
        """
        Test if a device's parameters are accessible.
        
        Useful for diagnosing VST parameter issues.
        
        Returns:
            Dict with accessibility info
        """
        result = {
            "accessible": False,
            "device_name": None,
            "param_count": 0,
            "sample_params": [],
            "message": ""
        }
        
        info = self._fetch_device_info(track_index, device_index)
        
        if info:
            result["device_name"] = info.device_name
            result["accessible"] = info.accessible
            result["param_count"] = len(info.param_names)
            result["sample_params"] = info.param_names[:10]
            result["is_vst"] = info.is_vst
            result["message"] = "Accessible" if info.accessible else "Parameters not accessible"
        else:
            result["message"] = "Could not fetch device info"
        
        return result


# Convenience function for creating controller with the global ableton instance
def get_reliable_controller(verbose: bool = False) -> ReliableParameterController:
    """
    Get a ReliableParameterController using the global ableton instance.
    
    Args:
        verbose: Enable verbose logging
        
    Returns:
        ReliableParameterController instance
    """
    from .controller import ableton
    return ReliableParameterController(ableton, verbose=verbose)

