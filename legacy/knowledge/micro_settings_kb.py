"""
Micro Settings Knowledge Base

Precise numeric parameter values for artist/era-specific plugin chains.
Replaces vague string-based settings (e.g., "fast", "2-5kHz aggressive") with
exact values that can be directly applied via OSC.

Values are stored in human-readable units and converted to Ableton's normalized
0.0-1.0 range at application time by research_bot._normalize_parameter().
"""

import json
import os
from typing import Dict, Any, Optional, List
from datetime import datetime


# ============================================================================
# CORE MICRO SETTINGS DATABASE
# ============================================================================
# Each entry uses human-readable values with explicit units.
# The normalization layer in research_bot.py handles conversion.

MICRO_SETTINGS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "kanye_west": {
        "donda_vocal": {
            "description": "Kanye Donda era: Aggressive, upfront, compressed vocal",
            "devices": {
                "eq_cleanup": {
                    "device": "EQ Eight",
                    "purpose": "high_pass",
                    "parameters": {
                        "band1_on": True,
                        "band1_type": "high_pass",
                        "band1_freq_hz": 100,
                        "band1_q": 0.71,
                        "band1_gain_db": 0.0,
                    }
                },
                "compressor": {
                    "device": "Compressor",
                    "purpose": "aggressive_compression",
                    "parameters": {
                        "threshold_db": -18.0,
                        "ratio": 8.0,
                        "attack_ms": 5.0,
                        "release_ms": 80.0,
                        "output_gain_db": 6.0,
                        "knee_db": 0.0,
                        "dry_wet_pct": 100.0,
                    }
                },
                "saturation": {
                    "device": "Saturator",
                    "purpose": "character",
                    "parameters": {
                        "drive_db": 8.0,
                        "type": "medium_curve",
                        "dry_wet_pct": 40.0,
                        "output_db": -2.0,
                    }
                },
                "eq_tone": {
                    "device": "EQ Eight",
                    "purpose": "presence_boost",
                    "parameters": {
                        "band1_on": True,
                        "band1_type": "high_pass",
                        "band1_freq_hz": 80,
                        "band1_q": 0.71,
                        "band2_on": True,
                        "band2_type": "bell",
                        "band2_freq_hz": 300,
                        "band2_gain_db": -3.0,
                        "band2_q": 1.0,
                        "band3_on": True,
                        "band3_type": "bell",
                        "band3_freq_hz": 3500,
                        "band3_gain_db": 4.5,
                        "band3_q": 1.2,
                        "band4_on": True,
                        "band4_type": "high_shelf",
                        "band4_freq_hz": 10000,
                        "band4_gain_db": 2.0,
                        "band4_q": 0.8,
                    }
                },
                "delay": {
                    "device": "Delay",
                    "purpose": "rhythmic_space",
                    "parameters": {
                        "delay_time_ms": 250,
                        "feedback_pct": 25.0,
                        "dry_wet_pct": 20.0,
                        "filter_on": True,
                        "filter_freq_hz": 2000,
                    }
                },
                "reverb": {
                    "device": "Reverb",
                    "purpose": "tight_depth",
                    "parameters": {
                        "decay_time_ms": 1200,
                        "predelay_ms": 30,
                        "dry_wet_pct": 12.0,
                        "room_size": 0.4,
                        "high_cut_hz": 6000,
                    }
                },
            }
        },
        "yeezus_vocal": {
            "description": "Kanye Yeezus era: Industrial, distorted, aggressive vocal",
            "devices": {
                "eq_cleanup": {
                    "device": "EQ Eight",
                    "purpose": "high_pass",
                    "parameters": {
                        "band1_on": True,
                        "band1_type": "high_pass",
                        "band1_freq_hz": 120,
                        "band1_q": 0.71,
                    }
                },
                "compressor": {
                    "device": "Compressor",
                    "purpose": "crushing_compression",
                    "parameters": {
                        "threshold_db": -24.0,
                        "ratio": 12.0,
                        "attack_ms": 1.0,
                        "release_ms": 50.0,
                        "output_gain_db": 8.0,
                        "dry_wet_pct": 100.0,
                    }
                },
                "saturation": {
                    "device": "Saturator",
                    "purpose": "heavy_distortion",
                    "parameters": {
                        "drive_db": 18.0,
                        "type": "hard_curve",
                        "dry_wet_pct": 60.0,
                        "output_db": -4.0,
                    }
                },
                "eq_tone": {
                    "device": "EQ Eight",
                    "purpose": "harsh_presence",
                    "parameters": {
                        "band2_on": True,
                        "band2_type": "bell",
                        "band2_freq_hz": 2500,
                        "band2_gain_db": 6.0,
                        "band2_q": 0.8,
                        "band3_on": True,
                        "band3_type": "bell",
                        "band3_freq_hz": 5000,
                        "band3_gain_db": 3.0,
                        "band3_q": 1.0,
                    }
                },
            }
        },
        "college_dropout_vocal": {
            "description": "Kanye College Dropout era: Warm, soulful, sped-up vocal character",
            "devices": {
                "eq_cleanup": {
                    "device": "EQ Eight",
                    "purpose": "high_pass",
                    "parameters": {
                        "band1_on": True,
                        "band1_type": "high_pass",
                        "band1_freq_hz": 80,
                        "band1_q": 0.71,
                    }
                },
                "compressor": {
                    "device": "Compressor",
                    "purpose": "smooth_leveling",
                    "parameters": {
                        "threshold_db": -14.0,
                        "ratio": 4.0,
                        "attack_ms": 10.0,
                        "release_ms": 120.0,
                        "output_gain_db": 3.0,
                        "dry_wet_pct": 100.0,
                    }
                },
                "saturation": {
                    "device": "Saturator",
                    "purpose": "warmth",
                    "parameters": {
                        "drive_db": 4.0,
                        "type": "soft_curve",
                        "dry_wet_pct": 30.0,
                    }
                },
                "eq_tone": {
                    "device": "EQ Eight",
                    "purpose": "warm_presence",
                    "parameters": {
                        "band2_on": True,
                        "band2_type": "bell",
                        "band2_freq_hz": 2000,
                        "band2_gain_db": 3.0,
                        "band2_q": 1.5,
                        "band4_on": True,
                        "band4_type": "high_shelf",
                        "band4_freq_hz": 8000,
                        "band4_gain_db": 1.5,
                        "band4_q": 0.71,
                    }
                },
                "reverb": {
                    "device": "Reverb",
                    "purpose": "warm_space",
                    "parameters": {
                        "decay_time_ms": 1800,
                        "predelay_ms": 40,
                        "dry_wet_pct": 18.0,
                        "room_size": 0.5,
                    }
                },
            }
        },
    },
    "billie_eilish": {
        "whisper_vocal": {
            "description": "Billie Eilish: Intimate, breathy, dark reverb, ASMR-like",
            "devices": {
                "eq_cleanup": {
                    "device": "EQ Eight",
                    "purpose": "gentle_high_pass",
                    "parameters": {
                        "band1_on": True,
                        "band1_type": "high_pass",
                        "band1_freq_hz": 60,
                        "band1_q": 0.71,
                    }
                },
                "compressor": {
                    "device": "Compressor",
                    "purpose": "gentle_leveling",
                    "parameters": {
                        "threshold_db": -12.0,
                        "ratio": 2.5,
                        "attack_ms": 15.0,
                        "release_ms": 150.0,
                        "output_gain_db": 2.0,
                        "dry_wet_pct": 100.0,
                    }
                },
                "saturation": {
                    "device": "Saturator",
                    "purpose": "subtle_warmth",
                    "parameters": {
                        "drive_db": 3.0,
                        "type": "soft_curve",
                        "dry_wet_pct": 20.0,
                    }
                },
                "eq_tone": {
                    "device": "EQ Eight",
                    "purpose": "intimacy",
                    "parameters": {
                        "band2_on": True,
                        "band2_type": "bell",
                        "band2_freq_hz": 200,
                        "band2_gain_db": 2.0,
                        "band2_q": 1.0,
                        "band3_on": True,
                        "band3_type": "bell",
                        "band3_freq_hz": 3000,
                        "band3_gain_db": 2.5,
                        "band3_q": 1.5,
                    }
                },
                "reverb": {
                    "device": "Reverb",
                    "purpose": "dark_atmosphere",
                    "parameters": {
                        "decay_time_ms": 3500,
                        "predelay_ms": 50,
                        "dry_wet_pct": 30.0,
                        "room_size": 0.7,
                        "high_cut_hz": 4000,
                    }
                },
                "delay": {
                    "device": "Delay",
                    "purpose": "filtered_depth",
                    "parameters": {
                        "delay_time_ms": 375,
                        "feedback_pct": 30.0,
                        "dry_wet_pct": 15.0,
                        "filter_on": True,
                        "filter_freq_hz": 1500,
                    }
                },
            }
        },
    },
    "the_weeknd": {
        "blinding_lights_vocal": {
            "description": "The Weeknd: Smooth R&B with modern synth-pop sheen",
            "devices": {
                "eq_cleanup": {
                    "device": "EQ Eight",
                    "purpose": "high_pass",
                    "parameters": {
                        "band1_on": True,
                        "band1_type": "high_pass",
                        "band1_freq_hz": 90,
                        "band1_q": 0.71,
                    }
                },
                "compressor": {
                    "device": "Compressor",
                    "purpose": "controlled_dynamics",
                    "parameters": {
                        "threshold_db": -16.0,
                        "ratio": 4.0,
                        "attack_ms": 8.0,
                        "release_ms": 100.0,
                        "output_gain_db": 4.0,
                        "dry_wet_pct": 100.0,
                    }
                },
                "eq_tone": {
                    "device": "EQ Eight",
                    "purpose": "air_and_presence",
                    "parameters": {
                        "band2_on": True,
                        "band2_type": "bell",
                        "band2_freq_hz": 4000,
                        "band2_gain_db": 3.0,
                        "band2_q": 1.2,
                        "band4_on": True,
                        "band4_type": "high_shelf",
                        "band4_freq_hz": 12000,
                        "band4_gain_db": 2.5,
                        "band4_q": 0.71,
                    }
                },
                "reverb": {
                    "device": "Reverb",
                    "purpose": "plate_shine",
                    "parameters": {
                        "decay_time_ms": 1500,
                        "predelay_ms": 25,
                        "dry_wet_pct": 15.0,
                        "room_size": 0.45,
                    }
                },
                "delay": {
                    "device": "Delay",
                    "purpose": "stereo_width",
                    "parameters": {
                        "delay_time_ms": 300,
                        "feedback_pct": 20.0,
                        "dry_wet_pct": 18.0,
                    }
                },
            }
        },
    },
    "drake": {
        "vocal": {
            "description": "Drake: Clean, upfront, modern hip-hop/R&B vocal",
            "devices": {
                "eq_cleanup": {
                    "device": "EQ Eight",
                    "purpose": "high_pass",
                    "parameters": {
                        "band1_on": True,
                        "band1_type": "high_pass",
                        "band1_freq_hz": 100,
                        "band1_q": 0.71,
                    }
                },
                "compressor": {
                    "device": "Compressor",
                    "purpose": "smooth_control",
                    "parameters": {
                        "threshold_db": -15.0,
                        "ratio": 5.0,
                        "attack_ms": 7.0,
                        "release_ms": 90.0,
                        "output_gain_db": 4.0,
                        "dry_wet_pct": 100.0,
                    }
                },
                "eq_tone": {
                    "device": "EQ Eight",
                    "purpose": "clarity_and_presence",
                    "parameters": {
                        "band2_on": True,
                        "band2_type": "bell",
                        "band2_freq_hz": 250,
                        "band2_gain_db": -2.5,
                        "band2_q": 1.2,
                        "band3_on": True,
                        "band3_type": "bell",
                        "band3_freq_hz": 3000,
                        "band3_gain_db": 3.5,
                        "band3_q": 1.0,
                        "band4_on": True,
                        "band4_type": "high_shelf",
                        "band4_freq_hz": 10000,
                        "band4_gain_db": 1.5,
                        "band4_q": 0.71,
                    }
                },
                "delay": {
                    "device": "Delay",
                    "purpose": "subtle_space",
                    "parameters": {
                        "delay_time_ms": 200,
                        "feedback_pct": 15.0,
                        "dry_wet_pct": 12.0,
                    }
                },
                "reverb": {
                    "device": "Reverb",
                    "purpose": "tight_ambience",
                    "parameters": {
                        "decay_time_ms": 800,
                        "predelay_ms": 20,
                        "dry_wet_pct": 10.0,
                        "room_size": 0.3,
                    }
                },
            }
        },
    },
    "travis_scott": {
        "vocal": {
            "description": "Travis Scott: Heavy autotune, dark reverb, psychedelic effects",
            "devices": {
                "eq_cleanup": {
                    "device": "EQ Eight",
                    "purpose": "high_pass",
                    "parameters": {
                        "band1_on": True,
                        "band1_type": "high_pass",
                        "band1_freq_hz": 110,
                        "band1_q": 0.71,
                    }
                },
                "compressor": {
                    "device": "Compressor",
                    "purpose": "heavy_compression",
                    "parameters": {
                        "threshold_db": -20.0,
                        "ratio": 6.0,
                        "attack_ms": 3.0,
                        "release_ms": 60.0,
                        "output_gain_db": 5.0,
                        "dry_wet_pct": 100.0,
                    }
                },
                "saturation": {
                    "device": "Saturator",
                    "purpose": "dark_grit",
                    "parameters": {
                        "drive_db": 10.0,
                        "type": "medium_curve",
                        "dry_wet_pct": 45.0,
                        "output_db": -3.0,
                    }
                },
                "eq_tone": {
                    "device": "EQ Eight",
                    "purpose": "dark_presence",
                    "parameters": {
                        "band2_on": True,
                        "band2_type": "bell",
                        "band2_freq_hz": 400,
                        "band2_gain_db": -3.0,
                        "band2_q": 0.8,
                        "band3_on": True,
                        "band3_type": "bell",
                        "band3_freq_hz": 2500,
                        "band3_gain_db": 4.0,
                        "band3_q": 1.0,
                    }
                },
                "reverb": {
                    "device": "Reverb",
                    "purpose": "psychedelic_space",
                    "parameters": {
                        "decay_time_ms": 4000,
                        "predelay_ms": 60,
                        "dry_wet_pct": 35.0,
                        "room_size": 0.8,
                        "high_cut_hz": 5000,
                    }
                },
                "delay": {
                    "device": "Delay",
                    "purpose": "trippy_echoes",
                    "parameters": {
                        "delay_time_ms": 500,
                        "feedback_pct": 40.0,
                        "dry_wet_pct": 25.0,
                        "filter_on": True,
                        "filter_freq_hz": 2500,
                    }
                },
            }
        },
    },
    "modern_pop": {
        "vocal": {
            "description": "Modern pop: Polished, upfront, presence and air",
            "devices": {
                "eq_cleanup": {
                    "device": "EQ Eight",
                    "purpose": "high_pass",
                    "parameters": {
                        "band1_on": True,
                        "band1_type": "high_pass",
                        "band1_freq_hz": 80,
                        "band1_q": 0.71,
                    }
                },
                "compressor": {
                    "device": "Compressor",
                    "purpose": "leveling",
                    "parameters": {
                        "threshold_db": -14.0,
                        "ratio": 4.0,
                        "attack_ms": 8.0,
                        "release_ms": 100.0,
                        "output_gain_db": 3.0,
                        "dry_wet_pct": 100.0,
                    }
                },
                "eq_tone": {
                    "device": "EQ Eight",
                    "purpose": "presence_and_air",
                    "parameters": {
                        "band2_on": True,
                        "band2_type": "bell",
                        "band2_freq_hz": 3500,
                        "band2_gain_db": 3.0,
                        "band2_q": 1.2,
                        "band4_on": True,
                        "band4_type": "high_shelf",
                        "band4_freq_hz": 10000,
                        "band4_gain_db": 2.5,
                        "band4_q": 0.71,
                    }
                },
                "reverb": {
                    "device": "Reverb",
                    "purpose": "polish",
                    "parameters": {
                        "decay_time_ms": 1000,
                        "predelay_ms": 20,
                        "dry_wet_pct": 12.0,
                        "room_size": 0.35,
                    }
                },
            }
        },
    },
    "hip_hop": {
        "vocal": {
            "description": "Hip hop: Punchy, upfront with grit",
            "devices": {
                "eq_cleanup": {
                    "device": "EQ Eight",
                    "purpose": "high_pass",
                    "parameters": {
                        "band1_on": True,
                        "band1_type": "high_pass",
                        "band1_freq_hz": 100,
                        "band1_q": 0.71,
                    }
                },
                "compressor": {
                    "device": "Compressor",
                    "purpose": "punch",
                    "parameters": {
                        "threshold_db": -16.0,
                        "ratio": 6.0,
                        "attack_ms": 5.0,
                        "release_ms": 70.0,
                        "output_gain_db": 5.0,
                        "dry_wet_pct": 100.0,
                    }
                },
                "saturation": {
                    "device": "Saturator",
                    "purpose": "grit",
                    "parameters": {
                        "drive_db": 6.0,
                        "type": "medium_curve",
                        "dry_wet_pct": 35.0,
                    }
                },
                "eq_tone": {
                    "device": "EQ Eight",
                    "purpose": "presence",
                    "parameters": {
                        "band2_on": True,
                        "band2_type": "bell",
                        "band2_freq_hz": 3000,
                        "band2_gain_db": 4.0,
                        "band2_q": 1.0,
                    }
                },
                "delay": {
                    "device": "Delay",
                    "purpose": "space",
                    "parameters": {
                        "delay_time_ms": 250,
                        "feedback_pct": 20.0,
                        "dry_wet_pct": 15.0,
                    }
                },
            }
        },
        "drums": {
            "description": "Hip hop drums: Punchy, heavy, saturated",
            "devices": {
                "eq_shape": {
                    "device": "EQ Eight",
                    "purpose": "weight_and_snap",
                    "parameters": {
                        "band1_on": True,
                        "band1_type": "bell",
                        "band1_freq_hz": 60,
                        "band1_gain_db": 3.0,
                        "band1_q": 1.0,
                        "band3_on": True,
                        "band3_type": "bell",
                        "band3_freq_hz": 4000,
                        "band3_gain_db": 2.0,
                        "band3_q": 1.2,
                    }
                },
                "compressor": {
                    "device": "Glue Compressor",
                    "purpose": "glue",
                    "parameters": {
                        "threshold_db": -12.0,
                        "ratio": 4.0,
                        "attack_ms": 10.0,
                        "release_ms": 100.0,
                        "makeup_gain_db": 3.0,
                        "dry_wet_pct": 100.0,
                    }
                },
                "saturation": {
                    "device": "Saturator",
                    "purpose": "punch",
                    "parameters": {
                        "drive_db": 8.0,
                        "type": "medium_curve",
                        "dry_wet_pct": 50.0,
                    }
                },
            }
        },
    },
    "rock": {
        "vocal": {
            "description": "Rock vocal: Powerful with edge, aggressive compression",
            "devices": {
                "eq_cleanup": {
                    "device": "EQ Eight",
                    "purpose": "high_pass",
                    "parameters": {
                        "band1_on": True,
                        "band1_type": "high_pass",
                        "band1_freq_hz": 120,
                        "band1_q": 0.71,
                    }
                },
                "compressor": {
                    "device": "Compressor",
                    "purpose": "aggressive",
                    "parameters": {
                        "threshold_db": -18.0,
                        "ratio": 8.0,
                        "attack_ms": 3.0,
                        "release_ms": 60.0,
                        "output_gain_db": 6.0,
                        "dry_wet_pct": 100.0,
                    }
                },
                "saturation": {
                    "device": "Saturator",
                    "purpose": "edge",
                    "parameters": {
                        "drive_db": 6.0,
                        "type": "medium_curve",
                        "dry_wet_pct": 30.0,
                    }
                },
                "eq_tone": {
                    "device": "EQ Eight",
                    "purpose": "cut_through",
                    "parameters": {
                        "band2_on": True,
                        "band2_type": "bell",
                        "band2_freq_hz": 3000,
                        "band2_gain_db": 3.5,
                        "band2_q": 1.0,
                    }
                },
                "reverb": {
                    "device": "Reverb",
                    "purpose": "room",
                    "parameters": {
                        "decay_time_ms": 1200,
                        "predelay_ms": 15,
                        "dry_wet_pct": 15.0,
                        "room_size": 0.4,
                    }
                },
            }
        },
    },
}


