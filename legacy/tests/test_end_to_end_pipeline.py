"""
End-to-End Pipeline Integration Tests

Verifies the complete flow:
  User request → Research → Planner → Implementation → Executor

Tests that:
1. Research finds MICRO_SETTINGS / WAVES_MICRO_SETTINGS for an artist
2. Planner produces steps with add_device + set_device_parameter from research
3. Implementation passes commands through unchanged
4. Executor dispatches add_device → load_device and set_device_parameter by name
5. The correct Ableton controller methods are called with correct args
"""

import asyncio
import unittest
from unittest.mock import MagicMock, patch
from typing import Dict, Any, Optional

from agents import AgentType, AgentMessage
from agents.planner_agent import PlannerAgent
from agents.implementation_agent import ImplementationAgent
from agents.executor_agent import ExecutorAgent
from agents.research_agent import ResearchAgent
from knowledge.micro_settings_kb import (
    get_micro_settings_kb, MICRO_SETTINGS, WAVES_MICRO_SETTINGS,
    PLUGIN_PREFERENCES,
)


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class MockOrchestrator:
    """Minimal orchestrator for unit-level pipeline tests."""

    def __init__(self, ableton=None):
        self._ableton = ableton
        self._agents: Dict[AgentType, Any] = {}

    @property
    def ableton(self):
        return self._ableton

    def get_agent(self, agent_type):
        return self._agents.get(agent_type)

    def register_agent(self, agent):
        self._agents[agent.agent_type] = agent


def _make_mock_ableton():
    """Create a mock Ableton controller that records calls."""
    mock = MagicMock()
    mock.load_device.return_value = {"success": True, "message": "Device loaded"}
    mock.set_device_parameter.return_value = {"success": True, "message": "Param set"}
    mock.safe_set_device_parameter.return_value = {"success": True, "message": "Param set"}
    mock.get_available_plugins.return_value = {
        "success": True,
        "plugins": [
            {"name": "EQ Eight"}, {"name": "Compressor"}, {"name": "Reverb"},
            {"name": "Saturator"}, {"name": "Delay"}, {"name": "Glue Compressor"},
        ],
        "count": 6,
    }
    return mock


# ============================================================================
# 1. STEP-BY-STEP PIPELINE: research → planner → implementation → executor
# ============================================================================

