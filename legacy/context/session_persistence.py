"""
Session Persistence

Provides persistent storage for:
- Learned knowledge and preferences
- Plugin chain discoveries
- User preferences
- Session history
"""

import os
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
import threading


@dataclass
class LearnedChain:
    """A learned plugin chain from research or user creation"""
    name: str
    artist_or_style: str
    track_type: str
    devices: List[Dict[str, Any]]
    sources: List[str]
    confidence: float
    created_at: str
    last_used: str
    use_count: int = 0
    user_rating: Optional[float] = None


@dataclass
class UserPreference:
    """User preference for a specific context"""
    key: str
    value: Any
    context: str  # e.g., "vocal", "drums", "master"
    created_at: str
    updated_at: str


@dataclass
class ActionHistoryEntry:
    """An entry in the action history for undo capability"""
    action_id: str
    action_type: str
    function_name: str
    parameters: Dict[str, Any]
    result: Dict[str, Any]
    timestamp: str
    can_undo: bool
    undo_action: Optional[Dict[str, Any]] = None


class SessionPersistence:
    """
    Manages persistent storage of learned knowledge and preferences.

    Features:
    - Save/load plugin chain discoveries
    - Track user preferences
    - Maintain undo history
    - Cross-session learning
    """

    def __init__(self, data_dir: str = None):
        """
        Initialize session persistence.

        Args:
            data_dir: Directory for persistent data. Defaults to ~/.jarvis_ableton/
        """
        if data_dir is None:
            data_dir = os.path.join(os.path.expanduser("~"), ".jarvis_ableton")

        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # File paths
        self.chains_file = self.data_dir / "learned_chains.json"
        self.preferences_file = self.data_dir / "preferences.json"
        self.history_file = self.data_dir / "action_history.json"
        self.session_state_file = self.data_dir / "session_state.json"

        # In-memory caches
        self._chains: Dict[str, LearnedChain] = {}
        self._preferences: Dict[str, UserPreference] = {}
        self._action_history: List[ActionHistoryEntry] = []

        # Thread safety
        self._lock = threading.RLock()

        # Load existing data
        self._load_all()

    def _load_all(self):
        """Load all persistent data from disk"""
        self._load_chains()
        self._load_preferences()
        self._load_history()

    def _load_chains(self):
        """Load learned chains from disk"""
        if self.chains_file.exists():
            try:
                with open(self.chains_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, chain_data in data.items():
                        self._chains[key] = LearnedChain(**chain_data)
            except Exception as e:
                print(f"[Persistence] Error loading chains: {e}")

    def _load_preferences(self):
        """Load preferences from disk"""
        if self.preferences_file.exists():
            try:
                with open(self.preferences_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, pref_data in data.items():
                        self._preferences[key] = UserPreference(**pref_data)
            except Exception as e:
                print(f"[Persistence] Error loading preferences: {e}")

    def _load_history(self):
        """Load action history from disk"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Only keep recent history
                    recent = data[-500:] if len(data) > 500 else data
                    for entry_data in recent:
                        self._action_history.append(ActionHistoryEntry(**entry_data))
            except Exception as e:
                print(f"[Persistence] Error loading history: {e}")

    def _save_chains(self):
        """Save chains to disk"""
        with self._lock:
            try:
                data = {key: asdict(chain) for key, chain in self._chains.items()}
                with open(self.chains_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                print(f"[Persistence] Error saving chains: {e}")

    def _save_preferences(self):
        """Save preferences to disk"""
        with self._lock:
            try:
                data = {key: asdict(pref) for key, pref in self._preferences.items()}
                with open(self.preferences_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                print(f"[Persistence] Error saving preferences: {e}")

    def _save_history(self):
        """Save action history to disk"""
        with self._lock:
            try:
                # Only save recent history
                recent = self._action_history[-500:]
                data = [asdict(entry) for entry in recent]
                with open(self.history_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                print(f"[Persistence] Error saving history: {e}")

    # ==================== CHAIN MANAGEMENT ====================

    def add_chain(self, name: str, artist_or_style: str, track_type: str,
                  devices: List[Dict], sources: List[str] = None,
                  confidence: float = 0.5) -> LearnedChain:
        """
        Add a learned chain to persistent storage.

        Args:
            name: Name for the chain
            artist_or_style: Artist or style this chain is for
            track_type: Type of track (vocal, drums, bass, etc.)
            devices: List of device configurations
            sources: List of source URLs
            confidence: Confidence score (0-1)

        Returns:
            The created LearnedChain
        """
        key = f"{artist_or_style.lower().replace(' ', '_')}_{track_type.lower()}"
        now = datetime.now().isoformat()

        chain = LearnedChain(
            name=name,
            artist_or_style=artist_or_style,
            track_type=track_type,
            devices=devices,
            sources=sources or [],
            confidence=confidence,
            created_at=now,
            last_used=now,
            use_count=1
        )

        with self._lock:
            self._chains[key] = chain
            self._save_chains()

        return chain

    def get_chain(self, artist_or_style: str, track_type: str) -> Optional[LearnedChain]:
        """Get a chain by artist/style and track type"""
        key = f"{artist_or_style.lower().replace(' ', '_')}_{track_type.lower()}"
        chain = self._chains.get(key)

        if chain:
            # Update usage stats
            chain.last_used = datetime.now().isoformat()
            chain.use_count += 1
            self._save_chains()

        return chain

    def search_chains(self, query: str, limit: int = 5) -> List[LearnedChain]:
        """Search for chains matching a query"""
        query_lower = query.lower()
        matches = []

        for key, chain in self._chains.items():
            score = 0
            if query_lower in chain.artist_or_style.lower():
                score += 2
            if query_lower in chain.name.lower():
                score += 1
            if query_lower in chain.track_type.lower():
                score += 1

            if score > 0:
                matches.append((score, chain))

        # Sort by score descending, then by use_count
        matches.sort(key=lambda x: (x[0], x[1].use_count), reverse=True)
        return [m[1] for m in matches[:limit]]

    def get_all_chains(self) -> List[LearnedChain]:
        """Get all learned chains"""
        return list(self._chains.values())

    def update_chain_rating(self, artist_or_style: str, track_type: str,
                            rating: float) -> bool:
        """Update user rating for a chain"""
        key = f"{artist_or_style.lower().replace(' ', '_')}_{track_type.lower()}"
        if key in self._chains:
            self._chains[key].user_rating = rating
            self._save_chains()
            return True
        return False

    # ==================== PREFERENCE MANAGEMENT ====================

    def set_preference(self, key: str, value: Any, context: str = "global"):
        """Set a user preference"""
        pref_key = f"{context}:{key}"
        now = datetime.now().isoformat()

        if pref_key in self._preferences:
            self._preferences[pref_key].value = value
            self._preferences[pref_key].updated_at = now
        else:
            self._preferences[pref_key] = UserPreference(
                key=key,
                value=value,
                context=context,
                created_at=now,
                updated_at=now
            )

        self._save_preferences()

    def get_preference(self, key: str, context: str = "global",
                       default: Any = None) -> Any:
        """Get a user preference"""
        pref_key = f"{context}:{key}"
        pref = self._preferences.get(pref_key)
        return pref.value if pref else default

    def get_preferences_for_context(self, context: str) -> Dict[str, Any]:
        """Get all preferences for a context"""
        result = {}
        for pref_key, pref in self._preferences.items():
            if pref.context == context:
                result[pref.key] = pref.value
        return result

    # ==================== ACTION HISTORY (UNDO) ====================

    def record_action(self, action_type: str, function_name: str,
                      parameters: Dict[str, Any], result: Dict[str, Any],
                      can_undo: bool = False,
                      undo_action: Dict[str, Any] = None) -> str:
        """
        Record an action for undo capability.

        Args:
            action_type: Type of action (transport, track, device, etc.)
            function_name: Name of the function called
            parameters: Parameters passed to the function
            result: Result of the action
            can_undo: Whether this action can be undone
            undo_action: The action to perform to undo this

        Returns:
            Action ID
        """
        import uuid
        action_id = str(uuid.uuid4())[:8]

        entry = ActionHistoryEntry(
            action_id=action_id,
            action_type=action_type,
            function_name=function_name,
            parameters=parameters,
            result=result,
            timestamp=datetime.now().isoformat(),
            can_undo=can_undo,
            undo_action=undo_action
        )

        with self._lock:
            self._action_history.append(entry)
            # Limit history size
            if len(self._action_history) > 500:
                self._action_history = self._action_history[-500:]

            # Periodically save (every 10 actions)
            if len(self._action_history) % 10 == 0:
                self._save_history()

        return action_id

    def get_undoable_actions(self, limit: int = 10) -> List[ActionHistoryEntry]:
        """Get recent undoable actions"""
        undoable = [a for a in reversed(self._action_history) if a.can_undo]
        return undoable[:limit]

    def get_undo_action(self, action_id: str) -> Optional[Dict[str, Any]]:
        """Get the undo action for a specific action ID"""
        for entry in reversed(self._action_history):
            if entry.action_id == action_id and entry.can_undo:
                return entry.undo_action
        return None

    def mark_action_undone(self, action_id: str):
        """Mark an action as having been undone"""
        for entry in self._action_history:
            if entry.action_id == action_id:
                entry.can_undo = False
                break
        self._save_history()

    def get_recent_history(self, limit: int = 20) -> List[ActionHistoryEntry]:
        """Get recent action history"""
        return list(reversed(self._action_history[-limit:]))

    # ==================== SESSION STATE ====================

    def save_session_state(self, state: Dict[str, Any]):
        """Save current session state for crash recovery"""
        with self._lock:
            try:
                state['saved_at'] = datetime.now().isoformat()
                with open(self.session_state_file, 'w', encoding='utf-8') as f:
                    json.dump(state, f, indent=2)
            except Exception as e:
                print(f"[Persistence] Error saving session state: {e}")

    def load_session_state(self) -> Optional[Dict[str, Any]]:
        """Load saved session state for recovery"""
        if self.session_state_file.exists():
            try:
                with open(self.session_state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[Persistence] Error loading session state: {e}")
        return None

    def clear_session_state(self):
        """Clear saved session state"""
        if self.session_state_file.exists():
            self.session_state_file.unlink()

    # ==================== UTILITIES ====================

    def flush(self):
        """Flush all data to disk"""
        self._save_chains()
        self._save_preferences()
        self._save_history()

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about stored data"""
        return {
            "chains_count": len(self._chains),
            "preferences_count": len(self._preferences),
            "history_count": len(self._action_history),
            "undoable_count": len([a for a in self._action_history if a.can_undo]),
            "data_dir": str(self.data_dir)
        }


# Singleton instance
_persistence: Optional[SessionPersistence] = None


def get_session_persistence() -> SessionPersistence:
    """Get the singleton SessionPersistence instance"""
    global _persistence
    if _persistence is None:
        _persistence = SessionPersistence()
    return _persistence
