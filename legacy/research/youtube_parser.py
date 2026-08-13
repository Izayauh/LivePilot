"""
YouTube Settings Parser

Parses YouTube video descriptions, transcripts, and article content
to extract:
- Plugin chains (what devices to use in what order)
- Parameter settings (specific values for each plugin)
- Audio engineering techniques being described

This enables Jarvis to learn from YouTube tutorials and apply the settings.
"""

import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class ParsedDevice:
    """A device parsed from text"""
    name: str
    device_type: str  # eq, compressor, reverb, etc.
    settings: Dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    confidence: float = 1.0


@dataclass
class ParsedChain:
    """A complete chain parsed from text"""
    artist_or_style: str
    track_type: str
    devices: List[ParsedDevice] = field(default_factory=list)
    source_url: str = ""
    source_title: str = ""
    raw_text: str = ""


class YouTubeSettingsParser:
    """
    Parser for extracting audio settings from YouTube content.
    
    Handles:
    - Video transcripts
    - Video descriptions
    - Article/blog content about audio production
    """
    
    def __init__(self):
        # Device name patterns (common plugin names)
        self._device_patterns = {
            "eq": [
                r"eq\s*eight", r"eq8", r"eq\s*3", r"pro[- ]?q\s*\d?", r"fabfilter.*eq",
                r"ssl.*eq", r"api.*eq", r"pultec", r"neve.*eq", r"channel.*eq",
                r"parametric\s*eq", r"graphic\s*eq", r"equalizer",
            ],
            "compressor": [
                r"compressor", r"comp", r"pro[- ]?c\s*\d?", r"ssl.*comp",
                r"1176", r"la[- ]?2a", r"la[- ]?3a", r"api.*comp", r"urei",
                r"fairchild", r"glue\s*compressor", r"glue\s*comp",
                r"multiband\s*dynamics", r"opto\s*comp", r"vca\s*comp",
            ],
            "reverb": [
                r"reverb", r"room", r"hall", r"plate", r"spring", r"chamber",
                r"pro[- ]?r", r"valhalla", r"h[- ]?reverb", r"lexicon", r"space",
                r"convolution", r"algorithmic", r"shimmer",
            ],
            "delay": [
                r"delay", r"echo", r"echoboy", r"h[- ]?delay", r"timeless",
                r"ping\s*pong", r"slap\s*back", r"tape\s*delay",
            ],
            "saturation": [
                r"saturator", r"saturation", r"distortion", r"tape",
                r"decapitator", r"saturn", r"sausage.*fattener", r"warm",
                r"drive", r"overdrive", r"tube", r"analog",
            ],
            "limiter": [
                r"limiter", r"pro[- ]?l\s*\d?", r"l[12]\s*limiter", r"ozone.*limiter",
                r"brickwall", r"maximizer",
            ],
            "de_esser": [
                r"de[- ]?esser", r"deesser", r"sibilance", r"soothe",
                r"ess\s*control", r"ess\s*remov",
            ],
            "modulation": [
                r"chorus", r"flanger", r"phaser", r"tremolo", r"vibrato",
                r"ensemble", r"uni[- ]?vibe", r"leslie",
            ],
            "utility": [
                r"utility", r"gain", r"trim", r"width", r"stereo.*imager",
                r"mid\s*side", r"m/s",
            ],
        }
        
        # Parameter patterns (common audio parameter names with values)
        self._param_patterns = {
            "frequency": [
                r"(?:freq|frequency|hz|hertz)[:\s]*(\d+(?:\.\d+)?)\s*(?:hz|hertz)?",
                r"(\d+(?:\.\d+)?)\s*(?:hz|hertz)",
                r"at\s*(\d+(?:\.\d+)?)\s*(?:hz|hertz)?",
            ],
            "gain": [
                r"(?:gain|boost|cut)[:\s]*([+-]?\d+(?:\.\d+)?)\s*(?:db|decibel)?",
                r"([+-]?\d+(?:\.\d+)?)\s*db",
                r"(?:plus|minus)\s*(\d+(?:\.\d+)?)\s*(?:db)?",
            ],
            "q": [
                r"(?:q|bandwidth|resonance)[:\s]*(\d+(?:\.\d+)?)",
                r"q\s*(?:of|=|:)\s*(\d+(?:\.\d+)?)",
            ],
            "threshold": [
                r"(?:threshold)[:\s]*([+-]?\d+(?:\.\d+)?)\s*(?:db)?",
                r"threshold.*?([+-]?\d+(?:\.\d+)?)\s*(?:db)?",
            ],
            "ratio": [
                r"(?:ratio)[:\s]*(\d+(?:\.\d+)?)[:\s]*1",
                r"(\d+(?:\.\d+)?)[:\s]*(?:to|:)\s*1\s*(?:ratio)?",
            ],
            "attack": [
                r"(?:attack)[:\s]*(\d+(?:\.\d+)?)\s*(?:ms|milliseconds)?",
                r"attack.*?(\d+(?:\.\d+)?)\s*(?:ms)?",
            ],
            "release": [
                r"(?:release)[:\s]*(\d+(?:\.\d+)?)\s*(?:ms|milliseconds|s|seconds)?",
                r"release.*?(\d+(?:\.\d+)?)\s*(?:ms|s)?",
            ],
            "wet": [
                r"(?:wet|mix|blend)[:\s]*(\d+(?:\.\d+)?)\s*(?:%|percent)?",
                r"(\d+(?:\.\d+)?)\s*(?:%|percent)\s*(?:wet|mix)",
            ],
            "decay": [
                r"(?:decay|reverb\s*time|rt60)[:\s]*(\d+(?:\.\d+)?)\s*(?:s|seconds|ms)?",
            ],
            "predelay": [
                r"(?:pre[- ]?delay)[:\s]*(\d+(?:\.\d+)?)\s*(?:ms|milliseconds)?",
            ],
            "drive": [
                r"(?:drive|saturation)[:\s]*(\d+(?:\.\d+)?)\s*(?:db|%)?",
            ],
        }
        
        # Filter type keywords
        self._filter_types = {
            "low_cut": ["high pass", "high-pass", "highpass", "hpf", "low cut", "low-cut", "lowcut", "rumble filter"],
            "low_shelf": ["low shelf", "low-shelf", "lowshelf", "bass shelf"],
            "bell": ["bell", "peak", "parametric", "peaking"],
            "notch": ["notch", "band reject"],
            "high_shelf": ["high shelf", "high-shelf", "highshelf", "treble shelf", "air shelf"],
            "high_cut": ["low pass", "low-pass", "lowpass", "lpf", "high cut", "high-cut", "highcut"],
        }
    
    def parse_text(self, text: str, artist_or_style: str = "", track_type: str = "vocal") -> ParsedChain:
        """
        Parse text to extract plugin chain and settings.
        
        Args:
            text: Text content (transcript, description, article)
            artist_or_style: Artist or style being researched
            track_type: Type of track (vocal, drums, etc.)
            
        Returns:
            ParsedChain with extracted devices and settings
        """
        text_lower = text.lower()
        
        chain = ParsedChain(
            artist_or_style=artist_or_style,
            track_type=track_type,
            raw_text=text
        )
        
        # Find devices mentioned in text
        devices = self._find_devices(text_lower)
        
        # For each device, try to extract settings
        for device_name, device_type, raw_match in devices:
            device = ParsedDevice(
                name=device_name,
                device_type=device_type,
                raw_text=raw_match
            )
            
            # Extract settings from context around the device mention
            device.settings = self._extract_settings(text_lower, raw_match, device_type)
            chain.devices.append(device)
        
        return chain
    
    def _find_devices(self, text: str) -> List[Tuple[str, str, str]]:
        """Find devices mentioned in text"""
        found_devices = []
        
        for device_type, patterns in self._device_patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    device_name = self._normalize_device_name(match.group(), device_type)
                    if device_name and (device_name, device_type, match.group()) not in found_devices:
                        found_devices.append((device_name, device_type, match.group()))
        
        return found_devices
    
    def _normalize_device_name(self, raw_name: str, device_type: str) -> str:
        """Convert raw matched name to standard device name"""
        raw_lower = raw_name.lower().strip()
        
        # Map to Ableton native devices
        name_mapping = {
            # EQ
            "eq eight": "EQ Eight",
            "eq8": "EQ Eight",
            "eq 3": "EQ Three",
            "eq3": "EQ Three",
            # Compression
            "compressor": "Compressor",
            "glue compressor": "Glue Compressor",
            "glue comp": "Glue Compressor",
            "multiband dynamics": "Multiband Dynamics",
            # Reverb
            "reverb": "Reverb",
            "room": "Reverb",
            "hall": "Reverb",
            "plate": "Reverb",
            # Delay
            "delay": "Delay",
            "echo": "Echo",
            "ping pong": "Delay",
            # Saturation
            "saturator": "Saturator",
            "saturation": "Saturator",
            # Other
            "limiter": "Limiter",
            "utility": "Utility",
            "chorus": "Chorus-Ensemble",
            "flanger": "Flanger",
            "phaser": "Phaser",
        }
        
        for key, value in name_mapping.items():
            if key in raw_lower:
                return value
        
        # For third-party plugins, try to clean up the name
        if "pro-q" in raw_lower or "pro q" in raw_lower:
            return "FabFilter Pro-Q 3"
        if "pro-c" in raw_lower or "pro c" in raw_lower:
            return "FabFilter Pro-C 2"
        if "1176" in raw_lower:
            return "CLA-76"  # Waves emulation
        if "la-2a" in raw_lower or "la2a" in raw_lower:
            return "CLA-2A"
        if "ssl" in raw_lower and device_type == "compressor":
            return "SSL G-Master Buss Compressor"
        if "ssl" in raw_lower and device_type == "eq":
            return "SSL E-Channel"
        if "pultec" in raw_lower:
            return "PuigTec EQP-1A"
        if "decapitator" in raw_lower:
            return "Decapitator"
        if "soothe" in raw_lower:
            return "Soothe2"
        if "echoboy" in raw_lower:
            return "EchoBoy"
        
        # Return capitalized raw name
        return raw_name.strip().title()
    
    def _extract_settings(self, text: str, device_context: str, device_type: str) -> Dict[str, Any]:
        """Extract parameter settings from text context"""
        settings = {}
        
        # Find the context around the device mention
        device_pos = text.find(device_context.lower())
        if device_pos >= 0:
            # Look at text surrounding the device mention (up to 500 chars)
            start = max(0, device_pos - 200)
            end = min(len(text), device_pos + len(device_context) + 500)
            context = text[start:end]
        else:
            context = text
        
        # Extract parameters based on device type
        if device_type == "eq":
            settings = self._extract_eq_settings(context)
        elif device_type == "compressor":
            settings = self._extract_compressor_settings(context)
        elif device_type == "reverb":
            settings = self._extract_reverb_settings(context)
        elif device_type == "delay":
            settings = self._extract_delay_settings(context)
        elif device_type == "saturation":
            settings = self._extract_saturation_settings(context)
        elif device_type == "limiter":
            settings = self._extract_limiter_settings(context)
        
        return settings
    
    def _extract_eq_settings(self, context: str) -> Dict[str, Any]:
        """Extract EQ settings from context"""
        settings = {}
        
        # Try to find frequency values
        for pattern in self._param_patterns["frequency"]:
            matches = re.findall(pattern, context, re.IGNORECASE)
            if matches:
                freq = float(matches[0])
                if freq > 20 and freq < 22000:  # Valid frequency range
                    settings["frequency"] = freq
                    break
        
        # Try to find gain values
        for pattern in self._param_patterns["gain"]:
            matches = re.findall(pattern, context, re.IGNORECASE)
            if matches:
                gain = float(matches[0].replace('+', ''))
                if -20 <= gain <= 20:  # Valid gain range
                    settings["gain"] = gain
                    break
        
        # Try to find Q values
        for pattern in self._param_patterns["q"]:
            matches = re.findall(pattern, context, re.IGNORECASE)
            if matches:
                q = float(matches[0])
                if 0.1 <= q <= 20:  # Valid Q range
                    settings["q"] = q
                    break
        
        # Try to determine filter type
        for filter_type, keywords in self._filter_types.items():
            for keyword in keywords:
                if keyword in context:
                    settings["filter_type"] = filter_type
                    break
            if "filter_type" in settings:
                break
        
        return settings
    
    def _extract_compressor_settings(self, context: str) -> Dict[str, Any]:
        """Extract compressor settings from context"""
        settings = {}
        
        # Threshold
        for pattern in self._param_patterns["threshold"]:
            matches = re.findall(pattern, context, re.IGNORECASE)
            if matches:
                threshold = float(matches[0])
                if -60 <= threshold <= 0:
                    settings["threshold"] = threshold
                    break
        
        # Ratio
        for pattern in self._param_patterns["ratio"]:
            matches = re.findall(pattern, context, re.IGNORECASE)
            if matches:
                ratio = float(matches[0])
                if 1 <= ratio <= 20:
                    settings["ratio"] = ratio
                    break
        
        # Attack
        for pattern in self._param_patterns["attack"]:
            matches = re.findall(pattern, context, re.IGNORECASE)
            if matches:
                attack = float(matches[0])
                if 0.01 <= attack <= 500:
                    settings["attack"] = attack
                    break
        
        # Release
        for pattern in self._param_patterns["release"]:
            matches = re.findall(pattern, context, re.IGNORECASE)
            if matches:
                release = float(matches[0])
                if 10 <= release <= 2000:
                    settings["release"] = release
                    break
        
        return settings
    
    def _extract_reverb_settings(self, context: str) -> Dict[str, Any]:
        """Extract reverb settings from context"""
        settings = {}
        
        # Decay time
        for pattern in self._param_patterns["decay"]:
            matches = re.findall(pattern, context, re.IGNORECASE)
            if matches:
                decay = float(matches[0])
                if decay < 20:  # Assume seconds if small number
                    settings["decay"] = decay
                else:
                    settings["decay"] = decay / 1000  # Convert ms to s
                break
        
        # Pre-delay
        for pattern in self._param_patterns["predelay"]:
            matches = re.findall(pattern, context, re.IGNORECASE)
            if matches:
                predelay = float(matches[0])
                settings["predelay"] = predelay
                break
        
        # Wet/dry mix
        for pattern in self._param_patterns["wet"]:
            matches = re.findall(pattern, context, re.IGNORECASE)
            if matches:
                wet = float(matches[0])
                if 0 <= wet <= 100:
                    settings["wet"] = wet
                    break
        
        return settings
    
    def _extract_delay_settings(self, context: str) -> Dict[str, Any]:
        """Extract delay settings from context"""
        settings = {}
        
        # Look for delay time in ms
        delay_pattern = r"(\d+(?:\.\d+)?)\s*(?:ms|milliseconds)"
        matches = re.findall(delay_pattern, context, re.IGNORECASE)
        if matches:
            settings["delay_time"] = float(matches[0])
        
        # Feedback
        feedback_pattern = r"feedback[:\s]*(\d+(?:\.\d+)?)\s*(?:%|percent)?"
        matches = re.findall(feedback_pattern, context, re.IGNORECASE)
        if matches:
            settings["feedback"] = float(matches[0])
        
        # Wet/dry
        for pattern in self._param_patterns["wet"]:
            matches = re.findall(pattern, context, re.IGNORECASE)
            if matches:
                wet = float(matches[0])
                if 0 <= wet <= 100:
                    settings["wet"] = wet
                    break
        
        return settings
    
    def _extract_saturation_settings(self, context: str) -> Dict[str, Any]:
        """Extract saturation settings from context"""
        settings = {}
        
        # Drive amount
        for pattern in self._param_patterns["drive"]:
            matches = re.findall(pattern, context, re.IGNORECASE)
            if matches:
                drive = float(matches[0])
                settings["drive"] = drive
                break
        
        # Wet/dry
        for pattern in self._param_patterns["wet"]:
            matches = re.findall(pattern, context, re.IGNORECASE)
            if matches:
                wet = float(matches[0])
                if 0 <= wet <= 100:
                    settings["wet"] = wet
                    break
        
        return settings
    
    def _extract_limiter_settings(self, context: str) -> Dict[str, Any]:
        """Extract limiter settings from context"""
        settings = {}
        
        # Ceiling
        ceiling_pattern = r"ceiling[:\s]*([+-]?\d+(?:\.\d+)?)\s*(?:db)?"
        matches = re.findall(ceiling_pattern, context, re.IGNORECASE)
        if matches:
            settings["ceiling"] = float(matches[0])
        
        # Gain
        for pattern in self._param_patterns["gain"]:
            matches = re.findall(pattern, context, re.IGNORECASE)
            if matches:
                gain = float(matches[0].replace('+', ''))
                settings["gain"] = gain
                break
        
        return settings
    
    def chain_to_device_list(self, chain: ParsedChain) -> List[Dict[str, Any]]:
        """
        Convert a ParsedChain to a list of device configs for the chain builder.
        
        Args:
            chain: ParsedChain from parse_text()
            
        Returns:
            List of device configuration dictionaries
        """
        device_list = []
        
        for device in chain.devices:
            device_config = {
                "name": device.name,
                "type": device.device_type,
                "purpose": self._infer_purpose(device),
                "settings": self._convert_settings_to_indices(device.name, device.settings),
            }
            device_list.append(device_config)
        
        return device_list
    
    def _infer_purpose(self, device: ParsedDevice) -> str:
        """Infer the purpose of a device from its settings"""
        if device.device_type == "eq":
            if device.settings.get("filter_type") == "low_cut":
                return "high_pass"
            elif device.settings.get("gain", 0) < 0:
                freq = device.settings.get("frequency", 1000)
                if 200 <= freq <= 500:
                    return "cut_mud"
                elif 2000 <= freq <= 5000:
                    return "de_harsh"
                elif freq > 5000:
                    return "de_sibilance"
                return "cut"
            elif device.settings.get("gain", 0) > 0:
                freq = device.settings.get("frequency", 1000)
                if freq > 8000:
                    return "air_boost"
                elif 2000 <= freq <= 5000:
                    return "presence_boost"
                return "boost"
            return "tone_shaping"
        
        elif device.device_type == "compressor":
            ratio = device.settings.get("ratio", 4)
            if ratio >= 10:
                return "limiting"
            elif ratio >= 6:
                return "heavy_compression"
            return "dynamics_control"
        
        elif device.device_type == "reverb":
            decay = device.settings.get("decay", 2)
            if decay > 3:
                return "hall"
            elif decay < 1:
                return "room"
            return "plate"
        
        elif device.device_type == "saturation":
            return "warmth"
        
        elif device.device_type == "delay":
            time = device.settings.get("delay_time", 250)
            if time < 80:
                return "slap"
            return "echo"
        
        return device.device_type
    
    def _convert_settings_to_indices(self, device_name: str, settings: Dict[str, Any]) -> Dict[int, Any]:
        """
        Convert named settings to parameter indices.
        
        This maps generic setting names to actual device parameter indices.
        """
        # Mapping for common Ableton devices
        param_mappings = {
            "EQ Eight": {
                "frequency": 1,  # Band 1 frequency
                "gain": 2,       # Band 1 gain
                "q": 3,          # Band 1 Q
                "filter_type": 4,  # Band 1 type
            },
            "Compressor": {
                "threshold": 1,
                "ratio": 2,
                "attack": 3,
                "release": 4,
                "output_gain": 5,
                "wet": 6,
            },
            "Reverb": {
                "decay": 1,
                "size": 2,
                "predelay": 3,
                "wet": 6,
            },
            "Saturator": {
                "drive": 1,
                "wet": 5,
            },
            "Delay": {
                "delay_time": 1,
                "feedback": 3,
                "wet": 5,
            },
            "Limiter": {
                "gain": 1,
                "ceiling": 2,
            },
        }
        
        mapping = param_mappings.get(device_name, {})
        indexed_settings = {}
        
        for name, value in settings.items():
            if name in mapping:
                indexed_settings[mapping[name]] = value
        
        return indexed_settings


def parse_settings_from_text(text: str, artist_or_style: str = "", track_type: str = "vocal") -> Dict[str, Any]:
    """
    Convenience function to parse settings from text.
    
    Args:
        text: Text content to parse
        artist_or_style: Artist or style being researched
        track_type: Type of track
        
    Returns:
        Dict with parsed chain information
    """
    parser = YouTubeSettingsParser()
    chain = parser.parse_text(text, artist_or_style, track_type)
    device_list = parser.chain_to_device_list(chain)
    
    return {
        "artist_or_style": artist_or_style,
        "track_type": track_type,
        "devices": device_list,
        "device_count": len(device_list),
        "raw_chain": {
            "devices": [
                {
                    "name": d.name,
                    "type": d.device_type,
                    "settings": d.settings,
                    "raw_text": d.raw_text,
                }
                for d in chain.devices
            ]
        }
    }

