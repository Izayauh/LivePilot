"""
Workflow Planner Agent

Converts high-level production goals into step-by-step executable workflows.
Takes input from the Audio Engineer agent and produces actionable plans.
"""

from typing import Dict, Any, List, Optional
from agents import AgentType, AgentMessage, WorkflowPlan
from agent_system import BaseAgent
from creative_workflow import annotate_plan_steps


class PlannerAgent(BaseAgent):
    """
    Creates executable workflow plans from production goals

    Responsibilities:
    - Convert high-level goals to step-by-step workflows
    - Map abstract concepts to concrete Ableton actions
    - Estimate execution time
    - Create rollback plans for failed workflows
    """

    DEVICE_TYPE_MAP = {
        "eq": "EQ Eight",
        "compressor": "Compressor",
        "reverb": "Reverb",
        "delay": "Delay",
        "saturation": "Saturator",
        "de-esser": "Multiband Dynamics",
        "limiter": "Limiter",
        "distortion": "Pedal",
        "chorus": "Chorus-Ensemble",
        "phaser": "Phaser",
        "flanger": "Flanger",
        "gate": "Gate",
        "glue compressor": "Glue Compressor",
        "multiband": "Multiband Dynamics",
        "utility": "Utility",
        "auto filter": "Auto Filter",
        "drum buss": "Drum Buss",
    }

    def __init__(self, orchestrator):
        super().__init__(AgentType.PLANNER, orchestrator)

        # Templates for common workflows
        self.workflow_templates = self._load_workflow_templates()
    
    def _load_workflow_templates(self) -> Dict[str, List[Dict]]:
        """Load workflow templates for common production tasks"""
        return {
            "add_punch_drums": [
                {
                    "step": 1,
                    "description": "Create parallel compression bus",
                    "osc_commands": [
                        {"function": "create_return_track", "args": {}}
                    ]
                },
                {
                    "step": 2,
                    "description": "Add compressor to return track",
                    "osc_commands": [
                        {"function": "add_device", "args": {"track_index": -1, "device": "Compressor"}}
                    ]
                },
                {
                    "step": 3,
                    "description": "Set heavy compression settings",
                    "osc_commands": [
                        {"function": "set_device_parameter", "args": {"param": "Ratio", "value": 8.0}},
                        {"function": "set_device_parameter", "args": {"param": "Attack", "value": 1.0}},
                        {"function": "set_device_parameter", "args": {"param": "Release", "value": 50.0}}
                    ]
                },
                {
                    "step": 4,
                    "description": "Route drum track to send",
                    "osc_commands": [
                        {"function": "set_track_send", "args": {"track_index": 0, "send_index": 0, "level": 0.3}}
                    ]
                }
            ],
            
            "mute_unmute_track": [
                {
                    "step": 1,
                    "description": "Toggle track mute state",
                    "osc_commands": [
                        {"function": "mute_track", "args": {"track_index": 0, "muted": 1}}
                    ]
                }
            ],
            
            "set_tempo": [
                {
                    "step": 1,
                    "description": "Set project tempo",
                    "osc_commands": [
                        {"function": "set_tempo", "args": {"bpm": 120}}
                    ]
                }
            ],
            
            "sidechain_bass_to_kick": [
                {
                    "step": 1,
                    "description": "Add compressor to bass track",
                    "osc_commands": [
                        {"function": "add_device", "args": {"track_index": 1, "device": "Compressor"}}
                    ]
                },
                {
                    "step": 2,
                    "description": "Enable sidechain from kick track",
                    "osc_commands": [
                        {"function": "set_device_parameter", "args": {"param": "Sidechain", "value": 1}},
                        {"function": "set_device_parameter", "args": {"param": "Sidechain_Source", "value": 0}}
                    ]
                },
                {
                    "step": 3,
                    "description": "Set compression parameters",
                    "osc_commands": [
                        {"function": "set_device_parameter", "args": {"param": "Ratio", "value": 6.0}},
                        {"function": "set_device_parameter", "args": {"param": "Attack", "value": 0.1}},
                        {"function": "set_device_parameter", "args": {"param": "Release", "value": 150.0}}
                    ]
                }
            ],
            
            "vocal_chain": [
                {
                    "step": 1,
                    "description": "Add EQ for high-pass filter",
                    "osc_commands": [
                        {"function": "add_device", "args": {"device": "EQ Eight"}}
                    ]
                },
                {
                    "step": 2,
                    "description": "Set high-pass at 100Hz",
                    "osc_commands": [
                        {"function": "set_device_parameter", "args": {"param": "1 Filter Type", "value": 1}},
                        {"function": "set_device_parameter", "args": {"param": "1 Frequency", "value": 100}}
                    ]
                },
                {
                    "step": 3,
                    "description": "Add compressor",
                    "osc_commands": [
                        {"function": "add_device", "args": {"device": "Compressor"}}
                    ]
                },
                {
                    "step": 4,
                    "description": "Set gentle compression",
                    "osc_commands": [
                        {"function": "set_device_parameter", "args": {"param": "Ratio", "value": 3.0}},
                        {"function": "set_device_parameter", "args": {"param": "Attack", "value": 20.0}},
                        {"function": "set_device_parameter", "args": {"param": "Release", "value": 150.0}}
                    ]
                },
                {
                    "step": 5,
                    "description": "Add reverb",
                    "osc_commands": [
                        {"function": "add_device", "args": {"device": "Reverb"}}
                    ]
                }
            ]
        }
    
    async def process(self, message: AgentMessage) -> AgentMessage:
        """Process planning requests"""
        content = message.content
        action = content.get("action", "create_plan")
        
        if action == "create_plan":
            creative_brief = content.get("creative_brief", {})
            plan = await self._create_plan(
                goal=content.get("goal", ""),
                analysis=content.get("analysis", {}),
                research=content.get("research", {}),
                creative_brief=creative_brief
            )
            return AgentMessage(
                sender=self.agent_type,
                recipient=message.sender,
                content={
                    "success": True,
                    "plan": plan.steps if plan else [],
                    "goal": plan.goal if plan else "",
                    "requires_confirmation": plan.requires_confirmation if plan else False,
                    "creative_brief": creative_brief
                },
                correlation_id=message.correlation_id
            )
        
        elif action == "get_template":
            template = self._get_template(content.get("name", ""))
            return AgentMessage(
                sender=self.agent_type,
                recipient=message.sender,
                content={
                    "success": template is not None,
                    "template": template
                },
                correlation_id=message.correlation_id
            )
        
        return AgentMessage(
            sender=self.agent_type,
            recipient=message.sender,
            content={"error": f"Unknown action: {action}"},
            correlation_id=message.correlation_id
        )
    
    async def _create_plan(self, goal: str, analysis: Dict, research: Dict,
                           creative_brief: Optional[Dict] = None) -> Optional[WorkflowPlan]:
        """
        Create a workflow plan from goal, analysis, and research
        """
        if not analysis and not research:
            return WorkflowPlan(
                goal=goal,
                steps=[],
                requires_confirmation=True
            )

        # If research contains a plugin chain, build steps from it
        plugin_chain = self._extract_chain_from_research(research)
        if plugin_chain:
            executable_steps = self._generate_steps_from_chain(plugin_chain, analysis)
        else:
            detected_intent = analysis.get("detected_intent", "unknown")
            target_element = analysis.get("target_element", "")
            workflow_steps = analysis.get("workflow_steps", [])

            # Generate executable steps from analysis
            executable_steps = []

            for step in workflow_steps:
                executable_step = {
                    "order": step.get("step", len(executable_steps) + 1),
                    "description": step.get("action", ""),
                    "commands": self._generate_commands_for_step(
                        step.get("action", ""),
                        target_element,
                        detected_intent
                    )
                }
                executable_steps.append(executable_step)
        
        executable_steps = annotate_plan_steps(executable_steps, creative_brief)

        # Create rollback steps (reverse order, opposite actions)
        rollback_steps = self._create_rollback_steps(executable_steps)
        requires_taste_confirmation = bool((creative_brief or {}).get("missing_decisions"))
        
        return WorkflowPlan(
            goal=goal,
            steps=executable_steps,
            estimated_duration=len(executable_steps) * 0.5,  # 0.5s per step estimate
            requires_confirmation=len(executable_steps) > 3 or requires_taste_confirmation,
            rollback_steps=rollback_steps
        )
    
    def _extract_chain_from_research(self, research: Dict) -> Optional[List[Dict]]:
        """Extract plugin chain from research result, handling multiple formats."""
        if not research:
            return None

        # Direct format: {"chain": [...]}
        if isinstance(research.get("chain"), list) and research["chain"]:
            return research["chain"]

        # Wrapped format: {"plugin_chain": {"chain": [...]}}
        plugin_chain = research.get("plugin_chain")
        if isinstance(plugin_chain, dict):
            chain = plugin_chain.get("chain")
            if isinstance(chain, list) and chain:
                return chain

        # Agent system format: {"research": {"plugin_chain": {"chain": [...]}}}
        inner_research = research.get("research")
        if isinstance(inner_research, dict):
            return self._extract_chain_from_research(inner_research)

        # Techniques format: {"techniques_found": [{"chain": [...]}]}
        techniques = research.get("techniques_found")
        if isinstance(techniques, list):
            for tech in techniques:
                if isinstance(tech, dict):
                    chain = tech.get("chain")
                    if isinstance(chain, list) and chain:
                        return chain

        return None

    def _generate_steps_from_chain(self, chain: List[Dict], analysis: Dict) -> List[Dict]:
        """Convert a research plugin chain into executable plan steps."""
        steps = []
        for i, device in enumerate(chain):
            device_type = device.get("type", "")
            purpose = device.get("purpose", "")
            settings = device.get("settings", {})
            desired_plugin = device.get("desired_plugin", "")

            # Use desired_plugin if provided, otherwise map type to Ableton device
            device_name = desired_plugin or self._type_to_device_name(device_type)

            # Command to load the device
            commands = [{"function": "add_device", "args": {"device": device_name}}]

            # Commands to set each numeric parameter
            for param_key, param_value in settings.items():
                if isinstance(param_value, (int, float)):
                    commands.append({
                        "function": "set_device_parameter",
                        "args": {"param": param_key, "value": param_value}
                    })

            steps.append({
                "order": i + 1,
                "description": f"Add {device_name} for {purpose}" if purpose else f"Add {device_name}",
                "commands": commands,
                "source": "research",
                "confidence": device.get("confidence", 0.5)
            })
        return steps

    def _type_to_device_name(self, device_type: str) -> str:
        """Map a generic device type string to an Ableton device name."""
        return self.DEVICE_TYPE_MAP.get(device_type.lower(), device_type or "Utility")

    def _generate_commands_for_step(self, action_description: str, target_element: str, intent: str) -> List[Dict]:
        """Generate OSC commands for a workflow step"""
        commands = []
        action_lower = action_description.lower()
        
        # Pattern matching for common actions
        if "compression" in action_lower and "bus" in action_lower:
            # This is a complex action - would need device creation
            # For now, return a placeholder
            commands.append({
                "function": "create_return_track",
                "args": {},
                "note": "Creates parallel compression bus"
            })
        
        elif "compressor" in action_lower or "compression" in action_lower:
            commands.append({
                "function": "add_device",
                "args": {"device": "Compressor"},
                "note": "Add compressor device"
            })
        
        elif "eq" in action_lower:
            commands.append({
                "function": "add_device",
                "args": {"device": "EQ Eight"},
                "note": "Add EQ device"
            })
        
        elif "reverb" in action_lower:
            commands.append({
                "function": "add_device",
                "args": {"device": "Reverb"},
                "note": "Add reverb device"
            })
        
        elif "saturation" in action_lower or "tape" in action_lower:
            commands.append({
                "function": "add_device",
                "args": {"device": "Saturator"},
                "note": "Add saturation device"
            })
        
        elif "transient" in action_lower:
            commands.append({
                "function": "add_device",
                "args": {"device": "Drum Buss"},
                "note": "Add transient shaping"
            })
        
        elif "blend" in action_lower or "send" in action_lower:
            commands.append({
                "function": "set_track_send",
                "args": {"track_index": 0, "send_index": 0, "level": 0.3},
                "note": "Set send level for blend"
            })
        
        elif "route" in action_lower:
            commands.append({
                "function": "set_track_send",
                "args": {"track_index": 0, "send_index": 0, "level": 1.0},
                "note": "Route to bus"
            })
        
        elif "high-pass" in action_lower or "high pass" in action_lower:
            commands.append({
                "function": "add_device",
                "args": {"device": "EQ Eight"},
                "note": "Add EQ for high-pass"
            })
        
        return commands
    
    def _create_rollback_steps(self, steps: List[Dict]) -> List[Dict]:
        """Create rollback steps for undo functionality"""
        rollback = []
        
        for step in reversed(steps):
            for cmd in step.get("commands", []):
                func = cmd.get("function", "")
                
                # Create opposite action
                if func == "mute_track":
                    rollback.append({
                        "function": "mute_track",
                        "args": {**cmd.get("args", {}), "muted": 0}
                    })
                elif func == "solo_track":
                    rollback.append({
                        "function": "solo_track",
                        "args": {**cmd.get("args", {}), "soloed": 0}
                    })
                # Add more rollback mappings as needed
        
        return rollback
    
    def _get_template(self, name: str) -> Optional[List[Dict]]:
        """Get a workflow template by name"""
        return self.workflow_templates.get(name)
    
    def get_available_templates(self) -> List[str]:
        """Get list of available workflow templates"""
        return list(self.workflow_templates.keys())

