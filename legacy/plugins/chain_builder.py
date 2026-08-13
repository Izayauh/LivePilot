"""
Plugin Chain Builder

Takes research results about plugin chains and creates them in Ableton Live.
Handles fuzzy matching of plugin names, finding alternatives when exact
plugins aren't available, and managing the device loading sequence.

Enhanced with:
- Plugin blacklist/whitelist filtering
- Fallback mappings for unavailable plugins
- User preference support
- Tiered plugin name resolution for better matching
"""

import asyncio
import json
import os
import fnmatch
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime

# Import VST Discovery
from discovery.vst_discovery import get_vst_discovery, PluginInfo, VSTDiscoveryService

# Import tiered plugin name resolver
try:
    from discovery.plugin_name_resolver import get_plugin_resolver, ResolveResult
    _HAS_RESOLVER = True
except ImportError:
    _HAS_RESOLVER = False
    ResolveResult = None


# ==================== PLUGIN PREFERENCES ====================

class PluginPreferences:
    """
    Manages plugin filtering preferences (blacklist, whitelist, fallbacks)
    """

    _instance = None
    _config_path = "config/plugin_preferences.json"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
        return cls._instance

    def __init__(self):
        if not self._loaded:
            self._blacklist_plugins: List[str] = []
            self._blacklist_patterns: List[str] = []
            self._whitelist_plugins: List[str] = []
            self._fallback_mappings: Dict[str, List[str]] = {}
            self._prefer_native: bool = True
            self._warn_on_unavailable: bool = True
            self._load_config()
            self._loaded = True

    def _load_config(self):
        """Load configuration from JSON file"""
        try:
            if os.path.exists(self._config_path):
                with open(self._config_path, 'r') as f:
                    config = json.load(f)

                blacklist = config.get("blacklist", {})
                self._blacklist_plugins = blacklist.get("plugins", [])
                self._blacklist_patterns = blacklist.get("patterns", [])

                whitelist = config.get("whitelist", {})
                self._whitelist_plugins = whitelist.get("plugins", [])

                fallback = config.get("fallback_mappings", {})
                self._fallback_mappings = fallback.get("mappings", {})

                self._prefer_native = config.get("prefer_native", {}).get("enabled", True)
                self._warn_on_unavailable = config.get("warn_on_unavailable", {}).get("enabled", True)

                print(f"[OK] Loaded plugin preferences: {len(self._blacklist_plugins)} blacklisted, "
                      f"{len(self._fallback_mappings)} fallback mappings")
        except Exception as e:
            print(f"[WARN] Could not load plugin preferences: {e}")

    def is_blacklisted(self, plugin_name: str) -> bool:
        """Check if a plugin is blacklisted"""
        if not plugin_name:
            return False

        # First check whitelist (overrides blacklist)
        for whitelist_name in self._whitelist_plugins:
            if whitelist_name.lower() in plugin_name.lower():
                return False

        # Check exact matches in blacklist
        plugin_lower = plugin_name.lower()
        for blacklist_name in self._blacklist_plugins:
            if blacklist_name.lower() in plugin_lower:
                return True

        # Check pattern matches
        for pattern in self._blacklist_patterns:
            # Convert glob pattern to check
            if fnmatch.fnmatch(plugin_name, pattern):
                return True
            # Also check lowercase
            if fnmatch.fnmatch(plugin_lower, pattern.lower()):
                return True

        return False

    def get_fallback(self, plugin_name: str) -> Optional[List[str]]:
        """Get fallback plugins for a blacklisted plugin"""
        if not plugin_name:
            return None

        plugin_lower = plugin_name.lower()

        for key, fallbacks in self._fallback_mappings.items():
            if key.lower() in plugin_lower:
                return fallbacks

        return None

    def should_prefer_native(self) -> bool:
        """Check if native plugins should be preferred"""
        return self._prefer_native

    def should_warn_unavailable(self) -> bool:
        """Check if we should warn about unavailable plugins"""
        return self._warn_on_unavailable

    def add_to_blacklist(self, plugin_name: str):
        """Add a plugin to the blacklist at runtime"""
        if plugin_name not in self._blacklist_plugins:
            self._blacklist_plugins.append(plugin_name)

    def remove_from_blacklist(self, plugin_name: str):
        """Remove a plugin from the blacklist at runtime"""
        if plugin_name in self._blacklist_plugins:
            self._blacklist_plugins.remove(plugin_name)