class TestStepByStepPipeline(unittest.TestCase):
    """Walk through each stage of the pipeline manually, asserting data
    contracts between agents."""

    def setUp(self):
        self.mock_ableton = _make_mock_ableton()
        self.orchestrator = MockOrchestrator(ableton=self.mock_ableton)
        self.kb = get_micro_settings_kb()
        self.planner = PlannerAgent(self.orchestrator)
        self.implementer = ImplementationAgent(self.orchestrator)
        self.executor = ExecutorAgent(self.orchestrator)
        self.orchestrator.register_agent(self.planner)
        self.orchestrator.register_agent(self.implementer)
        self.orchestrator.register_agent(self.executor)

    # ------------------------------------------------------------------
    # Stage 1: Research returns micro settings
    # ------------------------------------------------------------------
    def test_stage1_research_returns_kanye_donda_settings(self):
        """get_settings returns stock device settings for kanye/donda."""
        settings = self.kb.get_settings("kanye west", "donda", "vocal")
        self.assertIsNotNone(settings)
        self.assertIn("devices", settings)
        self.assertIn("compressor", settings["devices"])
        self.assertEqual(settings["devices"]["compressor"]["device"], "Compressor")

    def test_stage1_waves_settings_available_for_kanye_donda(self):
        """get_waves_settings returns Waves parameters for kanye/donda."""
        waves = self.kb.get_waves_settings("kanye west", "donda", "vocal")
        self.assertIsNotNone(waves)
        self.assertIn("devices", waves)
        comp = waves["devices"]["compressor"]
        self.assertEqual(comp["device"], "CLA-76")
        self.assertIn("Input", comp["parameters"])
        self.assertIsInstance(comp["parameters"]["Input"], float)

    def test_stage1_plugin_preferences_prefer_cla76(self):
        """Plugin preferences map kanye/donda compressor → CLA-76."""
        prefs = self.kb.get_plugin_preferences("kanye west", "donda", "vocal")
        self.assertIn("compressor", prefs)
        self.assertEqual(prefs["compressor"]["preferred_plugin"], "CLA-76")

    # ------------------------------------------------------------------
    # Stage 2: Planner produces steps from research chain
    # ------------------------------------------------------------------
    def test_stage2_planner_creates_steps_from_research_chain(self):
        """Planner generates add_device + set_device_parameter from research."""
        research = {
            "plugin_chain": {
                "chain": [
                    {
                        "type": "compressor",
                        "purpose": "aggressive_punch",
                        "desired_plugin": "CLA-76",
                        "settings": {"Input": 28.0, "Ratio": 1.0, "Attack": 4.0},
                        "confidence": 0.9,
                    },
                    {
                        "type": "reverb",
                        "purpose": "tight_depth",
                        "desired_plugin": "H-Reverb",
                        "settings": {"Time": 1.0, "Dry/Wet": 12.0},
                        "confidence": 0.85,
                    },
                ],
                "confidence": 0.9,
            }
        }

        plan = run_async(self.planner._create_plan(
            goal="Kanye Donda vocal chain",
            analysis={},
            research=research,
        ))
        self.assertEqual(len(plan.steps), 2)

        # Step 1: CLA-76
        step1 = plan.steps[0]
        funcs1 = [c["function"] for c in step1["commands"]]
        self.assertIn("add_device", funcs1)
        self.assertIn("set_device_parameter", funcs1)

        add_cmd = [c for c in step1["commands"] if c["function"] == "add_device"][0]
        self.assertEqual(add_cmd["args"]["device"], "CLA-76")

        param_cmds = [c for c in step1["commands"]
                      if c["function"] == "set_device_parameter"]
        param_map = {c["args"]["param"]: c["args"]["value"] for c in param_cmds}
        self.assertEqual(param_map["Input"], 28.0)
        self.assertEqual(param_map["Ratio"], 1.0)
        self.assertEqual(param_map["Attack"], 4.0)

        # Step 2: H-Reverb
        step2 = plan.steps[1]
        add_cmd2 = [c for c in step2["commands"] if c["function"] == "add_device"][0]
        self.assertEqual(add_cmd2["args"]["device"], "H-Reverb")

    # ------------------------------------------------------------------
    # Stage 3: Implementation passes research commands through
    # ------------------------------------------------------------------
    def test_stage3_implementation_preserves_research_commands(self):
        """Implementation agent passes through pre-formed commands."""
        plan_steps = [
            {
                "order": 1,
                "description": "Add CLA-76 for punch",
                "commands": [
                    {"function": "add_device", "args": {"device": "CLA-76"}},
                    {"function": "set_device_parameter",
                     "args": {"param": "Input", "value": 28.0}},
                ],
            }
        ]

        impl_msg = AgentMessage(
            sender=AgentType.PLANNER,
            recipient=AgentType.IMPLEMENTER,
            content={"action": "implement", "plan": {"steps": plan_steps}},
        )
        result = run_async(self.implementer.process(impl_msg))
        commands = result.content.get("commands", [])

        # Should have both commands preserved
        funcs = [c["function"] for c in commands]
        self.assertIn("add_device", funcs)
        self.assertIn("set_device_parameter", funcs)

        # Args should be intact
        add_cmd = [c for c in commands if c["function"] == "add_device"][0]
        self.assertEqual(add_cmd["args"]["device"], "CLA-76")

        param_cmd = [c for c in commands if c["function"] == "set_device_parameter"][0]
        self.assertEqual(param_cmd["args"]["param"], "Input")
        self.assertEqual(param_cmd["args"]["value"], 28.0)

    # ------------------------------------------------------------------
    # Stage 4: Executor dispatches commands to Ableton
    # ------------------------------------------------------------------
    def test_stage4_executor_dispatches_add_device_to_load_device(self):
        """Executor translates add_device → ableton.load_device."""
        commands = [
            {"function": "add_device", "args": {"device": "CLA-76"}},
        ]
        result = run_async(self.executor._execute_workflow({
            "commands": commands,
            "track_index": 2,
        }))
        self.assertTrue(result["success"])
        self.mock_ableton.load_device.assert_called_once_with(2, "CLA-76", -1)

    def test_stage4_executor_dispatches_set_device_parameter_by_name(self):
        """Executor routes name-based set_device_parameter to set_parameter_by_name."""
        mock_rpc = MagicMock()
        mock_rpc.set_parameter_by_name.return_value = {
            "success": True, "param_index": 5,
        }

        commands = [
            {"function": "set_device_parameter",
             "args": {"param": "Input", "value": 28.0}},
        ]

        with patch(
            "agents.executor_agent.get_reliable_controller",
            return_value=mock_rpc,
            create=True,
        ), patch(
            "ableton_controls.reliable_params.get_reliable_controller",
            return_value=mock_rpc,
        ):
            result = run_async(self.executor._execute_workflow({
                "commands": commands,
                "track_index": 2,
                "device_index": 0,
            }))

        self.assertTrue(result["success"])
        mock_rpc.set_parameter_by_name.assert_called_once_with(2, 0, "Input", 28.0)

    def test_stage4_executor_index_based_set_device_parameter(self):
        """Executor handles index-based set_device_parameter directly."""
        commands = [
            {"function": "set_device_parameter",
             "args": {"track_index": 1, "device_index": 0,
                      "param_index": 3, "value": 0.5}},
        ]
        result = run_async(self.executor._execute_workflow({"commands": commands}))
        self.assertTrue(result["success"])
        self.mock_ableton.set_device_parameter.assert_called_once_with(1, 0, 3, 0.5)


