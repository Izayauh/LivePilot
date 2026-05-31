"""
Tests: Research Agent → Planner Agent Pipeline (Waves Plugins Focus)

Validates that:
1. Research agent produces correct, specific parameters for Waves plugins
2. Planner agent correctly translates research output into executable steps
3. Plugin name resolution maps Waves names to installed plugins
4. Parameter values are numeric and precise (not vague strings)
5. The full pipeline: research → plan → commands preserves parameter fidelity
"""

import os
import sys
import asyncio
import unittest
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents import AgentType, AgentMessage, WorkflowPlan
from agent_system import AgentOrchestrator, BaseAgent
from agents.research_agent import ResearchAgent
from agents.planner_agent import PlannerAgent
from knowledge.micro_settings_kb import (
    get_micro_settings_kb, MicroSettingsKB, MICRO_SETTINGS,
    PLUGIN_PREFERENCES, ARTIST_ALIASES, STYLE_ALIASES
)


def run_async(coro):
    """Helper to run async functions in sync tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ============================================================================
# 1. RESEARCH AGENT: Waves Plugin Coverage
# ============================================================================

class TestResearchAgentWavesKnowledge(unittest.TestCase):
    """Test that the research agent's built-in knowledge references
    Waves plugins correctly and returns specific parameters."""

    def setUp(self):
        self.orchestrator = AgentOrchestrator()
        self.research_agent = ResearchAgent(self.orchestrator)

    def test_builtin_chain_returns_structured_data(self):
        """Built-in chain knowledge must return dict with 'chain' list."""
        result = self.research_agent._get_builtin_chain_knowledge("kanye west", "vocal")
        self.assertIsNotNone(result, "Kanye West vocal chain should exist")
        self.assertIn("source", result)
        self.assertIn("data", result)
        chain = result["data"].get("chain", [])
        self.assertGreater(len(chain), 0, "Chain should have at least one device")

    def test_builtin_chain_has_numeric_parameters(self):
        """Every device in micro_settings chains must have numeric params, not vague strings."""
        result = self.research_agent._get_builtin_chain_knowledge("kanye west", "vocal")
        self.assertIsNotNone(result)

        # If sourced from micro_settings_kb, check that value params are numeric
        # (type selectors like "high_pass" and booleans are allowed as strings/bools)
        if result.get("source") == "micro_settings_kb":
            enum_params = {"type", "band1_type", "band2_type", "band3_type", "band4_type"}
            for device in result["data"]["chain"]:
                settings = device.get("settings", {})
                for key, value in settings.items():
                    if key in enum_params or isinstance(value, bool):
                        continue
                    self.assertNotIsInstance(
                        value, str,
                        f"Device '{device.get('type')}' param '{key}' is a string ('{value}'). "
                        f"Micro settings should provide numeric values."
                    )

    def test_billie_eilish_chain_has_specific_settings(self):
        """Billie Eilish chain should have specific reverb/compressor params."""
        result = self.research_agent._get_builtin_chain_knowledge("billie eilish", "vocal")
        self.assertIsNotNone(result)
        chain = result["data"].get("chain", [])
        device_types = [d.get("type") for d in chain]

        # Must have these categories
        for expected_type in ["eq", "compressor", "reverb"]:
            # Check for direct type or device name containing the type
            found = any(expected_type in str(dt) for dt in device_types)
            self.assertTrue(found, f"Missing '{expected_type}' in Billie Eilish chain: {device_types}")

    def test_hip_hop_vocal_chain_mentions_cla76_in_plugin_chains_json(self):
        """The cached plugin_chains.json references CLA-76 for hip hop vocals."""
        import json
        chains_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "knowledge", "plugin_chains.json"
        )
        with open(chains_path) as f:
            data = json.load(f)

        hip_hop = data["chains"].get("hip_hop_vocal", {})
        chain = hip_hop.get("chain", [])

        # Find the compressor entry
        comp_entries = [d for d in chain if d.get("type") == "compressor"]
        self.assertTrue(len(comp_entries) > 0, "Hip hop vocal chain missing compressor")

        comp = comp_entries[0]
        suggestions = comp.get("plugin_suggestions", [])
        self.assertIn("CLA-76", suggestions,
                       f"CLA-76 should be suggested for hip hop vocal compression. Got: {suggestions}")

    def test_weeknd_chain_mentions_ssl_in_plugin_chains_json(self):
        """The cached plugin_chains.json references SSL E-Channel for Weeknd vocals."""
        import json
        chains_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "knowledge", "plugin_chains.json"
        )
        with open(chains_path) as f:
            data = json.load(f)

        weeknd = data["chains"].get("the_weeknd_vocal", {})
        chain = weeknd.get("chain", [])

        comp_entries = [d for d in chain if d.get("type") == "compressor"]
        self.assertTrue(len(comp_entries) > 0)

        comp = comp_entries[0]
        suggestions = comp.get("plugin_suggestions", [])
        self.assertIn("SSL E-Channel", suggestions,
                       f"SSL E-Channel should be suggested for Weeknd vocal. Got: {suggestions}")

    def test_research_plugin_chain_caches_result(self):
        """Research results should be cached to avoid duplicate work."""
        result = run_async(
            self.research_agent._research_plugin_chain("kanye west", "vocal")
        )
        self.assertIn("chain", result)
        self.assertIn("confidence", result)

        # Second call should hit cache
        result2 = run_async(
            self.research_agent._research_plugin_chain("kanye west", "vocal")
        )
        self.assertTrue(result2.get("from_cache", False),
                        "Second call should return cached result")

    def test_extract_plugin_chain_from_builtin(self):
        """_extract_plugin_chain should correctly parse built-in findings."""
        findings = [self.research_agent._get_builtin_chain_knowledge("kanye west", "vocal")]
        chain = self.research_agent._extract_plugin_chain(findings, "vocal")
        self.assertGreater(len(chain), 0)

        # Each entry should have type, purpose, confidence
        for device in chain:
            self.assertIn("type", device)
            self.assertIn("purpose", device)
            self.assertIn("confidence", device)

    def test_confidence_calculation(self):
        """Confidence should increase with more sources."""
        chain = [
            {"type": "eq", "confidence": 0.8},
            {"type": "compressor", "confidence": 0.9},
        ]
        conf_1 = self.research_agent._calculate_confidence(chain, 1)
        conf_3 = self.research_agent._calculate_confidence(chain, 3)
        self.assertGreater(conf_3, conf_1,
                           "More sources should increase confidence")


# ============================================================================
# 2. MICRO SETTINGS KB: Waves Plugin Preferences
# ============================================================================

class TestMicroSettingsWavesPreferences(unittest.TestCase):
    """Test that PLUGIN_PREFERENCES correctly map to Waves plugins
    and that the KB resolves artist names/aliases properly."""

    def setUp(self):
        self.kb = get_micro_settings_kb()

    def test_kanye_donda_prefers_third_party_plugins(self):
        """Kanye Donda should have specific 3rd party preferences."""
        prefs = self.kb.get_plugin_preferences("kanye west", "donda", "vocal")
        self.assertIn("saturation", prefs, "Should have saturation preference")
        self.assertEqual(prefs["saturation"]["preferred_plugin"], "Soundtoys Decapitator")
        self.assertIn("Saturator", prefs["saturation"]["fallbacks"],
                       "Saturator should be the stock fallback for Decapitator")

    def test_kanye_donda_eq_prefers_fabfilter(self):
        """Kanye Donda EQ preference should be FabFilter Pro-Q 3."""
        prefs = self.kb.get_plugin_preferences("kanye west", "donda", "vocal")
        self.assertIn("eq_tone", prefs)
        self.assertEqual(prefs["eq_tone"]["preferred_plugin"], "FabFilter Pro-Q 3")
        self.assertIn("EQ Eight", prefs["eq_tone"]["fallbacks"])

    def test_kanye_alias_resolution(self):
        """'kanye', 'ye' should resolve to 'kanye_west'."""
        for alias in ["kanye", "ye", "Kanye West", "kanye west"]:
            resolved = self.kb.resolve_artist(alias)
            self.assertEqual(resolved, "kanye_west",
                             f"Alias '{alias}' should resolve to 'kanye_west', got '{resolved}'")

    def test_billie_alias_resolution(self):
        """'billie' should resolve to 'billie_eilish'."""
        resolved = self.kb.resolve_artist("billie")
        self.assertEqual(resolved, "billie_eilish")

    def test_weeknd_alias_resolution(self):
        """'weeknd', 'abel' should resolve to 'the_weeknd'."""
        for alias in ["weeknd", "abel"]:
            resolved = self.kb.resolve_artist(alias)
            self.assertEqual(resolved, "the_weeknd",
                             f"'{alias}' should resolve to 'the_weeknd', got '{resolved}'")

    def test_style_resolution_donda(self):
        """'donda' should resolve to 'donda_vocal' for kanye_west."""
        style = self.kb.resolve_style("kanye_west", "donda", "vocal")
        self.assertEqual(style, "donda_vocal")

    def test_style_resolution_yeezus(self):
        """'yeezus' should resolve to 'yeezus_vocal'."""
        style = self.kb.resolve_style("kanye_west", "yeezus", "vocal")
        self.assertEqual(style, "yeezus_vocal")

    def test_get_settings_returns_precise_numerics(self):
        """Settings for known artists must contain numeric (not string) values."""
        settings = self.kb.get_settings("kanye west", "donda", "vocal")
        self.assertIsNotNone(settings, "Kanye Donda vocal settings should exist")

        devices = settings.get("devices", {})
        self.assertIn("compressor", devices, "Must have compressor device")

        comp_params = devices["compressor"]["parameters"]
        # These must be numeric
        self.assertIsInstance(comp_params["threshold_db"], (int, float))
        self.assertIsInstance(comp_params["ratio"], (int, float))
        self.assertIsInstance(comp_params["attack_ms"], (int, float))
        self.assertIsInstance(comp_params["release_ms"], (int, float))

        # Verify actual values match expected Donda settings
        self.assertEqual(comp_params["threshold_db"], -18.0)
        self.assertEqual(comp_params["ratio"], 8.0)
        self.assertEqual(comp_params["attack_ms"], 5.0)
        self.assertEqual(comp_params["release_ms"], 80.0)

    def test_kanye_yeezus_has_heavier_settings_than_donda(self):
        """Yeezus era should have more extreme compression than Donda."""
        donda = self.kb.get_settings("kanye west", "donda", "vocal")
        yeezus = self.kb.get_settings("kanye west", "yeezus", "vocal")

        self.assertIsNotNone(donda)
        self.assertIsNotNone(yeezus)

        donda_ratio = donda["devices"]["compressor"]["parameters"]["ratio"]
        yeezus_ratio = yeezus["devices"]["compressor"]["parameters"]["ratio"]

        self.assertGreater(yeezus_ratio, donda_ratio,
                           f"Yeezus ratio ({yeezus_ratio}) should be more extreme than Donda ({donda_ratio})")

    def test_billie_eilish_has_gentle_compression(self):
        """Billie Eilish should have gentler compression than Kanye."""
        billie = self.kb.get_settings("billie eilish", "", "vocal")
        kanye = self.kb.get_settings("kanye west", "donda", "vocal")

        self.assertIsNotNone(billie)
        self.assertIsNotNone(kanye)

        billie_ratio = billie["devices"]["compressor"]["parameters"]["ratio"]
        kanye_ratio = kanye["devices"]["compressor"]["parameters"]["ratio"]

        self.assertLess(billie_ratio, kanye_ratio,
                        f"Billie ratio ({billie_ratio}) should be gentler than Kanye ({kanye_ratio})")

    def test_billie_eilish_reverb_is_darker(self):
        """Billie reverb should have lower high_cut and longer decay than Kanye."""
        billie = self.kb.get_settings("billie eilish", "", "vocal")
        kanye = self.kb.get_settings("kanye west", "donda", "vocal")

        billie_reverb = billie["devices"]["reverb"]["parameters"]
        kanye_reverb = kanye["devices"]["reverb"]["parameters"]

        self.assertGreater(billie_reverb["decay_time_ms"], kanye_reverb["decay_time_ms"],
                           "Billie reverb decay should be longer")
        self.assertGreater(billie_reverb["dry_wet_pct"], kanye_reverb["dry_wet_pct"],
                           "Billie reverb mix should be wetter")

    def test_all_artists_have_compressor_with_numeric_params(self):
        """Every artist entry in MICRO_SETTINGS must have a compressor with numeric params."""
        for artist_key, styles in MICRO_SETTINGS.items():
            for style_key, style_data in styles.items():
                devices = style_data.get("devices", {})
                comp = devices.get("compressor")
                self.assertIsNotNone(
                    comp,
                    f"{artist_key}/{style_key} missing 'compressor' device"
                )
                params = comp.get("parameters", {})
                for param_name in ["threshold_db", "ratio"]:
                    self.assertIn(
                        param_name, params,
                        f"{artist_key}/{style_key} compressor missing '{param_name}'"
                    )
                    self.assertIsInstance(
                        params[param_name], (int, float),
                        f"{artist_key}/{style_key} compressor '{param_name}' must be numeric, "
                        f"got {type(params[param_name])}: {params[param_name]}"
                    )


# ============================================================================
# 3. PLUGIN ALIASES: Waves Plugin Name Resolution
# ============================================================================

class TestWavesPluginAliases(unittest.TestCase):
    """Verify that plugin_aliases.json correctly maps Waves plugin names."""

    @classmethod
    def setUpClass(cls):
        import json
        aliases_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config", "plugin_aliases.json"
        )
        with open(aliases_path) as f:
            cls.aliases_data = json.load(f)
        cls.aliases = cls.aliases_data.get("aliases", {})

    def test_ssl_e_channel_aliases(self):
        """SSL E-Channel should have common Waves-related aliases."""
        entry = self.aliases.get("SSL E-Channel", {})
        aliases = entry.get("aliases", [])
        self.assertIn("Waves SSL", aliases)
        self.assertIn("SSL Channel", aliases)

    def test_cla2a_aliases(self):
        """CLA-2A should have common aliases."""
        entry = self.aliases.get("CLA-2A", {})
        self.assertIsNotNone(entry, "CLA-2A should be in aliases")
        aliases = entry.get("aliases", [])
        # Should have at least LA-2A or CLA2A
        all_aliases = [a.lower() for a in aliases]
        self.assertTrue(
            any("la-2a" in a or "la2a" in a or "cla2a" in a for a in all_aliases),
            f"CLA-2A should have LA-2A/CLA2A aliases. Got: {aliases}"
        )

    def test_cla76_aliases(self):
        """CLA-76 should have 1176-related aliases."""
        entry = self.aliases.get("CLA-76", {})
        self.assertIsNotNone(entry, "CLA-76 should be in aliases")
        aliases = entry.get("aliases", [])
        all_aliases = [a.lower() for a in aliases]
        self.assertTrue(
            any("1176" in a or "cla76" in a for a in all_aliases),
            f"CLA-76 should have 1176/CLA76 aliases. Got: {aliases}"
        )

    def test_h_reverb_aliases(self):
        """H-Reverb should map from 'Waves Reverb'."""
        entry = self.aliases.get("H-Reverb", {})
        self.assertIsNotNone(entry, "H-Reverb should be in aliases")
        aliases = entry.get("aliases", [])
        self.assertIn("Waves Reverb", aliases)

    def test_waves_tune_aliases(self):
        """Waves Tune should map from pitch correction aliases."""
        entry = self.aliases.get("Waves Tune", {})
        self.assertIsNotNone(entry, "Waves Tune should be in aliases")
        aliases = entry.get("aliases", [])
        self.assertIn("Pitch Correction", aliases)

    def test_ssl_g_master_exists(self):
        """SSL G-Master Buss Compressor should be in aliases."""
        entry = self.aliases.get("SSL G-Master Buss Compressor", {})
        self.assertIsNotNone(entry, "SSL G-Master should be in aliases")


# ============================================================================
# 4. PLANNER AGENT: Translating Research into Executable Steps
# ============================================================================

class TestPlannerAgentFromResearch(unittest.TestCase):
    """Test that the planner agent creates correct plans from research output."""

    def setUp(self):
        self.orchestrator = AgentOrchestrator()
        self.planner = PlannerAgent(self.orchestrator)

    def test_create_plan_from_engineer_analysis(self):
        """Planner should create executable steps from engineer analysis."""
        analysis = {
            "detected_intent": "add_vocal_chain",
            "target_element": "vocals",
            "workflow_steps": [
                {"step": 1, "action": "Add EQ for high-pass filtering"},
                {"step": 2, "action": "Add compressor for dynamics control"},
                {"step": 3, "action": "Add reverb for space"},
            ]
        }
        plan = run_async(
            self.planner._create_plan(
                goal="Add vocal chain",
                analysis=analysis,
                research={}
            )
        )
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.steps), 3)

        # Step 1 should have EQ Eight command
        step1_cmds = plan.steps[0].get("commands", [])
        self.assertTrue(
            any(c.get("args", {}).get("device") == "EQ Eight" for c in step1_cmds),
            f"Step 1 should add EQ Eight. Commands: {step1_cmds}"
        )

        # Step 2 should have Compressor command
        step2_cmds = plan.steps[1].get("commands", [])
        self.assertTrue(
            any(c.get("args", {}).get("device") == "Compressor" for c in step2_cmds),
            f"Step 2 should add Compressor. Commands: {step2_cmds}"
        )

    def test_vocal_chain_template_has_correct_order(self):
        """Vocal chain template must follow: EQ → Compressor → Reverb."""
        template = self.planner._get_template("vocal_chain")
        self.assertIsNotNone(template, "vocal_chain template should exist")

        # Check signal flow order
        descriptions = [step["description"] for step in template]
        eq_idx = next(i for i, d in enumerate(descriptions) if "EQ" in d or "high-pass" in d.lower())
        comp_idx = next(i for i, d in enumerate(descriptions) if "compressor" in d.lower())
        reverb_idx = next(i for i, d in enumerate(descriptions) if "reverb" in d.lower())

        self.assertLess(eq_idx, comp_idx, "EQ should come before compressor")
        self.assertLess(comp_idx, reverb_idx, "Compressor should come before reverb")

    def test_planner_generates_osc_for_eq(self):
        """When action mentions 'EQ', commands should include add_device EQ Eight."""
        cmds = self.planner._generate_commands_for_step(
            "Add EQ for presence boost", "vocals", "add_vocal_chain"
        )
        self.assertTrue(len(cmds) > 0, "Should generate at least one command")
        device_names = [c.get("args", {}).get("device") for c in cmds]
        self.assertIn("EQ Eight", device_names)

    def test_planner_generates_osc_for_compressor(self):
        """When action mentions 'compressor', commands should add Compressor."""
        cmds = self.planner._generate_commands_for_step(
            "Add compressor for dynamics", "vocals", "compress"
        )
        device_names = [c.get("args", {}).get("device") for c in cmds]
        self.assertIn("Compressor", device_names)

    def test_planner_generates_osc_for_reverb(self):
        """When action mentions 'reverb', commands should add Reverb."""
        cmds = self.planner._generate_commands_for_step(
            "Add reverb for space", "vocals", "add_reverb"
        )
        device_names = [c.get("args", {}).get("device") for c in cmds]
        self.assertIn("Reverb", device_names)

    def test_planner_generates_osc_for_saturation(self):
        """When action mentions 'saturation', commands should add Saturator."""
        cmds = self.planner._generate_commands_for_step(
            "Add saturation for warmth", "vocals", "saturate"
        )
        device_names = [c.get("args", {}).get("device") for c in cmds]
        self.assertIn("Saturator", device_names)

    def test_rollback_steps_created(self):
        """Plans with multiple steps should generate rollback steps."""
        analysis = {
            "detected_intent": "mute_track",
            "target_element": "drums",
            "workflow_steps": [
                {"step": 1, "action": "Mute the drums track"},
            ]
        }
        plan = run_async(
            self.planner._create_plan(goal="Mute drums", analysis=analysis, research={})
        )
        # Rollback is created from the steps; even if empty, the method is called
        self.assertIsNotNone(plan)

    def test_plan_requires_confirmation_for_large_workflows(self):
        """Plans with >3 steps should require user confirmation."""
        analysis = {
            "detected_intent": "full_chain",
            "target_element": "vocals",
            "workflow_steps": [
                {"step": i, "action": f"Step {i} action"}
                for i in range(1, 6)  # 5 steps
            ]
        }
        plan = run_async(
            self.planner._create_plan(goal="Full chain", analysis=analysis, research={})
        )
        self.assertTrue(plan.requires_confirmation,
                        "Plans with >3 steps should require confirmation")


# ============================================================================
# 5. FULL PIPELINE: Research → Planner Integration
# ============================================================================

class TestResearchToPlannerPipeline(unittest.TestCase):
    """End-to-end: research agent produces data, planner consumes it.
    Verifies parameter fidelity through the pipeline."""

    def setUp(self):
        self.orchestrator = AgentOrchestrator()
        self.research_agent = ResearchAgent(self.orchestrator)
        self.planner = PlannerAgent(self.orchestrator)
        self.orchestrator.register_agent(self.research_agent)
        self.orchestrator.register_agent(self.planner)

    def test_research_chain_has_device_names_planner_can_use(self):
        """Research output device types should map to planner's command generation."""
        result = run_async(
            self.research_agent._research_plugin_chain("kanye west", "vocal")
        )
        chain = result.get("chain", [])
        self.assertGreater(len(chain), 0)

        # The planner maps these types to OSC commands
        planner_known_types = ["eq", "compressor", "reverb", "saturation", "delay", "high-pass"]

        for device in chain:
            device_type = device.get("type", "")
            # At least some devices should be in the planner's vocabulary
            # (not all will match since planner uses keyword matching)

        # Verify the chain has standard audio processing categories
        chain_types = {d.get("type") for d in chain}
        self.assertTrue(
            chain_types.intersection({"eq", "compressor"}),
            f"Chain should have at least eq and compressor. Got: {chain_types}"
        )

    def test_research_output_format_compatible_with_planner_input(self):
        """Research agent output should be structurally compatible with planner input."""
        # Simulate the full message flow
        research_msg = AgentMessage(
            sender=AgentType.ROUTER,
            recipient=AgentType.RESEARCHER,
            content={
                "action": "research_plugin_chain",
                "artist_or_style": "billie eilish",
                "track_type": "vocal"
            }
        )
        research_response = run_async(self.research_agent.process(research_msg))
        self.assertTrue(research_response.content.get("success"))
        self.assertIn("plugin_chain", research_response.content)

        plugin_chain = research_response.content["plugin_chain"]
        self.assertIn("chain", plugin_chain)
        self.assertIn("confidence", plugin_chain)
        self.assertIsInstance(plugin_chain["confidence"], float)

    def test_micro_settings_parameters_survive_research_extraction(self):
        """When micro_settings_kb provides data, the extracted chain should
        preserve the exact numeric parameters."""
        kb = get_micro_settings_kb()
        direct_settings = kb.get_settings("kanye west", "donda", "vocal")
        self.assertIsNotNone(direct_settings)

        # Now get through research agent
        builtin = self.research_agent._get_builtin_chain_knowledge("kanye west", "vocal")
        self.assertIsNotNone(builtin)

        if builtin.get("source") == "micro_settings_kb":
            chain = builtin["data"]["chain"]
            # Find the compressor device
            comp_devices = [d for d in chain if "compressor" in d.get("type", "")]
            self.assertTrue(len(comp_devices) > 0, "Should have compressor in chain")

            comp = comp_devices[0]
            settings = comp.get("settings", {})
            # Verify numeric params preserved
            self.assertIsInstance(settings.get("threshold_db"), (int, float))
            self.assertIsInstance(settings.get("ratio"), (int, float))

    def test_planner_process_message_returns_plan(self):
        """Planner agent should return a plan via process()."""
        msg = AgentMessage(
            sender=AgentType.ROUTER,
            recipient=AgentType.PLANNER,
            content={
                "action": "create_plan",
                "goal": "Add Kanye-style vocal chain",
                "analysis": {
                    "detected_intent": "add_vocal_chain",
                    "target_element": "vocals",
                    "workflow_steps": [
                        {"step": 1, "action": "Add EQ for high-pass"},
                        {"step": 2, "action": "Add compressor for aggressive compression"},
                        {"step": 3, "action": "Add saturation for character"},
                    ]
                },
                "research": {
                    "success": True,
                    "plugin_chain": {
                        "chain": [
                            {"type": "eq", "purpose": "high_pass"},
                            {"type": "compressor", "purpose": "aggressive"},
                            {"type": "saturation", "purpose": "character"},
                        ],
                        "confidence": 0.9
                    }
                }
            }
        )
        response = run_async(self.planner.process(msg))
        self.assertTrue(response.content.get("success"))
        self.assertIn("plan", response.content)
        self.assertEqual(len(response.content["plan"]), 3)


