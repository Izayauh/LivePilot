"""
Device Parameter Cache for Jarvis-Ableton

Provides a caching layer for device parameter names and indices,
avoiding repeated OSC queries to Ableton.

This is useful because:
1. OSC queries are async and don't return data directly
2. Parameter indices need to be known to set values
3. Common devices have predictable parameter layouts

NOTE: This cache is populated with known Ableton stock device parameters.
For VST/AU plugins, you'll need to query parameters at runtime.
"""

from typing import Dict, Optional, List


class DeviceParameterCache:
    """
    Cache for device parameter names to indices mapping.
    
    Provides quick lookup of parameter indices by name for common Ableton devices.
    """
    
    def __init__(self):
        """Initialize the parameter cache with known device parameters"""
        self._cache: Dict[str, Dict[str, int]] = {}
        self._load_stock_devices()
    
    def _load_stock_devices(self):
        """Load parameter mappings for Ableton stock devices"""
        
        # Compressor parameters (typical layout)
        self._cache["Compressor"] = {
            "Device On": 0,
            "Threshold": 1,
            "Ratio": 2,
            "Attack": 3,
            "Release": 4,
            "Output Gain": 5,
            "Dry/Wet": 6,
            "Model": 7,
            "Knee": 8,
            "Makeup": 9,
            "Env Mode": 10,
            "Sidechain": 11,
        }
        
        # Reverb parameters (typical layout)
        self._cache["Reverb"] = {
            "Device On": 0,
            "Decay Time": 1,
            "Room Size": 2,
            "Pre-Delay": 3,
            "Input Filter Freq": 4,
            "Input Filter Width": 5,
            "Early Reflect": 6,
            "Spin Rate": 7,
            "Spin Amount": 8,
            "Diffuse Network": 9,
            "Hi Shelf Freq": 10,
            "Hi Shelf Gain": 11,
            "Lo Shelf Freq": 12,
            "Lo Shelf Gain": 13,
            "Chorus Rate": 14,
            "Chorus Amount": 15,
            "Density": 16,
            "Scale": 17,
            "Flat": 18,
            "Stereo Image": 19,
            "Dry/Wet": 20,
        }
        
        # EQ Eight parameters
        self._cache["Eq8"] = {
            "Device On": 0,
            "Band 1 On": 1,
            "Band 1 Type": 2,
            "Band 1 Freq": 3,
            "Band 1 Gain": 4,
            "Band 1 Q": 5,
            "Band 2 On": 6,
            "Band 2 Type": 7,
            "Band 2 Freq": 8,
            "Band 2 Gain": 9,
            "Band 2 Q": 10,
            # ... bands 3-8 follow same pattern
        }
        
        # Delay parameters
        self._cache["Delay"] = {
            "Device On": 0,
            "L Time": 1,
            "L Sync": 2,
            "R Time": 3,
            "R Sync": 4,
            "Feedback": 5,
            "Dry/Wet": 6,
            "Filter On": 7,
            "Filter Freq": 8,
            "Filter Width": 9,
        }
        
        # Simple Delay
        self._cache["SimpleDelay"] = {
            "Device On": 0,
            "Delay Time": 1,
            "Sync": 2,
            "Feedback": 3,
            "Dry/Wet": 4,
        }
        
        # Auto Filter parameters
        self._cache["AutoFilter"] = {
            "Device On": 0,
            "Filter Type": 1,
            "Frequency": 2,
            "Resonance": 3,
            "Env Amount": 4,
            "Env Attack": 5,
            "Env Release": 6,
            "LFO Amount": 7,
            "LFO Rate": 8,
            "LFO Phase": 9,
            "LFO Sync": 10,
            "Dry/Wet": 11,
        }
        
        # Saturator parameters
        self._cache["Saturator"] = {
            "Device On": 0,
            "Drive": 1,
            "Type": 2,
            "Base": 3,
            "Frequency": 4,
            "Width": 5,
            "Depth": 6,
            "Output": 7,
            "Dry/Wet": 8,
        }
        
        # Limiter parameters
        self._cache["Limiter"] = {
            "Device On": 0,
            "Gain": 1,
            "Ceiling": 2,
            "Release": 3,
        }
        
        # Utility parameters
        self._cache["Utility"] = {
            "Device On": 0,
            "Gain": 1,
            "Mute": 2,
            "Phase Invert L": 3,
            "Phase Invert R": 4,
            "Channel Mode": 5,
            "Width": 6,
            "Mid/Side": 7,
            "Balance": 8,
            "Panorama": 9,
        }
        
        # Chorus parameters
        self._cache["Chorus"] = {
            "Device On": 0,
            "Rate": 1,
            "Amount": 2,
            "Delay 1 Time": 3,
            "Delay 2 Time": 4,
            "Feedback": 5,
            "Polarity": 6,
            "Dry/Wet": 7,
        }
        
        # Gate parameters
        self._cache["Gate"] = {
            "Device On": 0,
            "Threshold": 1,
            "Return": 2,
            "Attack": 3,
            "Hold": 4,
            "Release": 5,
            "Floor": 6,
        }
    
    def get_param_index(self, device_class: str, param_name: str) -> Optional[int]:
        """
        Get parameter index by device class and parameter name
        
        Args:
            device_class: Device class name (e.g., "Compressor", "Reverb")
            param_name: Parameter name (e.g., "Threshold", "Dry/Wet")
            
        Returns:
            Parameter index if found, None otherwise
        """
        device_params = self._cache.get(device_class)
        if device_params:
            return device_params.get(param_name)
        return None
    
    def get_param_name(self, device_class: str, param_index: int) -> Optional[str]:
        """
        Get parameter name by device class and index
        
        Args:
            device_class: Device class name (e.g., "Compressor", "Reverb")
            param_index: Parameter index
            
        Returns:
            Parameter name if found, None otherwise
        """
        device_params = self._cache.get(device_class)
        if device_params:
            for name, idx in device_params.items():
                if idx == param_index:
                    return name
        return None
    
    def get_device_params(self, device_class: str) -> Optional[Dict[str, int]]:
        """
        Get all parameters for a device class
        
        Args:
            device_class: Device class name (e.g., "Compressor", "Reverb")
            
        Returns:
            Dictionary of parameter names to indices, or None if unknown
        """
        return self._cache.get(device_class)
    
    def list_known_devices(self) -> List[str]:
        """
        Get list of all known device classes
        
        Returns:
            List of device class names
        """
        return list(self._cache.keys())
    
    def add_device(self, device_class: str, params: Dict[str, int]):
        """
        Add or update a device's parameter mapping
        
        Args:
            device_class: Device class name
            params: Dictionary mapping parameter names to indices
        """
        self._cache[device_class] = params
    
    def has_device(self, device_class: str) -> bool:
        """
        Check if a device class is in the cache
        
        Args:
            device_class: Device class name
            
        Returns:
            True if device is cached, False otherwise
        """
        return device_class in self._cache