# ============================================================================
# 2. FULL PIPELINE: research chain → plan → implement → execute
# ============================================================================

class TestFullPipelineKanyeDonda(unittest.TestCase):
    """Simulate the complete pipeline for 'Kanye Donda vocal chain'
    using real agent instances with mocked Ableton."""

    def setUp(self):
        self.mock_ableton = _make_mock_ableton()
        self.orchestrator = MockOrchestrator(ableton=self.mock_ableton)
        self.planner = PlannerAgent(self.orchestrator)
        self.implementer = ImplementationAgent(self.orchestrator)
        self.executor = ExecutorAgent(self.orchestrator)
        self.orchestrator.register_agent(self.planner)
        self.orchestrator.register_agent(self.implementer)
        self.orchestrator.register_agent(self.executor)
        self.kb = get_micro_settings_kb()

    def test_full_pipeline_with_waves_chain(self):
        """Research → Plan → Implement → Execute for a Waves CLA-76 chain.

        Verifies that numeric parameters from WAVES_MICRO_SETTINGS survive
        all the way to the executor's dispatch calls.
        """
        # --- Stage 1: Build research output from WAVES_MICRO_SETTINGS ---
        waves = self.kb.get_waves_settings("kanye west", "donda", "vocal")
        self.assertIsNotNone(waves)

        # Convert WAVES_MICRO_SETTINGS devices into a research chain
        chain = []
        for slot_key, dev in waves["devices"].items():
            chain.append({
                "type": slot_key,
                "purpose": dev["purpose"],
                "desired_plugin": dev["device"],
                "settings": {k: v for k, v in dev["parameters"].items()
                             if isinstance(v, (int, float))},
                "confidence": 0.9,
            })
        research = {"plugin_chain": {"chain": chain, "confidence": 0.9}}

        # --- Stage 2: Planner ---
        plan = run_async(self.planner._create_plan(
            goal="Kanye Donda vocal chain",
            analysis={},
            research=research,
        ))
        self.assertGreater(len(plan.steps), 0)

        # Collect all commands from all steps
        all_commands = []
        for step in plan.steps:
            all_commands.extend(step["commands"])

        # Verify CLA-76 is in the add_device commands
        add_devices = [c["args"]["device"] for c in all_commands
                       if c["function"] == "add_device"]
        self.assertIn("CLA-76", add_devices)

        # Verify CLA-76 Input param is in set_device_parameter commands
        param_cmds = [c for c in all_commands
                      if c["function"] == "set_device_parameter"]
        input_cmds = [c for c in param_cmds if c["args"]["param"] == "Input"]
        self.assertEqual(len(input_cmds), 1)
        self.assertEqual(input_cmds[0]["args"]["value"], 28.0)

        # --- Stage 3: Implementation ---
        impl_msg = AgentMessage(
            sender=AgentType.PLANNER,
            recipient=AgentType.IMPLEMENTER,
            content={"action": "implement", "plan": {"steps": plan.steps}},
        )
        impl_result = run_async(self.implementer.process(impl_msg))
        impl_commands = impl_result.content.get("commands", [])
        self.assertGreater(len(impl_commands), 0)

        # Verify commands survived implementation
        impl_funcs = [c["function"] for c in impl_commands]
        self.assertIn("add_device", impl_funcs)
        self.assertIn("set_device_parameter", impl_funcs)

        # --- Stage 4: Execution ---
        mock_rpc = MagicMock()
        mock_rpc.set_parameter_by_name.return_value = {
            "success": True, "param_index": 0,
        }

        with patch(
            "agents.executor_agent.get_reliable_controller",
            return_value=mock_rpc,
            create=True,
        ), patch(
            "ableton_controls.reliable_params.get_reliable_controller",
            return_value=mock_rpc,
        ):
            exec_result = run_async(self.executor._execute_workflow({
                "commands": impl_commands,
                "track_index": 0,
            }))

        # Verify execution succeeded
        self.assertTrue(exec_result["success"], f"Execution failed: {exec_result}")

        # Verify load_device was called for each device
        load_calls = self.mock_ableton.load_device.call_args_list
        loaded_names = [call.args[1] for call in load_calls]
        self.assertIn("CLA-76", loaded_names)

        # Verify set_parameter_by_name was called with Waves param names
        set_calls = mock_rpc.set_parameter_by_name.call_args_list
        set_param_names = [call.args[2] for call in set_calls]
        self.assertIn("Input", set_param_names)

    def test_full_pipeline_stock_fallback_no_research_chain(self):
        """Without a research chain, planner falls back to analysis-driven
        steps using stock Ableton device names."""
        analysis = {
            "detected_intent": "add_vocal_chain",
            "target_element": "vocals",
            "workflow_steps": [
                {"step": 1, "action": "Add EQ for high-pass filtering"},
                {"step": 2, "action": "Add compressor for dynamics control"},
            ],
        }
        plan = run_async(self.planner._create_plan(
            goal="Add vocal chain",
            analysis=analysis,
            research={},
        ))
        self.assertEqual(len(plan.steps), 2)

        # Should use stock device names from keyword matching
        all_commands = []
        for step in plan.steps:
            all_commands.extend(step["commands"])
        add_devices = [c["args"].get("device", c["args"].get("device_name", ""))
                       for c in all_commands if c["function"] == "add_device"]
        # Should contain stock names, not Waves
        for name in add_devices:
            self.assertNotIn("CLA", name)