def get_plugin_preferences() -> PluginPreferences:
    """Get the global plugin preferences instance"""
    return PluginPreferences()


@dataclass
class PluginSlot:
    """Represents a slot in a plugin chain"""
    plugin_type: str  # eq, compressor, reverb, etc.
    purpose: str      # high_pass, dynamics, sibilance, etc.
    desired_plugin: Optional[str] = None  # Specific plugin name from research
    matched_plugin: Optional[PluginInfo] = None  # Matched available plugin
    settings: Dict = field(default_factory=dict)
    is_alternative: bool = False  # True if using fallback
    match_confidence: float = 0.0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "type": self.plugin_type,
            "purpose": self.purpose,
            "desired": self.desired_plugin,
            "matched": self.matched_plugin.name if self.matched_plugin else None,
            "settings": self.settings,
            "is_alternative": self.is_alternative,
            "confidence": self.match_confidence
        }


@dataclass
class PluginChain:
    """A complete plugin chain ready to be loaded"""
    name: str
    track_type: str  # vocal, drums, bass, master, etc.
    slots: List[PluginSlot] = field(default_factory=list)
    source: str = ""  # Where this chain came from
    confidence: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for storage"""
        return {
            "name": self.name,
            "track_type": self.track_type,
            "slots": [s.to_dict() for s in self.slots],
            "source": self.source,
            "confidence": self.confidence,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'PluginChain':
        """Create from dictionary"""
        chain = cls(
            name=data.get("name", ""),
            track_type=data.get("track_type", ""),
            source=data.get("source", ""),
            confidence=data.get("confidence", 0.0),
            created_at=data.get("created_at", datetime.now().isoformat())
        )
        # Note: slots would need matched_plugin resolved
        return chain


class PluginChainBuilder:
    """
    Builds plugin chains from research results and loads them into Ableton
    
    Responsibilities:
    - Parse research data to extract plugin chain structure
    - Match desired plugins to available VSTs (using VST Discovery)
    - Find alternatives when exact plugins aren't available
    - Generate device loading sequence with parameter settings
    - Handle chain creation via Remote Script
    - Verify chain was created successfully
    """
    
    def __init__(self, vst_discovery: Optional[VSTDiscoveryService] = None):
        """
        Initialize the Plugin Chain Builder

        Args:
            vst_discovery: Optional VST Discovery Service instance
        """
        self.vst_discovery = vst_discovery or get_vst_discovery()
        self.preferences = get_plugin_preferences()

        # Track warnings for unavailable/blacklisted plugins
        self._warnings: List[Dict[str, str]] = []

        # Plugin type to Ableton native device mapping
        # Include multiple key variations (eq, eq_eight, eq8, equalizer, etc.)
        self._native_fallbacks = {
            # EQ variations
            "eq": ["EQ Eight", "EQ Three", "Channel EQ"],
            "eq_eight": ["EQ Eight", "EQ Three", "Channel EQ"],
            "eq8": ["EQ Eight", "EQ Three", "Channel EQ"],
            "equalizer": ["EQ Eight", "EQ Three", "Channel EQ"],
            "eq_three": ["EQ Three", "EQ Eight"],
            # Compressor variations
            "compressor": ["Compressor", "Glue Compressor"],
            "comp": ["Compressor", "Glue Compressor"],
            "glue_compressor": ["Glue Compressor", "Compressor"],
            # Limiter
            "limiter": ["Limiter"],
            # Reverb variations
            "reverb": ["Reverb"],
            "verb": ["Reverb"],
            # Delay variations
            "delay": ["Delay", "Echo", "Simple Delay"],
            "echo": ["Echo", "Delay"],
            # Saturation/distortion variations
            "distortion": ["Saturator", "Pedal", "Overdrive"],
            "saturation": ["Saturator", "Pedal"],
            "saturator": ["Saturator", "Pedal", "Overdrive"],
            "drive": ["Saturator", "Overdrive"],
            "overdrive": ["Overdrive", "Saturator"],
            # De-esser
            "de-esser": ["Multiband Dynamics"],
            "deesser": ["Multiband Dynamics"],
            "de_esser": ["Multiband Dynamics"],
            # Dynamics
            "dynamics": ["Multiband Dynamics", "Gate"],
            "multiband": ["Multiband Dynamics"],
            "gate": ["Gate"],
            # Modulation
            "modulation": ["Chorus-Ensemble", "Phaser", "Flanger"],
            "chorus": ["Chorus-Ensemble"],
            "phaser": ["Phaser"],
            "flanger": ["Flanger"],
            # Utility
            "utility": ["Utility"],
            # Filter
            "filter": ["Auto Filter"],
            "auto_filter": ["Auto Filter"],
            # Spectrum/analysis
            "spectrum": ["Spectrum"],
            "tuner": ["Tuner"],
        }
        
        # Common plugin aliases for matching
        self._plugin_aliases = {
            "fabfilter pro-q": ["FabFilter Pro-Q 3", "FabFilter Pro-Q 2", "Pro-Q"],
            "fabfilter pro-c": ["FabFilter Pro-C 2", "FabFilter Pro-C", "Pro-C"],
            "fabfilter pro-r": ["FabFilter Pro-R", "Pro-R"],
            "ssl channel": ["SSL E-Channel", "SSL G-Channel", "Waves SSL"],
            "1176": ["CLA-76", "1176", "UAD 1176"],
            "la-2a": ["CLA-2A", "LA-2A", "UAD LA-2A"],
            "pultec": ["PuigTec EQP-1A", "Pultec", "UAD Pultec"],
            "pro tools eq": ["EQ Eight"],  # Fallback
            "logic eq": ["EQ Eight"],  # Fallback
        }
    
    # ==================== CHAIN BUILDING ====================
    
    def build_chain_from_research(self, 
                                   research_result: Dict,
                                   chain_name: Optional[str] = None) -> PluginChain:
        """
        Build a plugin chain from research results
        
        Args:
            research_result: Result from ResearchAgent's _research_plugin_chain
            chain_name: Optional name for the chain
            
        Returns:
            PluginChain ready to be loaded
        """
        artist_or_style = research_result.get("artist_or_style", "unknown")
        track_type = research_result.get("track_type", "vocal")
        raw_chain = research_result.get("chain", [])
        
        print(f"[CHAIN] Building chain for {artist_or_style} ({len(raw_chain)} plugins)")

        if not chain_name:
            chain_name = f"{artist_or_style}_{track_type}_chain"
        
        chain = PluginChain(
            name=chain_name,
            track_type=track_type,
            source=artist_or_style,
            confidence=research_result.get("confidence", 0.5)
        )
        
        # Process each plugin in the research chain
        for plugin_data in raw_chain:
            slot = self._create_plugin_slot(plugin_data)
            chain.slots.append(slot)
        
        # Calculate overall confidence
        if chain.slots:
            avg_confidence = sum(s.match_confidence for s in chain.slots) / len(chain.slots)
            chain.confidence = avg_confidence
        
        return chain
    
    def _create_plugin_slot(self, plugin_data: Dict) -> PluginSlot:
        """
        Create a PluginSlot from research data and match to available plugins
        
        Args:
            plugin_data: Dict with type, purpose, settings, etc.
            
        Returns:
            PluginSlot with matched plugin
        """
        plugin_type = plugin_data.get("type", "")
        purpose = plugin_data.get("purpose", "")
        desired_name = plugin_data.get("plugin_name", plugin_data.get("name", ""))
        settings = plugin_data.get("settings", {})
        
        slot = PluginSlot(
            plugin_type=plugin_type,
            purpose=purpose,
            desired_plugin=desired_name if desired_name else None,
            settings=settings
        )
        
        # Try to match to available plugin
        matched, is_alternative, confidence = self._match_plugin(
            desired_name=desired_name,
            plugin_type=plugin_type
        )
        
        slot.matched_plugin = matched
        slot.is_alternative = is_alternative
        slot.match_confidence = confidence
        
        return slot
    
    def _match_plugin(self,
                      desired_name: Optional[str],
                      plugin_type: str) -> Tuple[Optional[PluginInfo], bool, float]:
        """
        Match a desired plugin to an available one.

        Enhanced with tiered resolution strategy:
        1. Blacklist check (priority - reject if blacklisted)
        2. Tiered name resolution (exact, alias, fuzzy)
        3. Category-based search
        4. Native device fallback

        Args:
            desired_name: Name of desired plugin (may be None)
            plugin_type: Type/category of plugin

        Returns:
            Tuple of (matched_plugin, is_alternative, confidence)
        """
        # If we have a specific plugin name, try to find it
        if desired_name:
            # CHECK BLACKLIST FIRST (before any resolution)
            if self.preferences.is_blacklisted(desired_name):
                print(f"[CHAIN] Plugin blacklisted: {desired_name}")
                if self.preferences.should_warn_unavailable():
                    self._warnings.append({
                        "plugin": desired_name,
                        "reason": "blacklisted",
                        "message": f"Plugin '{desired_name}' is blacklisted. Using native fallback."
                    })
                    print(f"[WARN] Plugin '{desired_name}' is blacklisted - using fallback")

                # Try to get configured fallback
                fallback_plugins = self.preferences.get_fallback(desired_name)
                if fallback_plugins:
                    for fallback_name in fallback_plugins:
                        plugin = self.vst_discovery.find_plugin(fallback_name)
                        if plugin:
                            return (plugin, True, 0.7)  # Configured fallback
                        # Try as native device
                        return (PluginInfo(
                            name=fallback_name,
                            plugin_type="audio_effect",
                            category=plugin_type,
                            path=f"Audio Effects/{fallback_name}"
                        ), True, 0.6)

                # Use native fallback based on plugin type
                native_fallback = self._get_native_fallback(plugin_type)
                if native_fallback:
                    return (PluginInfo(
                        name=native_fallback,
                        plugin_type="audio_effect",
                        category=plugin_type,
                        path=f"Audio Effects/{native_fallback}"
                    ), True, 0.5)

            # ==================== TIERED RESOLUTION ====================
            # Use the new PluginNameResolver for better matching
            if _HAS_RESOLVER:
                resolver = get_plugin_resolver()
                result = resolver.resolve(desired_name)

                if result.resolved_name and result.confidence >= 0.5:
                    # Check if resolved name is blacklisted
                    if not self.preferences.is_blacklisted(result.resolved_name):
                        # Find the PluginInfo for the resolved name
                        plugin = self._get_plugin_info_by_name(result.resolved_name, plugin_type)
                        if plugin:
                            print(f"[CHAIN] Resolved via {result.resolution_tier}: {desired_name} -> {result.resolved_name} (conf: {result.confidence:.2f})")
                            is_alternative = (result.resolution_tier != "exact" and
                                            result.resolved_name.lower() != desired_name.lower())
                            return (plugin, is_alternative, result.confidence)

                # If resolver returned alternatives, try them
                if result.alternatives:
                    for alt_name in result.alternatives:
                        if not self.preferences.is_blacklisted(alt_name):
                            plugin = self._get_plugin_info_by_name(alt_name, plugin_type)
                            if plugin:
                                print(f"[CHAIN] Using alternative: {desired_name} -> {alt_name}")
                                return (plugin, True, 0.6)

            # ==================== LEGACY FALLBACK ====================
            # Fall back to original alias checking if resolver didn't find a match
            alias_names = self._get_plugin_aliases(desired_name)

            for name in [desired_name] + alias_names:
                # Skip if this alias is also blacklisted
                if self.preferences.is_blacklisted(name):
                    continue

                plugin = self.vst_discovery.find_plugin(name)
                if plugin and plugin.matches_query(name) > 0.7:
                    # Double-check the matched plugin isn't blacklisted
                    if not self.preferences.is_blacklisted(plugin.name):
                        print(f"[CHAIN] Matched plugin (legacy): {desired_name} -> {plugin.name}")
                        return (plugin, False, plugin.matches_query(name))

        # If prefer_native is enabled and we have a native option, use it
        if self.preferences.should_prefer_native():
            native_fallback = self._get_native_fallback(plugin_type)
            if native_fallback:
                return (PluginInfo(
                    name=native_fallback,
                    plugin_type="audio_effect",
                    category=plugin_type,
                    path=f"Audio Effects/{native_fallback}"
                ), True, 0.5)

        # Try to find a plugin in the same category (check blacklist)
        category_plugins = self.vst_discovery.get_plugins_by_category(plugin_type)
        if category_plugins:
            for plugin in category_plugins:
                if not self.preferences.is_blacklisted(plugin.name):
                    return (plugin, True, 0.6)

        # Fall back to Ableton native devices
        native_fallback = self._get_native_fallback(plugin_type)
        if native_fallback:
            plugin = self.vst_discovery.find_plugin(native_fallback)
            if plugin:
                return (plugin, True, 0.5)

            # Create a synthetic PluginInfo for native device
            return (PluginInfo(
                name=native_fallback,
                plugin_type="audio_effect",
                category=plugin_type,
                path=f"Audio Effects/{native_fallback}"
            ), True, 0.5)

        return (None, False, 0.0)
    
    def _get_plugin_aliases(self, plugin_name: str) -> List[str]:
        """Get known aliases for a plugin name"""
        name_lower = plugin_name.lower()
        
        for key, aliases in self._plugin_aliases.items():
            if key in name_lower or any(a.lower() in name_lower for a in aliases):
                return aliases
        
        return []
    
    def _get_native_fallback(self, plugin_type: str) -> Optional[str]:
        """Get the Ableton native fallback for a plugin type"""
        fallbacks = self._native_fallbacks.get(plugin_type.lower(), [])
        return fallbacks[0] if fallbacks else None

    def _get_plugin_info_by_name(self, name: str, category: str) -> Optional[PluginInfo]:
        """
        Get a PluginInfo object for a resolved plugin name.

        Args:
            name: The exact plugin name
            category: The plugin category/type

        Returns:
            PluginInfo if found in VST discovery, or synthetic PluginInfo for native devices
        """
        # First try to find in VST discovery
        all_plugins = self.vst_discovery.get_all_plugins()
        for plugin in all_plugins:
            if plugin.name == name:
                return plugin

        # Try case-insensitive match
        name_lower = name.lower()
        for plugin in all_plugins:
            if plugin.name.lower() == name_lower:
                return plugin

        # Create synthetic PluginInfo for native/unknown devices
        return PluginInfo(
            name=name,
            plugin_type="audio_effect",
            category=category,
            path=f"Audio Effects/{name}"
        )

    def _validate_track_type_for_chain(self, track_index: int, chain: PluginChain) -> Dict[str, Any]:
        """
        Validate that track type is compatible with plugin chain.

        Args:
            track_index: Track to load on
            chain: Plugin chain to validate

        Returns:
            Dict with:
            - compatible: bool
            - message: str
            - expected_type: str (what track type is needed)
            - actual_type: str (what track type it is)
        """
        result = {
            "compatible": True,
            "message": "",
            "expected_type": "audio",
            "actual_type": "unknown"
        }

        # Determine what track type this chain needs
        # Audio effects chain needs audio track
        # MIDI effects chain needs MIDI track
        chain_needs_audio_track = False
        chain_needs_midi_track = False

        for slot in chain.slots:
            if not slot.matched_plugin:
                continue

            plugin_type = slot.matched_plugin.plugin_type.lower()

            if plugin_type in ["audio_effect", "audio_effects"]:
                chain_needs_audio_track = True
            elif plugin_type in ["midi_effect", "midi_effects", "instrument"]:
                chain_needs_midi_track = True

        # Query actual track type using JarvisDeviceLoader
        try:
            # Use the new OSC endpoint
            response = self.vst_discovery._send_osc_request(
                "/jarvis/track/type",
                [track_index],
                timeout=3.0
            )

            if response:
                _addr, args = response
                # Format: [success, track_type, has_audio_input, has_midi_input, can_audio_fx, can_midi_fx]
                if len(args) >= 6 and args[0] == 1:
                    actual_track_type = args[1]
                    can_audio_fx = args[4]
                    can_midi_fx = args[5]

                    result["actual_type"] = actual_track_type

                    # Check compatibility
                    if chain_needs_audio_track and not can_audio_fx:
                        result["compatible"] = False
                        result["expected_type"] = "audio"
                        result["message"] = (
                            f"Cannot load audio effects chain on {actual_track_type} track (track {track_index + 1}). "
                            f"This chain requires an Audio track. "
                            f"Please select an Audio track or create a new Audio track."
                        )
                        return result

                    if chain_needs_midi_track and not can_midi_fx:
                        result["compatible"] = False
                        result["expected_type"] = "midi"
                        result["message"] = (
                            f"Cannot load MIDI effects chain on {actual_track_type} track (track {track_index + 1}). "
                            f"This chain requires a MIDI track. "
                            f"Please select a MIDI track or create a new MIDI track."
                        )
                        return result

                    # Compatible
                    result["message"] = f"Track type {actual_track_type} is compatible with chain"
                    return result

            # If query failed, warn but allow (backward compatibility)
            print(f"[ChainBuilder] Warning: Could not verify track type for track {track_index}")
            result["message"] = "Track type validation unavailable (proceeding anyway)"
            return result

        except Exception as e:
            print(f"[ChainBuilder] Warning: Track type validation failed: {e}")
            result["message"] = f"Track type validation failed: {e} (proceeding anyway)"
            return result

    # ==================== CHAIN LOADING ====================
    
    async def load_chain_on_track(self,
                                   chain: PluginChain,
                                   track_index: int,
                                   clear_existing: bool = False,
                                   apply_parameters: bool = False) -> Dict[str, Any]:
        """
        Load a plugin chain onto a track in Ableton

        Args:
            chain: The PluginChain to load
            track_index: 0-based track index
            clear_existing: Whether to clear existing devices first
            apply_parameters: If True, apply slot.settings as device parameters
                after loading each device (uses ResearchBot normalization)

        Returns:
            Result dict with success status and details
        """
        print(f"[CHAIN] Loading chain '{chain.name}' onto track {track_index + 1}")
        
        results = {
            "success": True,
            "track_index": track_index,
            "chain_name": chain.name,
            "plugins_loaded": [],
            "plugins_failed": [],
            "message": ""
        }

        # Pre-flight check: Verify JarvisDeviceLoader is healthy
        health = self.vst_discovery._check_connection_health(timeout=3.0)
        if not health["healthy"]:
            results["success"] = False
            results["message"] = f"JarvisDeviceLoader not responding: {health['error']}"
            print(f"[ChainBuilder] Pre-flight check failed: {health}")
            return results

        print(f"[ChainBuilder] JarvisDeviceLoader healthy (response time: {health['response_time_ms']:.0f}ms)")

        # STEP 1: Validate track type BEFORE loading
        track_type_result = self._validate_track_type_for_chain(track_index, chain)
        if not track_type_result["compatible"]:
            results["success"] = False
            results["message"] = track_type_result["message"]
            results["track_type_mismatch"] = True
            results["expected_type"] = track_type_result["expected_type"]
            results["actual_type"] = track_type_result["actual_type"]
            return results

        print(f"[ChainBuilder] Track type validation passed: {track_type_result['message']}")

        # Load each plugin in order
        for i, slot in enumerate(chain.slots):
            if not slot.matched_plugin:
                results["plugins_failed"].append({
                    "index": i,
                    "type": slot.plugin_type,
                    "reason": "No matching plugin found"
                })
                continue
            
            try:
                # Load the device
                load_result = self.vst_discovery.load_device_on_track(
                    track_index=track_index,
                    device_name=slot.matched_plugin.name,
                    position=-1  # Add at end
                )
                
                print(f"[CHAIN] Loaded device: {slot.matched_plugin.name} (Success: {load_result.get('success')})")
                
                if load_result.get("success"):
                    loaded_info = {
                        "index": i,
                        "name": slot.matched_plugin.name,
                        "type": slot.plugin_type,
                        "is_alternative": slot.is_alternative,
                    }

                    # Optionally apply parameter settings after loading
                    if apply_parameters and slot.settings:
                        try:
                            from research_bot import get_research_bot
                            bot = get_research_bot()
                            # The device was just loaded at the end of the chain
                            from ableton_controls.controller import ableton
                            num_devices_result = ableton.get_num_devices(track_index)
                            dev_idx = (num_devices_result.get("count", i + 1) - 1
                                       if num_devices_result.get("success") else i)
                            apply_result = bot.apply_parameters(
                                track_index, dev_idx,
                                slot.matched_plugin.name, slot.settings
                            )
                            loaded_info["params_applied"] = len(apply_result.get("applied", []))
                            loaded_info["params_failed"] = len(apply_result.get("failed", []))
                            print(f"[CHAIN] Applied {loaded_info['params_applied']} params to {slot.matched_plugin.name}")
                        except Exception as param_err:
                            print(f"[CHAIN] Warning: Could not apply params to {slot.matched_plugin.name}: {param_err}")
                            loaded_info["params_error"] = str(param_err)

                    results["plugins_loaded"].append(loaded_info)
                else:
                    results["plugins_failed"].append({
                        "index": i,
                        "name": slot.matched_plugin.name,
                        "type": slot.plugin_type,
                        "reason": load_result.get("message", "Unknown error")
                    })
                    
                # Small delay between device loads
                await asyncio.sleep(0.5)
                
            except Exception as e:
                results["plugins_failed"].append({
                    "index": i,
                    "name": slot.matched_plugin.name if slot.matched_plugin else "unknown",
                    "type": slot.plugin_type,
                    "reason": str(e)
                })
        
        # Set overall success
        if results["plugins_failed"]:
            if results["plugins_loaded"]:
                results["success"] = True
                results["message"] = f"Partial success: {len(results['plugins_loaded'])} loaded, {len(results['plugins_failed'])} failed"
            else:
                results["success"] = False
                results["message"] = "Failed to load any plugins"
        else:
            results["message"] = f"Successfully loaded {len(results['plugins_loaded'])} plugins"
        
        return results
    
    # ==================== CHAIN TEMPLATES ====================
    
    def get_preset_chain(self, 
                         preset_name: str,
                         track_type: str = "vocal") -> PluginChain:
        """
        Get a preset plugin chain
        
        Args:
            preset_name: Name of preset (e.g., "basic", "full", "minimal")
            track_type: Type of track
            
        Returns:
            PluginChain with matched plugins
        """
        presets = {
            "vocal_basic": [
                {"type": "eq", "purpose": "high_pass"},
                {"type": "compressor", "purpose": "dynamics"},
                {"type": "reverb", "purpose": "space"},
            ],
            "vocal_full": [
                {"type": "eq", "purpose": "high_pass"},
                {"type": "compressor", "purpose": "dynamics"},
                {"type": "de-esser", "purpose": "sibilance"},
                {"type": "saturation", "purpose": "warmth"},
                {"type": "eq", "purpose": "tone"},
                {"type": "reverb", "purpose": "space"},
                {"type": "delay", "purpose": "depth"},
            ],
            "drum_bus": [
                {"type": "eq", "purpose": "shape"},
                {"type": "compressor", "purpose": "glue"},
                {"type": "saturation", "purpose": "punch"},
                {"type": "limiter", "purpose": "control"},
            ],
            "bass": [
                {"type": "eq", "purpose": "low_control"},
                {"type": "compressor", "purpose": "consistency"},
                {"type": "saturation", "purpose": "harmonics"},
            ],
            "master": [
                {"type": "eq", "purpose": "balance"},
                {"type": "compressor", "purpose": "glue"},
                {"type": "limiter", "purpose": "loudness"},
            ],
        }
        
        preset_key = f"{track_type}_{preset_name}" if preset_name != track_type else preset_name
        if preset_key not in presets:
            # Try just the track type
            for key in presets:
                if key.startswith(track_type):
                    preset_key = key
                    break
        
        if preset_key not in presets:
            preset_key = "vocal_basic"
        
        research_result = {
            "artist_or_style": f"preset_{preset_name}",
            "track_type": track_type,
            "chain": presets.get(preset_key, presets["vocal_basic"]),
            "confidence": 0.9
        }
        
        return self.build_chain_from_research(research_result, f"{preset_name}_{track_type}")
    
    # ==================== CHAIN VALIDATION ====================

    def get_warnings(self) -> List[Dict[str, str]]:
        """Get accumulated warnings from plugin matching"""
        return self._warnings.copy()

    def clear_warnings(self):
        """Clear accumulated warnings"""
        self._warnings.clear()

    def validate_chain(self, chain: PluginChain) -> Dict[str, Any]:
        """
        Validate a plugin chain before loading

        Args:
            chain: The PluginChain to validate

        Returns:
            Validation result with issues
        """
        issues = []
        warnings = []

        # Add accumulated blacklist warnings
        warnings.extend(self._warnings)

        for i, slot in enumerate(chain.slots):
            if not slot.matched_plugin:
                issues.append({
                    "slot": i,
                    "type": slot.plugin_type,
                    "issue": "No matching plugin found"
                })
            elif slot.is_alternative:
                warnings.append({
                    "slot": i,
                    "type": slot.plugin_type,
                    "warning": f"Using alternative: {slot.matched_plugin.name}"
                })
            elif slot.match_confidence < 0.5:
                warnings.append({
                    "slot": i,
                    "type": slot.plugin_type,
                    "warning": f"Low confidence match: {slot.matched_plugin.name}"
                })

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "confidence": chain.confidence,
            "blacklisted_plugins": [w for w in self._warnings if w.get("reason") == "blacklisted"]
        }
    
    # ==================== STORAGE ====================
    
    def save_chain(self, chain: PluginChain, filepath: str):
        """Save a plugin chain to JSON file"""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(chain.to_dict(), f, indent=2)
    
    def load_chain_from_file(self, filepath: str) -> Optional[PluginChain]:
        """Load a plugin chain from JSON file"""
        if not os.path.exists(filepath):
            return None
        
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        return PluginChain.from_dict(data)


# Convenience function for direct use
async def create_plugin_chain(
    artist_or_style: str,
    track_type: str,
    track_index: int
) -> Dict[str, Any]:
    """
    High-level function to research and create a plugin chain
    
    Args:
        artist_or_style: Artist name or style
        track_type: Type of track (vocal, drums, etc.)
        track_index: 0-based track index
        
    Returns:
        Result dict with chain details and load status
    """
    from agents.research_agent import research_plugin_chain
    
    # Research the chain
    research_result = await research_plugin_chain(artist_or_style, track_type)
    
    # Build the chain
    builder = PluginChainBuilder()
    chain = builder.build_chain_from_research(research_result)
    
    # Validate
    validation = builder.validate_chain(chain)
    if not validation["valid"]:
        return {
            "success": False,
            "message": "Chain validation failed",
            "issues": validation["issues"],
            "chain": chain.to_dict()
        }
    
    # Load onto track
    result = await builder.load_chain_on_track(chain, track_index)
    result["chain"] = chain.to_dict()
    result["validation"] = validation
    
    return result

