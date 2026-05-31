"""
Executor Agent

Executes commands and workflows against Ableton Live via OSC.
This is the final stage of the agent pipeline.

Enhanced with:
- Undo/rollback capability
- Action recording for session persistence
- Retry logic with exponential backoff
"""

from typing import Dict, Any, List, Optional, Tuple
from agents import AgentType, AgentMessage, ExecutionResult
from agent_system import BaseAgent
import asyncio


class ExecutorAgent(BaseAgent):
    """
    Executes commands against Ableton Live

    Responsibilities:
    - Execute simple commands directly
    - Execute multi-step workflows
    - Handle errors and retries
    - Provide undo/rollback capability
    - Record actions for persistence
    - Report results back to orchestrator
    """

    # Actions that can be undone with their inverse operations
    UNDOABLE_ACTIONS = {
        "mute_track": ("mute_track", lambda p: {**p, "muted": 0 if p.get("muted") else 1}),
        "solo_track": ("solo_track", lambda p: {**p, "soloed": 0 if p.get("soloed") else 1}),
        "arm_track": ("arm_track", lambda p: {**p, "armed": 0 if p.get("armed") else 1}),
        "set_track_volume": ("set_track_volume", lambda p: p),  # Needs previous value
        "set_track_pan": ("set_track_pan", lambda p: p),  # Needs previous value
        "set_tempo": ("set_tempo", lambda p: p),  # Needs previous value
        "set_loop": ("set_loop", lambda p: {**p, "enabled": 0 if p.get("enabled") else 1}),
        "toggle_metronome": ("toggle_metronome", lambda p: {"state": 0 if p.get("state") else 1}),
    }

    def __init__(self, orchestrator):
        super().__init__(AgentType.EXECUTOR, orchestrator)

        # Undo stack for this session
        self._undo_stack: List[Dict[str, Any]] = []
        self._max_undo_stack = 50

        # Persistence (lazy loaded)
        self._persistence = None

    @property
    def persistence(self):
        """Get the session persistence instance (lazy loaded)"""
        if self._persistence is None:
            try:
                from context.session_persistence import get_session_persistence
                self._persistence = get_session_persistence()
            except ImportError:
                pass
        return self._persistence
    
    async def process(self, message: AgentMessage) -> AgentMessage:
        """Process execution requests"""
        content = message.content
        action = content.get("action", "execute_simple")

        if action == "execute_simple":
            result = await self._execute_simple(content)
        elif action == "execute_workflow":
            result = await self._execute_workflow(content)
        elif action == "undo":
            result = await self._execute_undo(content.get("action_id"))
        elif action == "get_undo_history":
            result = self._get_undo_history(content.get("limit", 10))
        else:
            result = {"success": False, "message": f"Unknown action: {action}"}

        return AgentMessage(
            sender=self.agent_type,
            recipient=message.sender,
            content=result,
            correlation_id=message.correlation_id
        )

    def _record_action(self, function_name: str, parameters: Dict[str, Any],
                       result: Dict[str, Any], previous_value: Any = None):
        """Record an action for undo capability"""
        can_undo = function_name in self.UNDOABLE_ACTIONS
        undo_action = None

        if can_undo:
            undo_func, undo_params_fn = self.UNDOABLE_ACTIONS[function_name]

            # For value-based actions, we need the previous value
            if function_name in ("set_track_volume", "set_track_pan", "set_tempo"):
                if previous_value is not None:
                    if function_name == "set_tempo":
                        undo_action = {"function": undo_func, "args": {"bpm": previous_value}}
                    else:
                        param_key = "volume" if "volume" in function_name else "pan"
                        undo_action = {
                            "function": undo_func,
                            "args": {
                                "track_index": parameters.get("track_index"),
                                param_key: previous_value
                            }
                        }
                else:
                    can_undo = False
            else:
                undo_action = {"function": undo_func, "args": undo_params_fn(parameters)}

        # Add to undo stack
        if can_undo and undo_action:
            import uuid
            action_id = str(uuid.uuid4())[:8]

            self._undo_stack.append({
                "action_id": action_id,
                "function": function_name,
                "parameters": parameters,
                "undo_action": undo_action,
                "result": result
            })

            # Limit stack size
            if len(self._undo_stack) > self._max_undo_stack:
                self._undo_stack = self._undo_stack[-self._max_undo_stack:]

            # Also record in persistence if available
            if self.persistence:
                self.persistence.record_action(
                    action_type=self._get_action_type(function_name),
                    function_name=function_name,
                    parameters=parameters,
                    result=result,
                    can_undo=can_undo,
                    undo_action=undo_action
                )

    def _get_action_type(self, function_name: str) -> str:
        """Determine action type from function name"""
        if function_name in ("play", "stop", "continue_playback", "start_recording",
                             "stop_recording", "set_tempo", "set_position"):
            return "transport"
        elif function_name.startswith("mute") or function_name.startswith("solo") or \
             function_name.startswith("arm") or "track" in function_name:
            return "track"
        elif "device" in function_name or "plugin" in function_name:
            return "device"
        elif "scene" in function_name or "clip" in function_name:
            return "scene_clip"
        else:
            return "other"

    async def _execute_undo(self, action_id: str = None) -> Dict[str, Any]:
        """Execute an undo operation"""
        ableton = self.orchestrator.ableton
        if not ableton:
            return {"success": False, "message": "Ableton controller not available"}

        # If no action_id, undo the last action
        if not action_id and self._undo_stack:
            action_entry = self._undo_stack.pop()
        elif action_id:
            # Find the specific action
            action_entry = None
            for i, entry in enumerate(reversed(self._undo_stack)):
                if entry.get("action_id") == action_id:
                    action_entry = self._undo_stack.pop(-(i + 1))
                    break
            if not action_entry:
                return {"success": False, "message": f"Action {action_id} not found in undo stack"}
        else:
            return {"success": False, "message": "No actions to undo"}

        undo_action = action_entry.get("undo_action")
        if not undo_action:
            return {"success": False, "message": "No undo action available"}

        # Execute the undo
        func_name = undo_action.get("function")
        args = undo_action.get("args", {})

        if hasattr(ableton, func_name):
            try:
                func = getattr(ableton, func_name)
                result = func(**args) if args else func()

                # Mark as undone in persistence
                if self.persistence:
                    self.persistence.mark_action_undone(action_entry.get("action_id", ""))

                return {
                    "success": True,
                    "message": f"Undid: {action_entry.get('function')}",
                    "undone_action": action_entry.get("function"),
                    "result": result
                }
            except Exception as e:
                return {"success": False, "message": f"Undo failed: {e}"}
        else:
            return {"success": False, "message": f"Unknown undo function: {func_name}"}

    def _get_undo_history(self, limit: int = 10) -> Dict[str, Any]:
        """Get recent undoable actions"""
        undoable = []
        for entry in reversed(self._undo_stack[-limit:]):
            undoable.append({
                "action_id": entry.get("action_id"),
                "function": entry.get("function"),
                "parameters": entry.get("parameters")
            })

        return {
            "success": True,
            "undoable_actions": undoable,
            "count": len(undoable)
        }
    
    async def _execute_simple(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a simple command with action recording"""
        intent = content.get("intent", "")
        extracted_action = content.get("extracted_action", "")
        parameters = content.get("parameters", {})

        ableton = self.orchestrator.ableton
        if not ableton:
            return {"success": False, "message": "Ableton controller not available"}

        # Get previous values for undo if needed
        previous_value = None
        if extracted_action in ("set_track_volume", "set_track_pan"):
            track_idx = parameters.get("track_index")
            if track_idx is None:
                return {"success": False, "message": "track_index required for volume/pan operations"}
            try:
                if extracted_action == "set_track_volume":
                    prev_result = ableton.get_track_volume(track_idx)
                    if prev_result.get("success"):
                        previous_value = prev_result.get("volume")
                else:
                    prev_result = ableton.get_track_pan(track_idx)
                    if prev_result.get("success"):
                        previous_value = prev_result.get("pan")
            except Exception:
                pass
        elif extracted_action == "set_tempo":
            try:
                prev_result = ableton.get_tempo()
                if prev_result.get("success"):
                    previous_value = prev_result.get("tempo")
            except Exception:
                pass

        # Map actions to Ableton controller methods
        action_map = {
            # Playback
            "play": lambda: ableton.play(),
            "stop": lambda: ableton.stop(),
            "pause": lambda: ableton.stop(),
            "continue": lambda: ableton.continue_playback(),
            "start_recording": lambda: ableton.start_recording(),
            "stop_recording": lambda: ableton.stop_recording(),
            "toggle_recording": lambda: ableton.start_recording(),
            
            # Metronome/Loop
            "toggle_metronome": lambda: ableton.toggle_metronome(parameters.get("state", 1)),
            "toggle_loop": lambda: ableton.set_loop(parameters.get("state", 1)),
            
            # Tempo
            "set_tempo": lambda: ableton.set_tempo(parameters.get("bpm", 120)),
            
            # Track controls - IMPORTANT: track_index must be explicitly provided
            "mute_track": lambda: ableton.mute_track(
                parameters.get("track_index"),
                1
            ) if parameters.get("track_index") is not None else {"success": False, "message": "track_index required"},
            "unmute_track": lambda: ableton.mute_track(
                parameters.get("track_index"),
                0
            ) if parameters.get("track_index") is not None else {"success": False, "message": "track_index required"},
            "solo_track": lambda: ableton.solo_track(
                parameters.get("track_index"),
                1
            ) if parameters.get("track_index") is not None else {"success": False, "message": "track_index required"},
            "unsolo_track": lambda: ableton.solo_track(
                parameters.get("track_index"),
                0
            ) if parameters.get("track_index") is not None else {"success": False, "message": "track_index required"},
            "arm_track": lambda: ableton.arm_track(
                parameters.get("track_index"),
                1
            ) if parameters.get("track_index") is not None else {"success": False, "message": "track_index required"},
            "disarm_track": lambda: ableton.arm_track(
                parameters.get("track_index"),
                0
            ) if parameters.get("track_index") is not None else {"success": False, "message": "track_index required"},
            "set_track_volume": lambda: ableton.set_track_volume(
                parameters.get("track_index"),
                parameters.get("volume", 0.85)
            ) if parameters.get("track_index") is not None else {"success": False, "message": "track_index required"},
            "set_track_pan": lambda: ableton.set_track_pan(
                parameters.get("track_index"),
                parameters.get("pan", 0.0)
            ) if parameters.get("track_index") is not None else {"success": False, "message": "track_index required"},

            # Scene/Clip - scene_index and clip_index must be explicitly provided
            "fire_scene": lambda: ableton.fire_scene(
                parameters.get("scene_index")
            ) if parameters.get("scene_index") is not None else {"success": False, "message": "scene_index required"},
            "fire_clip": lambda: ableton.fire_clip(
                parameters.get("track_index"),
                parameters.get("clip_index")
            ) if parameters.get("track_index") is not None and parameters.get("clip_index") is not None else {"success": False, "message": "track_index and clip_index required"},
            "stop_clip": lambda: ableton.stop_clip(
                parameters.get("track_index")
            ) if parameters.get("track_index") is not None else {"success": False, "message": "track_index required"},
        }
        
        # Execute the action
        if extracted_action in action_map:
            try:
                print(f"[EXECUTOR] Executing simple action: {extracted_action}")
                result = action_map[extracted_action]()

                # Record the action for undo capability
                if result.get("success"):
                    self._record_action(extracted_action, parameters, result, previous_value)

                return result
            except Exception as e:
                return {"success": False, "message": f"Execution error: {e}"}

        # Try to parse the intent directly if action not found
        return await self._parse_and_execute_intent(intent, ableton)
    
    async def _parse_and_execute_intent(self, intent: str, ableton) -> Dict[str, Any]:
        """Parse natural language intent and execute"""
        intent_lower = intent.lower()
        
        # Simple pattern matching for common commands
        if "play" in intent_lower and "stop" not in intent_lower:
            return ableton.play()
        
        if "stop" in intent_lower:
            return ableton.stop()
        
        if "metronome on" in intent_lower or "turn on metronome" in intent_lower:
            return ableton.toggle_metronome(1)
        
        if "metronome off" in intent_lower or "turn off metronome" in intent_lower:
            return ableton.toggle_metronome(0)
        
        # Extract tempo
        import re
        tempo_match = re.search(r'(\d+)\s*(?:bpm|tempo)', intent_lower) or \
                      re.search(r'tempo\s*(?:to|at)?\s*(\d+)', intent_lower)
        if tempo_match:
            bpm = int(tempo_match.group(1))
            return ableton.set_tempo(bpm)
        
        return {"success": False, "message": f"Could not understand: {intent}"}
    
    async def _execute_workflow(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a multi-step workflow.

        Supports planner-generated commands including ``add_device`` (mapped
        to ``load_device``) and name-based ``set_device_parameter`` (resolved
        via ``reliable_params.set_parameter_by_name``).

        The workflow tracks ``track_index`` (from content or default 0) and
        ``last_device_index`` so that ``set_device_parameter`` commands issued
        right after an ``add_device`` target the correct device automatically.
        """
        commands = content.get("commands", [])

        print(f"[EXECUTOR] Starting workflow execution ({len(commands)} commands)")

        if not commands:
            return {"success": False, "message": "No commands to execute"}

        ableton = self.orchestrator.ableton
        if not ableton:
            return {"success": False, "message": "Ableton controller not available"}

        # Track context carried across commands
        track_index = content.get("track_index", 0)
        last_device_index = content.get("device_index", None)
        # When a device load falls back to a stock device, subsequent
        # Waves-specific set_device_parameter calls should be skipped.
        _last_load_is_stock_fallback = False

        results = []
        all_success = True

        for i, cmd in enumerate(commands):
            if not isinstance(cmd, dict):
                continue

            func_name = cmd.get("function", "")
            args = dict(cmd.get("args", {}))  # copy so we don't mutate original

            # Skip Waves name-based params when we fell back to stock device
            if (func_name == "set_device_parameter"
                    and _last_load_is_stock_fallback
                    and args.get("param") and args.get("param_index") is None):
                print(f"[EXECUTOR] SKIP: {args.get('param')} (stock fallback, Waves param not applicable)")
                results.append({"step": i, "function": func_name,
                                "result": {"success": True, "skipped": True,
                                           "message": "Skipped: stock fallback device loaded"}})
                continue

            try:
                result = self._dispatch_command(
                    ableton, func_name, args, track_index, last_device_index
                )

                # Track device index and fallback state after add_device / load_device
                if func_name in ("add_device", "load_device"):
                    if result.get("success"):
                        new_idx = result.get("device_index")
                        if new_idx is not None:
                            last_device_index = new_idx
                        elif hasattr(ableton, "_find_last_device_index"):
                            last_device_index = ableton._find_last_device_index(track_index)

                    # Track whether we fell back to a stock device
                    loaded = result.get("loaded_device")
                    _last_load_is_stock_fallback = (
                        result.get("is_fallback", False)
                        and loaded is not None
                        and self._is_stock_device(loaded)
                    )

                results.append({"step": i, "function": func_name, "result": result})

                if result.get("success", False):
                    print(f"[EXECUTOR] SUCCESS: {func_name}")
                else:
                    print(f"[EXECUTOR] FAILED: {func_name} - {result.get('message')}")
                    all_success = False
            except Exception as e:
                results.append({"step": i, "function": func_name, "error": str(e)})
                all_success = False

            await asyncio.sleep(0.1)

        return {
            "success": all_success,
            "message": f"Executed {len(results)} commands" + (" successfully" if all_success else " with errors"),
            "results": results
        }

    def _dispatch_command(
        self,
        ableton,
        func_name: str,
        args: Dict[str, Any],
        track_index: int,
        last_device_index: Optional[int],
    ) -> Dict[str, Any]:
        """Translate and dispatch a single workflow command.

        Handles planner-generated commands that don't map 1:1 to controller
        methods:

        * ``add_device`` → ``ableton.load_device(track_index, device_name)``
        * ``set_device_parameter`` with ``param`` (name) + ``value`` →
          ``reliable_params.set_parameter_by_name()`` or falls back to
          ``ableton.set_device_parameter()`` when ``param_index`` is provided.
        """

        # -- add_device → load_device translation with fallback --
        if func_name == "add_device":
            device_name = args.get("device", args.get("device_name", ""))
            ti = args.get("track_index", track_index)
            position = args.get("position", -1)
            print(f"[EXECUTOR] Running: load_device (from add_device) device={device_name} track={ti}")

            result = ableton.load_device(ti, device_name, position)
            if result.get("success"):
                result["loaded_device"] = device_name
                result["is_fallback"] = False
                return result

            # Load failed — try fallbacks from PLUGIN_PREFERENCES
            fallbacks = args.get("fallbacks", [])
            if not fallbacks:
                fallbacks = self._lookup_fallbacks(device_name)

            for fb in fallbacks:
                print(f"[EXECUTOR] Fallback: trying {fb} (instead of {device_name})")
                result = ableton.load_device(ti, fb, position)
                if result.get("success"):
                    result["loaded_device"] = fb
                    result["is_fallback"] = True
                    result["original_device"] = device_name
                    print(f"[EXECUTOR] Fallback SUCCESS: loaded {fb}")
                    return result

            # All fallbacks failed too — return the original failure
            result["loaded_device"] = None
            result["is_fallback"] = True
            result["original_device"] = device_name
            return result

        # -- set_device_parameter with name-based param --
        if func_name == "set_device_parameter":
            ti = args.get("track_index", track_index)
            di = args.get("device_index", last_device_index)
            value = args.get("value")

            # Name-based: {"param": "Ratio", "value": 8.0}
            param_name = args.get("param")
            param_index = args.get("param_index")

            if param_name and param_index is None and di is not None:
                print(f"[EXECUTOR] Running: set_parameter_by_name "
                      f"track={ti} device={di} param={param_name} value={value}")
                try:
                    from ableton_controls.reliable_params import get_reliable_controller
                    rpc = get_reliable_controller()
                    return rpc.set_parameter_by_name(ti, di, param_name, value)
                except Exception as e:
                    return {"success": False,
                            "message": f"set_parameter_by_name failed: {e}"}

            # Index-based: {"track_index": 0, "device_index": 1, "param_index": 3, "value": 0.5}
            if param_index is not None and di is not None:
                print(f"[EXECUTOR] Running: set_device_parameter "
                      f"track={ti} device={di} param_idx={param_index} value={value}")
                return ableton.set_device_parameter(ti, di, param_index, value)

            return {"success": False,
                    "message": f"set_device_parameter: missing device_index or param identifier. "
                               f"args={args}, last_device_index={last_device_index}"}

        # -- Default: direct dispatch to ableton controller --
        if hasattr(ableton, func_name):
            func = getattr(ableton, func_name)
            print(f"[EXECUTOR] Running: {func_name} {args}")
            return func(**args) if args else func()

        return {"success": False, "message": f"Unknown function: {func_name}"}

    # Stock Ableton devices that don't need availability checks
    STOCK_DEVICES = {
        "EQ Eight", "Compressor", "Glue Compressor", "Multiband Dynamics",
        "Reverb", "Delay", "Saturator", "Limiter", "Pedal", "Corpus",
        "Erosion", "Vinyl Distortion", "Auto Filter", "Auto Pan",
        "Chorus-Ensemble", "Phaser-Flanger", "Spectral Resonator",
        "Spectral Time", "Utility", "Tuner",
    }

    def _lookup_fallbacks(self, device_name: str) -> List[str]:
        """Look up fallback chain for a device from PLUGIN_PREFERENCES.

        Scans all artist/style entries for one where ``preferred_plugin``
        matches *device_name* and returns its ``fallbacks`` list.
        """
        try:
            from knowledge.micro_settings_kb import PLUGIN_PREFERENCES
        except ImportError:
            return []

        for artist_styles in PLUGIN_PREFERENCES.values():
            for style_slots in artist_styles.values():
                for slot_info in style_slots.values():
                    if slot_info.get("preferred_plugin") == device_name:
                        return list(slot_info.get("fallbacks", []))
        return []

    @staticmethod
    def _is_stock_device(device_name: str) -> bool:
        """Return True if device_name is a built-in Ableton device."""
        return device_name in ExecutorAgent.STOCK_DEVICES

    async def execute_command_list(self, commands: List[Dict[str, Any]]) -> ExecutionResult:
        """Execute a list of commands and return structured result"""
        result = await self._execute_workflow({"commands": commands})
        
        return ExecutionResult(
            success=result.get("success", False),
            message=result.get("message", ""),
            data={"results": result.get("results", [])},
            errors=[r.get("error") for r in result.get("results", []) if r.get("error")]
        )

