"""
Device Knowledge Base

Maps Ableton Live devices to their parameters with semantic meaning,
audio engineering context, and recommended settings for various use cases.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


@dataclass
class ParameterInfo:
    """Information about a device parameter"""
    index: int
    name: str
    purpose: str
    min_value: float = 0.0
    max_value: float = 1.0
    default_value: float = 0.5
    unit: str = ""
    display_range: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "index": self.index,
            "name": self.name,
            "purpose": self.purpose,
            "min": self.min_value,
            "max": self.max_value,
            "default": self.default_value,
            "unit": self.unit,
            "display_range": self.display_range
        }


@dataclass
class DeviceInfo:
    """Information about an Ableton device"""
    name: str
    category: str
    description: str
    parameters: List[ParameterInfo] = field(default_factory=list)
    presets: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    common_uses: List[str] = field(default_factory=list)
    tips: List[str] = field(default_factory=list)
    
    def get_parameter(self, index: int) -> Optional[ParameterInfo]:
        """Get parameter by index"""
        for param in self.parameters:
            if param.index == index:
                return param
        return None
    
    def get_parameter_by_name(self, name: str) -> Optional[ParameterInfo]:
        """Get parameter by name (case-insensitive partial match)"""
        name_lower = name.lower()
        for param in self.parameters:
            if name_lower in param.name.lower():
                return param
        return None
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "parameters": [p.to_dict() for p in self.parameters],
            "presets": self.presets,
            "common_uses": self.common_uses,
            "tips": self.tips
        }


class DeviceKnowledgeBase:
    """
    Knowledge base for Ableton Live devices and their parameters.
    
    Provides semantic understanding of what each parameter does,
    recommended settings for various purposes, and audio engineering context.
    """
    
    def __init__(self):
        self.devices: Dict[str, DeviceInfo] = {}
        self._load_native_devices()
    
    def _load_native_devices(self):
        """Load knowledge about Ableton's native devices"""
        
        # ==================== EQ EIGHT ====================
        eq_eight = DeviceInfo(
            name="EQ Eight",
            category="eq",
            description="8-band parametric EQ for precise tonal shaping. Each band can be set to different filter types.",
            common_uses=[
                "High-pass filtering to remove low-end rumble",
                "Cutting mud in the 200-400Hz range",
                "Boosting presence at 2-5kHz",
                "Adding air with high shelf at 10kHz+",
                "Surgical removal of problem frequencies"
            ],
            tips=[
                "Cut narrow, boost wide - use high Q for cuts, low Q for boosts",
                "Less is more - subtle moves often sound better",
                "Use the analyzer to visualize frequency content",
                "High-pass almost everything except bass and kick"
            ]
        )
        
        # EQ Eight has 8 bands, each with similar parameters
        # Band 1 parameters start at index 1 (0 is device on/off)
        # Each band has: Frequency, Gain, Q, Filter Type, Active
        for band in range(1, 9):
            base_idx = 1 + (band - 1) * 5  # 5 params per band
            eq_eight.parameters.extend([
                ParameterInfo(
                    index=base_idx,
                    name=f"Band {band} Frequency",
                    purpose=f"Center/cutoff frequency for band {band}",
                    min_value=20.0, max_value=20000.0, default_value=1000.0,
                    unit="Hz", display_range="20Hz - 20kHz"
                ),
                ParameterInfo(
                    index=base_idx + 1,
                    name=f"Band {band} Gain",
                    purpose=f"Boost or cut amount for band {band}",
                    min_value=-15.0, max_value=15.0, default_value=0.0,
                    unit="dB", display_range="-15dB to +15dB"
                ),
                ParameterInfo(
                    index=base_idx + 2,
                    name=f"Band {band} Q",
                    purpose=f"Bandwidth/resonance for band {band}. Lower = wider, higher = narrower",
                    min_value=0.1, max_value=18.0, default_value=0.71,
                    unit="", display_range="0.1 - 18"
                ),
                ParameterInfo(
                    index=base_idx + 3,
                    name=f"Band {band} Type",
                    purpose=f"Filter type: 0=LP48, 1=LP24, 2=LP12, 3=Notch, 4=HP12, 5=HP24, 6=HP48, 7=Bell, 8=LowShelf, 9=HighShelf",
                    min_value=0, max_value=9, default_value=7,
                    unit="", display_range="LP48/LP24/LP12/Notch/HP12/HP24/HP48/Bell/LowShelf/HighShelf"
                ),
                ParameterInfo(
                    index=base_idx + 4,
                    name=f"Band {band} Active",
                    purpose=f"Enable/disable band {band}",
                    min_value=0, max_value=1, default_value=1,
                    unit="", display_range="Off/On"
                ),
            ])
        
        # Add device on/off at index 0
        eq_eight.parameters.insert(0, ParameterInfo(
            index=0,
            name="Device On",
            purpose="Enable/disable the entire device",
            min_value=0, max_value=1, default_value=1,
            unit="", display_range="Off/On"
        ))
        
        # Presets for common purposes
        eq_eight.presets = {
            "high_pass_vocal": {
                "description": "High-pass filter for vocals to remove rumble and proximity effect",
                "settings": {
                    1: 100.0,   # Band 1 Freq: 100Hz
                    2: 0.0,     # Band 1 Gain: 0dB
                    3: 0.71,    # Band 1 Q
                    4: 4,       # Band 1 Type: HP12 (high-pass 12dB/oct)
                    5: 1        # Band 1 Active
                }
            },
            "cut_mud": {
                "description": "Cut low-mid mud around 300Hz",
                "settings": {
                    6: 300.0,   # Band 2 Freq
                    7: -3.0,    # Band 2 Gain: -3dB cut
                    8: 2.0,     # Band 2 Q: moderate width
                    9: 7,       # Band 2 Type: Bell
                    10: 1       # Band 2 Active
                }
            },
            "presence_boost": {
                "description": "Boost presence for vocals/guitars",
                "settings": {
                    11: 3000.0,  # Band 3 Freq
                    12: 2.5,     # Band 3 Gain: +2.5dB
                    13: 1.5,     # Band 3 Q
                    14: 7,       # Band 3 Type: Bell
                    15: 1        # Band 3 Active
                }
            },
            "air_boost": {
                "description": "Add air and sparkle with high shelf",
                "settings": {
                    16: 10000.0,  # Band 4 Freq
                    17: 2.0,      # Band 4 Gain
                    18: 0.71,     # Band 4 Q
                    19: 9,        # Band 4 Type: HighShelf
                    20: 1         # Band 4 Active
                }
            },
            "de_harsh": {
                "description": "Cut harshness in the 2-4kHz range",
                "settings": {
                    21: 3500.0,  # Band 5 Freq
                    22: -2.5,    # Band 5 Gain
                    23: 2.5,     # Band 5 Q
                    24: 7,       # Band 5 Type: Bell
                    25: 1        # Band 5 Active
                }
            },
            "de_sibilance": {
                "description": "Cut sibilance in the 6-8kHz range (manual de-essing)",
                "settings": {
                    26: 7000.0,  # Band 6 Freq
                    27: -3.0,    # Band 6 Gain
                    28: 3.0,     # Band 6 Q: narrow
                    29: 7,       # Band 6 Type: Bell
                    30: 1        # Band 6 Active
                }
            }
        }
        
        self.devices["EQ Eight"] = eq_eight
        self.devices["eq eight"] = eq_eight  # Lowercase alias
        
        # ==================== COMPRESSOR ====================
        compressor = DeviceInfo(
            name="Compressor",
            category="dynamics",
            description="Standard compressor for controlling dynamics. Reduces loud signals and can add punch, sustain, or glue.",
            common_uses=[
                "Controlling vocal dynamics for consistent level",
                "Adding punch to drums with fast attack",
                "Increasing sustain with slow attack",
                "Gluing mix elements together",
                "Parallel compression for punch without losing dynamics"
            ],
            tips=[
                "Faster attack catches transients (less punch), slower attack lets transients through (more punch)",
                "Match release to the tempo - too fast causes pumping, too slow doesn't recover",
                "Aim for 3-6dB of gain reduction for most sources",
                "Use makeup gain to compensate for level reduction",
                "Watch the gain reduction meter, not just your ears"
            ],
            parameters=[
                ParameterInfo(index=0, name="Device On", purpose="Enable/disable device",
                             min_value=0, max_value=1, default_value=1, display_range="Off/On"),
                ParameterInfo(index=1, name="Threshold", purpose="Level where compression starts. Lower = more compression",
                             min_value=-40.0, max_value=0.0, default_value=-20.0, unit="dB", display_range="-40dB to 0dB"),
                ParameterInfo(index=2, name="Ratio", purpose="Amount of gain reduction. 4:1 means 4dB over threshold becomes 1dB",
                             min_value=1.0, max_value=20.0, default_value=4.0, unit=":1", display_range="1:1 to Inf:1"),
                ParameterInfo(index=3, name="Attack", purpose="How fast compression engages. Fast=control, Slow=punch",
                             min_value=0.01, max_value=100.0, default_value=10.0, unit="ms", display_range="0.01ms - 100ms"),
                ParameterInfo(index=4, name="Release", purpose="How fast compression releases. Should match tempo or use Auto",
                             min_value=10.0, max_value=1000.0, default_value=100.0, unit="ms", display_range="10ms - 1000ms"),
                ParameterInfo(index=5, name="Output Gain", purpose="Makeup gain to compensate for level reduction",
                             min_value=-30.0, max_value=30.0, default_value=0.0, unit="dB", display_range="-30dB to +30dB"),
                ParameterInfo(index=6, name="Dry/Wet", purpose="Blend compressed and dry signal (parallel compression)",
                             min_value=0.0, max_value=100.0, default_value=100.0, unit="%", display_range="0% - 100%"),
                ParameterInfo(index=7, name="Knee", purpose="How gradual the compression onset is. Soft=gradual, Hard=abrupt",
                             min_value=0.0, max_value=1.0, default_value=0.0, display_range="Hard to Soft"),
                ParameterInfo(index=8, name="Model", purpose="Compression algorithm: FF1, FF2, FB, or custom",
                             min_value=0, max_value=3, default_value=0, display_range="FF1/FF2/FB/Custom"),
                ParameterInfo(index=9, name="Lookahead", purpose="Anticipate transients for better control",
                             min_value=0, max_value=1, default_value=0, display_range="Off/On"),
            ],
            presets={
                "vocal_control": {
                    "description": "Gentle vocal compression for consistency",
                    "settings": {1: -18.0, 2: 4.0, 3: 15.0, 4: 150.0, 5: 0.0, 6: 100.0}
                },
                "vocal_aggressive": {
                    "description": "Heavier vocal compression for upfront sound",
                    "settings": {1: -24.0, 2: 6.0, 3: 5.0, 4: 100.0, 5: 3.0, 6: 100.0}
                },
                "drum_punch": {
                    "description": "Punchy drum compression - slow attack preserves transients",
                    "settings": {1: -12.0, 2: 4.0, 3: 30.0, 4: 80.0, 5: 0.0, 6: 100.0}
                },
                "drum_smash": {
                    "description": "Heavy drum compression for parallel bus",
                    "settings": {1: -30.0, 2: 10.0, 3: 1.0, 4: 50.0, 5: 6.0, 6: 100.0}
                },
                "bass_control": {
                    "description": "Bass compression for even level",
                    "settings": {1: -16.0, 2: 4.0, 3: 10.0, 4: 150.0, 5: 2.0, 6: 100.0}
                },
                "parallel_crush": {
                    "description": "Heavy compression for parallel blending",
                    "settings": {1: -35.0, 2: 20.0, 3: 0.5, 4: 50.0, 5: 10.0, 6: 50.0}
                },
                "glue": {
                    "description": "Gentle bus compression for glue",
                    "settings": {1: -10.0, 2: 2.0, 3: 20.0, 4: 200.0, 5: 0.0, 6: 100.0}
                }
            }
        )
        
        self.devices["Compressor"] = compressor
        self.devices["compressor"] = compressor
        
        # ==================== GLUE COMPRESSOR ====================
        glue_comp = DeviceInfo(
            name="Glue Compressor",
            category="dynamics",
            description="SSL-style bus compressor. Excellent for gluing elements together on buses and master.",
            common_uses=[
                "Drum bus compression for cohesion",
                "Mix bus compression for glue",
                "Parallel compression via Range control"
            ],
            tips=[
                "The Range control limits maximum gain reduction - great for parallel compression",
                "Attack and Release are fixed values - choose based on tempo",
                "Soft clip adds subtle saturation at high levels"
            ],
            parameters=[
                ParameterInfo(index=0, name="Device On", purpose="Enable/disable device",
                             min_value=0, max_value=1, default_value=1),
                ParameterInfo(index=1, name="Threshold", purpose="Level where compression starts",
                             min_value=-40.0, max_value=0.0, default_value=-10.0, unit="dB"),
                ParameterInfo(index=2, name="Ratio", purpose="2:1, 4:1, or 10:1",
                             min_value=0, max_value=2, default_value=1, display_range="2:1/4:1/10:1"),
                ParameterInfo(index=3, name="Attack", purpose="Fixed attack times",
                             min_value=0, max_value=6, default_value=2, display_range="0.01/0.1/0.3/1/3/10/30 ms"),
                ParameterInfo(index=4, name="Release", purpose="Fixed release times or Auto",
                             min_value=0, max_value=6, default_value=3, display_range="0.1/0.2/0.4/0.6/0.8/1.2/A"),
                ParameterInfo(index=5, name="Makeup", purpose="Makeup gain",
                             min_value=-12.0, max_value=12.0, default_value=0.0, unit="dB"),
                ParameterInfo(index=6, name="Range", purpose="Limits max gain reduction. Lower = more parallel",
                             min_value=-40.0, max_value=0.0, default_value=-40.0, unit="dB"),
                ParameterInfo(index=7, name="Dry/Wet", purpose="Blend for parallel compression",
                             min_value=0.0, max_value=100.0, default_value=100.0, unit="%"),
                ParameterInfo(index=8, name="Soft Clip", purpose="Adds subtle saturation",
                             min_value=0, max_value=1, default_value=0),
            ],
            presets={
                "drum_bus": {
                    "description": "Classic drum bus glue",
                    "settings": {1: -10.0, 2: 1, 3: 2, 4: 3, 5: 0.0, 6: -40.0, 7: 100.0}
                },
                "mix_bus": {
                    "description": "Gentle mix bus glue",
                    "settings": {1: -6.0, 2: 0, 3: 3, 4: 6, 5: 0.0, 6: -40.0, 7: 100.0}
                },
                "parallel_drums": {
                    "description": "Heavy parallel compression via Range",
                    "settings": {1: -30.0, 2: 2, 3: 0, 4: 2, 5: 6.0, 6: -6.0, 7: 100.0}
                }
            }
        )
        
        self.devices["Glue Compressor"] = glue_comp
        self.devices["glue compressor"] = glue_comp
        
        # ==================== REVERB ====================
        reverb = DeviceInfo(
            name="Reverb",
            category="spatial",
            description="Algorithmic reverb for adding space and depth. Use on sends or directly on tracks.",
            common_uses=[
                "Creating sense of space and depth",
                "Blending elements together",
                "Adding dimension to dry recordings",
                "Creating atmosphere and mood"
            ],
            tips=[
                "Use pre-delay to separate the dry signal from reverb (15-50ms for vocals)",
                "More reverb = further back in the mix",
                "Roll off highs for darker, more natural reverb",
                "Use 100% wet on sends, blend with send level"
            ],
            parameters=[
                ParameterInfo(index=0, name="Device On", purpose="Enable/disable device",
                             min_value=0, max_value=1, default_value=1),
                ParameterInfo(index=1, name="Decay Time", purpose="How long the reverb tail lasts",
                             min_value=0.1, max_value=10.0, default_value=2.0, unit="s"),
                ParameterInfo(index=2, name="Size", purpose="Size of the virtual space",
                             min_value=0.0, max_value=100.0, default_value=50.0, unit="%"),
                ParameterInfo(index=3, name="Pre-Delay", purpose="Time before reverb starts. Separates dry signal",
                             min_value=0.0, max_value=250.0, default_value=20.0, unit="ms"),
                ParameterInfo(index=4, name="Reflect", purpose="Level of early reflections",
                             min_value=0.0, max_value=100.0, default_value=50.0, unit="%"),
                ParameterInfo(index=5, name="Diffuse", purpose="Diffusion/density of reverb",
                             min_value=0.0, max_value=100.0, default_value=80.0, unit="%"),
                ParameterInfo(index=6, name="Dry/Wet", purpose="Balance between dry and wet signal",
                             min_value=0.0, max_value=100.0, default_value=30.0, unit="%"),
                ParameterInfo(index=7, name="Stereo", purpose="Stereo width of reverb",
                             min_value=0.0, max_value=120.0, default_value=100.0, unit="%"),
                ParameterInfo(index=8, name="Hi Shelf Freq", purpose="High frequency shelving EQ",
                             min_value=500.0, max_value=16000.0, default_value=4500.0, unit="Hz"),
                ParameterInfo(index=9, name="Hi Shelf Gain", purpose="Damping of high frequencies",
                             min_value=-36.0, max_value=0.0, default_value=-6.0, unit="dB"),
            ],
            presets={
                "vocal_plate": {
                    "description": "Classic plate reverb for vocals",
                    "settings": {1: 1.5, 2: 60.0, 3: 30.0, 4: 50.0, 5: 80.0, 6: 25.0, 7: 100.0, 8: 6000.0, 9: -3.0}
                },
                "drum_room": {
                    "description": "Tight room for drums",
                    "settings": {1: 0.8, 2: 40.0, 3: 10.0, 4: 60.0, 5: 70.0, 6: 20.0, 7: 100.0, 8: 8000.0, 9: 0.0}
                },
                "dark_hall": {
                    "description": "Dark atmospheric hall (Billie Eilish style)",
                    "settings": {1: 4.0, 2: 80.0, 3: 50.0, 4: 40.0, 5: 90.0, 6: 35.0, 7: 100.0, 8: 3000.0, 9: -12.0}
                },
                "short_ambience": {
                    "description": "Short ambient reverb for subtle space",
                    "settings": {1: 0.5, 2: 30.0, 3: 15.0, 4: 50.0, 5: 60.0, 6: 15.0, 7: 100.0, 8: 8000.0, 9: -3.0}
                },
                "send_100wet": {
                    "description": "100% wet for send/return use",
                    "settings": {1: 2.0, 2: 50.0, 3: 25.0, 4: 50.0, 5: 80.0, 6: 100.0, 7: 100.0, 8: 5000.0, 9: -6.0}
                }
            }
        )
        
        self.devices["Reverb"] = reverb
        self.devices["reverb"] = reverb
        
        # ==================== SATURATOR ====================
        saturator = DeviceInfo(
            name="Saturator",
            category="distortion",
            description="Waveshaping distortion for adding warmth, harmonics, and character.",
            common_uses=[
                "Adding warmth to digital recordings",
                "Creating harmonic distortion for color",
                "Tape-style saturation for vintage sound",
                "Soft clipping for limiting"
            ],
            tips=[
                "Subtle saturation can add warmth without obvious distortion",
                "Use the output gain to compensate for level changes",
                "Different curve types (Analog, Soft, etc.) have different characters",
                "Watch for harsh frequencies - may need EQ after"
            ],
            parameters=[
                ParameterInfo(index=0, name="Device On", purpose="Enable/disable device",
                             min_value=0, max_value=1, default_value=1),
                ParameterInfo(index=1, name="Drive", purpose="Amount of saturation/distortion",
                             min_value=0.0, max_value=36.0, default_value=6.0, unit="dB"),
                ParameterInfo(index=2, name="Type", purpose="Saturation curve type",
                             min_value=0, max_value=5, default_value=0, display_range="Analog/Soft/Medium/Hard/Sinoid/Digital"),
                ParameterInfo(index=3, name="Base", purpose="Bass frequency handling",
                             min_value=0.0, max_value=100.0, default_value=50.0, unit="%"),
                ParameterInfo(index=4, name="Output", purpose="Output level compensation",
                             min_value=-36.0, max_value=36.0, default_value=0.0, unit="dB"),
                ParameterInfo(index=5, name="Dry/Wet", purpose="Blend saturated and dry signal",
                             min_value=0.0, max_value=100.0, default_value=100.0, unit="%"),
                ParameterInfo(index=6, name="Soft Clip", purpose="Enable soft clipping on output",
                             min_value=0, max_value=1, default_value=0),
            ],
            presets={
                "subtle_warmth": {
                    "description": "Subtle analog warmth",
                    "settings": {1: 3.0, 2: 0, 3: 50.0, 4: -3.0, 5: 100.0}
                },
                "tape_saturation": {
                    "description": "Tape-style saturation",
                    "settings": {1: 8.0, 2: 1, 3: 60.0, 4: -6.0, 5: 100.0}
                },
                "aggressive_drive": {
                    "description": "More aggressive saturation",
                    "settings": {1: 15.0, 2: 2, 3: 40.0, 4: -10.0, 5: 100.0}
                },
                "parallel_saturation": {
                    "description": "Heavy saturation for parallel blending",
                    "settings": {1: 20.0, 2: 2, 3: 30.0, 4: -12.0, 5: 50.0}
                }
            }
        )
        
        self.devices["Saturator"] = saturator
        self.devices["saturator"] = saturator
        
        # ==================== LIMITER ====================
        limiter = DeviceInfo(
            name="Limiter",
            category="dynamics",
            description="Peak limiter for preventing clipping and increasing loudness.",
            common_uses=[
                "Preventing digital clipping",
                "Increasing perceived loudness",
                "Final limiting on master bus",
                "Catching peaks on individual tracks"
            ],
            tips=[
                "Always leave some headroom - set ceiling to -0.3dB or lower",
                "Watch for pumping or distortion - reduce gain if heard",
                "For streaming, aim for -14 LUFS integrated",
                "Use true peak limiting if available"
            ],
            parameters=[
                ParameterInfo(index=0, name="Device On", purpose="Enable/disable device",
                             min_value=0, max_value=1, default_value=1),
                ParameterInfo(index=1, name="Gain", purpose="Input gain - increases loudness into limiter",
                             min_value=0.0, max_value=36.0, default_value=0.0, unit="dB"),
                ParameterInfo(index=2, name="Ceiling", purpose="Maximum output level. Set to -1dB for safety",
                             min_value=-6.0, max_value=0.0, default_value=-0.3, unit="dB"),
                ParameterInfo(index=3, name="Release", purpose="How fast limiting releases",
                             min_value=0.0, max_value=1000.0, default_value=300.0, unit="ms"),
                ParameterInfo(index=4, name="Lookahead", purpose="Anticipate peaks for cleaner limiting",
                             min_value=0, max_value=1, default_value=1),
            ],
            presets={
                "master_streaming": {
                    "description": "Mastering limiter for streaming (-14 LUFS target)",
                    "settings": {1: 4.0, 2: -1.0, 3: 300.0, 4: 1}
                },
                "master_loud": {
                    "description": "Louder mastering for club/EDM",
                    "settings": {1: 8.0, 2: -0.3, 3: 200.0, 4: 1}
                },
                "track_safety": {
                    "description": "Safety limiter on individual tracks",
                    "settings": {1: 0.0, 2: -1.0, 3: 300.0, 4: 1}
                }
            }
        )
        
        self.devices["Limiter"] = limiter
        self.devices["limiter"] = limiter
        
        # ==================== DELAY ====================
        delay = DeviceInfo(
            name="Delay",
            category="time",
            description="Stereo delay for echoes, rhythmic effects, and spatial depth.",
            common_uses=[
                "Adding depth to vocals",
                "Creating rhythmic echoes",
                "Stereo widening with ping-pong delay",
                "Doubling effect with short delays"
            ],
            tips=[
                "Sync to tempo for rhythmic delays",
                "Use feedback carefully - can build up quickly",
                "Filter the delays to sit better in the mix",
                "Ping-pong adds stereo interest"
            ],
            parameters=[
                ParameterInfo(index=0, name="Device On", purpose="Enable/disable device",
                             min_value=0, max_value=1, default_value=1),
                ParameterInfo(index=1, name="Left Delay Time", purpose="Delay time for left channel",
                             min_value=1.0, max_value=1000.0, default_value=250.0, unit="ms"),
                ParameterInfo(index=2, name="Right Delay Time", purpose="Delay time for right channel",
                             min_value=1.0, max_value=1000.0, default_value=250.0, unit="ms"),
                ParameterInfo(index=3, name="Feedback", purpose="Amount of signal fed back",
                             min_value=0.0, max_value=100.0, default_value=30.0, unit="%"),
                ParameterInfo(index=4, name="Filter", purpose="Low-pass filter on delays",
                             min_value=200.0, max_value=16000.0, default_value=8000.0, unit="Hz"),
                ParameterInfo(index=5, name="Dry/Wet", purpose="Balance between dry and delayed signal",
                             min_value=0.0, max_value=100.0, default_value=25.0, unit="%"),
                ParameterInfo(index=6, name="Ping Pong", purpose="Alternates delays between L/R",
                             min_value=0, max_value=1, default_value=0),
            ],
            presets={
                "vocal_slap": {
                    "description": "Short slap delay for vocals",
                    "settings": {1: 80.0, 2: 80.0, 3: 20.0, 4: 6000.0, 5: 20.0, 6: 0}
                },
                "quarter_note": {
                    "description": "Quarter note rhythmic delay",
                    "settings": {1: 500.0, 2: 500.0, 3: 35.0, 4: 4000.0, 5: 25.0, 6: 0}
                },
                "ping_pong_wide": {
                    "description": "Wide ping-pong delay for stereo interest",
                    "settings": {1: 333.0, 2: 500.0, 3: 40.0, 4: 5000.0, 5: 30.0, 6: 1}
                },
                "atmospheric": {
                    "description": "Dark, filtered atmospheric delay",
                    "settings": {1: 400.0, 2: 600.0, 3: 50.0, 4: 2000.0, 5: 35.0, 6: 1}
                }
            }
        )
        
        self.devices["Delay"] = delay
        self.devices["delay"] = delay
        
        # ==================== UTILITY ====================
        utility = DeviceInfo(
            name="Utility",
            category="utility",
            description="Essential utility device for gain, panning, stereo width, and phase control.",
            common_uses=[
                "Gain staging",
                "Adjusting stereo width",
                "Phase inversion for fixing issues",
                "Mono compatibility checking"
            ],
            tips=[
                "Use for gain staging at the start of chain",
                "Width below 100% narrows stereo, above 100% widens",
                "Use mono mode to check mix compatibility"
            ],
            parameters=[
                ParameterInfo(index=0, name="Device On", purpose="Enable/disable device",
                             min_value=0, max_value=1, default_value=1),
                ParameterInfo(index=1, name="Gain", purpose="Volume adjustment",
                             min_value=-36.0, max_value=35.0, default_value=0.0, unit="dB"),
                ParameterInfo(index=2, name="Width", purpose="Stereo width. 0%=mono, 100%=normal, 200%=wide",
                             min_value=0.0, max_value=400.0, default_value=100.0, unit="%"),
                ParameterInfo(index=3, name="Pan", purpose="Stereo panning",
                             min_value=-50.0, max_value=50.0, default_value=0.0),
                ParameterInfo(index=4, name="Mute", purpose="Mute the output",
                             min_value=0, max_value=1, default_value=0),
                ParameterInfo(index=5, name="Phase Invert Left", purpose="Invert phase of left channel",
                             min_value=0, max_value=1, default_value=0),
                ParameterInfo(index=6, name="Phase Invert Right", purpose="Invert phase of right channel",
                             min_value=0, max_value=1, default_value=0),
                ParameterInfo(index=7, name="Mono", purpose="Convert to mono for compatibility checking",
                             min_value=0, max_value=1, default_value=0),
            ],
            presets={
                "gain_staging": {
                    "description": "Basic gain staging utility",
                    "settings": {1: 0.0, 2: 100.0, 3: 0.0}
                },
                "stereo_widen": {
                    "description": "Widen stereo image",
                    "settings": {1: 0.0, 2: 130.0, 3: 0.0}
                },
                "mono_check": {
                    "description": "Check mono compatibility",
                    "settings": {1: 0.0, 2: 100.0, 3: 0.0, 7: 1}
                },
                "narrow_bass": {
                    "description": "Narrow bass for mono compatibility",
                    "settings": {1: 0.0, 2: 0.0, 3: 0.0}
                }
            }
        )
        
        self.devices["Utility"] = utility
        self.devices["utility"] = utility
        
        # ==================== MULTIBAND DYNAMICS ====================
        multiband = DeviceInfo(
            name="Multiband Dynamics",
            category="dynamics",
            description="3-band multiband compressor/expander. Can be configured as a de-esser.",
            common_uses=[
                "Multiband compression for mastering",
                "De-essing vocals (compress high band)",
                "Controlling low end independently",
                "Parallel multiband compression"
            ],
            tips=[
                "For de-essing, set high band to 5-8kHz and compress only that band",
                "Be careful with crossover settings - can cause phase issues",
                "Use the solo buttons to hear each band",
                "Gentle settings usually work better than aggressive"
            ],
            parameters=[
                ParameterInfo(index=0, name="Device On", purpose="Enable/disable device",
                             min_value=0, max_value=1, default_value=1),
                # Low band
                ParameterInfo(index=1, name="Low Threshold Above", purpose="Compression threshold for low band",
                             min_value=-36.0, max_value=0.0, default_value=-12.0, unit="dB"),
                ParameterInfo(index=2, name="Low Ratio Above", purpose="Compression ratio for low band",
                             min_value=1.0, max_value=16.0, default_value=2.0),
                # Mid band  
                ParameterInfo(index=3, name="Mid Threshold Above", purpose="Compression threshold for mid band",
                             min_value=-36.0, max_value=0.0, default_value=-12.0, unit="dB"),
                ParameterInfo(index=4, name="Mid Ratio Above", purpose="Compression ratio for mid band",
                             min_value=1.0, max_value=16.0, default_value=2.0),
                # High band
                ParameterInfo(index=5, name="High Threshold Above", purpose="Compression threshold for high band",
                             min_value=-36.0, max_value=0.0, default_value=-12.0, unit="dB"),
                ParameterInfo(index=6, name="High Ratio Above", purpose="Compression ratio for high band",
                             min_value=1.0, max_value=16.0, default_value=2.0),
                # Crossovers
                ParameterInfo(index=7, name="Low Crossover", purpose="Crossover between low and mid bands",
                             min_value=50.0, max_value=8000.0, default_value=250.0, unit="Hz"),
                ParameterInfo(index=8, name="High Crossover", purpose="Crossover between mid and high bands",
                             min_value=200.0, max_value=16000.0, default_value=2500.0, unit="Hz"),
            ],
            presets={
                "de_esser": {
                    "description": "De-essing configuration (compress 5-8kHz)",
                    "settings": {1: 0.0, 2: 1.0, 3: 0.0, 4: 1.0, 5: -24.0, 6: 4.0, 7: 250.0, 8: 5000.0}
                },
                "mastering_gentle": {
                    "description": "Gentle multiband for mastering",
                    "settings": {1: -18.0, 2: 2.0, 3: -18.0, 4: 2.0, 5: -18.0, 6: 2.0, 7: 200.0, 8: 3000.0}
                },
                "bass_control": {
                    "description": "Control low end only",
                    "settings": {1: -15.0, 2: 3.0, 3: 0.0, 4: 1.0, 5: 0.0, 6: 1.0, 7: 200.0, 8: 3000.0}
                }
            }
        )
        
        self.devices["Multiband Dynamics"] = multiband
        self.devices["multiband dynamics"] = multiband
    
    # ==================== QUERY METHODS ====================
    
    def get_device(self, name: str) -> Optional[DeviceInfo]:
        """Get device information by name"""
        # Try exact match first
        if name in self.devices:
            return self.devices[name]
        
        # Try lowercase
        if name.lower() in self.devices:
            return self.devices[name.lower()]
        
        # Try partial match
        name_lower = name.lower()
        for device_name, device_info in self.devices.items():
            if name_lower in device_name.lower() or device_name.lower() in name_lower:
                return device_info
        
        return None
    
    def get_parameter(self, device_name: str, param_index: int) -> Optional[ParameterInfo]:
        """Get parameter information by device name and parameter index"""
        device = self.get_device(device_name)
        if device:
            return device.get_parameter(param_index)
        return None
    
    def get_preset(self, device_name: str, preset_name: str) -> Optional[Dict]:
        """Get a preset configuration"""
        device = self.get_device(device_name)
        if device and preset_name in device.presets:
            return device.presets[preset_name]
        return None
    
    def search_presets(self, query: str) -> List[Dict]:
        """Search for presets matching a query"""
        query_lower = query.lower()
        results = []
        
        for device_name, device in self.devices.items():
            if isinstance(device, DeviceInfo):
                for preset_name, preset_data in device.presets.items():
                    if (query_lower in preset_name.lower() or 
                        query_lower in preset_data.get("description", "").lower()):
                        results.append({
                            "device": device.name,
                            "preset": preset_name,
                            "description": preset_data.get("description", ""),
                            "settings": preset_data.get("settings", {})
                        })
        
        return results
    
    def list_devices(self) -> List[str]:
        """List all known devices"""
        # Return unique device names (exclude lowercase aliases)
        seen = set()
        result = []
        for name, device in self.devices.items():
            if isinstance(device, DeviceInfo) and device.name not in seen:
                seen.add(device.name)
                result.append(device.name)
        return result
    
    def get_category_devices(self, category: str) -> List[DeviceInfo]:
        """Get all devices in a category"""
        seen = set()
        results = []
        for device in self.devices.values():
            if isinstance(device, DeviceInfo) and device.category == category.lower():
                if device.name not in seen:
                    seen.add(device.name)
                    results.append(device)
        return results


# Global instance
device_kb = DeviceKnowledgeBase()


def get_device_kb() -> DeviceKnowledgeBase:
    """Get the global device knowledge base instance"""
    return device_kb