# ============================================================================
# 3RD PARTY PLUGIN PREFERENCES
# ============================================================================
# Per-artist/style preferred 3rd party plugins with category and stock fallbacks.
# auto_chain reads these to decide whether to attempt a 3rd party plugin first.
# Format:
#   PLUGIN_PREFERENCES[artist_key][style_key][device_slot] = {
#       "preferred_plugin": "3rd party name",
#       "category": "eq|compressor|reverb|saturator|delay|limiter|multiband",
#       "fallbacks": ["Alternative3rdParty", "StockDevice"],
#   }

PLUGIN_PREFERENCES: Dict[str, Dict[str, Dict[str, Dict[str, Any]]]] = {
    "kanye_west": {
        "donda_vocal": {
            "saturation": {
                "preferred_plugin": "Soundtoys Decapitator",
                "category": "saturator",
                "fallbacks": ["Saturator"],
            },
            "compressor": {
                "preferred_plugin": "CLA-76",
                "category": "compressor",
                "fallbacks": ["FabFilter Pro-C 2", "Glue Compressor", "Compressor"],
                "notes": "CLA-76 Rev A for Kanye's punchy, upfront vocal sound",
            },
            "compressor_2": {
                "preferred_plugin": "CLA-2A",
                "category": "compressor",
                "fallbacks": ["Compressor"],
                "notes": "Second-stage leveling after CLA-76 for serial compression",
            },
            "eq_tone": {
                "preferred_plugin": "FabFilter Pro-Q 3",
                "category": "eq",
                "fallbacks": ["SSL E-Channel", "EQ Eight"],
            },
            "channel_strip": {
                "preferred_plugin": "SSL E-Channel",
                "category": "channel_strip",
                "fallbacks": ["EQ Eight"],
                "notes": "Can replace separate EQ + compressor if used as channel strip",
            },
            "reverb": {
                "preferred_plugin": "H-Reverb",
                "category": "reverb",
                "fallbacks": ["Reverb"],
                "notes": "H-Reverb tight room for Donda vocal depth",
            },
        },
        "yeezus_vocal": {
            "saturation": {
                "preferred_plugin": "Soundtoys Decapitator",
                "category": "saturator",
                "fallbacks": ["Saturator"],
            },
            "compressor": {
                "preferred_plugin": "CLA-76",
                "category": "compressor",
                "fallbacks": ["FabFilter Pro-C 2", "Compressor"],
                "notes": "CLA-76 All Buttons (Brit mode) for extreme Yeezus-era distortion",
            },
        },
        "college_dropout_vocal": {
            "compressor": {
                "preferred_plugin": "CLA-2A",
                "category": "compressor",
                "fallbacks": ["Compressor"],
                "notes": "Smooth optical compression for warm College Dropout soul vocal",
            },
            "reverb": {
                "preferred_plugin": "H-Reverb",
                "category": "reverb",
                "fallbacks": ["Reverb"],
                "notes": "Warm plate-style reverb for soulful vocal space",
            },
        },
    },
    "the_weeknd": {
        "blinding_lights_vocal": {
            "reverb": {
                "preferred_plugin": "H-Reverb",
                "category": "reverb",
                "fallbacks": ["Valhalla Room", "Valhalla VintageVerb", "Reverb"],
                "notes": "H-Reverb plate for polished synth-pop vocal sheen",
            },
            "compressor": {
                "preferred_plugin": "CLA-2A",
                "category": "compressor",
                "fallbacks": ["FabFilter Pro-C 2", "Glue Compressor", "Compressor"],
                "notes": "Smooth optical compression for clean R&B vocal",
            },
            "channel_strip": {
                "preferred_plugin": "SSL E-Channel",
                "category": "channel_strip",
                "fallbacks": ["EQ Eight"],
                "notes": "SSL channel strip for polished modern R&B processing",
            },
        },
    },
    "billie_eilish": {
        "whisper_vocal": {
            "compressor": {
                "preferred_plugin": "CLA-2A",
                "category": "compressor",
                "fallbacks": ["FabFilter Pro-C 2", "Compressor"],
                "notes": "Gentle optical compression preserves breathy intimacy",
            },
            "reverb": {
                "preferred_plugin": "H-Reverb",
                "category": "reverb",
                "fallbacks": ["Valhalla VintageVerb", "Valhalla Room", "Reverb"],
                "notes": "H-Reverb with heavy damping for dark atmospheric reverb",
            },
        },
    },
    "drake": {
        "vocal": {
            "compressor": {
                "preferred_plugin": "CLA-76",
                "category": "compressor",
                "fallbacks": ["CLA-2A", "Compressor"],
                "notes": "CLA-76 Rev E (blackface) for smooth but controlled Drake vocal",
            },
            "channel_strip": {
                "preferred_plugin": "SSL E-Channel",
                "category": "channel_strip",
                "fallbacks": ["EQ Eight"],
                "notes": "SSL E-Channel for clean, upfront hip-hop vocal",
            },
        },
    },
    "travis_scott": {
        "vocal": {
            "compressor": {
                "preferred_plugin": "CLA-76",
                "category": "compressor",
                "fallbacks": ["Compressor"],
                "notes": "CLA-76 for heavy compression before effects chain",
            },
            "reverb": {
                "preferred_plugin": "H-Reverb",
                "category": "reverb",
                "fallbacks": ["Reverb"],
                "notes": "H-Reverb with long decay and heavy damping for dark psychedelic space",
            },
        },
    },
    "hip_hop": {
        "vocal": {
            "compressor": {
                "preferred_plugin": "CLA-76",
                "category": "compressor",
                "fallbacks": ["CLA-2A", "Compressor"],
                "notes": "CLA-76 at 8:1 or 12:1 for punchy hip-hop vocal",
            },
            "compressor_2": {
                "preferred_plugin": "CLA-2A",
                "category": "compressor",
                "fallbacks": ["Compressor"],
                "notes": "CLA-2A after CLA-76 for smooth serial compression",
            },
            "channel_strip": {
                "preferred_plugin": "SSL E-Channel",
                "category": "channel_strip",
                "fallbacks": ["EQ Eight"],
            },
        },
        "drums": {
            "bus_compressor": {
                "preferred_plugin": "SSL G-Master Buss Compressor",
                "category": "compressor",
                "fallbacks": ["Glue Compressor"],
                "notes": "SSL G-Master for drum bus glue — 4:1, fast attack, auto release",
            },
        },
    },
    "rock": {
        "vocal": {
            "compressor": {
                "preferred_plugin": "CLA-76",
                "category": "compressor",
                "fallbacks": ["Compressor"],
                "notes": "CLA-76 Rev A for aggressive rock vocal compression",
            },
            "compressor_2": {
                "preferred_plugin": "CLA-2A",
                "category": "compressor",
                "fallbacks": ["Compressor"],
                "notes": "CLA-2A for second-stage leveling after CLA-76",
            },
            "bus_compressor": {
                "preferred_plugin": "SSL G-Master Buss Compressor",
                "category": "compressor",
                "fallbacks": ["Glue Compressor"],
                "notes": "SSL G-Master for vocal bus or mix bus glue",
            },
        },
    },
    "modern_pop": {
        "vocal": {
            "compressor": {
                "preferred_plugin": "CLA-2A",
                "category": "compressor",
                "fallbacks": ["Compressor"],
                "notes": "Smooth optical compression for polished pop vocal",
            },
            "channel_strip": {
                "preferred_plugin": "SSL E-Channel",
                "category": "channel_strip",
                "fallbacks": ["EQ Eight"],
                "notes": "SSL channel strip for complete pop vocal processing",
            },
            "reverb": {
                "preferred_plugin": "H-Reverb",
                "category": "reverb",
                "fallbacks": ["Reverb"],
                "notes": "H-Reverb plate for polished pop vocal space",
            },
        },
    },
}


