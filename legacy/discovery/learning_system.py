"""
Learning System for Jarvis AI Audio Engineer

Tracks successes and failures to improve over time.
Learns user preferences and adapts recommendations.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json
import os


@dataclass
class LearningEntry:
    """A single learning entry"""
    action: str
    success: bool
    context: Dict[str, Any] = field(default_factory=dict)
    user_feedback: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        return {
            "action": self.action,
            "success": self.success,
            "context": self.context,
            "user_feedback": self.user_feedback,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class UserPreference:
    """A learned user preference"""
    name: str
    value: Any
    confidence: float = 1.0
    learned_from: int = 0  # Number of observations
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "value": self.value,
            "confidence": self.confidence,
            "learned_from": self.learned_from
        }


class LearningSystem:
    """
    Tracks and learns from interactions
    
    Features:
    - Track command success/failure rates
    - Learn user preferences
    - Store user corrections
    - Improve recommendations over time
    """
    
    def __init__(self, storage_path: str = "config/learning_data.json"):
        self.storage_path = storage_path
        
        # Learning data
        self.action_history: List[LearningEntry] = []
        self.user_preferences: Dict[str, UserPreference] = {}
        self.corrections: List[Dict] = []
        self.technique_usage: Dict[str, int] = {}
        
        # Load persisted data
        self._load_data()
    
    def record_action(self, action: str, success: bool, 
                     context: Dict = None, user_feedback: str = None):
        """Record an action and its outcome"""
        entry = LearningEntry(
            action=action,
            success=success,
            context=context or {},
            user_feedback=user_feedback
        )
        self.action_history.append(entry)
        
        # Track technique usage
        if success:
            self.technique_usage[action] = self.technique_usage.get(action, 0) + 1
        
        # Save periodically
        if len(self.action_history) % 10 == 0:
            self._save_data()
    
    def record_user_correction(self, original_action: str, 
                               corrected_action: str, context: Dict = None):
        """Record when the user corrects the AI's action"""
        self.corrections.append({
            "original": original_action,
            "corrected": corrected_action,
            "context": context or {},
            "timestamp": datetime.now().isoformat()
        })
        self._save_data()
    
    def learn_preference(self, name: str, value: Any, context: Dict = None):
        """Learn a user preference"""
        if name in self.user_preferences:
            pref = self.user_preferences[name]
            # Update with increasing confidence
            if pref.value == value:
                pref.learned_from += 1
                pref.confidence = min(1.0, pref.confidence + 0.1)
            else:
                # Value changed, reduce confidence
                pref.value = value
                pref.confidence = 0.5
                pref.learned_from = 1
        else:
            self.user_preferences[name] = UserPreference(
                name=name,
                value=value,
                confidence=0.5,
                learned_from=1
            )
        
        self._save_data()
    
    def get_preference(self, name: str) -> Optional[Any]:
        """Get a learned preference value"""
        pref = self.user_preferences.get(name)
        if pref and pref.confidence >= 0.5:
            return pref.value
        return None
    
    def get_success_rate(self, action: str) -> float:
        """Get the success rate for an action"""
        relevant = [e for e in self.action_history if e.action == action]
        if not relevant:
            return 1.0  # Assume success if no data
        
        successes = sum(1 for e in relevant if e.success)
        return successes / len(relevant)
    
    def get_most_used_techniques(self, n: int = 10) -> List[tuple]:
        """Get the most frequently used techniques"""
        sorted_techniques = sorted(
            self.technique_usage.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_techniques[:n]
    
    def get_common_corrections(self) -> Dict[str, str]:
        """Get patterns of common corrections"""
        correction_map = {}
        for correction in self.corrections:
            original = correction["original"]
            corrected = correction["corrected"]
            
            # Track most common correction for each original
            if original not in correction_map:
                correction_map[original] = {}
            
            if corrected not in correction_map[original]:
                correction_map[original][corrected] = 0
            correction_map[original][corrected] += 1
        
        # Return the most common correction for each original
        result = {}
        for original, corrections in correction_map.items():
            most_common = max(corrections.items(), key=lambda x: x[1])
            result[original] = most_common[0]
        
        return result
    
    def should_suggest_alternative(self, action: str) -> Optional[str]:
        """Check if we should suggest an alternative based on past corrections"""
        corrections = self.get_common_corrections()
        return corrections.get(action)
    
    def get_learning_summary(self) -> Dict[str, Any]:
        """Get a summary of learning data"""
        return {
            "total_actions": len(self.action_history),
            "total_corrections": len(self.corrections),
            "learned_preferences": len(self.user_preferences),
            "techniques_tracked": len(self.technique_usage),
            "overall_success_rate": self._calculate_overall_success_rate(),
            "most_used": self.get_most_used_techniques(5)
        }
    
    def _calculate_overall_success_rate(self) -> float:
        """Calculate overall success rate"""
        if not self.action_history:
            return 1.0
        successes = sum(1 for e in self.action_history if e.success)
        return successes / len(self.action_history)
    
    def _save_data(self):
        """Save learning data to disk"""
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        
        data = {
            "version": "1.0",
            "action_history": [e.to_dict() for e in self.action_history[-1000:]],  # Keep last 1000
            "user_preferences": {k: v.to_dict() for k, v in self.user_preferences.items()},
            "corrections": self.corrections[-100:],  # Keep last 100
            "technique_usage": self.technique_usage
        }
        
        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _load_data(self):
        """Load learning data from disk"""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    
                    # Load action history
                    for entry_data in data.get("action_history", []):
                        entry = LearningEntry(
                            action=entry_data["action"],
                            success=entry_data["success"],
                            context=entry_data.get("context", {}),
                            user_feedback=entry_data.get("user_feedback")
                        )
                        self.action_history.append(entry)
                    
                    # Load preferences
                    for name, pref_data in data.get("user_preferences", {}).items():
                        self.user_preferences[name] = UserPreference(
                            name=pref_data["name"],
                            value=pref_data["value"],
                            confidence=pref_data.get("confidence", 1.0),
                            learned_from=pref_data.get("learned_from", 0)
                        )
                    
                    # Load corrections
                    self.corrections = data.get("corrections", [])
                    
                    # Load technique usage
                    self.technique_usage = data.get("technique_usage", {})
                    
            except Exception as e:
                print(f"Warning: Could not load learning data: {e}")
    
    def reset(self):
        """Reset all learning data"""
        self.action_history = []
        self.user_preferences = {}
        self.corrections = []
        self.technique_usage = {}
        
        if os.path.exists(self.storage_path):
            os.remove(self.storage_path)


# Global learning system instance
learning_system = LearningSystem()