# Common parameter shortcuts for voice commands
COMMON_PARAMS = {
    "dry wet": "Dry/Wet",
    "drywet": "Dry/Wet",
    "mix": "Dry/Wet",
    "volume": "Gain",
    "level": "Gain",
    "amount": "Amount",
    "rate": "Rate",
    "speed": "Rate",
    "decay": "Decay Time",
    "size": "Room Size",
    "attack": "Attack",
    "release": "Release",
    "threshold": "Threshold",
    "ratio": "Ratio",
    "frequency": "Frequency",
    "freq": "Frequency",
    "resonance": "Resonance",
    "feedback": "Feedback",
    "drive": "Drive",
    "width": "Width",
}


def normalize_param_name(spoken_name: str) -> str:
    """
    Convert a spoken parameter name to the actual parameter name
    
    Args:
        spoken_name: What the user said (e.g., "dry wet", "mix")
        
    Returns:
        Normalized parameter name (e.g., "Dry/Wet")
    """
    normalized = spoken_name.lower().strip()
    return COMMON_PARAMS.get(normalized, spoken_name)


# Singleton instance for easy import
device_cache = DeviceParameterCache()


if __name__ == "__main__":
    # Print all cached devices and their parameters
    print("=== Device Parameter Cache ===\n")
    
    cache = DeviceParameterCache()
    
    for device in cache.list_known_devices():
        print(f"\n{device}:")
        params = cache.get_device_params(device)
        if params:
            for name, idx in sorted(params.items(), key=lambda x: x[1]):
                print(f"  {idx:2d}: {name}")
    
    print(f"\n\nTotal cached devices: {len(cache.list_known_devices())}")
    
    # Test parameter lookup
    print("\n=== Parameter Lookup Test ===")
    print(f"Compressor -> Threshold: index {cache.get_param_index('Compressor', 'Threshold')}")
    print(f"Reverb -> Dry/Wet: index {cache.get_param_index('Reverb', 'Dry/Wet')}")
    print(f"Reverb -> index 1: {cache.get_param_name('Reverb', 1)}")