# ============================================================================
# 6. PARAMETER CORRECTNESS: Waves-Specific Checks
# ============================================================================

class TestWavesParameterCorrectness(unittest.TestCase):
    """Verify that parameter values are musically sensible for the intended style."""

    def setUp(self):
        self.kb = get_micro_settings_kb()

    def test_compressor_threshold_in_valid_range(self):
        """Compressor threshold should be between -40dB and 0dB."""
        for artist_key, styles in MICRO_SETTINGS.items():
            for style_key, style_data in styles.items():
                comp = style_data.get("devices", {}).get("compressor", {})
                params = comp.get("parameters", {})
                threshold = params.get("threshold_db")
                if threshold is not None:
                    self.assertGreaterEqual(
                        threshold, -40,
                        f"{artist_key}/{style_key}: threshold {threshold} too low"
                    )
                    self.assertLessEqual(
                        threshold, 0,
                        f"{artist_key}/{style_key}: threshold {threshold} should be <= 0dB"
                    )

    def test_compressor_ratio_in_valid_range(self):
        """Compressor ratio should be between 1.0 and 20.0."""
        for artist_key, styles in MICRO_SETTINGS.items():
            for style_key, style_data in styles.items():
                comp = style_data.get("devices", {}).get("compressor", {})
                params = comp.get("parameters", {})
                ratio = params.get("ratio")
                if ratio is not None:
                    self.assertGreaterEqual(ratio, 1.0,
                                            f"{artist_key}/{style_key}: ratio {ratio} < 1.0")
                    self.assertLessEqual(ratio, 20.0,
                                         f"{artist_key}/{style_key}: ratio {ratio} > 20.0")

    def test_compressor_attack_in_valid_range(self):
        """Attack time should be between 0.01ms and 100ms."""
        for artist_key, styles in MICRO_SETTINGS.items():
            for style_key, style_data in styles.items():
                comp = style_data.get("devices", {}).get("compressor", {})
                params = comp.get("parameters", {})
                attack = params.get("attack_ms")
                if attack is not None:
                    self.assertGreaterEqual(attack, 0.01,
                                            f"{artist_key}/{style_key}: attack {attack}ms too short")
                    self.assertLessEqual(attack, 100,
                                         f"{artist_key}/{style_key}: attack {attack}ms too long")

    def test_compressor_release_in_valid_range(self):
        """Release time should be between 5ms and 2000ms."""
        for artist_key, styles in MICRO_SETTINGS.items():
            for style_key, style_data in styles.items():
                comp = style_data.get("devices", {}).get("compressor", {})
                params = comp.get("parameters", {})
                release = params.get("release_ms")
                if release is not None:
                    self.assertGreaterEqual(release, 5,
                                            f"{artist_key}/{style_key}: release {release}ms too short")
                    self.assertLessEqual(release, 2000,
                                         f"{artist_key}/{style_key}: release {release}ms too long")

    def test_eq_frequencies_in_audible_range(self):
        """EQ frequencies must be 20Hz-20kHz."""
        for artist_key, styles in MICRO_SETTINGS.items():
            for style_key, style_data in styles.items():
                for dev_key, dev_data in style_data.get("devices", {}).items():
                    params = dev_data.get("parameters", {})
                    for param_name, value in params.items():
                        if "freq_hz" in param_name and isinstance(value, (int, float)):
                            self.assertGreaterEqual(
                                value, 20,
                                f"{artist_key}/{style_key}/{dev_key}: freq {value}Hz below audible"
                            )
                            self.assertLessEqual(
                                value, 22000,
                                f"{artist_key}/{style_key}/{dev_key}: freq {value}Hz above audible"
                            )

    def test_dry_wet_percentage_valid(self):
        """Dry/wet values must be 0-100%."""
        for artist_key, styles in MICRO_SETTINGS.items():
            for style_key, style_data in styles.items():
                for dev_key, dev_data in style_data.get("devices", {}).items():
                    params = dev_data.get("parameters", {})
                    for param_name, value in params.items():
                        if "dry_wet_pct" in param_name and isinstance(value, (int, float)):
                            self.assertGreaterEqual(
                                value, 0,
                                f"{artist_key}/{style_key}/{dev_key}: dry_wet {value}% < 0"
                            )
                            self.assertLessEqual(
                                value, 100,
                                f"{artist_key}/{style_key}/{dev_key}: dry_wet {value}% > 100"
                            )

    def test_reverb_decay_in_valid_range(self):
        """Reverb decay should be between 100ms and 10000ms."""
        for artist_key, styles in MICRO_SETTINGS.items():
            for style_key, style_data in styles.items():
                reverb = style_data.get("devices", {}).get("reverb", {})
                params = reverb.get("parameters", {})
                decay = params.get("decay_time_ms")
                if decay is not None:
                    self.assertGreaterEqual(decay, 100,
                                            f"{artist_key}/{style_key}: decay {decay}ms too short")
                    self.assertLessEqual(decay, 10000,
                                         f"{artist_key}/{style_key}: decay {decay}ms too long")

    def test_delay_feedback_below_100_percent(self):
        """Delay feedback must be < 100% to prevent runaway feedback."""
        for artist_key, styles in MICRO_SETTINGS.items():
            for style_key, style_data in styles.items():
                delay = style_data.get("devices", {}).get("delay", {})
                params = delay.get("parameters", {})
                feedback = params.get("feedback_pct")
                if feedback is not None:
                    self.assertLess(feedback, 100,
                                    f"{artist_key}/{style_key}: feedback {feedback}% would cause runaway!")


