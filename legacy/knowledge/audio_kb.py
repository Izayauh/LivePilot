"""
Audio Engineering Knowledge Base

Pre-loaded production knowledge for the AI Audio Engineer.
This provides the foundation of audio engineering understanding.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


@dataclass
class Technique:
    """Represents an audio production technique"""
    name: str
    description: str
    category: str
    use_cases: List[str] = field(default_factory=list)
    steps: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    related_techniques: List[str] = field(default_factory=list)
    genre_specific: List[str] = field(default_factory=list)


@dataclass  
class Effect:
    """Represents an audio effect/plugin"""
    name: str
    category: str
    ableton_name: str
    parameters: Dict[str, Dict] = field(default_factory=dict)
    common_uses: List[str] = field(default_factory=list)


class AudioKnowledgeBase:
    """
    Comprehensive audio engineering knowledge base
    """
    
    def __init__(self):
        self.techniques: Dict[str, Technique] = {}
        self.effects: Dict[str, Effect] = {}
        self.genres: Dict[str, Dict] = {}
        self.workflows: Dict[str, List[str]] = {}
        self.terminology: Dict[str, str] = {}
        
        # Load all knowledge
        self._load_techniques()
        self._load_effects()
        self._load_genres()
        self._load_workflows()
        self._load_terminology()
    
    def _load_techniques(self):
        """Load all production techniques"""
        techniques_data = [
            # Dynamics
            Technique(
                name="Parallel Compression",
                description="Blend heavily compressed signal with dry for punch without losing dynamics",
                category="dynamics",
                use_cases=["drums", "vocals", "bass", "master"],
                steps=[
                    "Create a bus/return track",
                    "Add compressor with heavy settings",
                    "High ratio (8:1 to infinity)",
                    "Fast attack (1-10ms)",
                    "Medium release (50-150ms)",
                    "Blend 20-40% with original"
                ],
                parameters={
                    "ratio": {"min": 8, "max": 20, "typical": 10},
                    "attack_ms": {"min": 1, "max": 10, "typical": 5},
                    "release_ms": {"min": 50, "max": 150, "typical": 100},
                    "blend_percent": {"min": 20, "max": 40, "typical": 30}
                },
                related_techniques=["New York Compression", "Drum Bus Processing"]
            ),
            Technique(
                name="Sidechain Compression",
                description="Use one signal to control compression on another, creating ducking/pumping effect",
                category="dynamics",
                use_cases=["bass_ducking", "EDM_pumping", "clarity"],
                steps=[
                    "Add compressor to target track",
                    "Enable sidechain input",
                    "Route trigger signal to sidechain",
                    "Set fast attack (0.1-5ms)",
                    "Set release for desired pumping",
                    "Adjust threshold and ratio"
                ],
                parameters={
                    "ratio": {"min": 4, "max": 10, "typical": 6},
                    "attack_ms": {"min": 0.1, "max": 5, "typical": 1},
                    "release_ms": {"min": 50, "max": 300, "typical": 150}
                },
                related_techniques=["Ducking", "Pumping"]
            ),
            Technique(
                name="Serial Compression",
                description="Use multiple compressors in series for transparent gain reduction",
                category="dynamics",
                use_cases=["vocals", "bass", "master"],
                steps=[
                    "Add first compressor (gentle, 2-3dB reduction)",
                    "Add second compressor (catch peaks, 2-3dB)",
                    "Each compressor does less work for transparent result"
                ],
                parameters={
                    "reduction_per_stage_db": {"min": 2, "max": 4, "typical": 3}
                }
            ),
            Technique(
                name="Multiband Compression",
                description="Compress different frequency bands independently",
                category="dynamics",
                use_cases=["mastering", "problem_solving", "bass"],
                steps=[
                    "Set crossover frequencies",
                    "Adjust compression per band",
                    "Focus on problem areas"
                ]
            ),
            
            # EQ
            Technique(
                name="Subtractive EQ",
                description="Cut problematic frequencies instead of boosting",
                category="eq",
                use_cases=["mixing", "clarity", "mud_removal"],
                steps=[
                    "Listen for problem frequencies",
                    "Boost to find, then cut",
                    "Narrow Q for surgical cuts",
                    "Wide Q for tonal shaping"
                ],
                parameters={
                    "common_cuts": {
                        "mud": "200-400Hz",
                        "boxiness": "300-600Hz",
                        "harshness": "2-4kHz",
                        "sibilance": "5-8kHz"
                    }
                }
            ),
            Technique(
                name="High Pass Filter",
                description="Remove low frequency content below a cutoff",
                category="eq",
                use_cases=["all_except_bass_kick", "mud_removal", "clarity"],
                steps=[
                    "Add EQ or filter",
                    "Set high-pass mode",
                    "Adjust cutoff frequency",
                    "Optionally adjust slope"
                ],
                parameters={
                    "vocals_hz": {"min": 80, "max": 120, "typical": 100},
                    "guitars_hz": {"min": 80, "max": 100, "typical": 80},
                    "synths_hz": {"min": 30, "max": 60, "typical": 40}
                }
            ),
            Technique(
                name="Presence Boost",
                description="Add clarity and presence in the 2-5kHz range",
                category="eq",
                use_cases=["vocals", "guitars", "snare"],
                steps=[
                    "Add shelving or peak EQ",
                    "Boost in 2-5kHz range",
                    "Be subtle to avoid harshness"
                ],
                parameters={
                    "frequency_hz": {"min": 2000, "max": 5000, "typical": 3000},
                    "gain_db": {"min": 1, "max": 4, "typical": 2}
                }
            ),
            Technique(
                name="Air Boost",
                description="Add sparkle and air in the 10-16kHz range",
                category="eq",
                use_cases=["vocals", "cymbals", "master", "acoustic"],
                steps=[
                    "Add high shelf EQ",
                    "Set frequency around 10-12kHz",
                    "Gentle boost 1-3dB"
                ],
                parameters={
                    "frequency_hz": {"min": 10000, "max": 16000, "typical": 12000},
                    "gain_db": {"min": 1, "max": 3, "typical": 2}
                }
            ),
            
            # Spatial
            Technique(
                name="Stereo Widening",
                description="Increase perceived stereo width of a sound",
                category="spatial",
                use_cases=["pads", "synths", "backing_vocals", "master"],
                steps=[
                    "Add stereo widener or Utility",
                    "Increase width parameter",
                    "Check mono compatibility",
                    "Avoid widening bass frequencies"
                ],
                parameters={
                    "width_percent": {"min": 100, "max": 200, "typical": 130}
                },
                related_techniques=["Haas Effect", "Mid/Side Processing"]
            ),
            Technique(
                name="Haas Effect",
                description="Create stereo width using short delays",
                category="spatial",
                use_cases=["doubling", "width", "vintage"],
                steps=[
                    "Duplicate track or use stereo delay",
                    "Pan original and duplicate",
                    "Add 10-30ms delay to one side",
                    "Check mono compatibility"
                ],
                parameters={
                    "delay_ms": {"min": 10, "max": 30, "typical": 20}
                }
            ),
            Technique(
                name="Reverb for Depth",
                description="Use reverb to create front-to-back depth in the mix",
                category="spatial",
                use_cases=["mixing", "depth", "space"],
                steps=[
                    "Less reverb = closer to front",
                    "More reverb = further back",
                    "Use pre-delay to separate from dry signal",
                    "Match reverb decay to tempo"
                ]
            ),
            
            # Saturation/Distortion
            Technique(
                name="Tape Saturation",
                description="Add harmonic warmth using tape-style saturation",
                category="saturation",
                use_cases=["warmth", "analog_feel", "glue"],
                steps=[
                    "Add saturator or tape plugin",
                    "Set subtle drive",
                    "Adjust input/output levels",
                    "May roll off harsh highs"
                ],
                parameters={
                    "drive_percent": {"min": 10, "max": 30, "typical": 15}
                }
            ),
            
            # Drums
            Technique(
                name="Drum Bus Processing",
                description="Process all drums together for glue and punch",
                category="drums",
                use_cases=["drums", "cohesion", "punch"],
                steps=[
                    "Route all drums to a bus",
                    "Add gentle compression (2-4dB reduction)",
                    "Add saturation for warmth",
                    "Optional: parallel compression",
                    "Optional: transient shaping"
                ]
            ),
            Technique(
                name="Transient Shaping",
                description="Control attack and sustain of transients",
                category="drums",
                use_cases=["drums", "percussion", "punch"],
                steps=[
                    "Add transient shaper (Drum Buss in Ableton)",
                    "Increase attack for more punch",
                    "Decrease sustain for tighter sound",
                    "Or reduce attack and increase sustain for softer feel"
                ]
            ),
            
            # Vocals
            Technique(
                name="Vocal Chain",
                description="Standard vocal processing chain",
                category="vocals",
                use_cases=["vocals", "lead_vocal", "mixing"],
                steps=[
                    "1. High-pass filter (80-120Hz)",
                    "2. Subtractive EQ (remove problems)",
                    "3. Compression (3-6dB reduction)",
                    "4. De-esser (if sibilant)",
                    "5. Additive EQ (presence, air)",
                    "6. Reverb/Delay (to taste)"
                ]
            ),
            
            # Mastering
            Technique(
                name="Basic Mastering Chain",
                description="Standard mastering processing chain",
                category="mastering",
                use_cases=["mastering", "final_mix"],
                steps=[
                    "1. Corrective EQ",
                    "2. Multiband compression (optional)",
                    "3. Stereo enhancement (subtle)",
                    "4. Peak limiting",
                    "5. Final EQ tweaks"
                ],
                parameters={
                    "target_loudness_lufs": {"streaming": -14, "cd": -9},
                    "true_peak_db": {"max": -1, "typical": -1}
                }
            ),
        ]
        
        for technique in techniques_data:
            self.techniques[technique.name.lower().replace(" ", "_")] = technique
    
    def _load_effects(self):
        """Load effects/plugin information"""
        effects_data = [
            Effect(
                name="Compressor",
                category="dynamics",
                ableton_name="Compressor",
                parameters={
                    "Threshold": {"min": -40, "max": 0, "unit": "dB"},
                    "Ratio": {"min": 1, "max": 20, "unit": ":1"},
                    "Attack": {"min": 0.01, "max": 100, "unit": "ms"},
                    "Release": {"min": 10, "max": 1000, "unit": "ms"},
                    "Output Gain": {"min": -30, "max": 30, "unit": "dB"}
                },
                common_uses=["dynamics_control", "punch", "sustain"]
            ),
            Effect(
                name="EQ Eight",
                category="eq",
                ableton_name="EQ Eight",
                parameters={
                    "8 bands": {"type": ["low_cut", "low_shelf", "peak", "high_shelf", "high_cut"]},
                    "Frequency": {"min": 20, "max": 20000, "unit": "Hz"},
                    "Gain": {"min": -15, "max": 15, "unit": "dB"},
                    "Q": {"min": 0.1, "max": 18}
                },
                common_uses=["tonal_shaping", "problem_solving", "enhancement"]
            ),
            Effect(
                name="Reverb",
                category="spatial",
                ableton_name="Reverb",
                parameters={
                    "Decay Time": {"min": 0.1, "max": 10, "unit": "s"},
                    "Size": {"min": 0, "max": 100, "unit": "%"},
                    "Pre-delay": {"min": 0, "max": 250, "unit": "ms"},
                    "Dry/Wet": {"min": 0, "max": 100, "unit": "%"}
                },
                common_uses=["space", "depth", "ambience"]
            ),
            Effect(
                name="Saturator",
                category="distortion",
                ableton_name="Saturator",
                parameters={
                    "Drive": {"min": 0, "max": 100, "unit": "%"},
                    "Type": {"options": ["Analog", "Soft Sine", "Medium Curve", "Hard Curve"]},
                    "Output": {"min": -30, "max": 0, "unit": "dB"}
                },
                common_uses=["warmth", "harmonics", "character"]
            ),
            Effect(
                name="Glue Compressor",
                category="dynamics",
                ableton_name="Glue Compressor",
                parameters={
                    "Threshold": {"min": -40, "max": 0, "unit": "dB"},
                    "Ratio": {"options": [2, 4, 10]},
                    "Attack": {"options": [0.01, 0.1, 0.3, 1, 3, 10, 30]},
                    "Release": {"options": ["auto", 0.1, 0.2, 0.4, 0.6, 0.8, 1.2]}
                },
                common_uses=["bus_compression", "glue", "punch"]
            ),
            Effect(
                name="Limiter",
                category="dynamics",
                ableton_name="Limiter",
                parameters={
                    "Gain": {"min": 0, "max": 36, "unit": "dB"},
                    "Ceiling": {"min": -6, "max": 0, "unit": "dB"}
                },
                common_uses=["loudness", "mastering", "peak_control"]
            ),
            Effect(
                name="Drum Buss",
                category="dynamics",
                ableton_name="Drum Buss",
                parameters={
                    "Drive": {"min": 0, "max": 100, "unit": "%"},
                    "Crunch": {"min": 0, "max": 100, "unit": "%"},
                    "Boom": {"min": -100, "max": 100, "unit": "%"},
                    "Transients": {"min": -100, "max": 100, "unit": "%"},
                    "Damping": {"min": 0, "max": 20000, "unit": "Hz"}
                },
                common_uses=["drum_processing", "punch", "warmth"]
            ),
            Effect(
                name="Utility",
                category="utility",
                ableton_name="Utility",
                parameters={
                    "Gain": {"min": -36, "max": 35, "unit": "dB"},
                    "Width": {"min": 0, "max": 400, "unit": "%"},
                    "Pan": {"min": -50, "max": 50, "unit": "L/R"}
                },
                common_uses=["gain_staging", "stereo_width", "mono_check"]
            ),
        ]
        
        for effect in effects_data:
            self.effects[effect.name.lower().replace(" ", "_")] = effect
    
    def _load_genres(self):
        """Load genre-specific production knowledge"""
        self.genres = {
            "trap": {
                "tempo_range": (130, 170),
                "typical_tempo": 140,
                "key_elements": ["808_bass", "hi_hat_rolls", "snare_reverb", "triplet_patterns"],
                "drum_characteristics": {
                    "kick": "heavy sub bass 808, long decay",
                    "snare": "tight with reverb tail",
                    "hihat": "rolls, triplets, pitch slides"
                },
                "mixing_tips": [
                    "808 should dominate low end",
                    "Hi-hats should have presence",
                    "Snare should cut through"
                ]
            },
            "hip_hop": {
                "tempo_range": (85, 115),
                "typical_tempo": 95,
                "key_elements": ["boom_bap", "samples", "vinyl_warmth"],
                "drum_characteristics": {
                    "kick": "punchy, round",
                    "snare": "cracky, layered",
                    "hihat": "groovy, swung"
                }
            },
            "edm": {
                "tempo_range": (125, 130),
                "typical_tempo": 128,
                "key_elements": ["sidechain", "drops", "builds", "risers"],
                "mixing_tips": [
                    "Heavy sidechain on bass",
                    "Wide stereo field",
                    "Big impact on drops"
                ]
            },
            "pop": {
                "tempo_range": (100, 130),
                "typical_tempo": 120,
                "key_elements": ["vocal_focus", "clean_mix", "wide_stereo"],
                "mixing_tips": [
                    "Vocals upfront and center",
                    "Polished, clean sound",
                    "Well-defined low end"
                ]
            },
            "rock": {
                "tempo_range": (100, 140),
                "typical_tempo": 120,
                "key_elements": ["live_feel", "room_sound", "dynamics"],
                "mixing_tips": [
                    "Preserve dynamics",
                    "Use room mics",
                    "Double-track guitars"
                ]
            }
        }
    
    def _load_workflows(self):
        """Load common production workflows"""
        self.workflows = {
            "mixing_drums": [
                "Start with gain staging",
                "Process kick (EQ, compression)",
                "Process snare (EQ, compression, reverb)",
                "Process hi-hats (EQ, panning)",
                "Create drum bus",
                "Add bus compression",
                "Add parallel compression if needed"
            ],
            "mixing_vocals": [
                "Apply vocal chain (HPF, EQ, comp)",
                "De-ess if needed",
                "Add reverb (send)",
                "Add delay (send)",
                "Automate levels"
            ],
            "mastering_basic": [
                "Reference against commercial tracks",
                "Apply corrective EQ",
                "Add gentle compression",
                "Enhance stereo if needed",
                "Apply limiting",
                "Check on multiple systems"
            ]
        }
    
    def _load_terminology(self):
        """Load audio engineering terminology"""
        self.terminology = {
            "gain staging": "Setting proper levels throughout the signal chain to avoid clipping and maintain headroom",
            "headroom": "The amount of level below 0dB, providing space before clipping",
            "transient": "The initial attack portion of a sound",
            "sustain": "The portion of sound after the initial transient",
            "mud": "Excessive low-mid frequency buildup (200-400Hz)",
            "sibilance": "Harsh 's' and 't' sounds in vocals (5-8kHz)",
            "pumping": "Audible compression artifacts, sometimes intentional in EDM",
            "ducking": "Lowering one signal when another plays",
            "glue": "Making multiple elements feel cohesive",
            "LUFS": "Loudness Units Full Scale - standard for measuring perceived loudness"
        }
    
    # Query methods
    def get_technique(self, name: str) -> Optional[Technique]:
        """Get a technique by name"""
        key = name.lower().replace(" ", "_")
        return self.techniques.get(key)
    
    def get_effect(self, name: str) -> Optional[Effect]:
        """Get an effect by name"""
        key = name.lower().replace(" ", "_")
        return self.effects.get(key)
    
    def get_genre(self, name: str) -> Optional[Dict]:
        """Get genre info by name"""
        return self.genres.get(name.lower())
    
    def search_techniques(self, query: str) -> List[Technique]:
        """Search techniques by keyword"""
        query_lower = query.lower()
        results = []
        
        for key, technique in self.techniques.items():
            if (query_lower in technique.name.lower() or
                query_lower in technique.description.lower() or
                any(query_lower in use.lower() for use in technique.use_cases)):
                results.append(technique)
        
        return results
    
    def get_terminology(self, term: str) -> Optional[str]:
        """Get definition for an audio term"""
        return self.terminology.get(term.lower())
    
    def get_workflow(self, name: str) -> Optional[List[str]]:
        """Get a workflow by name"""
        return self.workflows.get(name.lower().replace(" ", "_"))


# Global instance
audio_kb = AudioKnowledgeBase()

