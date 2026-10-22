"""
Session Manager

Tracks the current Ableton session state and provides context
for the AI to make better decisions.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TrackState:
    """State of a single track"""
    index: int
    name: str = ""
    muted: bool = False
    soloed: bool = False
    armed: bool = False
    volume: float = 0.85
    pan: float = 0.0
    has_clips: bool = False


@dataclass
class SessionState:
    """State of the Ableton session"""
    is_playing: bool = False
    is_recording: bool = False
    tempo: float = 120.0
    time_signature: tuple = (4, 4)
    loop_enabled: bool = False
    loop_start: float = 0.0
    loop_length: float = 4.0
    metronome_on: bool = False
    current_position: float = 0.0
    tracks: List[TrackState] = field(default_factory=list)
    num_scenes: int = 0
    selected_track: int = 0
    selected_scene: int = 0


class SessionManager:
    """
    Manages session context and state
    
    Features:
    - Track current project state
    - Provide context for AI decisions
    - Detect genre and style
    - Remember project-specific preferences
    """
    
    def __init__(self):
        self.state = SessionState()
        self.project_name: Optional[str] = None
        self.detected_genre: Optional[str] = None
        self.mixing_stage: str = "unknown"  # tracking, mixing, mastering
        self.last_updated: Optional[datetime] = None
        self.action_history: List[Dict] = []
    
    def update_transport(self, is_playing: bool = None, is_recording: bool = None,
                        tempo: float = None, position: float = None):
        """Update transport state"""
        if is_playing is not None:
            self.state.is_playing = is_playing
        if is_recording is not None:
            self.state.is_recording = is_recording
        if tempo is not None:
            self.state.tempo = tempo
        if position is not None:
            self.state.current_position = position
        
        self.last_updated = datetime.now()
    
    def update_track(self, track_index: int, **kwargs):
        """Update a track's state"""
        # Ensure we have enough tracks
        while len(self.state.tracks) <= track_index:
            self.state.tracks.append(TrackState(index=len(self.state.tracks)))
        
        track = self.state.tracks[track_index]
        for key, value in kwargs.items():
            if hasattr(track, key):
                setattr(track, key, value)
        
        self.last_updated = datetime.now()
    
    def get_track(self, index: int) -> Optional[TrackState]:
        """Get a track's state"""
        if 0 <= index < len(self.state.tracks):
            return self.state.tracks[index]
        return None
    
    def detect_genre(self) -> Optional[str]:
        """Attempt to detect the genre based on tempo and other factors"""
        tempo = self.state.tempo
        
        # Simple genre detection based on tempo
        if 130 <= tempo <= 170:
            self.detected_genre = "trap"
        elif 125 <= tempo <= 130:
            self.detected_genre = "edm"
        elif 85 <= tempo <= 115:
            self.detected_genre = "hip_hop"
        elif 100 <= tempo <= 140:
            self.detected_genre = "pop_rock"
        else:
            self.detected_genre = "unknown"
        
        return self.detected_genre
    
    def get_context_summary(self) -> Dict[str, Any]:
        """Get a summary of the current context for the AI"""
        muted_tracks = [t.index for t in self.state.tracks if t.muted]
        soloed_tracks = [t.index for t in self.state.tracks if t.soloed]
        armed_tracks = [t.index for t in self.state.tracks if t.armed]
        
        return {
            "transport": {
                "playing": self.state.is_playing,
                "recording": self.state.is_recording,
                "tempo": self.state.tempo,
                "position": self.state.current_position
            },
            "loop": {
                "enabled": self.state.loop_enabled,
                "start": self.state.loop_start,
                "length": self.state.loop_length
            },
            "tracks": {
                "count": len(self.state.tracks),
                "muted": muted_tracks,
                "soloed": soloed_tracks,
                "armed": armed_tracks
            },
            "meta": {
                "genre": self.detected_genre,
                "stage": self.mixing_stage,
                "project": self.project_name
            }
        }
    
    def record_action(self, action: str, params: Dict = None):
        """Record an action in history"""
        self.action_history.append({
            "action": action,
            "params": params or {},
            "timestamp": datetime.now().isoformat(),
            "state_snapshot": {
                "playing": self.state.is_playing,
                "tempo": self.state.tempo
            }
        })
        
        # Keep last 100 actions
        if len(self.action_history) > 100:
            self.action_history = self.action_history[-100:]
    
    def get_recent_actions(self, n: int = 10) -> List[Dict]:
        """Get recent actions"""
        return self.action_history[-n:]
    
    def can_undo(self) -> bool:
        """Check if undo is possible"""
        return len(self.action_history) > 0
    
    def reset(self):
        """Reset session state"""
        self.state = SessionState()
        self.project_name = None
        self.detected_genre = None
        self.mixing_stage = "unknown"
        self.action_history = []


# Global session manager
session_manager = SessionManager()