# ============================================================================
# 3. MULTI-ARTIST COVERAGE: verify pipeline data for several artists
# ============================================================================

class TestMultiArtistPipelineData(unittest.TestCase):
    """Verify that the pipeline data (MICRO_SETTINGS, WAVES_MICRO_SETTINGS,
    PLUGIN_PREFERENCES) is consistent across all artists that have Waves
    entries."""

    def setUp(self):
        self.kb = get_micro_settings_kb()

    def test_every_waves_micro_settings_artist_has_stock_fallback(self):
        """Every artist in WAVES_MICRO_SETTINGS also exists in MICRO_SETTINGS
        so the stock fallback path works."""
        for artist_key in WAVES_MICRO_SETTINGS:
            self.assertIn(artist_key, MICRO_SETTINGS,
                          f"WAVES_MICRO_SETTINGS has '{artist_key}' but MICRO_SETTINGS does not")

    def test_every_waves_device_has_plugin_preference(self):
        """Every Waves device in WAVES_MICRO_SETTINGS should have a
        corresponding entry in PLUGIN_PREFERENCES."""
        for artist_key, styles in WAVES_MICRO_SETTINGS.items():
            for style_key, style_data in styles.items():
                prefs = PLUGIN_PREFERENCES.get(artist_key, {}).get(style_key, {})
                for slot_key, dev in style_data.get("devices", {}).items():
                    waves_device = dev.get("device", "")
                    # Find any preference that references this Waves plugin
                    pref_plugins = [p.get("preferred_plugin", "")
                                    for p in prefs.values()]
                    self.assertIn(
                        waves_device, pref_plugins,
                        f"WAVES_MICRO_SETTINGS[{artist_key}][{style_key}].devices"
                        f"[{slot_key}] uses '{waves_device}' but no PLUGIN_PREFERENCES "
                        f"entry references it. Available: {pref_plugins}"
                    )

    def test_waves_parameter_names_are_strings(self):
        """All parameter names in WAVES_MICRO_SETTINGS should be strings
        (DAW-native names, not indices)."""
        for artist_key, styles in WAVES_MICRO_SETTINGS.items():
            for style_key, style_data in styles.items():
                for slot_key, dev in style_data.get("devices", {}).items():
                    for param_name in dev.get("parameters", {}):
                        self.assertIsInstance(
                            param_name, str,
                            f"Non-string param name in {artist_key}/{style_key}/{slot_key}"
                        )

    def test_waves_parameter_values_are_numeric(self):
        """All parameter values in WAVES_MICRO_SETTINGS should be int or float."""
        for artist_key, styles in WAVES_MICRO_SETTINGS.items():
            for style_key, style_data in styles.items():
                for slot_key, dev in style_data.get("devices", {}).items():
                    for param_name, param_val in dev.get("parameters", {}).items():
                        self.assertIsInstance(
                            param_val, (int, float),
                            f"Non-numeric value for {artist_key}/{style_key}"
                            f"/{slot_key}/{param_name}: {param_val}"
                        )

    def test_pipeline_data_for_each_artist(self):
        """For each artist with WAVES entries, verify the full data chain:
        MICRO_SETTINGS → PLUGIN_PREFERENCES → WAVES_MICRO_SETTINGS."""
        artists_with_waves = list(WAVES_MICRO_SETTINGS.keys())
        self.assertGreater(len(artists_with_waves), 0)

        for artist_key in artists_with_waves:
            # Stock settings exist
            stock = MICRO_SETTINGS.get(artist_key)
            self.assertIsNotNone(stock, f"No MICRO_SETTINGS for {artist_key}")

            # At least one style overlaps
            waves_styles = set(WAVES_MICRO_SETTINGS[artist_key].keys())
            stock_styles = set(stock.keys())
            overlap = waves_styles & stock_styles
            self.assertGreater(
                len(overlap), 0,
                f"No overlapping styles between WAVES and stock for {artist_key}. "
                f"Waves: {waves_styles}, Stock: {stock_styles}"
            )


