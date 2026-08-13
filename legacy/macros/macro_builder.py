"""
Macro Builder

Create, save, and execute custom command macros.
Macros are reusable sequences of Ableton commands.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json
import os


@dataclass
class MacroStep:
    """A single step in a macro"""
    function: str
    args: Dict[str, Any] = field(default_factory=dict)
    delay_after_ms: int = 100  # Delay after this step
    description: str = ""


@dataclass
class Macro:
    """A reusable command macro"""
    name: str
    description: str
    steps: List[MacroStep] = field(default_factory=list)
    category: str = "custom"
    trigger_phrase: Optional[str] = None  # Voice trigger
    created_at: datetime = field(default_factory=datetime.now)
    use_count: int = 0
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "steps": [
                {
                    "function": s.function,
                    "args": s.args,
                    "delay_after_ms": s.delay_after_ms,
                    "description": s.description
                }
                for s in self.steps
            ],
            "category": self.category,
            "trigger_phrase": self.trigger_phrase,
            "created_at": self.created_at.isoformat(),
            "use_count": self.use_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Macro':
        steps = [
            MacroStep(
                function=s["function"],
                args=s.get("args", {}),
                delay_after_ms=s.get("delay_after_ms", 100),
                description=s.get("description", "")
            )
            for s in data.get("steps", [])
        ]
        
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            steps=steps,
            category=data.get("category", "custom"),
            trigger_phrase=data.get("trigger_phrase"),
            use_count=data.get("use_count", 0)
        )


class MacroBuilder:
    """
    Build and manage macros
    
    Features:
    - Create macros from step sequences
    - Record macros from user actions
    - Execute macros
    - Persist macros to disk
    """
    
    def __init__(self, storage_path: str = "config/macros.json"):
        self.storage_path = storage_path
        self.macros: Dict[str, Macro] = {}
        self.recording: bool = False
        self.recorded_steps: List[MacroStep] = []
        
        # Load saved macros
        self._load_macros()
        
        # Add built-in macros
        self._create_builtin_macros()
    
    def _create_builtin_macros(self):
        """Create built-in macro presets"""
        builtin = [
            Macro(
                name="Solo Check All",
                description="Solo each track briefly to check the mix",
                steps=[
                    MacroStep("solo_track", {"track_index": 0, "soloed": 1}, 2000, "Solo track 1"),
                    MacroStep("solo_track", {"track_index": 0, "soloed": 0}, 100, "Unsolo track 1"),
                    MacroStep("solo_track", {"track_index": 1, "soloed": 1}, 2000, "Solo track 2"),
                    MacroStep("solo_track", {"track_index": 1, "soloed": 0}, 100, "Unsolo track 2"),
                ],
                category="mixing",
                trigger_phrase="solo check"
            ),
            Macro(
                name="Mute All",
                description="Mute all tracks (first 8)",
                steps=[
                    MacroStep("mute_track", {"track_index": i, "muted": 1}, 50)
                    for i in range(8)
                ],
                category="utility",
                trigger_phrase="mute all"
            ),
            Macro(
                name="Unmute All",
                description="Unmute all tracks (first 8)",
                steps=[
                    MacroStep("mute_track", {"track_index": i, "muted": 0}, 50)
                    for i in range(8)
                ],
                category="utility",
                trigger_phrase="unmute all"
            ),
            Macro(
                name="Reset Mix",
                description="Reset volume and pan on all tracks",
                steps=[
                    step
                    for i in range(8)
                    for step in [
                        MacroStep("set_track_volume", {"track_index": i, "volume": 0.85}, 50),
                        MacroStep("set_track_pan", {"track_index": i, "pan": 0.0}, 50),
                        MacroStep("mute_track", {"track_index": i, "muted": 0}, 50),
                        MacroStep("solo_track", {"track_index": i, "soloed": 0}, 50),
                    ]
                ],
                category="utility",
                trigger_phrase="reset mix"
            ),
            Macro(
                name="Playback Start",
                description="Stop, go to beginning, then play",
                steps=[
                    MacroStep("stop", {}, 100, "Stop playback"),
                    MacroStep("set_position", {"beat": 0}, 100, "Go to start"),
                    MacroStep("play", {}, 0, "Start playback"),
                ],
                category="playback",
                trigger_phrase="play from start"
            ),
            Macro(
                name="Quick Vocal Setup",
                description="Set up basic vocal processing on track 1",
                steps=[
                    MacroStep("load_device", {"track_index": 0, "device_name": "EQ Eight"}, 1500, "Add EQ"),
                    MacroStep("load_device", {"track_index": 0, "device_name": "Compressor"}, 1500, "Add Compressor"),
                    MacroStep("load_device", {"track_index": 0, "device_name": "Reverb"}, 1500, "Add Reverb"),
                ],
                category="production",
                trigger_phrase="vocal setup"
            ),
            Macro(
                name="Quick Drum Bus",
                description="Set up drum bus processing on track 1",
                steps=[
                    MacroStep("load_device", {"track_index": 0, "device_name": "Glue Compressor"}, 1500, "Add Glue Compressor"),
                    MacroStep("load_device", {"track_index": 0, "device_name": "Saturator"}, 1500, "Add Saturator"),
                    MacroStep("load_device", {"track_index": 0, "device_name": "EQ Eight"}, 1500, "Add EQ"),
                ],
                category="production",
                trigger_phrase="drum bus"
            ),
            Macro(
                name="Mastering Chain",
                description="Set up basic mastering chain on master",
                steps=[
                    MacroStep("load_device", {"track_index": -1, "device_name": "EQ Eight"}, 1500, "Add EQ"),
                    MacroStep("load_device", {"track_index": -1, "device_name": "Glue Compressor"}, 1500, "Add Glue Compressor"),
                    MacroStep("load_device", {"track_index": -1, "device_name": "Limiter"}, 1500, "Add Limiter"),
                ],
                category="production",
                trigger_phrase="mastering chain"
            ),
            Macro(
                name="A/B Reference",
                description="Toggle between solo track 1 and all tracks",
                steps=[
                    MacroStep("solo_track", {"track_index": 0, "soloed": 1}, 3000, "Solo reference"),
                    MacroStep("solo_track", {"track_index": 0, "soloed": 0}, 0, "Unsolo"),
                ],
                category="mixing",
                trigger_phrase="A B reference"
            ),
            Macro(
                name="Bounce Check",
                description="Prepare for bouncing - unsolo/unmute all, stop",
                steps=[
                    MacroStep("stop", {}, 100, "Stop playback"),
                    *[MacroStep("solo_track", {"track_index": i, "soloed": 0}, 50) for i in range(16)],
                    *[MacroStep("mute_track", {"track_index": i, "muted": 0}, 50) for i in range(16)],
                    MacroStep("set_position", {"beat": 0}, 100, "Go to start"),
                ],
                category="utility",
                trigger_phrase="bounce check"
            ),
        ]
        
        for macro in builtin:
            if macro.name not in self.macros:
                self.macros[macro.name] = macro
    
    def create_macro(self, name: str, description: str, 
                    steps: List[Dict], category: str = "custom",
                    trigger_phrase: str = None) -> Macro:
        """Create a new macro"""
        macro_steps = [
            MacroStep(
                function=s.get("function", ""),
                args=s.get("args", {}),
                delay_after_ms=s.get("delay_after_ms", 100),
                description=s.get("description", "")
            )
            for s in steps
        ]
        
        macro = Macro(
            name=name,
            description=description,
            steps=macro_steps,
            category=category,
            trigger_phrase=trigger_phrase
        )
        
        self.macros[name] = macro
        self._save_macros()
        
        return macro
    
    def start_recording(self):
        """Start recording a new macro"""
        self.recording = True
        self.recorded_steps = []
        print("[REC] Macro recording started...")
    
    def record_step(self, function: str, args: Dict = None, description: str = ""):
        """Record a step during macro recording"""
        if self.recording:
            self.recorded_steps.append(MacroStep(
                function=function,
                args=args or {},
                description=description
            ))
            print(f"  [+] Recorded: {function}")
    
    def stop_recording(self, name: str, description: str = "") -> Optional[Macro]:
        """Stop recording and save the macro"""
        if not self.recording:
            return None
        
        self.recording = False
        
        if not self.recorded_steps:
            print("[!] No steps recorded")
            return None
        
        macro = Macro(
            name=name,
            description=description,
            steps=self.recorded_steps,
            category="recorded"
        )
        
        self.macros[name] = macro
        self._save_macros()
        
        print(f"[OK] Saved macro '{name}' with {len(self.recorded_steps)} steps")
        self.recorded_steps = []
        
        return macro
    
    def cancel_recording(self):
        """Cancel macro recording"""
        self.recording = False
        self.recorded_steps = []
        print("[STOP] Macro recording cancelled")
    
    def get_macro(self, name: str) -> Optional[Macro]:
        """Get a macro by name"""
        return self.macros.get(name)
    
    def find_by_trigger(self, phrase: str) -> Optional[Macro]:
        """Find a macro by its trigger phrase"""
        phrase_lower = phrase.lower()
        for macro in self.macros.values():
            if macro.trigger_phrase and macro.trigger_phrase.lower() in phrase_lower:
                return macro
        return None
    
    def get_macros_by_category(self, category: str) -> List[Macro]:
        """Get all macros in a category"""
        return [m for m in self.macros.values() if m.category == category]
    
    def list_macros(self) -> List[str]:
        """List all macro names"""
        return list(self.macros.keys())
    
    def delete_macro(self, name: str) -> bool:
        """Delete a macro"""
        if name in self.macros:
            del self.macros[name]
            self._save_macros()
            return True
        return False
    
    async def execute_macro(self, name: str, ableton_controller) -> Dict[str, Any]:
        """Execute a macro"""
        macro = self.macros.get(name)
        if not macro:
            return {"success": False, "message": f"Macro '{name}' not found"}
        
        import asyncio
        
        results = []
        all_success = True
        
        print(f"[>] Executing macro: {macro.name}")
        
        for i, step in enumerate(macro.steps):
            # Get the function from the controller
            if hasattr(ableton_controller, step.function):
                func = getattr(ableton_controller, step.function)
                try:
                    result = func(**step.args) if step.args else func()
                    results.append({
                        "step": i + 1,
                        "function": step.function,
                        "result": result
                    })
                    
                    if not result.get("success", True):
                        all_success = False
                        
                except Exception as e:
                    results.append({
                        "step": i + 1,
                        "function": step.function,
                        "error": str(e)
                    })
                    all_success = False
            else:
                results.append({
                    "step": i + 1,
                    "function": step.function,
                    "error": "Function not found"
                })
                all_success = False
            
            # Delay before next step
            if step.delay_after_ms > 0:
                await asyncio.sleep(step.delay_after_ms / 1000)
        
        # Update use count
        macro.use_count += 1
        self._save_macros()
        
        return {
            "success": all_success,
            "message": f"Executed {len(macro.steps)} steps",
            "results": results
        }
    
    def _save_macros(self):
        """Save macros to disk"""
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        
        # Only save custom/recorded macros
        custom_macros = {
            name: macro.to_dict()
            for name, macro in self.macros.items()
            if macro.category in ["custom", "recorded"]
        }
        
        data = {
            "version": "1.0",
            "macros": custom_macros
        }
        
        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _load_macros(self):
        """Load macros from disk"""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    for name, macro_data in data.get("macros", {}).items():
                        self.macros[name] = Macro.from_dict(macro_data)
            except Exception as e:
                print(f"Warning: Could not load macros: {e}")


# Global macro builder instance
macro_builder = MacroBuilder()

