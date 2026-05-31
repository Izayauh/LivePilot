"""
Template Manager

Manages genre-specific project templates and production presets.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


@dataclass
class TrackTemplate:
    """Template for a single track"""
    name: str
    type: str  # audio, midi, return
    color: Optional[int] = None
    devices: List[str] = field(default_factory=list)
    settings: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectTemplate:
    """Template for a project/session"""
    name: str
    genre: str
    description: str
    tempo: float
    time_signature: tuple = (4, 4)
    tracks: List[TrackTemplate] = field(default_factory=list)
    return_tracks: List[TrackTemplate] = field(default_factory=list)
    master_devices: List[str] = field(default_factory=list)
    tips: List[str] = field(default_factory=list)


class TemplateManager:
    """
    Manages project templates
    
    Features:
    - Genre-specific templates
    - Quick session setup
    - Production tips per genre
    """
    
    def __init__(self):
        self.templates: Dict[str, ProjectTemplate] = {}
        self._load_builtin_templates()
    
    def _load_builtin_templates(self):
        """Load built-in genre templates"""
        
        # Trap Template
        self.templates["trap"] = ProjectTemplate(
            name="Trap Beat",
            genre="trap",
            description="Modern trap production template with 808 bass focus",
            tempo=140,
            time_signature=(4, 4),
            tracks=[
                TrackTemplate(
                    name="Kick",
                    type="midi",
                    devices=["Drum Rack"],
                    settings={"role": "kick_808"}
                ),
                TrackTemplate(
                    name="808",
                    type="midi", 
                    devices=["Operator"],
                    settings={"sub_bass": True, "glide": True}
                ),
                TrackTemplate(
                    name="Snare",
                    type="midi",
                    devices=["Drum Rack", "Reverb"],
                    settings={"reverb_short": True}
                ),
                TrackTemplate(
                    name="Hi-Hats",
                    type="midi",
                    devices=["Drum Rack"],
                    settings={"velocity_variation": True}
                ),
                TrackTemplate(
                    name="Percs",
                    type="midi",
                    devices=["Drum Rack"],
                    settings={}
                ),
                TrackTemplate(
                    name="Melody",
                    type="midi",
                    devices=["Wavetable"],
                    settings={"dark": True}
                ),
                TrackTemplate(
                    name="Chords",
                    type="midi",
                    devices=["Wavetable"],
                    settings={}
                ),
                TrackTemplate(
                    name="FX",
                    type="audio",
                    devices=[],
                    settings={}
                ),
            ],
            return_tracks=[
                TrackTemplate(
                    name="Reverb",
                    type="return",
                    devices=["Reverb"],
                    settings={"decay": 1.5}
                ),
                TrackTemplate(
                    name="Delay",
                    type="return",
                    devices=["Simple Delay"],
                    settings={"sync": True}
                ),
            ],
            master_devices=["EQ Eight", "Glue Compressor", "Limiter"],
            tips=[
                "808 should dominate the low end",
                "Use triplet hi-hat patterns",
                "Layer snares for impact",
                "Add short reverb to snare",
                "Use pitch slides on 808"
            ]
        )
        
        # Hip Hop Template
        self.templates["hip_hop"] = ProjectTemplate(
            name="Hip Hop Beat",
            genre="hip_hop",
            description="Classic hip hop boom bap style template",
            tempo=95,
            time_signature=(4, 4),
            tracks=[
                TrackTemplate(
                    name="Kick",
                    type="midi",
                    devices=["Drum Rack", "Saturator"],
                    settings={"warm": True}
                ),
                TrackTemplate(
                    name="Snare",
                    type="midi",
                    devices=["Drum Rack", "EQ Eight"],
                    settings={"crack": True}
                ),
                TrackTemplate(
                    name="Hi-Hats",
                    type="midi",
                    devices=["Drum Rack"],
                    settings={"swing": True}
                ),
                TrackTemplate(
                    name="Bass",
                    type="midi",
                    devices=["Operator"],
                    settings={"sub": True}
                ),
                TrackTemplate(
                    name="Sample",
                    type="audio",
                    devices=["EQ Eight", "Saturator"],
                    settings={"vinyl_warmth": True}
                ),
                TrackTemplate(
                    name="Keys",
                    type="midi",
                    devices=["Electric"],
                    settings={}
                ),
            ],
            return_tracks=[
                TrackTemplate(
                    name="Vinyl",
                    type="return",
                    devices=["Vinyl Distortion", "EQ Eight"],
                    settings={}
                ),
                TrackTemplate(
                    name="Reverb",
                    type="return",
                    devices=["Reverb"],
                    settings={"room": True}
                ),
            ],
            master_devices=["EQ Eight", "Compressor"],
            tips=[
                "Add swing to drums",
                "Use vinyl saturation for warmth",
                "Leave space for vocals",
                "Sample chops add character",
                "Layer kicks for punch"
            ]
        )
        
        # EDM Template
        self.templates["edm"] = ProjectTemplate(
            name="EDM Track",
            genre="edm",
            description="Electronic dance music template with sidechain focus",
            tempo=128,
            time_signature=(4, 4),
            tracks=[
                TrackTemplate(
                    name="Kick",
                    type="midi",
                    devices=["Drum Rack"],
                    settings={"punchy": True}
                ),
                TrackTemplate(
                    name="Clap",
                    type="midi",
                    devices=["Drum Rack", "Reverb"],
                    settings={}
                ),
                TrackTemplate(
                    name="Hi-Hats",
                    type="midi",
                    devices=["Drum Rack"],
                    settings={}
                ),
                TrackTemplate(
                    name="Bass",
                    type="midi",
                    devices=["Serum", "Compressor"],
                    settings={"sidechain": True}
                ),
                TrackTemplate(
                    name="Lead",
                    type="midi",
                    devices=["Wavetable"],
                    settings={"bright": True}
                ),
                TrackTemplate(
                    name="Pad",
                    type="midi",
                    devices=["Wavetable", "Chorus"],
                    settings={"wide": True}
                ),
                TrackTemplate(
                    name="Riser",
                    type="audio",
                    devices=["Auto Filter"],
                    settings={}
                ),
                TrackTemplate(
                    name="FX",
                    type="audio",
                    devices=[],
                    settings={}
                ),
            ],
            return_tracks=[
                TrackTemplate(
                    name="Reverb",
                    type="return",
                    devices=["Reverb"],
                    settings={"large": True}
                ),
                TrackTemplate(
                    name="Delay",
                    type="return",
                    devices=["Ping Pong Delay"],
                    settings={"sync": True}
                ),
                TrackTemplate(
                    name="Sidechain",
                    type="return",
                    devices=["Compressor"],
                    settings={"sidechain_from_kick": True}
                ),
            ],
            master_devices=["EQ Eight", "Multiband Dynamics", "Limiter"],
            tips=[
                "Heavy sidechain on bass and pads",
                "Build tension with risers",
                "Wide stereo field on synths",
                "Keep kick punchy and clear",
                "Layer sounds for impact on drops"
            ]
        )
        
        # Pop Template
        self.templates["pop"] = ProjectTemplate(
            name="Pop Track",
            genre="pop",
            description="Modern pop production template with vocal focus",
            tempo=120,
            time_signature=(4, 4),
            tracks=[
                TrackTemplate(
                    name="Drums",
                    type="midi",
                    devices=["Drum Rack", "Compressor"],
                    settings={}
                ),
                TrackTemplate(
                    name="Bass",
                    type="midi",
                    devices=["Operator"],
                    settings={}
                ),
                TrackTemplate(
                    name="Piano",
                    type="midi",
                    devices=["Grand Piano"],
                    settings={}
                ),
                TrackTemplate(
                    name="Synth",
                    type="midi",
                    devices=["Wavetable"],
                    settings={}
                ),
                TrackTemplate(
                    name="Strings",
                    type="midi",
                    devices=["Orchestral Strings"],
                    settings={}
                ),
                TrackTemplate(
                    name="Lead Vocal",
                    type="audio",
                    devices=["EQ Eight", "Compressor", "De-esser"],
                    settings={"lead": True}
                ),
                TrackTemplate(
                    name="BGV",
                    type="audio",
                    devices=["EQ Eight", "Compressor"],
                    settings={}
                ),
            ],
            return_tracks=[
                TrackTemplate(
                    name="Vocal Verb",
                    type="return",
                    devices=["Reverb"],
                    settings={"plate": True}
                ),
                TrackTemplate(
                    name="Vocal Delay",
                    type="return",
                    devices=["Simple Delay"],
                    settings={"1/4": True}
                ),
            ],
            master_devices=["EQ Eight", "Compressor", "Limiter"],
            tips=[
                "Keep vocals upfront and clear",
                "Polish the mix",
                "Wide stereo image",
                "Well-defined low end",
                "Catchy hooks are key"
            ]
        )

        self.templates["vocal_ready_beat"] = ProjectTemplate(
            name="Vocal-Ready Beat Template",
            genre="vocal_ready_beat",
            description=(
                "Modern rap/R&B/pop beat template with buses, placeholder vocals, "
                "filtered ambience, and vocal-pocket mix defaults."
            ),
            tempo=140,
            time_signature=(4, 4),
            tracks=[
                TrackTemplate(
                    name="DRUMS - Kick",
                    type="midi",
                    color=10,
                    devices=["Drum Rack", "EQ Eight", "Saturator", "Utility"],
                    settings={
                        "group": "drums",
                        "role": "low_end_anchor",
                        "pocket": "Own sub punch; leave 120 Hz+ space for bass and vocal body.",
                        "target_peak_db": -8,
                    },
                ),
                TrackTemplate(
                    name="DRUMS - Snare Clap",
                    type="midi",
                    color=10,
                    devices=["Drum Rack", "EQ Eight", "Compressor", "Utility"],
                    settings={
                        "group": "drums",
                        "role": "backbeat",
                        "pocket": "Control 2-5 kHz bite so the lead vocal can stay forward.",
                        "target_peak_db": -10,
                    },
                ),
                TrackTemplate(
                    name="DRUMS - Hats Perc Top",
                    type="midi",
                    color=10,
                    devices=["Drum Rack", "EQ Eight", "Utility"],
                    settings={
                        "group": "drums",
                        "role": "motion",
                        "pocket": "High-pass and de-harsh around vocal air bands when busy.",
                        "target_peak_db": -14,
                        "starter_pan": 0.08,
                    },
                ),
                TrackTemplate(
                    name="DRUM BUS",
                    type="audio",
                    color=10,
                    devices=["EQ Eight", "Glue Compressor", "Saturator", "Utility"],
                    settings={
                        "group": "drums",
                        "role": "bus",
                        "pocket": "Glue without pushing cymbals into the vocal presence range.",
                        "target_peak_db": -6,
                    },
                ),
                TrackTemplate(
                    name="BASS - Sub 808",
                    type="midi",
                    color=3,
                    devices=["Drift", "EQ Eight", "Saturator", "Compressor", "Utility"],
                    settings={
                        "group": "bass",
                        "role": "sub",
                        "sidechain_from": "DRUMS - Kick",
                        "pocket": "Mono low end; duck from kick; keep upper harmonics controlled.",
                        "target_peak_db": -8,
                    },
                ),
                TrackTemplate(
                    name="BASS BUS",
                    type="audio",
                    color=3,
                    devices=["EQ Eight", "Saturator", "Compressor", "Utility"],
                    settings={
                        "group": "bass",
                        "role": "bus",
                        "pocket": "Stable low-end owner below the music bus.",
                        "target_peak_db": -7,
                    },
                ),
                TrackTemplate(
                    name="MUSIC - Chords",
                    type="midi",
                    color=18,
                    devices=["Drift", "EQ Eight", "Auto Filter", "Utility"],
                    settings={
                        "group": "music",
                        "role": "harmony",
                        "pocket": "High-pass mud; leave 1-4 kHz for the vocal unless featured.",
                        "ambience_send": "Low SEND - Long Hall for filtered harmonic depth behind vocals.",
                        "target_peak_db": -12,
                        "starter_pan": -0.06,
                    },
                ),
                TrackTemplate(
                    name="MUSIC - Keys Pad",
                    type="midi",
                    color=18,
                    devices=["Drift", "EQ Eight", "Chorus-Ensemble", "Reverb", "Utility"],
                    settings={
                        "group": "music",
                        "role": "support",
                        "pocket": "Wide support layer, lower center density during verses.",
                        "target_peak_db": -14,
                        "starter_pan": -0.10,
                    },
                ),
                TrackTemplate(
                    name="MUSIC - Lead Hook",
                    type="midi",
                    color=18,
                    devices=["Drift", "EQ Eight", "Compressor", "Utility"],
                    settings={
                        "group": "music",
                        "role": "hook",
                        "vocal_duck_ready": True,
                        "pocket": "Automate down or thin during lead-vocal lines.",
                        "target_peak_db": -13,
                        "starter_pan": 0.08,
                    },
                ),
                TrackTemplate(
                    name="MUSIC BUS - Vocal Pocket",
                    type="audio",
                    color=18,
                    devices=["EQ Eight", "Compressor", "Utility"],
                    settings={
                        "group": "music",
                        "role": "bus",
                        "pocket": "Main instrumental carve point for vocal sidechain/dynamic EQ.",
                        "carve_ranges_hz": [(250, 450), (1200, 3500), (5000, 8000)],
                        "target_peak_db": -6,
                    },
                ),
                TrackTemplate(
                    name="VOCAL - Lead Placeholder",
                    type="audio",
                    color=27,
                    devices=[
                        "Utility",
                        "EQ Eight",
                        "Gate",
                        "Compressor",
                        "Multiband Dynamics",
                        "Saturator",
                        "Utility",
                    ],
                    settings={
                        "group": "vocal",
                        "role": "lead_placeholder",
                        "pocket_key": True,
                        "pocket": "Sidechain/key source for music-bus ducking and pocket checks.",
                        "target_peak_db": -10,
                    },
                ),
                TrackTemplate(
                    name="VOCAL - Doubles Adlibs",
                    type="audio",
                    color=27,
                    devices=["Utility", "EQ Eight", "Compressor", "Utility"],
                    settings={
                        "group": "vocal",
                        "role": "support_placeholder",
                        "pocket": "Ready for doubles, adlibs, harmonies, and throws.",
                        "target_peak_db": -14,
                        "starter_pan": 0.12,
                    },
                ),
                TrackTemplate(
                    name="VOCAL BUS",
                    type="audio",
                    color=27,
                    devices=[
                        "Utility",
                        "EQ Eight",
                        "Compressor",
                        "Multiband Dynamics",
                        "Saturator",
                        "EQ Eight",
                        "Utility",
                    ],
                    settings={
                        "group": "vocal",
                        "role": "bus",
                        "pocket": "Lead chain staging point before time effects and print.",
                        "target_peak_db": -8,
                    },
                ),
                TrackTemplate(
                    name="FX - Transitions Texture",
                    type="audio",
                    color=31,
                    devices=["EQ Eight", "Auto Filter", "Utility"],
                    settings={
                        "group": "fx",
                        "role": "transitions",
                        "pocket": "Filtered risers, impacts, and ear candy routed through the music-bus vocal pocket.",
                        "target_peak_db": -14,
                        "starter_pan": -0.12,
                    },
                ),
                TrackTemplate(
                    name="REFERENCE / PRINT",
                    type="audio",
                    color=5,
                    devices=["Utility", "EQ Eight"],
                    settings={
                        "group": "mix",
                        "role": "reference_print",
                        "pocket": "Muted/import-ready reference or rough-print lane.",
                        "target_peak_db": -12,
                        "muted": True,
                    },
                ),
            ],
            return_tracks=[
                TrackTemplate(
                    name="SEND - Short Plate",
                    type="return",
                    color=27,
                    devices=["EQ Eight", "Reverb", "Utility"],
                    settings={"high_pass_hz": 180, "low_pass_hz": 8500, "decay_s": 1.2},
                ),
                TrackTemplate(
                    name="SEND - Slap Delay",
                    type="return",
                    color=27,
                    devices=["EQ Eight", "Simple Delay", "Utility"],
                    settings={"high_pass_hz": 220, "low_pass_hz": 5000, "feedback": 0.18},
                ),
                TrackTemplate(
                    name="SEND - Long Hall",
                    type="return",
                    color=27,
                    devices=["EQ Eight", "Reverb", "Utility"],
                    settings={"high_pass_hz": 250, "low_pass_hz": 6500, "decay_s": 2.8},
                ),
                TrackTemplate(
                    name="SEND - Throw Delay",
                    type="return",
                    color=27,
                    devices=["EQ Eight", "Ping Pong Delay", "Utility"],
                    settings={"high_pass_hz": 260, "low_pass_hz": 4800, "feedback": 0.32},
                ),
                TrackTemplate(
                    name="SEND - Parallel Drum Comp",
                    type="return",
                    color=10,
                    devices=["EQ Eight", "Compressor", "Saturator", "Utility"],
                    settings={
                        "blend_target": "drum punch without cymbal harshness",
                        "high_pass_hz": 35,
                        "low_pass_hz": 7800,
                        "low_mid_tame_hz": 320,
                    },
                ),
            ],
            master_devices=["Utility", "EQ Eight", "Glue Compressor", "Limiter"],
            tips=[
                "Keep lead-vocal placeholders in the session even before recording.",
                "Write verses with less midrange motion than hooks.",
                "Filter every reverb and delay return before it reaches the vocal center.",
                "Use the MUSIC BUS - Vocal Pocket track as the main instrumental carve point.",
                "Let arrangement density create hook lift before adding extra loudness.",
            ],
        )
    
    def get_template(self, genre: str) -> Optional[ProjectTemplate]:
        """Get a template by genre"""
        return self.templates.get(genre.lower())
    
    def list_templates(self) -> List[str]:
        """List available template names"""
        return list(self.templates.keys())
    
    def get_tips_for_genre(self, genre: str) -> List[str]:
        """Get production tips for a genre"""
        template = self.templates.get(genre.lower())
        if template:
            return template.tips
        return []
    
    def get_tempo_for_genre(self, genre: str) -> Optional[float]:
        """Get typical tempo for a genre"""
        template = self.templates.get(genre.lower())
        if template:
            return template.tempo
        return None
    
    def get_track_layout(self, genre: str) -> List[Dict]:
        """Get the track layout for a template"""
        template = self.templates.get(genre.lower())
        if not template:
            return []
        
        layout = []
        for i, track in enumerate(template.tracks):
            layout.append({
                "index": i,
                "name": track.name,
                "type": track.type,
                "devices": track.devices,
                "settings": track.settings
            })
        return layout


# Global template manager
template_manager = TemplateManager()

