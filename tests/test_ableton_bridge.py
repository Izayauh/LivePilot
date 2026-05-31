#!/usr/bin/env python3
"""
Smoke tests for ableton_bridge.py

Validates:
- Script compiles without errors
- --list produces valid JSON with expected functions
- No google.genai / LLM imports in the bridge source
- Dispatch table covers all expected function names
"""

import json
import os
import subprocess
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BRIDGE_PATH = os.path.join(_REPO_ROOT, "ableton_bridge.py")


class TestAbletonBridgeCompile(unittest.TestCase):
    """Verify the bridge script compiles without syntax errors."""

    def test_py_compile(self):
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", _BRIDGE_PATH],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0,
                         f"py_compile failed:\n{result.stderr}")


class TestAbletonBridgeList(unittest.TestCase):
    """Verify --list returns well-formed JSON with the expected functions."""

    @classmethod
    def setUpClass(cls):
        result = subprocess.run(
            [sys.executable, _BRIDGE_PATH, "--list"],
            capture_output=True, text=True, timeout=15,
        )
        cls.returncode = result.returncode
        cls.stdout = result.stdout
        cls.stderr = result.stderr

    def test_exit_code_zero(self):
        self.assertEqual(self.returncode, 0,
                         f"--list returned exit code {self.returncode}\n{self.stderr}")

    def test_valid_json(self):
        data = json.loads(self.stdout)
        self.assertIn("functions", data)
        self.assertIsInstance(data["functions"], list)

    def test_expected_functions_present(self):
        data = json.loads(self.stdout)
        functions = set(data["functions"])

        expected = {
            # Playback
            "play", "stop", "continue_playback",
            "start_recording", "stop_recording", "toggle_metronome",
            # Transport
            "set_tempo", "set_position", "set_loop",
            "set_loop_start", "set_loop_length",
            # Track controls
            "mute_track", "solo_track", "arm_track",
            "set_track_volume", "set_track_pan", "set_track_send",
            # Track queries
            "get_track_list", "get_track_mute", "get_track_solo",
            "get_track_arm", "get_track_status", "get_armed_tracks",
            "find_track_by_name",
            # Track management
            "create_audio_track", "create_midi_track", "create_return_track",
            "delete_track", "delete_return_track", "duplicate_track",
            "set_track_name", "set_track_color",
            # Scene / clip
            "fire_scene", "fire_clip", "stop_clip",
            "set_clip_path", "get_clip_audio_path", "set_clip_detune",
            # Device queries
            "get_num_devices", "get_track_devices", "get_device_name",
            "get_device_class_name", "get_device_parameters",
            "get_device_parameter_value", "get_device_parameter_value_string",
            "get_device_tree", "get_all_device_trees", "get_device_params_by_path",
            # Device control
            "set_device_parameter", "set_device_parameter_by_name",
            "set_device_parameters_by_name",
            "set_device_enabled", "delete_device", "add_utility_device",
            # Plugin management
            "add_plugin_to_track", "get_available_plugins",
            "find_plugin", "refresh_plugin_list",
            # Plugin recipes
            "list_plugin_recipes", "save_plugin_recipe", "apply_plugin_recipe",
            # Creative context
            "get_creative_context", "get_project_intent", "set_project_intent",
            "plan_arrangement_move",
        }

        missing = expected - functions
        self.assertFalse(missing,
                         f"Missing functions in --list output: {sorted(missing)}")

    def test_no_unexpected_agent_functions(self):
        """Agent-dependent functions should NOT be in the bridge."""
        data = json.loads(self.stdout)
        functions = set(data["functions"])

        forbidden = {
            "create_plugin_chain", "load_preset_chain",
            "consult_audio_engineer", "suggest_device_settings",
            "apply_audio_intent", "explain_adjustment",
            "research_vocal_chain", "execute_macro", "list_macros",
        }
        leaked = forbidden & functions
        self.assertFalse(leaked,
                         f"Agent-dependent functions leaked into bridge: {sorted(leaked)}")


class TestNoGeminiImports(unittest.TestCase):
    """Ensure the bridge has zero LLM / Gemini dependencies."""

    def test_no_google_genai_in_source(self):
        with open(_BRIDGE_PATH, "r") as f:
            source = f.read()

        banned = ["google.genai", "google.generativeai", "genai", "openai",
                   "import gemini", "from gemini"]
        for term in banned:
            self.assertNotIn(term, source,
                             f"Found banned import '{term}' in ableton_bridge.py")


class TestDispatchTableCoverage(unittest.TestCase):
    """Verify dispatch table via direct import (avoids OSC connection issues)."""

    def test_dispatch_keys_match_list(self):
        # Import the module to access list_functions()
        sys.path.insert(0, _REPO_ROOT)
        import ableton_bridge
        fn_list = ableton_bridge.list_functions()
        dispatch_keys = sorted(ableton_bridge._build_dispatch({}).keys())
        self.assertEqual(fn_list, dispatch_keys,
                         "list_functions() and _build_dispatch() keys diverge")


class TestCLIErrorHandling(unittest.TestCase):
    """Verify the bridge handles bad inputs gracefully."""

    def test_no_args_prints_usage(self):
        result = subprocess.run(
            [sys.executable, _BRIDGE_PATH],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 1)
        data = json.loads(result.stdout)
        self.assertIn("error", data)

    def test_unknown_function(self):
        result = subprocess.run(
            [sys.executable, _BRIDGE_PATH, "nonexistent_func", "{}"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 1)
        data = json.loads(result.stdout)
        self.assertIn("error", data)
        self.assertIn("Unknown function", data["error"])

    def test_invalid_json_args(self):
        result = subprocess.run(
            [sys.executable, _BRIDGE_PATH, "play", "not-json"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 1)
        data = json.loads(result.stdout)
        self.assertIn("error", data)

    def test_missing_track_index(self):
        result = subprocess.run(
            [sys.executable, _BRIDGE_PATH, "mute_track", "{}"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 1)
        data = json.loads(result.stdout)
        self.assertIn("error", data)
        self.assertIn("track_index", data["error"])


if __name__ == "__main__":
    unittest.main()
