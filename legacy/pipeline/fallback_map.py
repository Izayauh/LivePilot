"""
Plugin fallback resolution for the non-chatty pipeline.

Resolves device names to loadable devices using:
- STOCK_DEVICES: Always-available Ableton built-in devices
- NATIVE_FALLBACKS: Type-based fallback chains
- PluginPreferences: Blacklist/whitelist from config

Sources:
- STOCK_DEVICES from agents/executor_agent.py:551
- NATIVE_FALLBACKS from plugins/chain_builder.py:238
"""

from typing import List, Optional, Tuple


# Stock Ableton devices that are always available (no plugin scan needed)
STOCK_DEVICES = {
    "EQ Eight", "EQ Three", "Channel EQ",
    "Compressor", "Glue Compressor", "Multiband Dynamics",
    "Reverb", "Delay", "Echo", "Simple Delay",
    "Saturator", "Limiter", "Pedal", "Overdrive",
    "Corpus", "Erosion", "Vinyl Distortion",
    "Auto Filter", "Auto Pan",
    "Chorus-Ensemble", "Phaser-Flanger",
    "Spectral Resonator", "Spectral Time",
    "Utility", "Tuner", "Gate", "Drum Buss",
}

# Plugin type keyword -> ordered fallback list of native devices
NATIVE_FALLBACKS = {
    "eq": ["EQ Eight", "EQ Three", "Channel EQ"],
    "eq_eight": ["EQ Eight"],
    "equalizer": ["EQ Eight", "EQ Three"],
    "compressor": ["Compressor", "Glue Compressor"],
    "comp": ["Compressor", "Glue Compressor"],
    "glue_compressor": ["Glue Compressor", "Compressor"],
    "limiter": ["Limiter"],
    "reverb": ["Reverb"],
    "delay": ["Delay", "Echo", "Simple Delay"],
    "echo": ["Echo", "Delay"],
    "saturation": ["Saturator", "Pedal"],
    "saturator": ["Saturator", "Pedal", "Overdrive"],
    "distortion": ["Saturator", "Pedal", "Overdrive"],
    "drive": ["Saturator", "Overdrive"],
    "overdrive": ["Overdrive", "Saturator"],
    "de-esser": ["Multiband Dynamics"],
    "deesser": ["Multiband Dynamics"],
    "de_esser": ["Multiband Dynamics"],
    "dynamics": ["Multiband Dynamics", "Gate"],
    "multiband": ["Multiband Dynamics"],
    "gate": ["Gate"],
    "chorus": ["Chorus-Ensemble"],
    "phaser": ["Phaser-Flanger"],
    "flanger": ["Phaser-Flanger"],
    "modulation": ["Chorus-Ensemble", "Phaser-Flanger"],
    "utility": ["Utility"],
    "filter": ["Auto Filter"],
    "auto_filter": ["Auto Filter"],
    "spectrum": ["Spectrum"],
    "tuner": ["Tuner"],
}


def resolve_device_name(
    requested_name: str,
    fallback_override: Optional[str] = None,
) -> Tuple[str, bool]:
    """Resolve a device name to a loadable device.

    Resolution order:
    1. Exact match in STOCK_DEVICES
    2. Case-insensitive match in STOCK_DEVICES
    3. Explicit fallback_override
    4. PluginPreferences blacklist -> configured fallback
    5. Type-keyword match in NATIVE_FALLBACKS
    6. Return as-is (let load_device_verified handle failure)

    Returns:
        (resolved_name, is_fallback) where is_fallback=True if the
        resolved name differs from the requested name.
    """
    # 1. Direct match to stock device
    if requested_name in STOCK_DEVICES:
        return (requested_name, False)

    # 2. Case-insensitive match
    for stock in STOCK_DEVICES:
        if stock.lower() == requested_name.lower():
            return (stock, False)

    # 3. If fallback_override is set, still return primary name first.
    #    The executor will try loading the primary and only use fallback
    #    on failure (see executor._execute_device).

    # 4. Check blacklist and configured fallbacks
    try:
        from plugins.chain_builder import get_plugin_preferences
        prefs = get_plugin_preferences()
        if prefs.is_blacklisted(requested_name):
            fb = prefs.get_fallback(requested_name)
            if fb:
                return (fb[0], True)
    except ImportError:
        pass

    # 5. Type-keyword match in NATIVE_FALLBACKS
    name_lower = requested_name.lower()
    for type_key, fallbacks in NATIVE_FALLBACKS.items():
        if type_key in name_lower:
            return (fallbacks[0], True)

    # 6. Return as-is (third-party plugin or unknown)
    return (requested_name, False)


def get_fallback_chain(device_name: str) -> List[str]:
    """Get the full fallback chain for a device name.

    Returns a list of alternative device names to try, in priority order.
    Returns empty list if no fallbacks are available.
    """
    fallbacks = []

    # Check configured fallbacks first
    try:
        from plugins.chain_builder import get_plugin_preferences
        prefs = get_plugin_preferences()
        fb = prefs.get_fallback(device_name)
        if fb:
            fallbacks.extend(fb)
    except ImportError:
        pass

    # Then type-keyword fallbacks
    name_lower = device_name.lower()
    for type_key, native_fbs in NATIVE_FALLBACKS.items():
        if type_key in name_lower:
            for nfb in native_fbs:
                if nfb not in fallbacks:
                    fallbacks.append(nfb)
            break

    return fallbacks