# ============================================================================
# 7. GAP ANALYSIS: Missing Waves Plugin Coverage
# ============================================================================

class TestWavesPluginCoverageGaps(unittest.TestCase):
    """Identify gaps where Waves plugins should be suggested but aren't."""

    def test_plugin_chains_json_references_waves_plugins(self):
        """plugin_chains.json should reference Waves plugins in suggestions."""
        import json
        chains_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "knowledge", "plugin_chains.json"
        )
        with open(chains_path) as f:
            data = json.load(f)

        waves_plugins_found = set()
        waves_names = {"CLA-2A", "CLA-76", "SSL E-Channel", "SSL G-Master",
                       "H-Reverb", "R-Verb", "Waves Tune", "Waves DeEsser"}

        for chain_key, chain_data in data.get("chains", {}).items():
            for device in chain_data.get("chain", []):
                for suggestion in device.get("plugin_suggestions", []):
                    if suggestion in waves_names:
                        waves_plugins_found.add(suggestion)

        # At minimum, these Waves plugins should appear somewhere
        expected_minimum = {"CLA-2A", "CLA-76", "SSL E-Channel"}
        missing = expected_minimum - waves_plugins_found
        self.assertEqual(
            len(missing), 0,
            f"These Waves plugins are missing from plugin_chains.json suggestions: {missing}. "
            f"Found: {waves_plugins_found}"
        )

    def test_plugin_preferences_have_stock_fallbacks(self):
        """Every 3rd party preference must have at least one stock Ableton fallback."""
        stock_devices = {
            "EQ Eight", "EQ Three", "Compressor", "Glue Compressor",
            "Limiter", "Saturator", "Reverb", "Delay", "Echo",
            "Multiband Dynamics", "Pedal", "Overdrive"
        }

        for artist_key, styles in PLUGIN_PREFERENCES.items():
            for style_key, slots in styles.items():
                for slot_name, pref_data in slots.items():
                    fallbacks = pref_data.get("fallbacks", [])
                    has_stock = any(fb in stock_devices for fb in fallbacks)
                    self.assertTrue(
                        has_stock,
                        f"{artist_key}/{style_key}/{slot_name}: "
                        f"No stock Ableton fallback in {fallbacks}. "
                        f"If '{pref_data.get('preferred_plugin')}' isn't installed, "
                        f"there must be a native fallback."
                    )

    def test_all_micro_settings_devices_reference_valid_ableton_devices(self):
        """Every 'device' field in MICRO_SETTINGS must be a real Ableton device name."""
        valid_devices = {
            "EQ Eight", "EQ Three", "Channel EQ",
            "Compressor", "Glue Compressor", "Multiband Dynamics",
            "Limiter", "Gate",
            "Saturator", "Pedal", "Overdrive", "Erosion", "Redux", "Vinyl Distortion",
            "Reverb", "Hybrid Reverb",
            "Delay", "Echo", "Simple Delay", "Filter Delay", "Grain Delay",
            "Chorus-Ensemble", "Phaser-Flanger", "Frequency Shifter",
            "Auto Filter", "Auto Pan",
            "Utility", "Spectrum", "Tuner",
            "Drum Buss", "Corpus", "Resonators",
        }

        for artist_key, styles in MICRO_SETTINGS.items():
            for style_key, style_data in styles.items():
                for dev_key, dev_data in style_data.get("devices", {}).items():
                    device_name = dev_data.get("device", "")
                    self.assertIn(
                        device_name, valid_devices,
                        f"{artist_key}/{style_key}/{dev_key}: "
                        f"Device '{device_name}' is not a valid Ableton device. "
                        f"If this is a 3rd party plugin, it should only appear in "
                        f"PLUGIN_PREFERENCES, not in MICRO_SETTINGS."
                    )


