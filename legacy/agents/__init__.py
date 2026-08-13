"""
Jarvis Multi-Agent System

This package contains all agents for the Jarvis AI Audio Engineer:
- Router Agent: Classifies and routes requests
- Audio Engineer Agent: Understands production concepts
- Research Agent: Searches web/YouTube for techniques
- Planner Agent: Creates execution workflows
- Implementation Agent: Converts plans to OSC commands
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime


class AgentType(Enum):
    """Types of agents in the system"""
    ROUTER = "intent_router"           # Routes requests to appropriate agent
    AUDIO_ENGINEER = "audio_engineer"  # Understands production concepts
    RESEARCHER = "researcher"          # Finds information online
    PLANNER = "workflow_planner"       # Creates execution plans
    IMPLEMENTER = "implementer"        # Converts plans to code
    EXECUTOR = "executor"              # Runs commands


class IntentType(Enum):
    """Types of user intents"""
    SIMPLE_COMMAND = "simple"          # Direct action (play, stop, mute)
    COMPLEX_WORKFLOW = "complex"       # Multi-step production task
    QUESTION = "question"              # Information request
    RESEARCH_NEEDED = "research"       # Needs external knowledge
    LIBRARY_LOOKUP = "library_lookup"  # Local librarian chain lookup
    TEACHER_QUERY = "teacher_query"    # Explain loaded chain/parameter
    UNKNOWN = "unknown"                # Cannot determine


@dataclass
class AgentMessage:
    """Message passed between agents"""
    sender: AgentType
    recipient: AgentType
    content: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    correlation_id: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "sender": self.sender.value,
            "recipient": self.recipient.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id
        }


@dataclass
class UserIntent:
    """Classified user intent"""
    type: IntentType
    original_request: str
    extracted_action: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    needs_research: bool = False
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowPlan:
    """A plan for executing a complex workflow"""
    goal: str
    steps: List[Dict[str, Any]] = field(default_factory=list)
    estimated_duration: Optional[float] = None
    requires_confirmation: bool = False
    rollback_steps: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ExecutionResult:
    """Result of executing an action or workflow"""
    success: bool
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    execution_time: float = 0.0

