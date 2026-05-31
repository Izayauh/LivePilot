"""
Intent Router Agent

Routes user requests to the appropriate agent based on intent classification.
Acts as the first point of contact for all user interactions.
"""

from agents import AgentType, AgentMessage, IntentType, UserIntent
from agent_system import BaseAgent


class RouterAgent(BaseAgent):
    """
    Routes user requests to appropriate agents
    
    Responsibilities:
    - Classify user intent (simple command, complex workflow, question)
    - Route to appropriate agent
    - Handle fallbacks and errors
    """
    
    def __init__(self, orchestrator):
        super().__init__(AgentType.ROUTER, orchestrator)
        
        # Keywords for intent classification
        self.simple_command_keywords = {
            "play", "stop", "pause", "record", "recording",
            "mute", "unmute", "solo", "unsolo", "arm", "disarm",
            "tempo", "bpm", "metronome", "click",
            "loop", "looping",
            "scene", "clip", "launch", "fire", "trigger",
            "volume", "pan", "fader",
            "undo", "redo",
            "add", "plugin", "device",  # Simple plugin add
        }
        
        self.complex_workflow_keywords = {
            "make", "improve", "enhance", "fix", "better", "more",
            "mix", "master", "mastering", "mixing",
            "compress", "compression", "compressor",
            "eq", "equalize", "equalizer",
            "reverb", "delay", "effect", "effects",
            "punch", "warm", "bright", "fat", "thick", "crisp",
            "sidechain", "ducking",
            "bus", "send", "return",
            "process", "processing",
        }
        
        # Plugin chain specific keywords
        self.plugin_chain_keywords = {
            "chain", "plugin chain", "signal chain", "fx chain",
            "like", "style", "sound like", "vocal chain", "drum bus",
            "billie eilish", "weeknd", "drake", "travis scott",
            "pop", "hip hop", "rock", "r&b", "edm",
        }

        self.library_lookup_keywords = {
            "chain", "vocal chain", "load", "from", "style", "like",
            "section", "verse", "chorus", "adlibs", "background vocals",
            "ultralight beam", "saint pablo", "apocalypse",
        }

        self.teacher_keywords = {
            "why", "explain", "what does", "reason", "because", "purpose",
            "what did you set", "tell me about",
        }
        
        self.question_keywords = {
            "how", "what", "why", "when", "where", "which",
            "explain", "tell me", "describe",
            "can you", "could you",
            "help me understand",
        }
    
    async def process(self, message: AgentMessage) -> AgentMessage:
        """Process incoming routing request"""
        content = message.content
        action = content.get("action", "classify")
        
        if action == "classify":
            request = content.get("request", "")
            intent = self._classify_intent(request)
            
            return AgentMessage(
                sender=self.agent_type,
                recipient=message.sender,
                content={
                    "intent_type": intent.type.value,
                    "confidence": intent.confidence,
                    "extracted_action": intent.extracted_action,
                    "needs_research": intent.needs_research,
                    "parameters": intent.parameters
                },
                correlation_id=message.correlation_id
            )
        
        return AgentMessage(
            sender=self.agent_type,
            recipient=message.sender,
            content={"error": f"Unknown action: {action}"},
            correlation_id=message.correlation_id
        )
    
    def _classify_intent(self, request: str) -> UserIntent:
        """Classify the user's intent based on keywords and patterns"""
        request_lower = request.lower()
        words = set(request_lower.split())
        
        # Count keyword matches for each category
        simple_matches = len(words & self.simple_command_keywords)
        complex_matches = len(words & self.complex_workflow_keywords)
        question_matches = sum(1 for kw in self.question_keywords if kw in request_lower)
        
        # Determine intent type based on matches
        teacher_matches = sum(1 for kw in self.teacher_keywords if kw in request_lower)
        library_matches = sum(1 for kw in self.library_lookup_keywords if kw in request_lower)

        if teacher_matches > 0 and any(k in request_lower for k in ("ratio", "threshold", "attack", "release", "parameter", "plugin", "set")):
            return UserIntent(
                type=IntentType.TEACHER_QUERY,
                original_request=request,
                confidence=0.8,
                needs_research=False
            )

        if library_matches > 0:
            return UserIntent(
                type=IntentType.LIBRARY_LOOKUP,
                original_request=request,
                confidence=0.8,
                needs_research=False
            )

        if question_matches > 0 and simple_matches == 0:
            return UserIntent(
                type=IntentType.QUESTION,
                original_request=request,
                confidence=0.8,
                needs_research=True
            )
        
        if simple_matches > 0 and complex_matches == 0:
            extracted = self._extract_simple_action(request_lower)
            return UserIntent(
                type=IntentType.SIMPLE_COMMAND,
                original_request=request,
                extracted_action=extracted,
                confidence=0.9,
                parameters=self._extract_parameters(request_lower, extracted)
            )
        
        if complex_matches > 0:
            return UserIntent(
                type=IntentType.COMPLEX_WORKFLOW,
                original_request=request,
                confidence=0.7,
                needs_research=True
            )
        
        # Default to complex (requires more analysis)
        return UserIntent(
            type=IntentType.COMPLEX_WORKFLOW,
            original_request=request,
            confidence=0.5,
            needs_research=True
        )
    
    def _extract_simple_action(self, request: str) -> str:
        """Extract the primary action from a simple command"""
        # Playback actions
        if "play" in request and "stop" not in request:
            return "play"
        if "stop" in request:
            return "stop"
        if "pause" in request:
            return "pause"
        if "record" in request:
            return "start_recording" if "start" in request or "begin" in request else "toggle_recording"
        
        # Track actions
        if "mute" in request:
            return "unmute_track" if "unmute" in request or "un-mute" in request else "mute_track"
        if "solo" in request:
            return "unsolo_track" if "unsolo" in request or "un-solo" in request else "solo_track"
        if "arm" in request:
            return "disarm_track" if "disarm" in request or "un-arm" in request else "arm_track"
        
        # Transport actions
        if "tempo" in request or "bpm" in request:
            return "set_tempo"
        if "metronome" in request or "click" in request:
            return "toggle_metronome"
        if "loop" in request:
            return "toggle_loop"
        
        # Scene/Clip actions
        if "scene" in request:
            return "fire_scene"
        if "clip" in request:
            return "fire_clip"
        
        # Volume/Pan
        if "volume" in request:
            return "set_track_volume"
        if "pan" in request:
            return "set_track_pan"
        
        return "unknown"
    
    def _extract_parameters(self, request: str, action: str) -> dict:
        """Extract parameters from the request based on the action"""
        params = {}
        
        # Extract track number
        import re
        track_match = re.search(r'track\s*(\d+)', request)
        if track_match:
            params["track_index"] = int(track_match.group(1)) - 1  # Convert to 0-indexed
        
        # Extract tempo/BPM
        bpm_match = re.search(r'(\d+)\s*(?:bpm|tempo)', request) or \
                    re.search(r'(?:tempo|bpm)\s*(?:to|at|=)?\s*(\d+)', request)
        if bpm_match:
            params["bpm"] = int(bpm_match.group(1))
        
        # Extract scene number
        scene_match = re.search(r'scene\s*(\d+)', request)
        if scene_match:
            params["scene_index"] = int(scene_match.group(1)) - 1  # Convert to 0-indexed
        
        # Extract clip number
        clip_match = re.search(r'clip\s*(\d+)', request)
        if clip_match:
            params["clip_index"] = int(clip_match.group(1)) - 1  # Convert to 0-indexed
        
        # Extract volume level
        volume_match = re.search(r'volume\s*(?:to|at|=)?\s*(\d+(?:\.\d+)?)\s*%?', request)
        if volume_match:
            vol = float(volume_match.group(1))
            params["volume"] = vol / 100 if vol > 1 else vol
        
        # Extract on/off for toggles
        if "on" in request:
            params["state"] = 1
        elif "off" in request:
            params["state"] = 0
        
        return params