# ============================================================================
# WAVES PLUGIN MICRO SETTINGS
# ============================================================================
# Precise numeric presets for Waves plugins, keyed by artist/era.
# These are the actual parameter values to send when a Waves plugin is loaded.
# Parameter names match the Waves plugin parameter names as exposed to the DAW.
# Structure mirrors MICRO_SETTINGS but uses Waves plugin names as device keys.

WAVES_MICRO_SETTINGS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "kanye_west": {
        "donda_vocal": {
            "description": "Kanye Donda era Waves chain: CLA-76 punch → CLA-2A leveling → SSL E-Channel tone → H-Reverb tight room",
            "devices": {
                "compressor": {
                    "device": "CLA-76",
                    "purpose": "aggressive_punch",
                    "parameters": {
                        "Input": 28.0,
                        "Output": 16.0,
                        "Attack": 4.0,
                        "Release": 5.0,
                        "Ratio": 1.0,
                        "Revision": 0.0,
                        "Mix": 100.0,
                    }
                },
                "compressor_2": {
                    "device": "CLA-2A",
                    "purpose": "smooth_leveling",
                    "parameters": {
                        "Peak Reduction": 45.0,
                        "Gain": 52.0,
                        "Mode": 0.0,
                        "Mix": 100.0,
                    }
                },
                "channel_strip": {
                    "device": "SSL E-Channel",
                    "purpose": "eq_and_tone",
                    "parameters": {
                        "HP Freq": 100.0,
                        "LMF Gain": -3.0,
                        "LMF Freq": 350.0,
                        "LMF Q": 1.2,
                        "HMF Gain": 4.0,
                        "HMF Freq": 3500.0,
                        "HMF Q": 1.0,
                        "HF Gain": 2.0,
                        "HF Freq": 10000.0,
                        "EQ On": 1.0,
                        "Dyn On": 0.0,
                    }
                },
                "reverb": {
                    "device": "H-Reverb",
                    "purpose": "tight_depth",
                    "parameters": {
                        "Time": 1.0,
                        "Size": 30.0,
                        "Pre Delay": 25.0,
                        "Damping": 4000.0,
                        "Lo Cut": 300.0,
                        "Hi Cut": 8000.0,
                        "Dry/Wet": 12.0,
                    }
                },
            }
        },
        "yeezus_vocal": {
            "description": "Kanye Yeezus era Waves chain: CLA-76 All-Buttons crushed distortion",
            "devices": {
                "compressor": {
                    "device": "CLA-76",
                    "purpose": "crushed_distortion",
                    "parameters": {
                        "Input": 45.0,
                        "Output": 20.0,
                        "Attack": 7.0,
                        "Release": 7.0,
                        "Ratio": 4.0,
                        "Revision": 0.0,
                        "Mix": 100.0,
                    }
                },
            }
        },
        "college_dropout_vocal": {
            "description": "Kanye College Dropout era Waves chain: CLA-2A smooth warmth → H-Reverb soulful plate",
            "devices": {
                "compressor": {
                    "device": "CLA-2A",
                    "purpose": "warm_leveling",
                    "parameters": {
                        "Peak Reduction": 35.0,
                        "Gain": 48.0,
                        "Mode": 0.0,
                        "Mix": 100.0,
                    }
                },
                "reverb": {
                    "device": "H-Reverb",
                    "purpose": "soulful_plate",
                    "parameters": {
                        "Time": 2.0,
                        "Size": 50.0,
                        "Pre Delay": 40.0,
                        "Damping": 6000.0,
                        "Lo Cut": 200.0,
                        "Dry/Wet": 20.0,
                    }
                },
            }
        },
    },
    "billie_eilish": {
        "whisper_vocal": {
            "description": "Billie Eilish Waves chain: CLA-2A gentle optical → H-Reverb dark atmosphere",
            "devices": {
                "compressor": {
                    "device": "CLA-2A",
                    "purpose": "gentle_optical",
                    "parameters": {
                        "Peak Reduction": 30.0,
                        "Gain": 45.0,
                        "Mode": 0.0,
                        "Mix": 100.0,
                    }
                },
                "reverb": {
                    "device": "H-Reverb",
                    "purpose": "dark_atmosphere",
                    "parameters": {
                        "Time": 3.5,
                        "Size": 70.0,
                        "Pre Delay": 50.0,
                        "Damping": 2500.0,
                        "Lo Cut": 150.0,
                        "Hi Cut": 5000.0,
                        "Dry/Wet": 30.0,
                    }
                },
            }
        },
    },
    "the_weeknd": {
        "blinding_lights_vocal": {
            "description": "The Weeknd Waves chain: CLA-2A smooth R&B → SSL E-Channel polish → H-Reverb plate shine",
            "devices": {
                "compressor": {
                    "device": "CLA-2A",
                    "purpose": "smooth_rnb",
                    "parameters": {
                        "Peak Reduction": 38.0,
                        "Gain": 50.0,
                        "Mode": 0.0,
                        "Mix": 100.0,
                    }
                },
                "channel_strip": {
                    "device": "SSL E-Channel",
                    "purpose": "polish_and_air",
                    "parameters": {
                        "HP Freq": 90.0,
                        "LMF Gain": -2.0,
                        "LMF Freq": 300.0,
                        "LMF Q": 1.0,
                        "HMF Gain": 3.0,
                        "HMF Freq": 4000.0,
                        "HMF Q": 1.2,
                        "HF Gain": 2.5,
                        "HF Freq": 12000.0,
                        "HF Bell": 0.0,
                        "EQ On": 1.0,
                        "Dyn On": 0.0,
                    }
                },
                "reverb": {
                    "device": "H-Reverb",
                    "purpose": "plate_shine",
                    "parameters": {
                        "Time": 1.8,
                        "Size": 50.0,
                        "Pre Delay": 35.0,
                        "Damping": 7000.0,
                        "Lo Cut": 250.0,
                        "Dry/Wet": 22.0,
                    }
                },
            }
        },
    },
    "drake": {
        "vocal": {
            "description": "Drake Waves chain: CLA-76 Rev E smooth control → SSL E-Channel clarity",
            "devices": {
                "compressor": {
                    "device": "CLA-76",
                    "purpose": "smooth_control",
                    "parameters": {
                        "Input": 22.0,
                        "Output": 14.0,
                        "Attack": 3.0,
                        "Release": 4.0,
                        "Ratio": 1.0,
                        "Revision": 1.0,
                        "Mix": 100.0,
                    }
                },
                "channel_strip": {
                    "device": "SSL E-Channel",
                    "purpose": "clarity_and_presence",
                    "parameters": {
                        "HP Freq": 100.0,
                        "LMF Gain": -2.5,
                        "LMF Freq": 280.0,
                        "LMF Q": 1.0,
                        "HMF Gain": 3.5,
                        "HMF Freq": 3000.0,
                        "HMF Q": 1.0,
                        "HF Gain": 1.5,
                        "HF Freq": 10000.0,
                        "EQ On": 1.0,
                        "Dyn On": 0.0,
                    }
                },
            }
        },
    },
    "travis_scott": {
        "vocal": {
            "description": "Travis Scott Waves chain: CLA-76 heavy compression → H-Reverb dark psychedelic space",
            "devices": {
                "compressor": {
                    "device": "CLA-76",
                    "purpose": "heavy_compression",
                    "parameters": {
                        "Input": 35.0,
                        "Output": 18.0,
                        "Attack": 5.0,
                        "Release": 6.0,
                        "Ratio": 2.0,
                        "Revision": 0.0,
                        "Mix": 100.0,
                    }
                },
                "reverb": {
                    "device": "H-Reverb",
                    "purpose": "dark_psychedelic",
                    "parameters": {
                        "Time": 4.0,
                        "Size": 75.0,
                        "Pre Delay": 55.0,
                        "Damping": 2000.0,
                        "Lo Cut": 200.0,
                        "Hi Cut": 5000.0,
                        "Dry/Wet": 32.0,
                    }
                },
            }
        },
    },
    "hip_hop": {
        "vocal": {
            "description": "Generic hip-hop Waves vocal chain: CLA-76 punch → CLA-2A leveling → SSL E-Channel presence",
            "devices": {
                "compressor": {
                    "device": "CLA-76",
                    "purpose": "punch",
                    "parameters": {
                        "Input": 25.0,
                        "Output": 15.0,
                        "Attack": 4.0,
                        "Release": 5.0,
                        "Ratio": 1.0,
                        "Revision": 0.0,
                        "Mix": 100.0,
                    }
                },
                "compressor_2": {
                    "device": "CLA-2A",
                    "purpose": "leveling",
                    "parameters": {
                        "Peak Reduction": 40.0,
                        "Gain": 50.0,
                        "Mode": 0.0,
                        "Mix": 100.0,
                    }
                },
                "channel_strip": {
                    "device": "SSL E-Channel",
                    "purpose": "presence",
                    "parameters": {
                        "HP Freq": 100.0,
                        "LMF Gain": -3.0,
                        "LMF Freq": 350.0,
                        "LMF Q": 1.0,
                        "HMF Gain": 3.5,
                        "HMF Freq": 3000.0,
                        "HMF Q": 1.0,
                        "EQ On": 1.0,
                        "Dyn On": 0.0,
                    }
                },
            }
        },
        "drums": {
            "description": "Hip-hop drum bus Waves chain: SSL G-Master glue",
            "devices": {
                "bus_compressor": {
                    "device": "SSL G-Master Buss Compressor",
                    "purpose": "drum_bus_glue",
                    "parameters": {
                        "Threshold": -8.0,
                        "Ratio": 1.0,
                        "Attack": 3.0,
                        "Release": 4.0,
                        "Makeup": 2.0,
                    }
                },
            }
        },
    },
    "rock": {
        "vocal": {
            "description": "Rock Waves vocal chain: CLA-76 Rev A aggressive → CLA-2A leveling → SSL G-Master bus glue",
            "devices": {
                "compressor": {
                    "device": "CLA-76",
                    "purpose": "aggressive_rock",
                    "parameters": {
                        "Input": 32.0,
                        "Output": 18.0,
                        "Attack": 5.0,
                        "Release": 5.0,
                        "Ratio": 2.0,
                        "Revision": 0.0,
                        "Mix": 100.0,
                    }
                },
                "compressor_2": {
                    "device": "CLA-2A",
                    "purpose": "leveling",
                    "parameters": {
                        "Peak Reduction": 42.0,
                        "Gain": 50.0,
                        "Mode": 0.0,
                        "Mix": 100.0,
                    }
                },
                "bus_compressor": {
                    "device": "SSL G-Master Buss Compressor",
                    "purpose": "vocal_bus_glue",
                    "parameters": {
                        "Threshold": -6.0,
                        "Ratio": 0.0,
                        "Attack": 4.0,
                        "Release": 4.0,
                        "Makeup": 1.5,
                    }
                },
            }
        },
    },
    "modern_pop": {
        "vocal": {
            "description": "Modern pop Waves vocal chain: CLA-2A polish → SSL E-Channel clarity → H-Reverb plate",
            "devices": {
                "compressor": {
                    "device": "CLA-2A",
                    "purpose": "polished_leveling",
                    "parameters": {
                        "Peak Reduction": 36.0,
                        "Gain": 48.0,
                        "Mode": 0.0,
                        "Mix": 100.0,
                    }
                },
                "channel_strip": {
                    "device": "SSL E-Channel",
                    "purpose": "clarity_and_air",
                    "parameters": {
                        "HP Freq": 80.0,
                        "LMF Gain": -2.0,
                        "LMF Freq": 300.0,
                        "LMF Q": 1.2,
                        "HMF Gain": 2.5,
                        "HMF Freq": 3500.0,
                        "HMF Q": 1.0,
                        "HF Gain": 2.5,
                        "HF Freq": 10000.0,
                        "HF Bell": 0.0,
                        "EQ On": 1.0,
                        "Dyn On": 0.0,
                    }
                },
                "reverb": {
                    "device": "H-Reverb",
                    "purpose": "polished_plate",
                    "parameters": {
                        "Time": 1.6,
                        "Size": 45.0,
                        "Pre Delay": 35.0,
                        "Damping": 7000.0,
                        "Lo Cut": 250.0,
                        "Dry/Wet": 18.0,
                    }
                },
            }
        },
    },
}