# ============================================================================
# 4. EXECUTOR DEVICE INDEX TRACKING
# ============================================================================

class TestExecutorDeviceIndexTracking(unittest.TestCase):
    """Verify that the executor tracks device indices across sequential
    add_device + set_device_parameter commands."""

    def setUp(self):
        self.mock_ableton = _make_mock_ableton()
        self.orchestrator = MockOrchestrator(ableton=self.mock_ableton)
        self.executor = ExecutorAgent(self.orchestrator)
        self.orchestrator.register_agent(self.executor)

    def test_set_device_parameter_uses_last_device_index(self):
        """set_device_parameter should target the device loaded by the
        preceding add_device command."""
        # load_device returns device_index
        self.mock_ableton.load_device.return_value = {
            "success": True, "device_index": 3,
        }
        mock_rpc = MagicMock()
        mock_rpc.set_parameter_by_name.return_value = {
            "success": True, "param_index": 1,
        }

        commands = [
            {"function": "add_device", "args": {"device": "CLA-76"}},
            {"function": "set_device_parameter",
             "args": {"param": "Input", "value": 28.0}},
            {"function": "set_device_parameter",
             "args": {"param": "Ratio", "value": 1.0}},
        ]

        with patch(
            "agents.executor_agent.get_reliable_controller",
            return_value=mock_rpc,
            create=True,
        ), patch(
            "ableton_controls.reliable_params.get_reliable_controller",
            return_value=mock_rpc,
        ):
            result = run_async(self.executor._execute_workflow({
                "commands": commands,
                "track_index": 0,
            }))

        self.assertTrue(result["success"])

        # Both set_parameter_by_name calls should use device_index=3
        for call in mock_rpc.set_parameter_by_name.call_args_list:
            self.assertEqual(call.args[1], 3,
                             f"Expected device_index=3 but got {call.args[1]}")

    def test_device_index_updates_per_add_device(self):
        """When multiple add_device commands run, the device index should
        update for each one."""
        # First load returns index 2, second returns index 3
        self.mock_ableton.load_device.side_effect = [
            {"success": True, "device_index": 2},
            {"success": True, "device_index": 3},
        ]
        mock_rpc = MagicMock()
        mock_rpc.set_parameter_by_name.return_value = {
            "success": True, "param_index": 0,
        }

        commands = [
            {"function": "add_device", "args": {"device": "CLA-76"}},
            {"function": "set_device_parameter",
             "args": {"param": "Input", "value": 28.0}},
            {"function": "add_device", "args": {"device": "H-Reverb"}},
            {"function": "set_device_parameter",
             "args": {"param": "Time", "value": 1.0}},
        ]

        with patch(
            "agents.executor_agent.get_reliable_controller",
            return_value=mock_rpc,
            create=True,
        ), patch(
            "ableton_controls.reliable_params.get_reliable_controller",
            return_value=mock_rpc,
        ):
            result = run_async(self.executor._execute_workflow({
                "commands": commands,
                "track_index": 0,
            }))

        self.assertTrue(result["success"])

        # First set_parameter_by_name call targets device 2
        call1 = mock_rpc.set_parameter_by_name.call_args_list[0]
        self.assertEqual(call1.args[1], 2)
        self.assertEqual(call1.args[2], "Input")

        # Second set_parameter_by_name call targets device 3
        call2 = mock_rpc.set_parameter_by_name.call_args_list[1]
        self.assertEqual(call2.args[1], 3)
        self.assertEqual(call2.args[2], "Time")


