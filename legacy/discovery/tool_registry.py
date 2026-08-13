"""
Dynamic Tool Registry

Manages available tools/functions for the AI.
Allows runtime discovery and registration of new capabilities.
"""

from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
import json
import os


@dataclass
class Tool:
    """Represents a registered tool/function"""
    name: str
    osc_path: str
    description: str
    parameters: Dict[str, Dict] = field(default_factory=dict)
    category: str = "general"
    success_count: int = 0
    failure_count: int = 0
    last_used: Optional[datetime] = None
    confidence: float = 1.0
    discovered: bool = False  # True if discovered at runtime
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "osc_path": self.osc_path,
            "description": self.description,
            "parameters": self.parameters,
            "category": self.category,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "confidence": self.confidence,
            "discovered": self.discovered
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Tool':
        return cls(
            name=data["name"],
            osc_path=data["osc_path"],
            description=data["description"],
            parameters=data.get("parameters", {}),
            category=data.get("category", "general"),
            success_count=data.get("success_count", 0),
            failure_count=data.get("failure_count", 0),
            confidence=data.get("confidence", 1.0),
            discovered=data.get("discovered", False)
        )


class ToolRegistry:
    """
    Dynamic registry for Ableton control tools
    
    Features:
    - Register new tools at runtime
    - Track success/failure rates
    - Generate Gemini function declarations
    - Persist discovered tools
    """
    
    def __init__(self, storage_path: str = "config/tool_registry.json"):
        self.tools: Dict[str, Tool] = {}
        self.storage_path = storage_path
        self.categories = {
            "playback": "Playback controls (play, stop, record)",
            "transport": "Transport controls (tempo, loop, position)",
            "track": "Track controls (mute, solo, volume, pan)",
            "scene": "Scene controls (fire, select)",
            "clip": "Clip controls (fire, stop)",
            "device": "Device controls (add, parameter)",
            "query": "Query functions (get state)",
            "discovered": "Dynamically discovered functions"
        }
        
        # Load persisted tools
        self._load_registry()
        
        # Register core tools
        self._register_core_tools()
    
    def _register_core_tools(self):
        """Register the core set of known tools"""
        core_tools = [
            # Playback
            Tool(
                name="play",
                osc_path="/live/song/start_playing",
                description="Start playback in Ableton Live",
                parameters={},
                category="playback"
            ),
            Tool(
                name="stop",
                osc_path="/live/song/stop_playing",
                description="Stop playback in Ableton Live",
                parameters={},
                category="playback"
            ),
            Tool(
                name="continue_playback",
                osc_path="/live/song/continue_playing",
                description="Continue playback from current position",
                parameters={},
                category="playback"
            ),
            Tool(
                name="start_recording",
                osc_path="/live/song/set/record_mode",
                description="Enable record mode",
                parameters={"value": {"type": "int", "default": 1}},
                category="playback"
            ),
            Tool(
                name="stop_recording",
                osc_path="/live/song/set/record_mode",
                description="Disable record mode",
                parameters={"value": {"type": "int", "default": 0}},
                category="playback"
            ),
            Tool(
                name="toggle_metronome",
                osc_path="/live/song/set/metronome",
                description="Set metronome on/off",
                parameters={"state": {"type": "int", "enum": [0, 1]}},
                category="playback"
            ),
            
            # Transport
            Tool(
                name="set_tempo",
                osc_path="/live/song/set/tempo",
                description="Set the tempo/BPM",
                parameters={"bpm": {"type": "float", "min": 20, "max": 999}},
                category="transport"
            ),
            Tool(
                name="set_position",
                osc_path="/live/song/set/current_song_time",
                description="Set playback position in beats",
                parameters={"beat": {"type": "float", "min": 0}},
                category="transport"
            ),
            Tool(
                name="set_loop",
                osc_path="/live/song/set/loop",
                description="Enable/disable loop",
                parameters={"enabled": {"type": "int", "enum": [0, 1]}},
                category="transport"
            ),
            Tool(
                name="set_loop_start",
                osc_path="/live/song/set/loop_start",
                description="Set loop start position",
                parameters={"beat": {"type": "float"}},
                category="transport"
            ),
            Tool(
                name="set_loop_length",
                osc_path="/live/song/set/loop_length",
                description="Set loop length in beats",
                parameters={"beats": {"type": "float"}},
                category="transport"
            ),
            
            # Track controls
            Tool(
                name="mute_track",
                osc_path="/live/track/set/mute",
                description="Mute/unmute a track. Track 1 = index 0.",
                parameters={
                    "track_index": {"type": "int", "description": "0-based track index"},
                    "muted": {"type": "int", "enum": [0, 1]}
                },
                category="track"
            ),
            Tool(
                name="solo_track",
                osc_path="/live/track/set/solo",
                description="Solo/unsolo a track. Track 1 = index 0.",
                parameters={
                    "track_index": {"type": "int"},
                    "soloed": {"type": "int", "enum": [0, 1]}
                },
                category="track"
            ),
            Tool(
                name="arm_track",
                osc_path="/live/track/set/arm",
                description="Arm/disarm track for recording. Track 1 = index 0.",
                parameters={
                    "track_index": {"type": "int"},
                    "armed": {"type": "int", "enum": [0, 1]}
                },
                category="track"
            ),
            Tool(
                name="set_track_volume",
                osc_path="/live/track/set/volume",
                description="Set track volume. Track 1 = index 0.",
                parameters={
                    "track_index": {"type": "int"},
                    "volume": {"type": "float", "min": 0.0, "max": 1.0}
                },
                category="track"
            ),
            Tool(
                name="set_track_pan",
                osc_path="/live/track/set/panning",
                description="Set track pan. Track 1 = index 0.",
                parameters={
                    "track_index": {"type": "int"},
                    "pan": {"type": "float", "min": -1.0, "max": 1.0}
                },
                category="track"
            ),
            Tool(
                name="set_track_send",
                osc_path="/live/track/set/send",
                description="Set track send level. Track 1 = index 0.",
                parameters={
                    "track_index": {"type": "int"},
                    "send_index": {"type": "int"},
                    "level": {"type": "float", "min": 0.0, "max": 1.0}
                },
                category="track"
            ),
            
            # Scene controls
            Tool(
                name="fire_scene",
                osc_path="/live/scene/fire",
                description="Fire a scene. Scene 1 = index 0.",
                parameters={"scene_index": {"type": "int"}},
                category="scene"
            ),
            
            # Clip controls
            Tool(
                name="fire_clip",
                osc_path="/live/clip/fire",
                description="Fire a clip. Track 1 = index 0, Clip 1 = index 0.",
                parameters={
                    "track_index": {"type": "int"},
                    "clip_index": {"type": "int"}
                },
                category="clip"
            ),
            Tool(
                name="stop_clip",
                osc_path="/live/track/stop_all_clips",
                description="Stop all clips on a track. Track 1 = index 0.",
                parameters={"track_index": {"type": "int"}},
                category="clip"
            ),
            Tool(
                name="stop_all_clips",
                osc_path="/live/song/stop_all_clips",
                description="Stop all clips in the session",
                parameters={},
                category="clip"
            ),
        ]
        
        for tool in core_tools:
            if tool.name not in self.tools:
                self.tools[tool.name] = tool
    
    def register_tool(self, tool: Tool) -> bool:
        """Register a new tool"""
        if tool.name in self.tools:
            # Update existing
            existing = self.tools[tool.name]
            existing.osc_path = tool.osc_path
            existing.description = tool.description
            existing.parameters = tool.parameters
            return False
        
        self.tools[tool.name] = tool
        self._save_registry()
        return True
    
    def discover_tool(self, name: str, osc_path: str, description: str, 
                     parameters: Dict = None) -> Tool:
        """Register a dynamically discovered tool"""
        tool = Tool(
            name=name,
            osc_path=osc_path,
            description=description,
            parameters=parameters or {},
            category="discovered",
            discovered=True
        )
        self.register_tool(tool)
        return tool
    
    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a tool by name"""
        return self.tools.get(name)
    
    def get_tools_by_category(self, category: str) -> List[Tool]:
        """Get all tools in a category"""
        return [t for t in self.tools.values() if t.category == category]
    
    def record_success(self, name: str):
        """Record a successful tool execution"""
        if name in self.tools:
            self.tools[name].success_count += 1
            self.tools[name].last_used = datetime.now()
            self._update_confidence(name)
            self._save_registry()
    
    def record_failure(self, name: str):
        """Record a failed tool execution"""
        if name in self.tools:
            self.tools[name].failure_count += 1
            self._update_confidence(name)
            self._save_registry()
    
    def _update_confidence(self, name: str):
        """Update confidence score based on success/failure rate"""
        tool = self.tools.get(name)
        if tool:
            total = tool.success_count + tool.failure_count
            if total > 0:
                tool.confidence = tool.success_count / total
    
    def get_all_tools(self) -> List[Tool]:
        """Get all registered tools"""
        return list(self.tools.values())
    
    def get_tool_names(self) -> List[str]:
        """Get all tool names"""
        return list(self.tools.keys())
    
    def generate_gemini_tools(self) -> List[Dict]:
        """Generate Gemini function declarations from registry"""
        from google.genai import types
        
        function_declarations = []
        
        for tool in self.tools.values():
            # Build parameter schema
            properties = {}
            required = []
            
            for param_name, param_info in tool.parameters.items():
                param_type = param_info.get("type", "string")
                type_map = {
                    "int": "integer",
                    "float": "number",
                    "string": "string",
                    "bool": "boolean"
                }
                
                schema = {"type": type_map.get(param_type, "string")}
                
                if "description" in param_info:
                    schema["description"] = param_info["description"]
                if "enum" in param_info:
                    schema["enum"] = param_info["enum"]
                if "min" in param_info:
                    schema["minimum"] = param_info["min"]
                if "max" in param_info:
                    schema["maximum"] = param_info["max"]
                
                properties[param_name] = schema
                
                if "default" not in param_info:
                    required.append(param_name)
            
            function_declarations.append(
                types.FunctionDeclaration(
                    name=tool.name,
                    description=tool.description,
                    parameters=types.Schema(
                        type="object",
                        properties={k: types.Schema(**v) for k, v in properties.items()},
                        required=required
                    )
                )
            )
        
        return [types.Tool(function_declarations=function_declarations)]
    
    def _save_registry(self):
        """Save registry to disk"""
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        
        data = {
            "version": "1.0",
            "tools": {name: tool.to_dict() for name, tool in self.tools.items() if tool.discovered}
        }
        
        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    
    def _load_registry(self):
        """Load registry from disk"""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    for name, tool_data in data.get("tools", {}).items():
                        self.tools[name] = Tool.from_dict(tool_data)
            except Exception as e:
                print(f"Warning: Could not load tool registry: {e}")


# Global registry instance
tool_registry = ToolRegistry()