# ============================================================================
# ARTIST NAME ALIASES
# ============================================================================
ARTIST_ALIASES: Dict[str, str] = {
    "kanye": "kanye_west",
    "ye": "kanye_west",
    "billie": "billie_eilish",
    "weeknd": "the_weeknd",
    "abel": "the_weeknd",
    "drizzy": "drake",
    "travis": "travis_scott",
    "la flame": "travis_scott",
}

# ============================================================================
# ERA/STYLE ALIASES
# ============================================================================
STYLE_ALIASES: Dict[str, Dict[str, str]] = {
    "kanye_west": {
        "donda": "donda_vocal",
        "vultures": "donda_vocal",
        "yeezus": "yeezus_vocal",
        "college dropout": "college_dropout_vocal",
        "graduation": "college_dropout_vocal",
        "808s": "yeezus_vocal",
        "vocal": "donda_vocal",
    },
    "billie_eilish": {
        "vocal": "whisper_vocal",
        "whisper": "whisper_vocal",
        "when we all fall asleep": "whisper_vocal",
    },
    "the_weeknd": {
        "vocal": "blinding_lights_vocal",
        "after hours": "blinding_lights_vocal",
        "blinding lights": "blinding_lights_vocal",
    },
    "drake": {
        "vocal": "vocal",
    },
    "travis_scott": {
        "vocal": "vocal",
        "astroworld": "vocal",
        "rodeo": "vocal",
    },
    "modern_pop": {
        "vocal": "vocal",
    },
    "hip_hop": {
        "vocal": "vocal",
        "drums": "drums",
    },
    "rock": {
        "vocal": "vocal",
    },
}