class TestPluginAvailabilityFallback(unittest.TestCase):
    """Task #5: Executor falls back through PLUGIN_PREFERENCES when a plugin
    isn't installed, and skips Waves-specific params for stock fallbacks."""

    def _make_executor(self, ableton_mock):
        orch = MockOrchestrator(ableton=ableton_mock)
        ex = ExecutorAgent.__new__(ExecutorAgent)
        ex.orchestrator = orch
        ex.agent_type = AgentType.EXECUTOR
        return ex

    # -- _lookup_fallbacks --

    def test_lookup_fallbacks_finds_chain(self):
        """CLA-76 should resolve to a fallback list ending with stock Compressor."""
        ex = self._make_executor(MagicMock())
        fallbacks = ex._lookup_fallbacks("CLA-76")
        self.assertIsInstance(fallbacks, list)
        self.assertTrue(len(fallbacks) > 0)
        # Last entry should be a stock device
        self.assertTrue(ex._is_stock_device(fallbacks[-1]))

    def test_lookup_fallbacks_unknown_returns_empty(self):
        ex = self._make_executor(MagicMock())
        self.assertEqual(ex._lookup_fallbacks("NonExistentPlugin9000"), [])

    # -- _dispatch_command add_device fallback --

    def test_add_device_success_no_fallback(self):
        """When load_device succeeds, no fallback is attempted."""
        mock_ab = MagicMock()
        mock_ab.load_device.return_value = {"success": True, "message": "ok"}
        ex = self._make_executor(mock_ab)
        result = ex._dispatch_command(mock_ab, "add_device",
                                      {"device": "CLA-76"}, 0, None)
        self.assertTrue(result["success"])
        self.assertEqual(result["loaded_device"], "CLA-76")
        self.assertFalse(result["is_fallback"])
        mock_ab.load_device.assert_called_once()

    def test_add_device_falls_back_to_stock(self):
        """When preferred plugin fails, executor tries fallbacks."""
        mock_ab = MagicMock()
        # First call (CLA-76) fails, subsequent calls succeed
        mock_ab.load_device.side_effect = [
            {"success": False, "message": "not found"},  # CLA-76
            {"success": False, "message": "not found"},  # FabFilter Pro-C 2
            {"success": False, "message": "not found"},  # Glue Compressor
            {"success": True, "message": "ok"},           # Compressor (stock)
        ]
        ex = self._make_executor(mock_ab)
        result = ex._dispatch_command(mock_ab, "add_device",
                                      {"device": "CLA-76"}, 0, None)
        self.assertTrue(result["success"])
        self.assertEqual(result["loaded_device"], "Compressor")
        self.assertTrue(result["is_fallback"])
        self.assertEqual(result["original_device"], "CLA-76")

    def test_add_device_all_fallbacks_fail(self):
        """When all fallbacks fail, returns failure with metadata."""
        mock_ab = MagicMock()
        mock_ab.load_device.return_value = {"success": False, "message": "nope"}
        ex = self._make_executor(mock_ab)
        result = ex._dispatch_command(mock_ab, "add_device",
                                      {"device": "CLA-76"}, 0, None)
        self.assertFalse(result["success"])
        self.assertTrue(result["is_fallback"])
        self.assertIsNone(result["loaded_device"])

    def test_add_device_uses_explicit_fallbacks_arg(self):
        """Fallbacks passed via args take priority over KB lookup."""
        mock_ab = MagicMock()
        mock_ab.load_device.side_effect = [
            {"success": False, "message": "no"},
            {"success": True, "message": "ok"},
        ]
        ex = self._make_executor(mock_ab)
        result = ex._dispatch_command(mock_ab, "add_device",
                                      {"device": "MyPlugin", "fallbacks": ["Reverb"]},
                                      0, None)
        self.assertTrue(result["success"])
        self.assertEqual(result["loaded_device"], "Reverb")

    # -- _execute_workflow skips Waves params on stock fallback --

    def test_workflow_skips_waves_params_after_stock_fallback(self):
        """When add_device falls back to stock, subsequent name-based
        set_device_parameter commands are skipped."""
        mock_ab = MagicMock()
        mock_ab.load_device.side_effect = [
            {"success": False, "message": "no"},   # CLA-76
            {"success": True, "message": "ok", "device_index": 0},  # Compressor (stock)
        ]
        ex = self._make_executor(mock_ab)

        commands = [
            {"function": "add_device", "args": {"device": "CLA-76",
                                                 "fallbacks": ["Compressor"]}},
            {"function": "set_device_parameter", "args": {"param": "Input", "value": 28.0}},
            {"function": "set_device_parameter", "args": {"param": "Ratio", "value": 4.0}},
        ]
        result = run_async(ex._execute_workflow({"commands": commands}))
        self.assertTrue(result["success"])

        # The two set_device_parameter steps should be skipped
        param_results = [r for r in result["results"]
                         if r["function"] == "set_device_parameter"]
        self.assertEqual(len(param_results), 2)
        for pr in param_results:
            self.assertTrue(pr["result"]["skipped"])

    def test_workflow_applies_params_when_no_fallback(self):
        """When plugin loads successfully (no fallback), params are applied normally."""
        mock_ab = MagicMock()
        mock_ab.load_device.return_value = {"success": True, "message": "ok",
                                             "device_index": 0}
        mock_rpc = MagicMock()
        mock_rpc.set_parameter_by_name.return_value = {"success": True}

        ex = self._make_executor(mock_ab)
        commands = [
            {"function": "add_device", "args": {"device": "CLA-76"}},
            {"function": "set_device_parameter", "args": {"param": "Input", "value": 28.0}},
        ]
        with patch("agents.executor_agent.get_reliable_controller",
                    return_value=mock_rpc, create=True):
            # Need to patch at import location inside _dispatch_command
            with patch("ableton_controls.reliable_params.get_reliable_controller",
                       return_value=mock_rpc):
                result = run_async(ex._execute_workflow({"commands": commands}))

        self.assertTrue(result["success"])
        param_results = [r for r in result["results"]
                         if r["function"] == "set_device_parameter"]
        self.assertEqual(len(param_results), 1)
        self.assertFalse(param_results[0]["result"].get("skipped", False))

    def test_workflow_resets_fallback_flag_on_next_device(self):
        """The skip-Waves-params flag resets when the next add_device succeeds
        without fallback."""
        mock_ab = MagicMock()
        mock_ab.load_device.side_effect = [
            {"success": False, "message": "no"},   # CLA-76 fails
            {"success": True, "message": "ok", "device_index": 0},  # Compressor fallback
            {"success": True, "message": "ok", "device_index": 1},  # H-Reverb succeeds
        ]
        mock_rpc = MagicMock()
        mock_rpc.set_parameter_by_name.return_value = {"success": True}

        ex = self._make_executor(mock_ab)
        commands = [
            {"function": "add_device", "args": {"device": "CLA-76",
                                                 "fallbacks": ["Compressor"]}},
            {"function": "set_device_parameter", "args": {"param": "Input", "value": 28.0}},
            # Next device loads fine — params should apply
            {"function": "add_device", "args": {"device": "H-Reverb"}},
            {"function": "set_device_parameter", "args": {"param": "Time", "value": 1.5}},
        ]
        with patch("ableton_controls.reliable_params.get_reliable_controller",
                    return_value=mock_rpc):
            result = run_async(ex._execute_workflow({"commands": commands}))

        param_results = [r for r in result["results"]
                         if r["function"] == "set_device_parameter"]
        # First param skipped (stock fallback), second applied
        self.assertTrue(param_results[0]["result"].get("skipped", False))
        self.assertFalse(param_results[1]["result"].get("skipped", False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
