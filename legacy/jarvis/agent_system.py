"""
Multi-Agent Orchestration System for Jarvis AI Audio Engineer

This is the central coordinator that manages all agents:
- Routes user requests to appropriate agents
- Manages inter-agent communication
- Tracks conversation context and state
- Coordinates complex multi-step workflows
"""

import asyncio
import uuid
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from agents import (
    AgentType, 
    IntentType, 
    AgentMessage, 
    UserIntent, 
    WorkflowPlan, 
    ExecutionResult
)


@dataclass
class ConversationContext:
    """Maintains context across the conversation"""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = field(default_factory=datetime.now)
    messages: List[Dict[str, Any]] = field(default_factory=list)
    current_genre: Optional[str] = None
    current_project: Optional[str] = None
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    active_workflow: Optional[WorkflowPlan] = None
    last_actions: List[Dict[str, Any]] = field(default_factory=list)
    
    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None):
        """Add a message to the conversation history"""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        })
    
    def get_recent_context(self, n_messages: int = 5) -> List[Dict]:
        """Get the most recent n messages for context"""
        return self.messages[-n_messages:] if self.messages else []


class BaseAgent:
    """Base class for all agents"""
    
    def __init__(self, agent_type: AgentType, orchestrator: 'AgentOrchestrator'):
        self.agent_type = agent_type
        self.orchestrator = orchestrator
        self.message_handlers: Dict[str, Callable] = {}
    
    async def process(self, message: AgentMessage) -> AgentMessage:
        """Process an incoming message - override in subclasses"""
        raise NotImplementedError
    
    async def send_to(self, recipient: AgentType, content: Dict[str, Any], 
                     correlation_id: Optional[str] = None) -> AgentMessage:
        """Send a message to another agent"""
        message = AgentMessage(
            sender=self.agent_type,
            recipient=recipient,
            content=content,
            correlation_id=correlation_id or str(uuid.uuid4())
        )
        return await self.orchestrator.route_message(message)
    
    def register_handler(self, message_type: str, handler: Callable):
        """Register a handler for a specific message type"""
        self.message_handlers[message_type] = handler


