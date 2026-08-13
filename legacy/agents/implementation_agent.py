"""
Implementation Agent

Converts workflow plans into executable Python/OSC commands.
This agent bridges the gap between abstract production goals and concrete actions.
"""

from typing import Dict, Any, List, Optional
from agents import AgentType, AgentMessage
from agent_system import BaseAgent


class ImplementationAgent(BaseAgent):
    """
    Converts plans into executable commands
    
    Responsibilities:
    - Generate OSC commands from workflow plans
    - Map abstract concepts to concrete Ableton actions
    - Handle parameter validation
    - Generate code for complex operations
    """
    
    def __init__(self, orchestrator):
        super().__init__(AgentType.IMPLEMENTER, orchestrator)
        
        # Device name mappings (common names to Ableton device names)
        self.device_mappings = {
            "compressor": "Compressor",
            "eq": "EQ Eight",
            "equalizer": "EQ Eight",
            "reverb": "Reverb",
            "delay": "Simple Delay",
            "chorus": "Chorus",
            "saturator": "Saturator",
            "saturation": "Saturator",
            "limiter": "Limiter",
            "gate": "Gate",
            "glue": "Glue Compressor",
            "drum_buss": "Drum Buss",
            "utility": "Utility",
            "auto_filter": "Auto Filter",
            "phaser": "Phaser",
            "flanger": "Flanger",
            "vocoder": "Vocoder",
        }
    
    async def process(self, message: AgentMessage) -> AgentMessage:
        """Process implementation requests"""
        content = message.content
        action = content.get("action", "implement")
        
        if action == "implement":
            commands = await self._implement_plan(content.get("plan", {}))
            return AgentMessage(
                sender=self.agent_type,
                recipient=message.sender,
                content={
                    "success": True,
                    "commands": commands
                },
                correlation_id=message.correlation_id
            )
        
        elif action == "generate_command":
            command = self._generate_single_command(
                content.get("operation", ""),
                content.get("parameters", {})
            )
            return AgentMessage(
                sender=self.agent_type,
                recipient=message.sender,
                content={
                    "success": command is not None,
                    "command": command
                },
                correlation_id=message.correlation_id
            )
        
        return AgentMessage(
            sender=self.agent_type,
            recipient=message.sender,
            content={"error": f"Unknown action: {action}"},
            correlation_id=message.correlation_id
        )
    
    async def _implement_plan(self, plan: Dict) -> List[Dict]:
        """
        Convert a workflow plan into executable commands
        """
        print(f"[IMPLEMENTATION] Translating plan to commands")
        if isinstance(plan, list):
            # Plan is already a list of steps
            steps = plan
        else:
            # Plan is a dict with a 'steps' key
            steps = plan.get("plan", plan.get("steps", []))
        
        commands = []
        
        for step in steps:
            step_commands = self._convert_step_to_commands(step)
            # print(f"[IMPLEMENTATION] Step: {step.get('description', 'unnamed')} -> {len(step_commands)} commands")
            commands.extend(step_commands)
        
        print(f"[IMPLEMENTATION] Generated {len(commands)} total commands")
        return commands
    
    def _convert_step_to_commands(self, step: Dict) -> List[Dict]:
        """Convert a single workflow step to OSC commands"""
        commands = []
        
        # If step already has commands, use them
        if "commands" in step:
            for cmd in step["commands"]:
                processed_cmd = self._process_command(cmd)
                if processed_cmd:
                    commands.append(processed_cmd)
            return commands
        
        # Otherwise, try to parse the step description
        description = step.get("description", step.get("action", ""))
        
        parsed_commands = self._parse_description_to_commands(description)
        commands.extend(parsed_commands)
        
        return commands
    
    def _process_command(self, cmd: Dict) -> Optional[Dict]:
        """Process and validate a command"""
        function = cmd.get("function", "")
        args = cmd.get("args", {})

        print(f"[IMPLEMENTATION] Processing command request: {function}")
        
        # Validate function exists
        valid_functions = {
            # Playback
            "play", "stop", "continue_playback",
            "start_recording", "stop_recording",
            "toggle_metronome", "set_tempo",
            
            # Track controls
            "mute_track", "solo_track", "arm_track",
            "set_track_volume", "set_track_pan", "set_track_send",
            
            # Transport
            "set_loop", "set_loop_start", "set_loop_length", "set_position",
            
            # Scene/Clip
            "fire_scene", "fire_clip", "stop_clip", "stop_all_clips",
            
            # Device (advanced - may not work with basic AbletonOSC)
            "add_device", "set_device_parameter", "get_device_parameters",
            
            # Track creation (advanced)
            "create_return_track", "create_audio_track", "create_midi_track",
        }
        
        if function not in valid_functions:
            return None
        
        return {
            "function": function,
            "args": args
        }
    
    def _parse_description_to_commands(self, description: str) -> List[Dict]:
        """Parse a text description into commands"""
        commands = []
        desc_lower = description.lower()
        
        # Add device patterns
        if "add compressor" in desc_lower:
            commands.append({
                "function": "add_device",
                "args": {"device": "Compressor"}
            })
        
        if "add eq" in desc_lower or "add equalizer" in desc_lower:
            commands.append({
                "function": "add_device",
                "args": {"device": "EQ Eight"}
            })
        
        if "add reverb" in desc_lower:
            commands.append({
                "function": "add_device",
                "args": {"device": "Reverb"}
            })
        
        if "add saturat" in desc_lower:
            commands.append({
                "function": "add_device",
                "args": {"device": "Saturator"}
            })
        
        # Track actions
        if "mute" in desc_lower:
            # Try to extract track number
            import re
            track_match = re.search(r'track\s*(\d+)', desc_lower)
            track_idx = int(track_match.group(1)) - 1 if track_match else 0
            commands.append({
                "function": "mute_track",
                "args": {"track_index": track_idx, "muted": 1}
            })
        
        if "solo" in desc_lower:
            import re
            track_match = re.search(r'track\s*(\d+)', desc_lower)
            track_idx = int(track_match.group(1)) - 1 if track_match else 0
            commands.append({
                "function": "solo_track",
                "args": {"track_index": track_idx, "soloed": 1}
            })
        
        # Send/routing
        if "send" in desc_lower or "route" in desc_lower:
            commands.append({
                "function": "set_track_send",
                "args": {"track_index": 0, "send_index": 0, "level": 0.5}
            })
        
        # High-pass filter
        if "high-pass" in desc_lower or "high pass" in desc_lower:
            commands.append({
                "function": "add_device",
                "args": {"device": "EQ Eight"}
            })
        
        return commands
    
    def _generate_single_command(self, operation: str, parameters: Dict) -> Optional[Dict]:
        """Generate a single command from an operation description"""
        op_lower = operation.lower()
        
        # Playback operations
        if op_lower in ["play", "start"]:
            return {"function": "play", "args": {}}
        
        if op_lower in ["stop", "pause"]:
            return {"function": "stop", "args": {}}
        
        # Tempo
        if "tempo" in op_lower or "bpm" in op_lower:
            bpm = parameters.get("bpm", parameters.get("tempo", 120))
            return {"function": "set_tempo", "args": {"bpm": bpm}}
        
        # Track mute - STANDARDIZED: require track_index, convert 1-based to 0-based
        if "mute" in op_lower:
            track = parameters.get("track_index", parameters.get("track"))
            if track is None:
                return None  # track_index required
            if isinstance(track, int) and track > 0:
                track -= 1  # Convert 1-based to 0-based
            return {"function": "mute_track", "args": {"track_index": track, "muted": 1}}

        # Track solo - STANDARDIZED: require track_index, convert 1-based to 0-based
        if "solo" in op_lower:
            track = parameters.get("track_index", parameters.get("track"))
            if track is None:
                return None  # track_index required
            if isinstance(track, int) and track > 0:
                track -= 1  # Convert 1-based to 0-based
            return {"function": "solo_track", "args": {"track_index": track, "soloed": 1}}
        
        # Volume - STANDARDIZED: Convert 1-based to 0-based
        if "volume" in op_lower:
            track = parameters.get("track_index", parameters.get("track"))
            if track is None:
                return None  # track_index required
            if isinstance(track, int) and track > 0:
                track -= 1  # Convert 1-based to 0-based
            volume = parameters.get("volume", 0.85)
            return {"function": "set_track_volume", "args": {"track_index": track, "volume": volume}}

        # Pan - STANDARDIZED: Convert 1-based to 0-based
        if "pan" in op_lower:
            track = parameters.get("track_index", parameters.get("track"))
            if track is None:
                return None  # track_index required
            if isinstance(track, int) and track > 0:
                track -= 1  # Convert 1-based to 0-based
            pan = parameters.get("pan", 0.0)
            return {"function": "set_track_pan", "args": {"track_index": track, "pan": pan}}

        # Scene - Convert 1-based to 0-based
        if "scene" in op_lower:
            scene = parameters.get("scene_index", parameters.get("scene"))
            if scene is None:
                return None  # scene_index required
            if isinstance(scene, int) and scene > 0:
                scene -= 1  # Convert 1-based to 0-based
            return {"function": "fire_scene", "args": {"scene_index": scene}}

        # Clip - STANDARDIZED: Convert 1-based to 0-based for both track and clip
        if "clip" in op_lower:
            track = parameters.get("track_index", parameters.get("track"))
            clip = parameters.get("clip_index", parameters.get("clip"))
            if track is None or clip is None:
                return None  # track_index and clip_index required
            if isinstance(track, int) and track > 0:
                track -= 1  # Convert 1-based to 0-based
            if isinstance(clip, int) and clip > 0:
                clip -= 1  # Convert 1-based to 0-based
            return {"function": "fire_clip", "args": {"track_index": track, "clip_index": clip}}
        
        return None
    
    def get_available_devices(self) -> List[str]:
        """Get list of available device names"""
        return list(self.device_mappings.values())
    
    def get_device_name(self, common_name: str) -> Optional[str]:
        """Get Ableton device name from common name"""
        return self.device_mappings.get(common_name.lower())

