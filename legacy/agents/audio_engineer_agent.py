"""
Audio Engineer Agent

The core intelligence that understands professional audio engineering and music production.
This agent analyzes user requests, understands production concepts, and generates
high-level plans for achieving production goals.
"""

from typing import Dict, Any, List, Optional
from agents import AgentType, AgentMessage
from agent_system import BaseAgent


class AudioEngineerAgent(BaseAgent):
    """
    The Audio Engineer Brain
    
    Responsibilities:
    - Understand music production concepts
    - Analyze user requests for production intent
    - Determine appropriate techniques and workflows
    - Generate high-level production plans
    - Consider genre-specific best practices
    """
    
    def __init__(self, orchestrator):
        super().__init__(AgentType.AUDIO_ENGINEER, orchestrator)
        
        # Production knowledge base
        self.techniques = self._load_techniques()
        self.genre_presets = self._load_genre_presets()
        self.effect_chains = self._load_effect_chains()
    
    def _load_techniques(self) -> Dict[str, Dict]:
        """Load production technique knowledge"""
        return {
            # Dynamics Processing
            "parallel_compression": {
                "description": "Blend heavily compressed signal with dry signal for punch without losing dynamics",
                "use_cases": ["drums", "vocals", "master"],
                "steps": [
                    "Create return track or bus",
                    "Send signal to bus",
                    "Add compressor with heavy settings (high ratio, fast attack)",
                    "Blend to taste (20-40% typically)"
                ],
                "parameters": {
                    "ratio": "8:1 to 20:1",
                    "attack": "1-10ms",
                    "release": "50-150ms",
                    "blend": "20-40%"
                }
            },
            "sidechain_compression": {
                "description": "Duck one signal when another plays, creating pumping effect or clarity",
                "use_cases": ["bass_vs_kick", "pads", "edm"],
                "steps": [
                    "Add compressor to target track",
                    "Set sidechain input to trigger track",
                    "Adjust threshold and ratio",
                    "Set attack and release for desired pumping"
                ],
                "parameters": {
                    "ratio": "4:1 to 10:1",
                    "attack": "0.1-10ms",
                    "release": "100-300ms (sync to tempo)"
                }
            },
            "serial_compression": {
                "description": "Use multiple compressors in series for transparent gain reduction",
                "use_cases": ["vocals", "master", "bass"],
                "steps": [
                    "Add first compressor (gentle, 2-3dB reduction)",
                    "Add second compressor (catch peaks)",
                    "Each compressor does less work"
                ]
            },
            
            # EQ Techniques
            "subtractive_eq": {
                "description": "Cut problematic frequencies rather than boosting",
                "use_cases": ["mixing", "clarity", "mud_removal"],
                "common_cuts": {
                    "mud": "200-400Hz",
                    "boxiness": "300-600Hz", 
                    "harshness": "2-4kHz",
                    "sibilance": "5-8kHz"
                }
            },
            "high_pass_filter": {
                "description": "Remove low frequency rumble and mud",
                "use_cases": ["most_tracks_except_bass_kick"],
                "common_settings": {
                    "vocals": "80-120Hz",
                    "guitars": "80-100Hz",
                    "synths": "30-60Hz"
                }
            },
            "presence_boost": {
                "description": "Add clarity and presence in the 2-5kHz range",
                "use_cases": ["vocals", "guitars", "snare"]
            },
            "air_boost": {
                "description": "Add sparkle and air in the 10-16kHz range",
                "use_cases": ["vocals", "cymbals", "master"]
            },
            
            # Spatial Processing
            "stereo_widening": {
                "description": "Increase stereo width of a sound",
                "use_cases": ["pads", "synths", "backing_vocals"],
                "techniques": ["haas_effect", "mid_side_eq", "chorus"]
            },
            "reverb_for_depth": {
                "description": "Use reverb to create front-to-back depth",
                "use_cases": ["mixing", "spatial"],
                "tips": [
                    "Less reverb = closer",
                    "More reverb = further away",
                    "Pre-delay affects perceived distance"
                ]
            },
            
            # Drum Processing
            "drum_bus_processing": {
                "description": "Process all drums together for glue and punch",
                "steps": [
                    "Route all drums to a bus",
                    "Add gentle compression (2-4dB GR)",
                    "Add saturation for warmth",
                    "Optional: parallel compression"
                ]
            },
            "transient_shaping": {
                "description": "Enhance or reduce transients for punch or smoothness",
                "use_cases": ["drums", "percussion", "bass"],
                "parameters": {
                    "attack_boost": "more punch, snap",
                    "attack_reduce": "softer, smoother",
                    "sustain_boost": "more body, sustain",
                    "sustain_reduce": "tighter, punchier"
                }
            },
            
            # Vocal Processing
            "vocal_chain": {
                "description": "Standard vocal processing chain",
                "steps": [
                    "1. High-pass filter (80-120Hz)",
                    "2. Subtractive EQ (remove problems)",
                    "3. Compression (3-6dB reduction)",
                    "4. De-esser (if needed)",
                    "5. Additive EQ (presence, air)",
                    "6. Reverb/Delay (to taste)"
                ]
            },
            
            # Mastering
            "mastering_chain": {
                "description": "Basic mastering chain",
                "steps": [
                    "1. Corrective EQ",
                    "2. Multiband compression (optional)",
                    "3. Stereo enhancement (subtle)",
                    "4. Peak limiting",
                    "5. Final EQ tweaks"
                ],
                "targets": {
                    "loudness": "-14 LUFS for streaming",
                    "true_peak": "-1dB"
                }
            }
        }
    
    def _load_genre_presets(self) -> Dict[str, Dict]:
        """Load genre-specific production presets"""
        return {
            "trap": {
                "kick": {"sub_heavy": True, "distortion": "light", "808": True},
                "snare": {"reverb": "short", "transient": "sharp"},
                "hihat": {"rolls": True, "pattern": "triplet"},
                "bass": {"808_style": True, "glide": True},
                "tempo_range": "130-170 BPM",
                "key_elements": ["808 bass", "hi-hat rolls", "snare reverb"]
            },
            "hip_hop": {
                "kick": {"punchy": True, "sub": "moderate"},
                "snare": {"crack": True, "layers": 2},
                "bass": {"warm": True, "sub_bass": True},
                "tempo_range": "85-115 BPM",
                "key_elements": ["boom bap feel", "sample chops", "vinyl warmth"]
            },
            "edm": {
                "kick": {"punchy": True, "sidechain": "heavy"},
                "bass": {"sidechain_to_kick": True},
                "synths": {"wide_stereo": True},
                "tempo_range": "125-130 BPM",
                "key_elements": ["sidechain pumping", "builds", "drops"]
            },
            "rock": {
                "drums": {"room_mics": True, "parallel_compression": True},
                "guitars": {"double_tracked": True, "mid_focus": True},
                "bass": {"pick_attack": True},
                "key_elements": ["live feel", "dynamics", "room sound"]
            },
            "pop": {
                "vocals": {"upfront": True, "compressed": True},
                "production": {"polished": True, "wide": True},
                "key_elements": ["vocal focus", "clean mix", "wide stereo"]
            }
        }
    
    def _load_effect_chains(self) -> Dict[str, List[Dict]]:
        """Load common effect chain templates"""
        return {
            "punchy_drums": [
                {"device": "Compressor", "params": {"ratio": 4, "attack": 10, "release": 100}},
                {"device": "Saturator", "params": {"drive": 10}},
                {"device": "EQ Eight", "params": {"low_shelf_boost": 2, "high_shelf_boost": 1}}
            ],
            "warm_vocals": [
                {"device": "EQ Eight", "params": {"high_pass": 100, "presence_boost": 2}},
                {"device": "Compressor", "params": {"ratio": 3, "attack": 20, "release": 150}},
                {"device": "Reverb", "params": {"size": 40, "decay": 1.5}}
            ],
            "wide_synths": [
                {"device": "Chorus", "params": {"rate": 0.5, "amount": 30}},
                {"device": "Utility", "params": {"width": 120}},
                {"device": "EQ Eight", "params": {"high_pass": 60}}
            ]
        }
    
    async def process(self, message: AgentMessage) -> AgentMessage:
        """Process analysis requests"""
        content = message.content
        action = content.get("action", "analyze")
        
        if action == "analyze":
            analysis = await self._analyze_request(
                content.get("request", ""),
                content.get("context", [])
            )
            return AgentMessage(
                sender=self.agent_type,
                recipient=message.sender,
                content={
                    "success": True,
                    "analysis": analysis
                },
                correlation_id=message.correlation_id
            )
        
        elif action == "get_technique":
            technique = self._get_technique(content.get("name", ""))
            return AgentMessage(
                sender=self.agent_type,
                recipient=message.sender,
                content={
                    "success": technique is not None,
                    "technique": technique
                },
                correlation_id=message.correlation_id
            )
        
        elif action == "get_genre_preset":
            preset = self._get_genre_preset(content.get("genre", ""))
            return AgentMessage(
                sender=self.agent_type,
                recipient=message.sender,
                content={
                    "success": preset is not None,
                    "preset": preset
                },
                correlation_id=message.correlation_id
            )
        
        return AgentMessage(
            sender=self.agent_type,
            recipient=message.sender,
            content={"error": f"Unknown action: {action}"},
            correlation_id=message.correlation_id
        )
    
    async def _analyze_request(self, request: str, context: List[Dict]) -> Dict[str, Any]:
        """
        Analyze a production request and determine the best approach
        """
        request_lower = request.lower()
        
        analysis = {
            "original_request": request,
            "detected_intent": None,
            "target_element": None,
            "recommended_techniques": [],
            "potential_issues": [],
            "workflow_steps": [],
            "requires_research": False,
            "confidence": 0.0
        }
        
        # Detect target element (drums, vocals, bass, etc.)
        elements = {
            "drums": ["drum", "kick", "snare", "hihat", "percussion"],
            "bass": ["bass", "sub", "low end", "808"],
            "vocals": ["vocal", "voice", "singing", "vox"],
            "synths": ["synth", "pad", "lead", "keys"],
            "guitars": ["guitar", "gtr"],
            "master": ["master", "mix", "overall", "whole"]
        }
        
        for element, keywords in elements.items():
            if any(kw in request_lower for kw in keywords):
                analysis["target_element"] = element
                break
        
        # Detect intent and recommend techniques
        if "punch" in request_lower or "punchy" in request_lower:
            analysis["detected_intent"] = "add_punch"
            analysis["recommended_techniques"] = [
                "parallel_compression",
                "transient_shaping",
                "drum_bus_processing"
            ]
            analysis["workflow_steps"] = [
                {"step": 1, "action": "Create parallel compression bus"},
                {"step": 2, "action": "Route target to bus"},
                {"step": 3, "action": "Add heavy compression to bus"},
                {"step": 4, "action": "Blend 20-40%"},
                {"step": 5, "action": "Optional: Add transient shaper"}
            ]
            analysis["confidence"] = 0.85
        
        elif "warm" in request_lower or "warmer" in request_lower:
            analysis["detected_intent"] = "add_warmth"
            analysis["recommended_techniques"] = [
                "saturation",
                "subtractive_eq",
                "tube_compression"
            ]
            analysis["workflow_steps"] = [
                {"step": 1, "action": "Add saturation/tape emulation"},
                {"step": 2, "action": "Cut harsh frequencies (2-5kHz)"},
                {"step": 3, "action": "Boost low-mids slightly (200-400Hz)"}
            ]
            analysis["confidence"] = 0.8
        
        elif "bright" in request_lower or "brighter" in request_lower:
            analysis["detected_intent"] = "add_brightness"
            analysis["recommended_techniques"] = [
                "air_boost",
                "presence_boost",
                "high_shelf_eq"
            ]
            analysis["workflow_steps"] = [
                {"step": 1, "action": "Add high shelf EQ boost (10kHz+)"},
                {"step": 2, "action": "Add presence boost (2-5kHz)"},
                {"step": 3, "action": "Check for harshness, cut if needed"}
            ]
            analysis["confidence"] = 0.8
        
        elif "wide" in request_lower or "stereo" in request_lower:
            analysis["detected_intent"] = "increase_width"
            analysis["recommended_techniques"] = [
                "stereo_widening",
                "haas_effect",
                "mid_side_processing"
            ]
            analysis["workflow_steps"] = [
                {"step": 1, "action": "Add stereo widener or Utility"},
                {"step": 2, "action": "Increase width parameter"},
                {"step": 3, "action": "Check mono compatibility"}
            ]
            analysis["confidence"] = 0.8
        
        elif "mix" in request_lower and "vocal" in request_lower:
            analysis["detected_intent"] = "mix_vocals"
            analysis["recommended_techniques"] = ["vocal_chain"]
            analysis["workflow_steps"] = [
                {"step": 1, "action": "High-pass filter at 80-120Hz"},
                {"step": 2, "action": "Subtractive EQ for problem frequencies"},
                {"step": 3, "action": "Compression for consistency"},
                {"step": 4, "action": "De-esser if sibilant"},
                {"step": 5, "action": "Presence/air EQ"},
                {"step": 6, "action": "Reverb and delay to taste"}
            ]
            analysis["confidence"] = 0.9
        
        elif "sidechain" in request_lower:
            analysis["detected_intent"] = "sidechain_setup"
            analysis["recommended_techniques"] = ["sidechain_compression"]
            analysis["workflow_steps"] = [
                {"step": 1, "action": "Add compressor to target track"},
                {"step": 2, "action": "Enable sidechain"},
                {"step": 3, "action": "Set sidechain source to kick/trigger"},
                {"step": 4, "action": "Adjust threshold and ratio"},
                {"step": 5, "action": "Set attack and release for desired effect"}
            ]
            analysis["confidence"] = 0.85
        
        else:
            # Need more analysis or research
            analysis["detected_intent"] = "unknown"
            analysis["requires_research"] = True
            analysis["confidence"] = 0.3
        
        return analysis
    
    def _get_technique(self, name: str) -> Optional[Dict]:
        """Get a specific production technique"""
        return self.techniques.get(name)
    
    def _get_genre_preset(self, genre: str) -> Optional[Dict]:
        """Get genre-specific preset"""
        return self.genre_presets.get(genre.lower())
    
    def get_all_techniques(self) -> List[str]:
        """Get list of all known techniques"""
        return list(self.techniques.keys())
    
    def get_all_genres(self) -> List[str]:
        """Get list of all known genres"""
        return list(self.genre_presets.keys())

