"""
Device Intelligence Service

Provides semantic understanding of device parameters, suggests settings based on
audio engineering best practices, and explains adjustments in context.

Supports dynamic parameter discovery from actual Ableton devices for handling
unknown or third-party plugins.
"""

from typing import Dict, Any, List, Optional, Tuple
from knowledge.device_kb import get_device_kb, DeviceKnowledgeBase, DeviceInfo, ParameterInfo
import time


class DeviceIntelligence:
    """
    Intelligence layer for device parameters.
    
    Provides:
    - Semantic understanding of what each parameter does
    - Suggested settings based on purpose and track type
    - Explanation of why/when to make adjustments
    - Context-aware recommendations
    """
    
    def __init__(self, device_kb: Optional[DeviceKnowledgeBase] = None):
        self.kb = device_kb or get_device_kb()
        
        # Purpose to preset mappings for common intents
        self._intent_mappings = {
            # EQ intents
            "high_pass": {"device": "EQ Eight", "preset": "high_pass_vocal"},
            "remove_rumble": {"device": "EQ Eight", "preset": "high_pass_vocal"},
            "cut_mud": {"device": "EQ Eight", "preset": "cut_mud"},
            "remove_mud": {"device": "EQ Eight", "preset": "cut_mud"},
            "muddy": {"device": "EQ Eight", "preset": "cut_mud"},
            "presence": {"device": "EQ Eight", "preset": "presence_boost"},
            "cut_through": {"device": "EQ Eight", "preset": "presence_boost"},
            "air": {"device": "EQ Eight", "preset": "air_boost"},
            "sparkle": {"device": "EQ Eight", "preset": "air_boost"},
            "bright": {"device": "EQ Eight", "preset": "air_boost"},
            "brighter": {"device": "EQ Eight", "preset": "air_boost"},
            "harsh": {"device": "EQ Eight", "preset": "de_harsh"},
            "harshness": {"device": "EQ Eight", "preset": "de_harsh"},
            "sibilance": {"device": "EQ Eight", "preset": "de_sibilance"},
            "sibilant": {"device": "EQ Eight", "preset": "de_sibilance"},
            
            # Compression intents
            "vocal_compression": {"device": "Compressor", "preset": "vocal_control"},
            "control_dynamics": {"device": "Compressor", "preset": "vocal_control"},
            "punch": {"device": "Compressor", "preset": "drum_punch"},
            "punchy": {"device": "Compressor", "preset": "drum_punch"},
            "smash": {"device": "Compressor", "preset": "drum_smash"},
            "crush": {"device": "Compressor", "preset": "parallel_crush"},
            "glue": {"device": "Glue Compressor", "preset": "drum_bus"},
            "bus_compression": {"device": "Glue Compressor", "preset": "drum_bus"},
            
            # Reverb intents
            "plate_reverb": {"device": "Reverb", "preset": "vocal_plate"},
            "room": {"device": "Reverb", "preset": "drum_room"},
            "dark_reverb": {"device": "Reverb", "preset": "dark_hall"},
            "atmosphere": {"device": "Reverb", "preset": "dark_hall"},
            "atmospheric": {"device": "Reverb", "preset": "dark_hall"},
            "ambient": {"device": "Reverb", "preset": "short_ambience"},
            
            # Saturation intents
            "warm": {"device": "Saturator", "preset": "subtle_warmth"},
            "warmth": {"device": "Saturator", "preset": "subtle_warmth"},
            "warmer": {"device": "Saturator", "preset": "subtle_warmth"},
            "tape": {"device": "Saturator", "preset": "tape_saturation"},
            "drive": {"device": "Saturator", "preset": "aggressive_drive"},
            
            # Delay intents
            "slap": {"device": "Delay", "preset": "vocal_slap"},
            "slap_delay": {"device": "Delay", "preset": "vocal_slap"},
            "echo": {"device": "Delay", "preset": "quarter_note"},
            "ping_pong": {"device": "Delay", "preset": "ping_pong_wide"},
            "wide_delay": {"device": "Delay", "preset": "ping_pong_wide"},
            
            # Utility intents
            "widen": {"device": "Utility", "preset": "stereo_widen"},
            "wider": {"device": "Utility", "preset": "stereo_widen"},
            "stereo": {"device": "Utility", "preset": "stereo_widen"},
            "mono_check": {"device": "Utility", "preset": "mono_check"},
            
            # Limiter intents
            "limit": {"device": "Limiter", "preset": "master_streaming"},
            "loudness": {"device": "Limiter", "preset": "master_streaming"},
            "louder": {"device": "Limiter", "preset": "master_loud"},
            
            # De-esser intents
            "de_ess": {"device": "Multiband Dynamics", "preset": "de_esser"},
            "deess": {"device": "Multiband Dynamics", "preset": "de_esser"},
            "de-ess": {"device": "Multiband Dynamics", "preset": "de_esser"},
        }
        
        # Track type specific adjustments
        self._track_type_adjustments = {
            "vocal": {
                "high_pass_freq": 100,
                "compression_ratio": 4,
                "compression_attack": 15,
                "reverb_wet": 25,
            },
            "drums": {
                "high_pass_freq": 30,
                "compression_ratio": 4,
                "compression_attack": 30,  # Slower for punch
                "reverb_wet": 15,
            },
            "bass": {
                "high_pass_freq": 30,
                "compression_ratio": 4,
                "compression_attack": 10,
                "reverb_wet": 0,  # Usually no reverb on bass
            },
            "guitar": {
                "high_pass_freq": 80,
                "compression_ratio": 3,
                "compression_attack": 20,
                "reverb_wet": 20,
            },
            "synth": {
                "high_pass_freq": 40,
                "compression_ratio": 2,
                "compression_attack": 20,
                "reverb_wet": 30,
            },
            "master": {
                "high_pass_freq": 20,
                "compression_ratio": 2,
                "compression_attack": 30,
                "limiter_ceiling": -1.0,
            }
        }
    
    # ==================== PARAMETER INFO ====================
    
    def get_param_info(self, device_name: str, param_index: int) -> Optional[Dict[str, Any]]:
        """
        Get semantic information about a device parameter.
        
        Args:
            device_name: Name of the device
            param_index: Parameter index
            
        Returns:
            Dict with name, purpose, range, and audio engineering context
        """
        param = self.kb.get_parameter(device_name, param_index)
        if not param:
            return None
        
        device = self.kb.get_device(device_name)
        
        return {
            "device": device.name if device else device_name,
            "index": param.index,
            "name": param.name,
            "purpose": param.purpose,
            "range": param.display_range or f"{param.min_value} to {param.max_value}",
            "unit": param.unit,
            "default": param.default_value,
            "tips": device.tips if device else []
        }
    
    def explain_parameter(self, device_name: str, param_index: int) -> str:
        """
        Get a human-readable explanation of a parameter.
        
        Args:
            device_name: Name of the device
            param_index: Parameter index
            
        Returns:
            Human-readable explanation string
        """
        info = self.get_param_info(device_name, param_index)
        if not info:
            return f"Unknown parameter {param_index} on device {device_name}"
        
        explanation = f"{info['name']} ({info['device']}): {info['purpose']}"
        if info['range']:
            explanation += f". Range: {info['range']}"
        if info['unit']:
            explanation += f" ({info['unit']})"
        
        return explanation
    
    # ==================== SUGGEST SETTINGS ====================
    
    def suggest_settings(self, 
                        device_name: str, 
                        purpose: str,
                        track_type: str = "vocal") -> Dict[str, Any]:
        """
        Suggest parameter settings for a specific purpose.
        
        Args:
            device_name: Name of the device
            purpose: What you're trying to achieve (e.g., "high_pass", "punch", "warm")
            track_type: Type of track (vocal, drums, bass, etc.)
            
        Returns:
            Dict with suggested settings and explanation
        """
        device = self.kb.get_device(device_name)
        if not device:
            return {
                "success": False,
                "message": f"Unknown device: {device_name}",
                "settings": {}
            }
        
        # Try to find matching preset
        purpose_lower = purpose.lower().replace(" ", "_")
        
        # Check device presets first
        preset = None
        for preset_name, preset_data in device.presets.items():
            if purpose_lower in preset_name.lower():
                preset = preset_data
                break
        
        if preset:
            # Apply track type adjustments
            settings = preset.get("settings", {}).copy()
            adjusted = self._apply_track_type_adjustments(device_name, settings, track_type)
            
            return {
                "success": True,
                "device": device.name,
                "purpose": purpose,
                "description": preset.get("description", ""),
                "settings": adjusted,
                "track_type": track_type
            }
        
        # If no preset, return basic info
        return {
            "success": False,
            "message": f"No preset found for purpose '{purpose}' on {device.name}",
            "available_presets": list(device.presets.keys())
        }
    
    def suggest_for_intent(self, 
                          intent: str,
                          track_type: str = "vocal") -> Dict[str, Any]:
        """
        Suggest device and settings based on a user intent.
        
        Args:
            intent: User intent like "make it warmer", "remove mud", "add punch"
            track_type: Type of track
            
        Returns:
            Dict with suggested device, settings, and explanation
        """
        intent_lower = intent.lower()
        
        # Find matching intent
        matched_intent = None
        for key in self._intent_mappings:
            if key in intent_lower:
                matched_intent = self._intent_mappings[key]
                break
        
        if not matched_intent:
            # Try to infer from keywords
            suggestions = self._infer_intent(intent_lower)
            if suggestions:
                return suggestions
            
            return {
                "success": False,
                "message": f"Could not understand intent: {intent}",
                "suggestion": "Try being more specific, like 'remove mud', 'add warmth', 'make it brighter'"
            }
        
        # Get the preset
        device = self.kb.get_device(matched_intent["device"])
        preset = device.presets.get(matched_intent["preset"]) if device else None
        
        if not device or not preset:
            return {
                "success": False,
                "message": f"Could not find suggested preset"
            }
        
        # Apply track type adjustments
        settings = preset.get("settings", {}).copy()
        adjusted = self._apply_track_type_adjustments(device.name, settings, track_type)
        
        return {
            "success": True,
            "device": device.name,
            "preset": matched_intent["preset"],
            "description": preset.get("description", ""),
            "settings": adjusted,
            "track_type": track_type,
            "explanation": self._generate_explanation(device.name, matched_intent["preset"], intent)
        }
    
    def _infer_intent(self, intent: str) -> Optional[Dict]:
        """Try to infer intent from keywords"""
        # Check for EQ-related keywords
        eq_keywords = ["eq", "frequency", "boost", "cut", "filter", "low", "high", "mid"]
        if any(kw in intent for kw in eq_keywords):
            if "low" in intent and "cut" in intent:
                return self.suggest_settings("EQ Eight", "high_pass")
            elif "mid" in intent and "cut" in intent:
                return self.suggest_settings("EQ Eight", "cut_mud")
            elif "high" in intent and "boost" in intent:
                return self.suggest_settings("EQ Eight", "air")
        
        # Check for compression keywords
        comp_keywords = ["compress", "dynamics", "level", "consistent"]
        if any(kw in intent for kw in comp_keywords):
            if "heavy" in intent or "aggressive" in intent:
                return self.suggest_settings("Compressor", "vocal_aggressive")
            else:
                return self.suggest_settings("Compressor", "vocal_control")
        
        # Check for space/reverb keywords
        space_keywords = ["reverb", "space", "room", "hall", "depth"]
        if any(kw in intent for kw in space_keywords):
            if "big" in intent or "large" in intent or "hall" in intent:
                return self.suggest_settings("Reverb", "dark_hall")
            elif "small" in intent or "tight" in intent or "room" in intent:
                return self.suggest_settings("Reverb", "drum_room")
            else:
                return self.suggest_settings("Reverb", "vocal_plate")
        
        return None
    
    def _apply_track_type_adjustments(self, 
                                      device_name: str, 
                                      settings: Dict,
                                      track_type: str) -> Dict:
        """Apply track-type specific adjustments to settings"""
        if track_type not in self._track_type_adjustments:
            return settings
        
        adjustments = self._track_type_adjustments[track_type]
        adjusted = settings.copy()
        
        device_lower = device_name.lower()
        
        # Apply EQ adjustments
        if "eq" in device_lower:
            if "high_pass_freq" in adjustments:
                # Adjust band 1 frequency if it's a high-pass setting
                if 1 in adjusted:  # Band 1 Frequency
                    adjusted[1] = adjustments["high_pass_freq"]
        
        # Apply compression adjustments
        if "compressor" in device_lower:
            if "compression_ratio" in adjustments and 2 in adjusted:
                adjusted[2] = adjustments["compression_ratio"]
            if "compression_attack" in adjustments and 3 in adjusted:
                adjusted[3] = adjustments["compression_attack"]
        
        # Apply reverb adjustments
        if "reverb" in device_lower:
            if "reverb_wet" in adjustments and 6 in adjusted:
                adjusted[6] = adjustments["reverb_wet"]
        
        return adjusted
    
    def _generate_explanation(self, device_name: str, preset: str, intent: str) -> str:
        """Generate a human-readable explanation for the suggestion"""
        explanations = {
            # EQ explanations
            "high_pass_vocal": "Adding a high-pass filter to remove low-end rumble and proximity effect",
            "cut_mud": "Cutting around 300Hz to remove muddy low-mid buildup",
            "presence_boost": "Boosting presence frequencies (2-5kHz) to help the sound cut through the mix",
            "air_boost": "Adding a high-shelf boost for air and sparkle",
            "de_harsh": "Cutting harshness in the 2-4kHz range for a smoother sound",
            "de_sibilance": "Reducing sibilance (harsh 's' sounds) in the 6-8kHz range",
            
            # Compression explanations
            "vocal_control": "Applying gentle compression to control vocal dynamics",
            "vocal_aggressive": "Using heavier compression for a more upfront vocal sound",
            "drum_punch": "Setting slow attack to preserve drum transients for punch",
            "drum_smash": "Heavy compression for aggressive parallel drum processing",
            "parallel_crush": "Crushing the signal for parallel blending",
            "glue": "Gentle bus compression to glue elements together",
            
            # Reverb explanations
            "vocal_plate": "Adding classic plate reverb for vocals",
            "drum_room": "Adding tight room reverb for drums",
            "dark_hall": "Using a dark, atmospheric hall reverb (Billie Eilish style)",
            "short_ambience": "Adding subtle ambient reverb for space",
            
            # Saturation explanations
            "subtle_warmth": "Adding subtle analog warmth through saturation",
            "tape_saturation": "Applying tape-style saturation for vintage character",
            "aggressive_drive": "Adding more aggressive saturation for color",
            
            # Delay explanations
            "vocal_slap": "Adding a short slap delay for depth",
            "quarter_note": "Setting up a rhythmic quarter-note delay",
            "ping_pong_wide": "Creating stereo width with ping-pong delay",
            "atmospheric": "Adding dark, filtered delay for atmosphere",
            
            # Utility explanations
            "stereo_widen": "Widening the stereo image",
            "mono_check": "Switching to mono to check compatibility",
            
            # Limiter explanations
            "master_streaming": "Setting up mastering limiter for streaming (-14 LUFS target)",
            "master_loud": "Configuring limiter for louder output",
            
            # De-esser explanations
            "de_esser": "Configuring multiband dynamics as a de-esser",
        }
        
        return explanations.get(preset, f"Applying {preset} settings on {device_name}")
    
    # ==================== EXPLAIN ADJUSTMENTS ====================
    
    def explain_adjustment(self, 
                          device_name: str, 
                          param_index: int, 
                          value: float,
                          track_type: str = "vocal") -> str:
        """
        Explain an adjustment in audio engineering terms.
        
        Args:
            device_name: Name of the device
            param_index: Parameter index being adjusted
            value: New value being set
            track_type: Type of track
            
        Returns:
            Human-readable explanation of the adjustment
        """
        param = self.kb.get_parameter(device_name, param_index)
        if not param:
            return f"Setting parameter {param_index} to {value}"
        
        device = self.kb.get_device(device_name)
        device_lower = device_name.lower()
        
        # Generate contextual explanation based on device type
        if "eq" in device_lower:
            return self._explain_eq_adjustment(param, value, track_type)
        elif "compressor" in device_lower:
            return self._explain_compressor_adjustment(param, value, track_type)
        elif "reverb" in device_lower:
            return self._explain_reverb_adjustment(param, value)
        elif "saturator" in device_lower:
            return self._explain_saturation_adjustment(param, value)
        elif "limiter" in device_lower:
            return self._explain_limiter_adjustment(param, value)
        elif "delay" in device_lower:
            return self._explain_delay_adjustment(param, value)
        elif "utility" in device_lower:
            return self._explain_utility_adjustment(param, value)
        
        # Generic explanation
        return f"Setting {param.name} to {value}{param.unit}"
    
    def _explain_eq_adjustment(self, param: ParameterInfo, value: float, track_type: str) -> str:
        """Explain an EQ adjustment"""
        name_lower = param.name.lower()
        
        if "frequency" in name_lower:
            if value < 100:
                return f"Setting frequency to {value}Hz for sub-bass filtering"
            elif value < 250:
                return f"Setting frequency to {value}Hz to target low-end mud"
            elif value < 500:
                return f"Setting frequency to {value}Hz to address low-mid muddiness"
            elif value < 2000:
                return f"Setting frequency to {value}Hz in the midrange"
            elif value < 5000:
                return f"Setting frequency to {value}Hz for presence adjustment"
            elif value < 10000:
                return f"Setting frequency to {value}Hz to address harshness or sibilance"
            else:
                return f"Setting frequency to {value}Hz for air/sparkle adjustment"
        
        elif "gain" in name_lower:
            if value > 0:
                return f"Boosting by {value}dB"
            elif value < 0:
                return f"Cutting by {abs(value)}dB"
            else:
                return "Setting gain to neutral (0dB)"
        
        elif "q" in name_lower:
            if value < 1:
                return f"Using wide Q ({value}) for smooth, broad adjustment"
            elif value < 3:
                return f"Using moderate Q ({value}) for targeted adjustment"
            else:
                return f"Using narrow Q ({value}) for surgical precision"
        
        elif "type" in name_lower:
            # Correct EQ Eight types: 0=LP48, 1=LP24, 2=LP12, 3=Notch, 4=HP12, 5=HP24, 6=HP48, 7=Bell, 8=LowShelf, 9=HighShelf
            types = ["LP48 (Low Pass)", "LP24 (Low Pass)", "LP12 (Low Pass)", "Notch",
                     "HP12 (High Pass)", "HP24 (High Pass)", "HP48 (High Pass)",
                     "Bell", "Low Shelf", "High Shelf"]
            type_idx = int(value) if value < len(types) else 7
            return f"Setting filter type to {types[type_idx]}"
        
        return f"Adjusting {param.name} to {value}"
    
    def _explain_compressor_adjustment(self, param: ParameterInfo, value: float, track_type: str) -> str:
        """Explain a compressor adjustment"""
        name_lower = param.name.lower()
        
        if "threshold" in name_lower:
            return f"Setting threshold to {value}dB - lower values mean more compression"
        
        elif "ratio" in name_lower:
            if value <= 2:
                return f"Using gentle {value}:1 ratio for subtle dynamics control"
            elif value <= 4:
                return f"Using moderate {value}:1 ratio for standard compression"
            elif value <= 8:
                return f"Using firm {value}:1 ratio for noticeable compression"
            else:
                return f"Using aggressive {value}:1 ratio approaching limiting"
        
        elif "attack" in name_lower:
            if value < 5:
                return f"Using fast {value}ms attack to catch transients (more control, less punch)"
            elif value < 20:
                return f"Using medium {value}ms attack for balanced control"
            else:
                return f"Using slow {value}ms attack to let transients through (more punch)"
        
        elif "release" in name_lower:
            if value < 50:
                return f"Using fast {value}ms release (may cause pumping)"
            elif value < 200:
                return f"Using medium {value}ms release for natural recovery"
            else:
                return f"Using slow {value}ms release for smooth gain reduction"
        
        elif "output" in name_lower or "makeup" in name_lower:
            return f"Adding {value}dB makeup gain to compensate for compression"
        
        elif "wet" in name_lower:
            if value < 100:
                return f"Blending {value}% compressed signal for parallel compression effect"
            else:
                return "Using 100% wet - full compression"
        
        return f"Adjusting {param.name} to {value}"
    
    def _explain_reverb_adjustment(self, param: ParameterInfo, value: float) -> str:
        """Explain a reverb adjustment"""
        name_lower = param.name.lower()
        
        if "decay" in name_lower:
            if value < 1:
                return f"Setting short {value}s decay for tight room sound"
            elif value < 2:
                return f"Setting medium {value}s decay for natural space"
            else:
                return f"Setting long {value}s decay for large space/atmosphere"
        
        elif "size" in name_lower:
            return f"Setting room size to {value}% - affects density and character"
        
        elif "pre" in name_lower and "delay" in name_lower:
            return f"Adding {value}ms pre-delay to separate dry signal from reverb"
        
        elif "wet" in name_lower:
            if value <= 20:
                return f"Using subtle {value}% wet for natural space"
            elif value <= 40:
                return f"Using moderate {value}% wet for noticeable reverb"
            elif value < 100:
                return f"Using heavy {value}% wet for lush reverb"
            else:
                return "Using 100% wet (send configuration)"
        
        return f"Adjusting {param.name} to {value}"
    
    def _explain_saturation_adjustment(self, param: ParameterInfo, value: float) -> str:
        """Explain a saturation adjustment"""
        name_lower = param.name.lower()
        
        if "drive" in name_lower:
            if value < 6:
                return f"Using subtle {value}dB drive for gentle warmth"
            elif value < 15:
                return f"Using moderate {value}dB drive for noticeable color"
            else:
                return f"Using aggressive {value}dB drive for obvious distortion"
        
        elif "type" in name_lower:
            types = ["Analog Clip", "Soft Sine", "Medium Curve", "Hard Curve", "Sinoid Fold", "Digital Clip"]
            type_idx = int(value) if value < len(types) else 0
            return f"Using {types[type_idx]} saturation curve"
        
        return f"Adjusting {param.name} to {value}"
    
    def _explain_limiter_adjustment(self, param: ParameterInfo, value: float) -> str:
        """Explain a limiter adjustment"""
        name_lower = param.name.lower()
        
        if "gain" in name_lower:
            return f"Adding {value}dB input gain to increase loudness"
        
        elif "ceiling" in name_lower:
            if value >= -0.5:
                return f"Setting ceiling to {value}dB - careful, leaving little headroom"
            else:
                return f"Setting ceiling to {value}dB for safe headroom"
        
        elif "release" in name_lower:
            return f"Setting {value}ms release - faster may cause distortion"
        
        return f"Adjusting {param.name} to {value}"
    
    def _explain_delay_adjustment(self, param: ParameterInfo, value: float) -> str:
        """Explain a delay adjustment"""
        name_lower = param.name.lower()
        
        if "time" in name_lower or "delay" in name_lower:
            if value < 50:
                return f"Setting {value}ms delay for doubling/thickening effect"
            elif value < 150:
                return f"Setting {value}ms delay for slap-back effect"
            else:
                return f"Setting {value}ms delay for rhythmic echo"
        
        elif "feedback" in name_lower:
            if value < 30:
                return f"Using {value}% feedback for subtle echoes"
            elif value < 60:
                return f"Using {value}% feedback for repeating echoes"
            else:
                return f"Using high {value}% feedback for sustained trails (watch for buildup)"
        
        return f"Adjusting {param.name} to {value}"
    
    def _explain_utility_adjustment(self, param: ParameterInfo, value: float) -> str:
        """Explain a utility adjustment"""
        name_lower = param.name.lower()
        
        if "width" in name_lower:
            if value == 0:
                return "Setting to mono"
            elif value < 100:
                return f"Narrowing stereo width to {value}%"
            elif value == 100:
                return "Setting normal stereo width (100%)"
            else:
                return f"Widening stereo image to {value}%"
        
        elif "gain" in name_lower:
            return f"Adjusting level by {value}dB"
        
        return f"Adjusting {param.name} to {value}"
    
    # ==================== DYNAMIC PARAMETER DISCOVERY ====================
    
    def find_param_by_name(self, 
                          param_name: str, 
                          param_list: List[Dict[str, Any]]) -> Optional[int]:
        """
        Find a parameter index by name from a list of actual device parameters.
        
        Args:
            param_name: Name of the parameter to find (case-insensitive, partial match)
            param_list: List of parameter dicts from Ableton (from get_device_parameters)
            
        Returns:
            Parameter index if found, None otherwise
        """
        param_lower = param_name.lower()
        
        # First try exact match
        for i, param in enumerate(param_list):
            name = param.get("name", "").lower()
            if name == param_lower:
                return i
        
        # Then try contains match
        for i, param in enumerate(param_list):
            name = param.get("name", "").lower()
            if param_lower in name or name in param_lower:
                return i
        
        return None
    
    def map_settings_to_params(self,
                               preset_settings: Dict[str, Any],
                               param_list: List[Dict[str, Any]],
                               device_name: str) -> Dict[int, Any]:
        """
        Map preset settings (with name-based keys) to actual parameter indices.
        
        This allows us to use semantic names in presets that get mapped to
        the actual parameter indices on the device.
        
        Args:
            preset_settings: Dict with parameter names as keys, values as values
            param_list: List of actual parameters from the device
            device_name: Name of the device (for KB lookup fallback)
            
        Returns:
            Dict with parameter indices as keys, values as values
        """
        mapped = {}
        
        for key, value in preset_settings.items():
            if isinstance(key, int):
                # Already an index
                mapped[key] = value
            elif isinstance(key, str):
                # Try to find by name
                idx = self.find_param_by_name(key, param_list)
                if idx is not None:
                    mapped[idx] = value
                else:
                    # Fallback to KB-based mapping
                    device = self.kb.get_device(device_name)
                    if device:
                        param = device.get_parameter_by_name(key)
                        if param:
                            mapped[param.index] = value
        
        return mapped
    
    def apply_settings_dynamically(self,
                                   track_index: int,
                                   device_index: int,
                                   settings: Dict[int, Any]) -> Dict[str, Any]:
        """
        Apply settings to a device with verification.
        
        Args:
            track_index: Track index
            device_index: Device index on track
            settings: Dict of param_index -> value
            
        Returns:
            Result dict with success status and details
        """
        try:
            from ableton_controls import ableton
        except ImportError:
            return {"success": False, "message": "Could not import ableton_controls"}
        
        results = {
            "success": True,
            "applied": [],
            "failed": []
        }
        
        for param_idx, value in settings.items():
            try:
                result = ableton.safe_set_device_parameter(track_index, device_index, param_idx, value)
                time.sleep(0.1)  # Small delay between params
                
                if result.get("success"):
                    results["applied"].append({
                        "param_index": param_idx,
                        "value": value
                    })
                else:
                    results["failed"].append({
                        "param_index": param_idx,
                        "value": value,
                        "reason": result.get("message", "Unknown")
                    })
            except Exception as e:
                results["failed"].append({
                    "param_index": param_idx,
                    "value": value,
                    "reason": str(e)
                })
        
        if results["failed"]:
            results["success"] = False if not results["applied"] else True
            results["message"] = f"Applied {len(results['applied'])}, failed {len(results['failed'])}"
        else:
            results["message"] = f"Successfully applied {len(results['applied'])} parameters"
        
        return results
    
    def configure_device_for_purpose(self,
                                     track_index: int,
                                     device_index: int,
                                     device_name: str,
                                     purpose: str,
                                     track_type: str = "vocal") -> Dict[str, Any]:
        """
        Configure a device for a specific purpose using the best available method.
        
        This is the main entry point for intelligent device configuration.
        
        Args:
            track_index: Track index
            device_index: Device index on track
            device_name: Name of the device
            purpose: Purpose/intent (e.g., "high_pass", "cut_mud", "compress")
            track_type: Type of track
            
        Returns:
            Result dict with success status and applied settings
        """
        # Get suggested settings from our knowledge base
        suggestion = self.suggest_settings(device_name, purpose, track_type)
        
        if not suggestion.get("success"):
            # Try intent-based matching
            suggestion = self.suggest_for_intent(purpose, track_type)
        
        if not suggestion.get("success"):
            return {
                "success": False,
                "message": f"Could not find settings for purpose '{purpose}' on {device_name}",
                "device": device_name,
                "purpose": purpose
            }
        
        settings = suggestion.get("settings", {})
        if not settings:
            return {
                "success": False,
                "message": "No settings to apply",
                "device": device_name,
                "purpose": purpose
            }
        
        # Apply the settings
        result = self.apply_settings_dynamically(track_index, device_index, settings)
        result["device"] = device_name
        result["purpose"] = purpose
        result["description"] = suggestion.get("description", "")
        
        return result
    
    # ==================== BATCH OPERATIONS ====================
    
    def get_chain_settings(self, 
                          chain_type: str,
                          track_type: str = "vocal") -> List[Dict[str, Any]]:
        """
        Get suggested settings for a complete processing chain.
        
        Args:
            chain_type: Type of chain (e.g., "vocal", "drums", "master")
            track_type: Type of track
            
        Returns:
            List of device settings for the chain
        """
        chains = {
            "vocal": [
                {"device": "EQ Eight", "preset": "high_pass_vocal"},
                {"device": "Compressor", "preset": "vocal_control"},
                {"device": "EQ Eight", "preset": "presence_boost"},
                {"device": "Reverb", "preset": "vocal_plate"},
            ],
            "drums": [
                {"device": "EQ Eight", "preset": "cut_mud"},
                {"device": "Glue Compressor", "preset": "drum_bus"},
                {"device": "Saturator", "preset": "subtle_warmth"},
            ],
            "bass": [
                {"device": "EQ Eight", "preset": "high_pass_vocal"},  # Will be adjusted for bass
                {"device": "Compressor", "preset": "bass_control"},
                {"device": "Saturator", "preset": "subtle_warmth"},
            ],
            "master": [
                {"device": "EQ Eight", "preset": "presence_boost"},
                {"device": "Glue Compressor", "preset": "mix_bus"},
                {"device": "Limiter", "preset": "master_streaming"},
            ]
        }
        
        chain_config = chains.get(chain_type.lower(), chains["vocal"])
        results = []
        
        for item in chain_config:
            device = self.kb.get_device(item["device"])
            preset = device.presets.get(item["preset"]) if device else None
            
            if device and preset:
                settings = preset.get("settings", {}).copy()
                adjusted = self._apply_track_type_adjustments(device.name, settings, track_type)
                
                results.append({
                    "device": device.name,
                    "preset": item["preset"],
                    "description": preset.get("description", ""),
                    "settings": adjusted
                })
        
        return results

    # ==================== CUSTOM PARAMETER REQUESTS ====================

    def build_custom_eq_settings(self,
                                  frequency: float,
                                  gain: float,
                                  q: float = 1.0,
                                  filter_type: str = "bell",
                                  band: int = None,
                                  occupied_bands: List[int] = None) -> Dict[str, Any]:
        """
        Build EQ Eight settings for an arbitrary frequency/gain/Q request.

        Instead of relying on presets, this constructs the exact parameter
        values needed for a custom EQ adjustment.

        Args:
            frequency: Target frequency in Hz (20-20000)
            gain: Gain in dB (-15 to +15)
            q: Q/bandwidth (0.1-18, default 1.0)
            filter_type: "bell", "low_cut", "low_shelf", "notch", "high_shelf", "high_cut"
            band: Specific band to use (1-8). If None, auto-selects.
            occupied_bands: List of already-used band numbers to avoid.

        Returns:
            Dict with success, settings dict (param_index -> value), and metadata
        """
        # Map filter type strings to EQ Eight type indices
        # Correct EQ Eight types: 0=LP48, 1=LP24, 2=LP12, 3=Notch, 4=HP12, 5=HP24, 6=HP48, 7=Bell, 8=LowShelf, 9=HighShelf
        type_map = {
            "low_cut": 4, "highpass": 4, "high_pass": 4, "hp": 4,  # HP12 cuts low frequencies
            "low_shelf": 8, "lowshelf": 8, "ls": 8,
            "bell": 7, "peak": 7, "parametric": 7,
            "notch": 3, "band_reject": 3,
            "high_shelf": 9, "highshelf": 9, "hs": 9,
            "high_cut": 0, "lowpass": 0, "low_pass": 0, "lp": 0,  # LP48 cuts high frequencies
        }

        filter_type_idx = type_map.get(filter_type.lower(), 7)  # Default to bell

        # Clamp values to EQ Eight ranges
        frequency = max(20.0, min(20000.0, frequency))
        gain = max(-15.0, min(15.0, gain))
        q = max(0.1, min(18.0, q))

        # Auto-select band if not specified
        if band is None:
            occupied = set(occupied_bands or [])
            # Prefer bands 3-6 for mid-range work, 1-2 for low, 7-8 for high
            if frequency < 200:
                preferred_order = [1, 2, 3, 4, 5, 6, 7, 8]
            elif frequency < 2000:
                preferred_order = [3, 4, 2, 5, 6, 1, 7, 8]
            elif frequency < 8000:
                preferred_order = [4, 5, 3, 6, 7, 2, 8, 1]
            else:
                preferred_order = [7, 8, 6, 5, 4, 3, 2, 1]

            band = None
            for b in preferred_order:
                if b not in occupied:
                    band = b
                    break

            if band is None:
                return {
                    "success": False,
                    "message": "All 8 EQ bands are occupied",
                    "settings": {}
                }

        if band < 1 or band > 8:
            return {
                "success": False,
                "message": f"Band must be 1-8, got {band}",
                "settings": {}
            }

        # Calculate parameter indices: band N starts at index 1 + (N-1)*5
        base_idx = 1 + (band - 1) * 5

        settings = {
            base_idx:     frequency,       # Frequency
            base_idx + 1: gain,            # Gain
            base_idx + 2: q,               # Q
            base_idx + 3: filter_type_idx, # Type
            base_idx + 4: 1,               # Active (on)
        }

        return {
            "success": True,
            "device": "EQ Eight",
            "band": band,
            "settings": settings,
            "description": f"Band {band}: {filter_type} at {frequency}Hz, {gain:+.1f}dB, Q={q}",
            "metadata": {
                "frequency": frequency,
                "gain": gain,
                "q": q,
                "filter_type": filter_type,
                "filter_type_index": filter_type_idx,
                "band": band,
            }
        }

    def build_custom_eq_chain(self, bands: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Build a multi-band EQ configuration from a list of band specs.

        Args:
            bands: List of dicts, each with:
                - frequency (float): Hz
                - gain (float): dB
                - q (float, optional): default 1.0
                - filter_type (str, optional): default "bell"
                - band (int, optional): specific band number

        Returns:
            Dict with combined settings for all bands
        """
        all_settings = {}
        occupied = []
        descriptions = []

        for band_spec in bands:
            result = self.build_custom_eq_settings(
                frequency=band_spec["frequency"],
                gain=band_spec["gain"],
                q=band_spec.get("q", 1.0),
                filter_type=band_spec.get("filter_type", "bell"),
                band=band_spec.get("band"),
                occupied_bands=occupied
            )

            if result["success"]:
                all_settings.update(result["settings"])
                occupied.append(result["band"])
                descriptions.append(result["description"])
            else:
                return result  # Propagate error

        return {
            "success": True,
            "device": "EQ Eight",
            "settings": all_settings,
            "bands_used": occupied,
            "descriptions": descriptions,
            "description": " | ".join(descriptions)
        }

    def parse_eq_request(self, request: str) -> Dict[str, Any]:
        """
        Parse a natural language EQ request into specific settings.

        Examples:
            "presence boost at 7kHz +3dB"
            "high pass at 80Hz"
            "cut 300Hz by 4dB with narrow Q"
            "boost 3k by 2dB, cut 400Hz by 3dB"

        Returns:
            Dict with parsed bands and built settings
        """
        import re

        request_lower = request.lower()
        bands = []

        # Pattern: frequency + gain combinations
        # Matches: "7kHz +3dB", "300hz -4db", "3k +2db", "80 hz"
        freq_patterns = [
            # "boost/cut at Xhz by YdB" or "Xhz +/-YdB"
            r'(\d+(?:\.\d+)?)\s*(?:k(?:hz)?|khz)\s*(?:at|by|to)?\s*([+-]?\d+(?:\.\d+)?)\s*(?:db)?',
            r'(\d+(?:\.\d+)?)\s*(?:hz)\s*(?:at|by|to)?\s*([+-]?\d+(?:\.\d+)?)\s*(?:db)?',
            # "+YdB at Xhz/Xk"
            r'([+-]?\d+(?:\.\d+)?)\s*(?:db)\s*(?:at|around|near)?\s*(\d+(?:\.\d+)?)\s*(?:k(?:hz)?|khz)',
            r'([+-]?\d+(?:\.\d+)?)\s*(?:db)\s*(?:at|around|near)?\s*(\d+(?:\.\d+)?)\s*(?:hz)',
        ]

        # Try to extract frequency/gain pairs
        found_pairs = []

        # First try: "Xk +YdB" pattern (frequency then gain)
        for match in re.finditer(r'(\d+(?:\.\d+)?)\s*k(?:hz)?\s*(?:at|by|to)?\s*([+-]?\d+(?:\.\d+)?)\s*(?:db)?', request_lower):
            freq = float(match.group(1)) * 1000
            gain = float(match.group(2))
            found_pairs.append((freq, gain))

        if not found_pairs:
            # Try: "Xhz +YdB"
            for match in re.finditer(r'(\d+(?:\.\d+)?)\s*hz\s*(?:at|by|to)?\s*([+-]?\d+(?:\.\d+)?)\s*(?:db)?', request_lower):
                freq = float(match.group(1))
                gain = float(match.group(2))
                found_pairs.append((freq, gain))

        if not found_pairs:
            # Try: "+YdB at Xk"
            for match in re.finditer(r'([+-]?\d+(?:\.\d+)?)\s*(?:db)\s*(?:at|around|near)\s*(\d+(?:\.\d+)?)\s*k(?:hz)?', request_lower):
                gain = float(match.group(1))
                freq = float(match.group(2)) * 1000
                found_pairs.append((freq, gain))

        if not found_pairs:
            # Try: "+YdB at Xhz"
            for match in re.finditer(r'([+-]?\d+(?:\.\d+)?)\s*(?:db)\s*(?:at|around|near)\s*(\d+(?:\.\d+)?)\s*hz', request_lower):
                gain = float(match.group(1))
                freq = float(match.group(2))
                found_pairs.append((freq, gain))

        # Determine filter type from context
        filter_type = "bell"  # default
        if "high pass" in request_lower or "high-pass" in request_lower or "highpass" in request_lower:
            filter_type = "low_cut"
        elif "low pass" in request_lower or "low-pass" in request_lower or "lowpass" in request_lower:
            filter_type = "high_cut"
        elif "shelf" in request_lower:
            if "high" in request_lower:
                filter_type = "high_shelf"
            elif "low" in request_lower:
                filter_type = "low_shelf"
        elif "notch" in request_lower:
            filter_type = "notch"

        # Determine Q from context
        q = 1.0  # default
        if "narrow" in request_lower or "surgical" in request_lower or "tight" in request_lower:
            q = 4.0
        elif "wide" in request_lower or "broad" in request_lower or "gentle" in request_lower:
            q = 0.5
        elif "very narrow" in request_lower:
            q = 8.0

        # Explicit Q value
        q_match = re.search(r'q\s*(?:=|of|:)?\s*(\d+(?:\.\d+)?)', request_lower)
        if q_match:
            q = float(q_match.group(1))

        # Handle "boost" / "cut" without explicit +/- sign
        for freq, gain in found_pairs:
            if "cut" in request_lower and gain > 0:
                gain = -abs(gain)
            elif "boost" in request_lower and gain < 0:
                gain = abs(gain)

            # For high-pass, gain doesn't apply the same way
            if filter_type == "low_cut":
                gain = 0.0

            bands.append({
                "frequency": freq,
                "gain": gain,
                "q": q,
                "filter_type": filter_type,
            })

        # Handle high-pass with just frequency, no gain
        if not found_pairs and filter_type == "low_cut":
            freq_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:hz|k(?:hz)?)', request_lower)
            if freq_match:
                freq = float(freq_match.group(1))
                if 'k' in request_lower[freq_match.end()-3:freq_match.end()]:
                    freq *= 1000
                bands.append({
                    "frequency": freq,
                    "gain": 0.0,
                    "q": 0.71,
                    "filter_type": "low_cut",
                })

        if not bands:
            return {
                "success": False,
                "message": f"Could not parse EQ request: '{request}'",
                "hint": "Try format like: '7kHz +3dB' or 'high pass at 80Hz' or 'cut 300Hz by 4dB'"
            }

        return self.build_custom_eq_chain(bands)


# Global instance
_device_intelligence = None


def get_device_intelligence() -> DeviceIntelligence:
    """Get the global DeviceIntelligence instance"""
    global _device_intelligence
    if _device_intelligence is None:
        _device_intelligence = DeviceIntelligence()
    return _device_intelligence