# ============================================================================
# CACHE PATH
# ============================================================================
CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "micro_settings_cache.json")


class MicroSettingsKB:
    """Knowledge base for precise plugin parameter settings."""

    def __init__(self):
        self._cache = self._load_cache()

    def _load_cache(self) -> Dict:
        """Load cached research-augmented settings from disk."""
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def _save_cache(self):
        """Persist the cache to disk."""
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump(self._cache, f, indent=2)

    def resolve_artist(self, artist_or_style: str) -> str:
        """Resolve an artist name/alias to the canonical key."""
        key = artist_or_style.lower().strip().replace(" ", "_")
        if key in MICRO_SETTINGS:
            return key
        if key in ARTIST_ALIASES:
            return ARTIST_ALIASES[key]
        # Fuzzy substring match
        for alias, canonical in ARTIST_ALIASES.items():
            if alias in key or key in alias:
                return canonical
        for canonical_key in MICRO_SETTINGS:
            if canonical_key.replace("_", " ") in artist_or_style.lower():
                return canonical_key
        return key

    def resolve_style(self, artist_key: str, style_hint: str, track_type: str = "vocal") -> Optional[str]:
        """Resolve a style/era hint to the canonical style key."""
        style_lower = style_hint.lower().strip() if style_hint else track_type.lower()
        aliases = STYLE_ALIASES.get(artist_key, {})

        # Direct match
        if style_lower in aliases:
            return aliases[style_lower]

        # Substring match
        for alias, canonical in aliases.items():
            if alias in style_lower or style_lower in alias:
                return canonical

        # Fall back to track_type match
        if track_type.lower() in aliases:
            return aliases[track_type.lower()]

        return None

    def get_settings(self, artist_or_style: str, style_hint: str = "",
                     track_type: str = "vocal") -> Optional[Dict[str, Any]]:
        """
        Look up precise micro settings for an artist/style/era.

        Returns:
            Dict with 'description' and 'devices' if found, else None.
        """
        artist_key = self.resolve_artist(artist_or_style)

        # Check cache first (research-augmented entries)
        cache_key = f"{artist_key}_{style_hint}_{track_type}".lower()
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if entry.get("confidence", 0) >= 0.7:
                return entry.get("settings")

        # Check built-in database
        artist_data = MICRO_SETTINGS.get(artist_key)
        if not artist_data:
            return None

        style_key = self.resolve_style(artist_key, style_hint, track_type)
        if style_key and style_key in artist_data:
            return artist_data[style_key]

        # Try any key containing the track_type
        for key, data in artist_data.items():
            if track_type.lower() in key.lower():
                return data

        return None

    def store_researched_settings(self, artist_or_style: str, style_hint: str,
                                  track_type: str, settings: Dict[str, Any],
                                  confidence: float, sources: List[str]):
        """Store settings discovered via web research into the cache."""
        cache_key = f"{self.resolve_artist(artist_or_style)}_{style_hint}_{track_type}".lower()
        self._cache[cache_key] = {
            "settings": settings,
            "confidence": confidence,
            "sources": sources,
            "cached_at": datetime.now().isoformat(),
        }
        self._save_cache()

    def get_plugin_preferences(self, artist_or_style: str, style_hint: str = "",
                                track_type: str = "vocal") -> Dict[str, Dict[str, Any]]:
        """
        Get 3rd party plugin preferences for an artist/style.

        Returns:
            Dict mapping device_slot → {"preferred_plugin", "category", "fallbacks"}
            Empty dict if no preferences defined.
        """
        artist_key = self.resolve_artist(artist_or_style)
        style_key = self.resolve_style(artist_key, style_hint, track_type)

        artist_prefs = PLUGIN_PREFERENCES.get(artist_key, {})
        if style_key and style_key in artist_prefs:
            return artist_prefs[style_key]

        # Try any key containing the track_type
        for key, prefs in artist_prefs.items():
            if track_type.lower() in key.lower():
                return prefs

        return {}

    def get_waves_settings(self, artist_or_style: str, style_hint: str = "",
                           track_type: str = "vocal") -> Optional[Dict[str, Any]]:
        """
        Look up Waves-specific micro settings for an artist/style/era.

        Returns:
            Dict with 'description' and 'devices' (keyed by Waves plugin names)
            if found, else None.
        """
        artist_key = self.resolve_artist(artist_or_style)

        artist_data = WAVES_MICRO_SETTINGS.get(artist_key)
        if not artist_data:
            return None

        style_key = self.resolve_style(artist_key, style_hint, track_type)
        if style_key and style_key in artist_data:
            return artist_data[style_key]

        # Try any key containing the track_type
        for key, data in artist_data.items():
            if track_type.lower() in key.lower():
                return data

        return None

    def list_available(self) -> Dict[str, List[str]]:
        """List all available artist/style combinations."""
        result = {}
        for artist_key, styles in MICRO_SETTINGS.items():
            result[artist_key] = list(styles.keys())
        return result


# Singleton
_kb_instance: Optional[MicroSettingsKB] = None


def get_micro_settings_kb() -> MicroSettingsKB:
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = MicroSettingsKB()
    return _kb_instance