class AgentOrchestrator:
    """
    Central orchestrator that coordinates all agents
    """
    
    def __init__(self):
        self.agents: Dict[AgentType, BaseAgent] = {}
        self.context = ConversationContext()
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.active = False
        self._gemini_client = None
        self._ableton_controller = None
    
    def register_agent(self, agent: BaseAgent):
        """Register an agent with the orchestrator"""
        self.agents[agent.agent_type] = agent
        print(f"[OK] Registered agent: {agent.agent_type.value}")

    def get_agent(self, agent_type: AgentType) -> Optional[BaseAgent]:
        """Get an agent by type"""
        return self.agents.get(agent_type)
    
    def set_gemini_client(self, client):
        """Set the Gemini client for AI operations"""
        self._gemini_client = client
    
    def set_ableton_controller(self, controller):
        """Set the Ableton controller for OSC operations"""
        self._ableton_controller = controller
    
    @property
    def gemini(self):
        return self._gemini_client
    
    @property
    def ableton(self):
        return self._ableton_controller
    
    async def route_message(self, message: AgentMessage) -> AgentMessage:
        """Route a message to the appropriate agent"""
        if message.recipient not in self.agents:
            return AgentMessage(
                sender=AgentType.ROUTER,
                recipient=message.sender,
                content={"error": f"Agent {message.recipient} not found"},
                correlation_id=message.correlation_id
            )
        
        target_agent = self.agents[message.recipient]
        return await target_agent.process(message)
    
    async def process_user_request(self, request: str) -> ExecutionResult:
        """
        Main entry point for processing user requests
        
        This determines whether the request is:
        1. A simple command -> direct execution
        2. A complex workflow -> multi-agent processing
        3. A question -> research and answer
        """
        # Add to conversation context
        self.context.add_message("user", request)
        
        # First, classify the intent
        intent = await self.classify_intent(request)
        
        if intent.type == IntentType.SIMPLE_COMMAND:
            # Direct execution path
            result = await self.execute_simple_command(intent)
        
        elif intent.type == IntentType.COMPLEX_WORKFLOW:
            # Multi-agent workflow path
            result = await self.execute_complex_workflow(intent)
        
        elif intent.type == IntentType.QUESTION:
            # Research and answer path
            result = await self.answer_question(intent)
        
        elif intent.type == IntentType.RESEARCH_NEEDED:
            # Research first, then plan and execute
            result = await self.research_and_execute(intent)
        
        else:
            result = ExecutionResult(
                success=False,
                message="I'm not sure how to help with that. Could you rephrase?",
                data={"intent": intent.type.value}
            )
        
        # Add result to context
        self.context.add_message("assistant", result.message, {"success": result.success})
        
        return result
    
    async def classify_intent(self, request: str) -> UserIntent:
        """
        Classify the user's intent
        
        Simple commands: play, stop, mute track 1, set tempo to 120
        Complex workflows: make drums punch through, mix the vocals
        Questions: how do I, what is, explain
        """
        request_lower = request.lower()
        
        # Simple command patterns
        simple_patterns = [
            "play", "stop", "pause", "record",
            "mute", "unmute", "solo", "unsolo", "arm", "disarm",
            "set tempo", "set bpm", "tempo to",
            "loop", "metronome",
            "fire scene", "launch scene", "trigger scene",
            "fire clip", "launch clip", "trigger clip",
            "volume", "pan",
        ]
        
        # Check for simple commands
        for pattern in simple_patterns:
            if pattern in request_lower:
                return UserIntent(
                    type=IntentType.SIMPLE_COMMAND,
                    original_request=request,
                    extracted_action=pattern,
                    confidence=0.9
                )
        
        # Question patterns
        question_patterns = ["how do", "what is", "explain", "why", "can you tell me"]
        for pattern in question_patterns:
            if pattern in request_lower:
                return UserIntent(
                    type=IntentType.QUESTION,
                    original_request=request,
                    confidence=0.8,
                    needs_research=True
                )
        
        # Complex workflow indicators
        complex_patterns = [
            "make", "improve", "enhance", "fix", "better",
            "mix", "master", "process", "add effect",
            "sound like", "more punch", "warmer", "brighter",
            "compress", "eq", "reverb", "delay",
        ]
        
        for pattern in complex_patterns:
            if pattern in request_lower:
                return UserIntent(
                    type=IntentType.COMPLEX_WORKFLOW,
                    original_request=request,
                    confidence=0.7,
                    needs_research=True
                )
        
        # Default to complex (safer - triggers more analysis)
        return UserIntent(
            type=IntentType.COMPLEX_WORKFLOW,
            original_request=request,
            confidence=0.5,
            needs_research=True
        )
    
    async def execute_simple_command(self, intent: UserIntent) -> ExecutionResult:
        """Execute a simple, direct command"""
        # Route to executor agent
        if AgentType.EXECUTOR in self.agents:
            message = AgentMessage(
                sender=AgentType.ROUTER,
                recipient=AgentType.EXECUTOR,
                content={
                    "action": "execute_simple",
                    "intent": intent.original_request,
                    "extracted_action": intent.extracted_action
                }
            )
            response = await self.route_message(message)
            return ExecutionResult(
                success=response.content.get("success", False),
                message=response.content.get("message", "Command executed"),
                data=response.content
            )
        
        # Fallback if no executor agent
        return ExecutionResult(
            success=False,
            message="Executor agent not available",
            data={}
        )
    
    async def execute_complex_workflow(self, intent: UserIntent) -> ExecutionResult:
        """Execute a complex multi-step workflow"""
        results = []
        
        # Step 1: Audio Engineer analyzes the request
        if AgentType.AUDIO_ENGINEER in self.agents:
            engineer_msg = AgentMessage(
                sender=AgentType.ROUTER,
                recipient=AgentType.AUDIO_ENGINEER,
                content={
                    "action": "analyze",
                    "request": intent.original_request,
                    "context": self.context.get_recent_context()
                }
            )
            engineer_response = await self.route_message(engineer_msg)
            results.append(("engineer", engineer_response.content))
        
        # Step 2: Research if needed
        if intent.needs_research and AgentType.RESEARCHER in self.agents:
            research_msg = AgentMessage(
                sender=AgentType.ROUTER,
                recipient=AgentType.RESEARCHER,
                content={
                    "action": "research",
                    "topic": intent.original_request,
                    "engineer_analysis": results[-1][1] if results else None
                }
            )
            research_response = await self.route_message(research_msg)
            results.append(("research", research_response.content))
        
        # Step 3: Planner creates workflow
        if AgentType.PLANNER in self.agents:
            planner_msg = AgentMessage(
                sender=AgentType.ROUTER,
                recipient=AgentType.PLANNER,
                content={
                    "action": "create_plan",
                    "goal": intent.original_request,
                    "analysis": results[0][1] if results else None,
                    "research": results[1][1] if len(results) > 1 else None
                }
            )
            planner_response = await self.route_message(planner_msg)
            results.append(("plan", planner_response.content))
        
        # Step 4: Implementation converts to commands
        if AgentType.IMPLEMENTER in self.agents:
            impl_msg = AgentMessage(
                sender=AgentType.ROUTER,
                recipient=AgentType.IMPLEMENTER,
                content={
                    "action": "implement",
                    "plan": results[-1][1] if results else None
                }
            )
            impl_response = await self.route_message(impl_msg)
            results.append(("implementation", impl_response.content))
        
        # Step 5: Execute the implementation
        if AgentType.EXECUTOR in self.agents:
            exec_msg = AgentMessage(
                sender=AgentType.ROUTER,
                recipient=AgentType.EXECUTOR,
                content={
                    "action": "execute_workflow",
                    "commands": results[-1][1] if results else None
                }
            )
            exec_response = await self.route_message(exec_msg)
            results.append(("execution", exec_response.content))
        
        # Compile final result
        final_success = all(r[1].get("success", False) for r in results if isinstance(r[1], dict))
        final_message = results[-1][1].get("message", "Workflow completed") if results else "No actions taken"
        
        return ExecutionResult(
            success=final_success,
            message=final_message,
            data={"workflow_results": results}
        )
    
    async def answer_question(self, intent: UserIntent) -> ExecutionResult:
        """Answer a question, potentially with research"""
        if AgentType.RESEARCHER in self.agents:
            research_msg = AgentMessage(
                sender=AgentType.ROUTER,
                recipient=AgentType.RESEARCHER,
                content={
                    "action": "answer_question",
                    "question": intent.original_request
                }
            )
            response = await self.route_message(research_msg)
            return ExecutionResult(
                success=True,
                message=response.content.get("answer", "I couldn't find an answer"),
                data=response.content
            )
        
        return ExecutionResult(
            success=False,
            message="Research agent not available",
            data={}
        )
    
    async def research_and_execute(self, intent: UserIntent) -> ExecutionResult:
        """Research a topic first, then plan and execute"""
        # This is similar to complex workflow but with more emphasis on research
        return await self.execute_complex_workflow(intent)
    
    def get_registered_agents(self) -> List[str]:
        """Get list of registered agent names"""
        return [agent.value for agent in self.agents.keys()]
    
    def update_context(self, key: str, value: Any):
        """Update conversation context"""
        if key == "genre":
            self.context.current_genre = value
        elif key == "project":
            self.context.current_project = value
        else:
            self.context.user_preferences[key] = value


# Global orchestrator instance
orchestrator = AgentOrchestrator()