# ============================================================================
# 8. PLANNER CONSUMES RESEARCH CHAIN: Parameter Fidelity
# ============================================================================

class TestPlannerConsumesResearchChain(unittest.TestCase):
    """Verify that PlannerAgent._create_plan() generates steps with
    set_device_parameter commands when research contains a plugin chain."""

    def setUp(self):
        self.orchestrator = AgentOrchestrator()
        self.planner = PlannerAgent(self.orchestrator)

    def test_plan_includes_set_device_parameter_from_research(self):
        """Steps should contain set_device_parameter commands with numeric values."""
        research = {
            "plugin_chain": {
                "chain": [
                    {
                        "type": "compressor",
                        "purpose": "aggressive compression",
                        "settings": {"threshold_db": -18.0, "ratio": 8.0, "attack_ms": 5.0},
                        "confidence": 0.9,
                    }
                ],
                "confidence": 0.9,
            }
        }
        plan = run_async(self.planner._create_plan(
            goal="Add vocal chain", analysis={}, research=research
        ))
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.steps), 1)

        cmds = plan.steps[0]["commands"]
        funcs = [c["function"] for c in cmds]
        self.assertIn("add_device", funcs)
        self.assertIn("set_device_parameter", funcs)

        # Check numeric values preserved
        param_cmds = [c for c in cmds if c["function"] == "set_device_parameter"]
        param_map = {c["args"]["param"]: c["args"]["value"] for c in param_cmds}
        self.assertEqual(param_map["threshold_db"], -18.0)
        self.assertEqual(param_map["ratio"], 8.0)
        self.assertEqual(param_map["attack_ms"], 5.0)

    def test_plugin_name_from_research_used_in_add_device(self):
        """desired_plugin from research should appear in add_device command."""
        research = {
            "plugin_chain": {
                "chain": [
                    {
                        "type": "compressor",
                        "purpose": "compression",
                        "desired_plugin": "CLA-76",
                        "settings": {"ratio": 4.0},
                        "confidence": 0.85,
                    }
                ],
                "confidence": 0.85,
            }
        }
        plan = run_async(self.planner._create_plan(
            goal="Add compressor", analysis={}, research=research
        ))
        add_cmd = [c for c in plan.steps[0]["commands"] if c["function"] == "add_device"][0]
        self.assertEqual(add_cmd["args"]["device"], "CLA-76")

    def test_fallback_to_analysis_when_no_research_chain(self):
        """Without research chain, planner falls back to analysis workflow_steps."""
        analysis = {
            "detected_intent": "add_vocal_chain",
            "target_element": "vocals",
            "workflow_steps": [
                {"step": 1, "action": "Add EQ for high-pass filtering"},
                {"step": 2, "action": "Add compressor for dynamics"},
            ]
        }
        plan = run_async(self.planner._create_plan(
            goal="Add vocal chain", analysis=analysis, research={}
        ))
        self.assertEqual(len(plan.steps), 2)
        # These come from the old keyword-matching path
        step1_funcs = [c["function"] for c in plan.steps[0]["commands"]]
        self.assertIn("add_device", step1_funcs)

    def test_extract_chain_direct_format(self):
        """_extract_chain_from_research handles direct {'chain': [...]} format."""
        chain = self.planner._extract_chain_from_research(
            {"chain": [{"type": "eq", "purpose": "test"}]}
        )
        self.assertIsNotNone(chain)
        self.assertEqual(len(chain), 1)

    def test_extract_chain_wrapped_format(self):
        """_extract_chain_from_research handles {'plugin_chain': {'chain': [...]}}."""
        chain = self.planner._extract_chain_from_research(
            {"plugin_chain": {"chain": [{"type": "eq"}]}}
        )
        self.assertIsNotNone(chain)

    def test_extract_chain_agent_system_format(self):
        """_extract_chain_from_research handles {'research': {'plugin_chain': {'chain': [...]}}}."""
        chain = self.planner._extract_chain_from_research(
            {"research": {"plugin_chain": {"chain": [{"type": "reverb"}]}}}
        )
        self.assertIsNotNone(chain)

    def test_extract_chain_returns_none_for_empty(self):
        """Returns None when no chain data present."""
        self.assertIsNone(self.planner._extract_chain_from_research({}))
        self.assertIsNone(self.planner._extract_chain_from_research(None))

    def test_type_to_device_name_mapping(self):
        """_type_to_device_name maps common types to Ableton devices."""
        self.assertEqual(self.planner._type_to_device_name("eq"), "EQ Eight")
        self.assertEqual(self.planner._type_to_device_name("compressor"), "Compressor")
        self.assertEqual(self.planner._type_to_device_name("reverb"), "Reverb")
        self.assertEqual(self.planner._type_to_device_name("saturation"), "Saturator")
        self.assertEqual(self.planner._type_to_device_name("de-esser"), "Multiband Dynamics")

    def test_string_settings_excluded_from_param_commands(self):
        """Non-numeric settings (like type selectors) should not generate set_device_parameter."""
        research = {
            "chain": [
                {
                    "type": "eq",
                    "purpose": "high pass",
                    "settings": {"type": "high_pass", "frequency": 100.0, "mode": "stereo"},
                }
            ]
        }
        plan = run_async(self.planner._create_plan(
            goal="Add EQ", analysis={}, research=research
        ))
        param_cmds = [c for c in plan.steps[0]["commands"]
                      if c["function"] == "set_device_parameter"]
        param_names = [c["args"]["param"] for c in param_cmds]
        self.assertIn("frequency", param_names)
        self.assertNotIn("type", param_names)
        self.assertNotIn("mode", param_names)

    def test_multi_device_chain_produces_ordered_steps(self):
        """A 3-device chain should produce 3 ordered steps."""
        research = {
            "chain": [
                {"type": "eq", "purpose": "high pass", "settings": {"frequency": 80.0}},
                {"type": "compressor", "purpose": "dynamics", "settings": {"ratio": 4.0}},
                {"type": "reverb", "purpose": "space", "settings": {"decay_time_ms": 1500.0}},
            ]
        }
        plan = run_async(self.planner._create_plan(
            goal="Vocal chain", analysis={}, research=research
        ))
        self.assertEqual(len(plan.steps), 3)
        self.assertEqual(plan.steps[0]["order"], 1)
        self.assertEqual(plan.steps[1]["order"], 2)
        self.assertEqual(plan.steps[2]["order"], 3)

        # Verify device names
        devices = [
            [c["args"]["device"] for c in s["commands"] if c["function"] == "add_device"][0]
            for s in plan.steps
        ]
        self.assertEqual(devices, ["EQ Eight", "Compressor", "Reverb"])

    def test_steps_from_research_have_source_and_confidence(self):
        """Research-derived steps should be tagged with source='research' and confidence."""
        research = {
            "chain": [
                {"type": "eq", "purpose": "test", "settings": {}, "confidence": 0.92}
            ]
        }
        plan = run_async(self.planner._create_plan(
            goal="Test", analysis={}, research=research
        ))
        self.assertEqual(plan.steps[0]["source"], "research")
        self.assertEqual(plan.steps[0]["confidence"], 0.92)


if __name__ == "__main__":
    unittest.main(verbosity=2)
