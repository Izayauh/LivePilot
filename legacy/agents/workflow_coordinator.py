"""
Workflow Coordinator

Orchestrates end-to-end workflows by coordinating all agents:
Router -> Audio Engineer -> Research -> Planner -> Implementer -> Executor

This is the brain that ties the multi-agent system together.
"""

import asyncio
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from agents import AgentType, AgentMessage, IntentType
from creative_workflow import build_creative_brief
from discovery.learning_system import learning_system


class WorkflowState(Enum):
    """State of a workflow execution"""
    PENDING = "pending"
    ROUTING = "routing"
    ANALYZING = "analyzing"
    RESEARCHING = "researching"
    PLANNING = "planning"
    IMPLEMENTING = "implementing"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class WorkflowResult:
    """Result of a workflow execution"""
    success: bool
    message: str
    state: WorkflowState
    execution_time: float
    actions_taken: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    can_undo: bool = False


@dataclass
class WorkflowContext:
    """Context for workflow execution"""
    workflow_id: str
    original_request: str
    intent_type: IntentType
    state: WorkflowState = WorkflowState.PENDING
    routing_result: Optional[Dict] = None
    analysis_result: Optional[Dict] = None
    research_result: Optional[Dict] = None
    plan_result: Optional[Dict] = None
    implementation_result: Optional[Dict] = None
    execution_result: Optional[Dict] = None
    creative_brief: Optional[Dict] = None
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class WorkflowCoordinator:
    """
    Coordinates end-to-end workflows through the multi-agent system.

    Responsibilities:
    - Route requests to appropriate agents
    - Orchestrate complex multi-step workflows
    - Handle errors and rollbacks
    - Provide workflow status and history
    """

    def __init__(self, orchestrator):
        """
        Initialize the workflow coordinator.

        Args:
            orchestrator: The AgentOrchestrator instance
        """
        self.orchestrator = orchestrator
        self.active_workflows: Dict[str, WorkflowContext] = {}
        self.workflow_history: List[WorkflowContext] = []
        self._max_history = 100

    async def execute_request(self, request: str,
                               skip_confirmation: bool = False) -> WorkflowResult:
        """
        Execute a user request through the full workflow pipeline.

        Args:
            request: The user's natural language request
            skip_confirmation: Skip confirmation for large workflows

        Returns:
            WorkflowResult with the outcome
        """
        import uuid
        workflow_id = str(uuid.uuid4())[:8]

        context = WorkflowContext(
            workflow_id=workflow_id,
            original_request=request,
            intent_type=IntentType.UNKNOWN
        )
        self.active_workflows[workflow_id] = context

        start_time = datetime.now()
        
        print(f"[WORKFLOW] Received request: \"{request}\" (ID: {workflow_id})")

        try:
            # Step 1: Route the request
            context.state = WorkflowState.ROUTING
            routing_result = await self._route_request(request)
            context.routing_result = routing_result
            context.intent_type = self._parse_intent_type(
                routing_result.get("intent_type", IntentType.UNKNOWN.value)
            )
            
            print(f"[WORKFLOW] Routing result: {context.intent_type.value} (Confidence: {routing_result.get('confidence', 0.0)})")

            # Step 2: Handle based on intent type
            if context.intent_type == IntentType.SIMPLE_COMMAND:
                result = await self._execute_simple_command(context, routing_result)
            elif context.intent_type == IntentType.COMPLEX_WORKFLOW:
                result = await self._execute_complex_workflow(context, routing_result,
                                                              skip_confirmation)
            elif context.intent_type == IntentType.QUESTION:
                result = await self._handle_question(context, routing_result)
            else:
                result = await self._execute_complex_workflow(context, routing_result,
                                                              skip_confirmation)

            context.state = WorkflowState.COMPLETED
            context.completed_at = datetime.now()

            execution_time = (context.completed_at - start_time).total_seconds()

            # Move to history
            del self.active_workflows[workflow_id]
            self._add_to_history(context)

            return WorkflowResult(
                success=result.get("success", False),
                message=result.get("message", "Workflow completed"),
                state=context.state,
                execution_time=execution_time,
                actions_taken=result.get("actions", []),
                can_undo=result.get("can_undo", False)
            )

        except Exception as e:
            print(f"[WORKFLOW] FAILED: {str(e)}")
            context.state = WorkflowState.FAILED
            context.error = str(e)
            context.completed_at = datetime.now()

            execution_time = (context.completed_at - start_time).total_seconds()

            del self.active_workflows[workflow_id]
            self._add_to_history(context)

            return WorkflowResult(
                success=False,
                message=f"Workflow failed: {e}",
                state=context.state,
                execution_time=execution_time,
                error=str(e)
            )

    async def _route_request(self, request: str) -> Dict[str, Any]:
        """Route the request using the Router Agent"""
        router = self.orchestrator.get_agent(AgentType.ROUTER)
        if not router:
            # Fallback routing
            return self._fallback_routing(request)

        message = AgentMessage(
            sender=AgentType.ROUTER,
            recipient=AgentType.ROUTER,
            content={"action": "classify", "request": request}
        )

        result = await router.process(message)
        return result.content

    def _fallback_routing(self, request: str) -> Dict[str, Any]:
        """Fallback routing when Router Agent is unavailable"""
        request_lower = request.lower()

        # Simple commands
        simple_keywords = {"play", "stop", "mute", "solo", "arm", "tempo", "volume", "pan"}
        if any(kw in request_lower for kw in simple_keywords):
            return {
                "intent_type": IntentType.SIMPLE_COMMAND.value,
                "confidence": 0.7,
                "needs_research": False
            }

        # Complex workflows
        complex_keywords = {"chain", "mix", "master", "compress", "eq", "effect", "like", "style"}
        if any(kw in request_lower for kw in complex_keywords):
            return {
                "intent_type": IntentType.COMPLEX_WORKFLOW.value,
                "confidence": 0.6,
                "needs_research": True
            }

        # Questions
        question_keywords = {"how", "what", "why", "explain", "help"}
        if any(kw in request_lower for kw in question_keywords):
            return {
                "intent_type": IntentType.QUESTION.value,
                "confidence": 0.7,
                "needs_research": True
            }

        return {
            "intent_type": IntentType.COMPLEX_WORKFLOW.value,
            "confidence": 0.5,
            "needs_research": True
        }

    def _parse_intent_type(self, raw_intent: str) -> IntentType:
        """
        Parse intent type from either enum values or legacy labels.
        """
        if not raw_intent:
            return IntentType.UNKNOWN

        normalized = str(raw_intent).strip().lower()

        legacy_map = {
            "simple_command": IntentType.SIMPLE_COMMAND,
            "complex_workflow": IntentType.COMPLEX_WORKFLOW,
            "question": IntentType.QUESTION,
            "research_needed": IntentType.RESEARCH_NEEDED,
            "unknown": IntentType.UNKNOWN,
            IntentType.SIMPLE_COMMAND.value: IntentType.SIMPLE_COMMAND,
            IntentType.COMPLEX_WORKFLOW.value: IntentType.COMPLEX_WORKFLOW,
            IntentType.QUESTION.value: IntentType.QUESTION,
            IntentType.RESEARCH_NEEDED.value: IntentType.RESEARCH_NEEDED,
            IntentType.UNKNOWN.value: IntentType.UNKNOWN,
        }

        return legacy_map.get(normalized, IntentType.UNKNOWN)

    async def _execute_simple_command(self, context: WorkflowContext,
                                       routing: Dict) -> Dict[str, Any]:
        """Execute a simple command directly via Executor"""
        context.state = WorkflowState.EXECUTING

        executor = self.orchestrator.get_agent(AgentType.EXECUTOR)
        if not executor:
            return {"success": False, "message": "Executor agent not available"}

        message = AgentMessage(
            sender=AgentType.ROUTER,
            recipient=AgentType.EXECUTOR,
            content={
                "action": "execute_simple",
                "intent": context.original_request,
                "extracted_action": routing.get("extracted_action", ""),
                "parameters": routing.get("parameters", {})
            }
        )

        result = await executor.process(message)
        context.execution_result = result.content

        return {
            "success": result.content.get("success", False),
            "message": result.content.get("message", "Command executed"),
            "actions": [{"type": "simple_command", "result": result.content}],
            "can_undo": True
        }

    async def _execute_complex_workflow(self, context: WorkflowContext, routing: Dict,
                                         skip_confirmation: bool = False) -> Dict[str, Any]:
        """Execute a complex workflow through the full pipeline"""
        print(f"[WORKFLOW] Starting complex workflow execution")
        actions = []

        # Step 1: Audio Engineer Analysis
        context.state = WorkflowState.ANALYZING
        engineer = self.orchestrator.get_agent(AgentType.AUDIO_ENGINEER)

        if engineer:
            message = AgentMessage(
                sender=AgentType.ROUTER,
                recipient=AgentType.AUDIO_ENGINEER,
                content={
                    "action": "analyze_request",
                    "request": context.original_request
                }
            )
            analysis_result = await engineer.process(message)
            context.analysis_result = analysis_result.content
            actions.append({"type": "analysis", "result": analysis_result.content})
            print(f"[WORKFLOW] Audio Engineer analysis complete")

        # Step 2: Research if needed
        if routing.get("needs_research", False):
            print(f"[WORKFLOW] Research required for this request")
            context.state = WorkflowState.RESEARCHING
            research = self.orchestrator.get_agent(AgentType.RESEARCHER)

            if research:
                message = AgentMessage(
                    sender=AgentType.AUDIO_ENGINEER,
                    recipient=AgentType.RESEARCHER,
                    content={
                        "action": "research_chain",
                        "query": context.original_request,
                        "analysis": context.analysis_result
                    }
                )
                research_result = await research.process(message)
                context.research_result = research_result.content
                actions.append({"type": "research", "result": research_result.content})
                print(f"[WORKFLOW] Research complete")

        # Step 3: Build deterministic creative brief / taste workflow contract
        context.creative_brief = build_creative_brief(
            request=context.original_request,
            analysis=context.analysis_result or {},
            research=context.research_result or {},
            learning_system=learning_system,
            orchestrator=self.orchestrator,
        )
        actions.append({"type": "creative_brief", "result": context.creative_brief})

        # Step 4: Planning
        context.state = WorkflowState.PLANNING
        planner = self.orchestrator.get_agent(AgentType.PLANNER)

        if planner:
            message = AgentMessage(
                sender=AgentType.RESEARCHER,
                recipient=AgentType.PLANNER,
                content={
                    "action": "create_plan",
                    "goal": context.original_request,
                    "analysis": context.analysis_result or {},
                    "research": context.research_result or {},
                    "creative_brief": context.creative_brief
                }
            )
            plan_result = await planner.process(message)
            context.plan_result = plan_result.content
            actions.append({"type": "planning", "result": plan_result.content})
            print(f"[WORKFLOW] Plan created: {len(plan_result.content.get('plan', []))} steps")

            # Check if confirmation is needed
            if not skip_confirmation and plan_result.content.get("requires_confirmation"):
                print(f"[WORKFLOW] Pausing for user confirmation")
                return {
                    "success": True,
                    "message": "Plan created - awaiting confirmation",
                    "plan": plan_result.content.get("plan", []),
                    "actions": actions,
                    "requires_confirmation": True
                }

        # Step 5: Implementation
        context.state = WorkflowState.IMPLEMENTING
        implementer = self.orchestrator.get_agent(AgentType.IMPLEMENTER)

        if implementer and context.plan_result:
            message = AgentMessage(
                sender=AgentType.PLANNER,
                recipient=AgentType.IMPLEMENTER,
                content={
                    "action": "implement",
                    "plan": context.plan_result
                }
            )
            impl_result = await implementer.process(message)
            context.implementation_result = impl_result.content
            actions.append({"type": "implementation", "result": impl_result.content})
            print(f"[WORKFLOW] Implementation complete: {len(impl_result.content.get('commands', []))} commands generated")

        # Step 6: Execution
        context.state = WorkflowState.EXECUTING
        executor = self.orchestrator.get_agent(AgentType.EXECUTOR)

        if executor and context.implementation_result:
            message = AgentMessage(
                sender=AgentType.IMPLEMENTER,
                recipient=AgentType.EXECUTOR,
                content={
                    "action": "execute_workflow",
                    "commands": context.implementation_result.get("commands", [])
                }
            )
            exec_result = await executor.process(message)
            context.execution_result = exec_result.content
            actions.append({"type": "execution", "result": exec_result.content})
            print(f"[WORKFLOW] Execution complete. Success: {exec_result.content.get('success', False)}")

            return {
                "success": exec_result.content.get("success", False),
                "message": exec_result.content.get("message", "Workflow executed"),
                "actions": actions,
                "can_undo": True
            }

        return {
            "success": True,
            "message": "Workflow planned but not executed",
            "actions": actions
        }

    async def _handle_question(self, context: WorkflowContext,
                                routing: Dict) -> Dict[str, Any]:
        """Handle a question by gathering information"""
        context.state = WorkflowState.RESEARCHING
        actions = []

        # Use Audio Engineer for domain knowledge
        engineer = self.orchestrator.get_agent(AgentType.AUDIO_ENGINEER)
        if engineer:
            message = AgentMessage(
                sender=AgentType.ROUTER,
                recipient=AgentType.AUDIO_ENGINEER,
                content={
                    "action": "answer_question",
                    "question": context.original_request
                }
            )
            result = await engineer.process(message)
            actions.append({"type": "knowledge", "result": result.content})

            return {
                "success": True,
                "message": result.content.get("answer", "Question processed"),
                "actions": actions
            }

        return {
            "success": False,
            "message": "Could not process question",
            "actions": actions
        }

    async def execute_plan(self, workflow_id: str) -> WorkflowResult:
        """Execute a previously created plan that was awaiting confirmation"""
        if workflow_id not in self.active_workflows:
            return WorkflowResult(
                success=False,
                message=f"Workflow {workflow_id} not found",
                state=WorkflowState.FAILED,
                execution_time=0.0
            )

        context = self.active_workflows[workflow_id]

        if not context.plan_result:
            return WorkflowResult(
                success=False,
                message="No plan to execute",
                state=WorkflowState.FAILED,
                execution_time=0.0
            )

        # Continue from implementation step
        start_time = datetime.now()
        actions = []

        try:
            # Implementation
            context.state = WorkflowState.IMPLEMENTING
            implementer = self.orchestrator.get_agent(AgentType.IMPLEMENTER)

            if implementer:
                message = AgentMessage(
                    sender=AgentType.PLANNER,
                    recipient=AgentType.IMPLEMENTER,
                    content={
                        "action": "implement",
                        "plan": context.plan_result
                    }
                )
                impl_result = await implementer.process(message)
                context.implementation_result = impl_result.content
                actions.append({"type": "implementation", "result": impl_result.content})

            # Execution
            context.state = WorkflowState.EXECUTING
            executor = self.orchestrator.get_agent(AgentType.EXECUTOR)

            if executor and context.implementation_result:
                message = AgentMessage(
                    sender=AgentType.IMPLEMENTER,
                    recipient=AgentType.EXECUTOR,
                    content={
                        "action": "execute_workflow",
                        "commands": context.implementation_result.get("commands", [])
                    }
                )
                exec_result = await executor.process(message)
                context.execution_result = exec_result.content
                actions.append({"type": "execution", "result": exec_result.content})

            context.state = WorkflowState.COMPLETED
            context.completed_at = datetime.now()

            execution_time = (context.completed_at - start_time).total_seconds()

            del self.active_workflows[workflow_id]
            self._add_to_history(context)

            return WorkflowResult(
                success=context.execution_result.get("success", False) if context.execution_result else False,
                message="Plan executed",
                state=context.state,
                execution_time=execution_time,
                actions_taken=actions,
                can_undo=True
            )

        except Exception as e:
            context.state = WorkflowState.FAILED
            context.error = str(e)

            return WorkflowResult(
                success=False,
                message=f"Execution failed: {e}",
                state=context.state,
                execution_time=(datetime.now() - start_time).total_seconds(),
                error=str(e)
            )

    async def cancel_workflow(self, workflow_id: str) -> bool:
        """Cancel an active workflow"""
        if workflow_id in self.active_workflows:
            context = self.active_workflows[workflow_id]
            context.state = WorkflowState.CANCELLED
            context.completed_at = datetime.now()

            del self.active_workflows[workflow_id]
            self._add_to_history(context)
            return True
        return False

    def get_workflow_status(self, workflow_id: str) -> Optional[WorkflowContext]:
        """Get the status of an active workflow"""
        return self.active_workflows.get(workflow_id)

    def get_active_workflows(self) -> List[WorkflowContext]:
        """Get all active workflows"""
        return list(self.active_workflows.values())

    def get_workflow_history(self, limit: int = 20) -> List[WorkflowContext]:
        """Get recent workflow history"""
        return self.workflow_history[-limit:]

    def _add_to_history(self, context: WorkflowContext):
        """Add a workflow to history"""
        self.workflow_history.append(context)
        if len(self.workflow_history) > self._max_history:
            self.workflow_history = self.workflow_history[-self._max_history:]


# Singleton instance
_coordinator: Optional[WorkflowCoordinator] = None


def get_workflow_coordinator(orchestrator=None) -> Optional[WorkflowCoordinator]:
    """Get the workflow coordinator instance"""
    global _coordinator
    if _coordinator is None and orchestrator is not None:
        _coordinator = WorkflowCoordinator(orchestrator)
    return _coordinator
