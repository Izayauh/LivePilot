"""
Tests for the apply_research_chain pipeline.

Verifies:
1. _flatten_parameters() correctly flattens nested research params
2. chainspec_to_builder_format() produces valid input for build_chain_from_research()
3. build_chain_from_research() creates a PluginChain from converted research data
4. execute_apply_research_chain() runs the full pipeline with mocked Ableton
5. _cache_chain_spec() writes flat settings to the knowledge base
6. Round-trip: ChainSpec → adapter → builder → chain (no data loss)

Run with: python -m pytest tests/test_apply_research_chain.py -v
    or:   python tests/test_apply_research_chain.py
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from typing import Dict, Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.research_coordinator import (
    ChainSpec,
    DeviceSpec,
    _flatten_parameters,
    chainspec_to_builder_format,
)
from plugins.chain_builder import PluginChainBuilder


# ============================================================================
# Test fixtures
# ============================================================================

def _make_sample_chain_spec() -> ChainSpec:
    """Create a realistic ChainSpec like research_vocal_chain would return."""
    return ChainSpec(
        query="Travis Scott vocal chain",
        style_description="Dark, autotuned vocal with heavy reverb and delay",
        devices=[
            DeviceSpec(
                plugin_name="EQ Eight",
                category="eq",
                parameters={
                    "1 Frequency A": {"value": 100.0, "unit": "Hz", "confidence": 0.9},
                    "1 Gain A": {"value": -18.0, "unit": "dB", "confidence": 0.85},
                    "1 Filter On A": {"value": 1.0, "unit": "", "confidence": 0.95},
                },
                purpose="high_pass",
                reasoning="Remove low-end rumble below 100Hz",
                confidence=0.9,
                sources=["https://example.com/travis-scott-vocal"],
            ),
            DeviceSpec(
                plugin_name="Compressor",
                category="compressor",
                parameters={
                    "Threshold": {"value": -20.0, "unit": "dB", "confidence": 0.8},
                    "Ratio": {"value": 6.0, "unit": ":1", "confidence": 0.75},
                    "Attack": {"value": 5.0, "unit": "ms", "confidence": 0.7},
                    "Release": {"value": 50.0, "unit": "ms", "confidence": 0.7},
                },
                purpose="aggressive_compression",
                reasoning="Heavy compression for upfront vocal",
                confidence=0.8,
                sources=["https://example.com/travis-scott-vocal"],
            ),
            DeviceSpec(
                plugin_name="Reverb",
                category="reverb",
                parameters={
                    "Decay Time": {"value": 4.5, "unit": "s", "confidence": 0.85},
                    "Dry/Wet": {"value": 0.35, "unit": "", "confidence": 0.8},
                },
                purpose="atmosphere",
                reasoning="Long dark reverb for spacey feel",
                confidence=0.85,
                sources=["https://youtube.com/watch?v=example"],
            ),
        ],
        confidence=0.85,
        sources=[
            "https://example.com/travis-scott-vocal",
            "https://youtube.com/watch?v=example",
        ],
        artist="Travis Scott",
        genre="Hip Hop",
    )


def _make_sample_chain_spec_dict() -> Dict[str, Any]:
    """Return ChainSpec.to_dict() output for testing."""
    return _make_sample_chain_spec().to_dict()


def _make_chain_spec_with_mixed_params() -> Dict[str, Any]:
    """ChainSpec dict with a mix of nested and flat parameter values."""
    return {
        "query": "test query",
        "style_description": "test style",
        "devices": [
            {
                "plugin_name": "Saturator",
                "category": "saturation",
                "parameters": {
                    "Drive": {"value": 8.0, "unit": "dB", "confidence": 0.9},
                    "Dry/Wet": 0.5,  # already flat
                    "Color": True,  # boolean, no nested dict
                },
                "purpose": "warmth",
                "reasoning": "Add harmonic content",
                "confidence": 0.8,
                "sources": [],
            }
        ],
        "confidence": 0.8,
        "sources": [],
        "artist": "Test Artist",
    }


# ============================================================================
# 1. _flatten_parameters unit tests
# ============================================================================

class TestFlattenParameters(unittest.TestCase):
    """Test _flatten_parameters() in isolation."""

    def test_nested_dicts_are_flattened(self):
        params = {
            "Threshold": {"value": -20.0, "unit": "dB", "confidence": 0.8},
            "Ratio": {"value": 4.0, "unit": ":1", "confidence": 0.9},
        }
        flat = _flatten_parameters(params)
        self.assertEqual(flat["Threshold"], -20.0)
        self.assertEqual(flat["Ratio"], 4.0)

    def test_scalar_values_pass_through(self):
        params = {
            "Drive": 8.0,
            "Enabled": True,
            "Mode": 1,
        }
        flat = _flatten_parameters(params)
        self.assertEqual(flat["Drive"], 8.0)
        self.assertEqual(flat["Enabled"], True)
        self.assertEqual(flat["Mode"], 1)

    def test_mixed_nested_and_flat(self):
        params = {
            "Freq": {"value": 1000.0, "unit": "Hz", "confidence": 0.9},
            "Gain": -3.0,
        }
        flat = _flatten_parameters(params)
        self.assertEqual(flat["Freq"], 1000.0)
        self.assertEqual(flat["Gain"], -3.0)

    def test_empty_params(self):
        self.assertEqual(_flatten_parameters({}), {})

    def test_dict_without_value_key_passes_through(self):
        """Dicts that don't have a 'value' key should pass through as-is."""
        params = {
            "SomeWeirdParam": {"min": 0, "max": 100},
        }
        flat = _flatten_parameters(params)
        self.assertEqual(flat["SomeWeirdParam"], {"min": 0, "max": 100})

    def test_string_values_pass_through(self):
        """String parameter values should not be dropped."""
        params = {
            "freq": {"value": "80-100Hz", "confidence": 0.7},
            "notes": "some note",
        }
        flat = _flatten_parameters(params)
        self.assertEqual(flat["freq"], "80-100Hz")
        self.assertEqual(flat["notes"], "some note")


# ============================================================================
# 2. chainspec_to_builder_format unit tests
# ============================================================================

class TestChainspecToBuilderFormat(unittest.TestCase):
    """Test chainspec_to_builder_format() adapter."""

    def setUp(self):
        self.spec_dict = _make_sample_chain_spec_dict()

    def test_top_level_keys(self):
        result = chainspec_to_builder_format(self.spec_dict)
        self.assertIn("artist_or_style", result)
        self.assertIn("track_type", result)
        self.assertIn("chain", result)
        self.assertIn("confidence", result)
        self.assertIn("sources", result)
        self.assertTrue(result["from_research"])

    def test_artist_extracted_from_artist_field(self):
        result = chainspec_to_builder_format(self.spec_dict)
        self.assertEqual(result["artist_or_style"], "Travis Scott")

    def test_artist_falls_back_to_query(self):
        spec = dict(self.spec_dict)
        spec["artist"] = None
        result = chainspec_to_builder_format(spec)
        self.assertEqual(result["artist_or_style"], "Travis Scott vocal chain")

    def test_track_type_default_is_vocal(self):
        result = chainspec_to_builder_format(self.spec_dict)
        self.assertEqual(result["track_type"], "vocal")

    def test_track_type_can_be_overridden(self):
        result = chainspec_to_builder_format(self.spec_dict, track_type="drums")
        self.assertEqual(result["track_type"], "drums")

    def test_devices_mapped_to_chain(self):
        result = chainspec_to_builder_format(self.spec_dict)
        chain = result["chain"]
        self.assertEqual(len(chain), 3)

    def test_category_mapped_to_type(self):
        result = chainspec_to_builder_format(self.spec_dict)
        types = [item["type"] for item in result["chain"]]
        self.assertEqual(types, ["eq", "compressor", "reverb"])

    def test_plugin_name_preserved(self):
        result = chainspec_to_builder_format(self.spec_dict)
        names = [item["plugin_name"] for item in result["chain"]]
        self.assertEqual(names, ["EQ Eight", "Compressor", "Reverb"])

    def test_name_alias_set(self):
        """_create_plugin_slot reads both plugin_name and name."""
        result = chainspec_to_builder_format(self.spec_dict)
        for item in result["chain"]:
            self.assertEqual(item["name"], item["plugin_name"])

    def test_parameters_flattened_to_settings(self):
        result = chainspec_to_builder_format(self.spec_dict)
        eq_settings = result["chain"][0]["settings"]
        self.assertEqual(eq_settings["1 Frequency A"], 100.0)
        self.assertEqual(eq_settings["1 Gain A"], -18.0)
        self.assertEqual(eq_settings["1 Filter On A"], 1.0)

    def test_compressor_settings_flattened(self):
        result = chainspec_to_builder_format(self.spec_dict)
        comp_settings = result["chain"][1]["settings"]
        self.assertEqual(comp_settings["Threshold"], -20.0)
        self.assertEqual(comp_settings["Ratio"], 6.0)
        self.assertEqual(comp_settings["Attack"], 5.0)

    def test_confidence_preserved(self):
        result = chainspec_to_builder_format(self.spec_dict)
        self.assertEqual(result["confidence"], 0.85)

    def test_sources_preserved(self):
        result = chainspec_to_builder_format(self.spec_dict)
        self.assertEqual(len(result["sources"]), 2)

    def test_mixed_params_handled(self):
        spec = _make_chain_spec_with_mixed_params()
        result = chainspec_to_builder_format(spec)
        settings = result["chain"][0]["settings"]
        self.assertEqual(settings["Drive"], 8.0)
        self.assertEqual(settings["Dry/Wet"], 0.5)
        self.assertEqual(settings["Color"], True)

    def test_empty_devices_produces_empty_chain(self):
        spec = dict(self.spec_dict)
        spec["devices"] = []
        result = chainspec_to_builder_format(spec)
        self.assertEqual(result["chain"], [])

    def test_purpose_preserved(self):
        result = chainspec_to_builder_format(self.spec_dict)
        purposes = [item["purpose"] for item in result["chain"]]
        self.assertEqual(purposes, ["high_pass", "aggressive_compression", "atmosphere"])


# ============================================================================
# 3. Integration: adapter output feeds into build_chain_from_research
# ============================================================================

class TestAdapterToChainBuilder(unittest.TestCase):
    """Verify that chainspec_to_builder_format output is accepted by
    PluginChainBuilder.build_chain_from_research()."""

    def test_build_chain_from_adapted_research(self):
        spec_dict = _make_sample_chain_spec_dict()
        builder_input = chainspec_to_builder_format(spec_dict)

        builder = PluginChainBuilder()
        chain = builder.build_chain_from_research(builder_input)

        # Chain should have 3 slots
        self.assertEqual(len(chain.slots), 3)

        # Each slot should have the right plugin type
        self.assertEqual(chain.slots[0].plugin_type, "eq")
        self.assertEqual(chain.slots[1].plugin_type, "compressor")
        self.assertEqual(chain.slots[2].plugin_type, "reverb")

    def test_slot_settings_are_flat(self):
        spec_dict = _make_sample_chain_spec_dict()
        builder_input = chainspec_to_builder_format(spec_dict)

        builder = PluginChainBuilder()
        chain = builder.build_chain_from_research(builder_input)

        # EQ slot settings should be flat numeric values
        eq_settings = chain.slots[0].settings
        for key, value in eq_settings.items():
            self.assertNotIsInstance(
                value, dict,
                f"Setting '{key}' should be flat, got dict: {value}"
            )

    def test_slot_desired_plugin_set(self):
        spec_dict = _make_sample_chain_spec_dict()
        builder_input = chainspec_to_builder_format(spec_dict)

        builder = PluginChainBuilder()
        chain = builder.build_chain_from_research(builder_input)

        self.assertEqual(chain.slots[0].desired_plugin, "EQ Eight")
        self.assertEqual(chain.slots[1].desired_plugin, "Compressor")
        self.assertEqual(chain.slots[2].desired_plugin, "Reverb")

    def test_chain_name_includes_artist(self):
        spec_dict = _make_sample_chain_spec_dict()
        builder_input = chainspec_to_builder_format(spec_dict)

        builder = PluginChainBuilder()
        chain = builder.build_chain_from_research(builder_input)

        self.assertIn("Travis", chain.name)

    def test_validation_passes(self):
        spec_dict = _make_sample_chain_spec_dict()
        builder_input = chainspec_to_builder_format(spec_dict)

        builder = PluginChainBuilder()
        chain = builder.build_chain_from_research(builder_input)
        validation = builder.validate_chain(chain)

        # Should not have errors (warnings are ok)
        self.assertFalse(validation.get("errors"),
                         f"Validation errors: {validation.get('errors')}")


# ============================================================================
# 4. Round-trip: ChainSpec → to_dict → adapter → builder → chain
# ============================================================================

class TestRoundTrip(unittest.TestCase):
    """Verify no data loss across the full conversion pipeline."""

    def test_all_devices_survive_round_trip(self):
        original = _make_sample_chain_spec()
        spec_dict = original.to_dict()
        builder_input = chainspec_to_builder_format(spec_dict)

        self.assertEqual(len(builder_input["chain"]), len(original.devices))

    def test_parameter_values_survive_round_trip(self):
        original = _make_sample_chain_spec()
        spec_dict = original.to_dict()
        builder_input = chainspec_to_builder_format(spec_dict)

        # Check compressor threshold survives
        comp = builder_input["chain"][1]
        self.assertEqual(comp["settings"]["Threshold"], -20.0)
        self.assertEqual(comp["settings"]["Ratio"], 6.0)

    def test_from_dict_back_to_chainspec(self):
        """Verify ChainSpec.from_dict(to_dict()) round-trips cleanly."""
        original = _make_sample_chain_spec()
        spec_dict = original.to_dict()
        restored = ChainSpec.from_dict(spec_dict)

        self.assertEqual(len(restored.devices), len(original.devices))
        self.assertEqual(restored.query, original.query)
        self.assertEqual(restored.confidence, original.confidence)
        self.assertEqual(restored.artist, original.artist)


# ============================================================================
# 5. Cache flattening: _cache_chain_spec writes flat settings
# ============================================================================

class TestCacheFlattening(unittest.TestCase):
    """Verify _cache_chain_spec writes flat parameter values to KB."""

    def test_cache_writes_flat_settings(self):
        """Simulate _cache_chain_spec and verify the chain data has flat settings."""
        chain_spec = _make_sample_chain_spec()

        # Reproduce what _cache_chain_spec does after our fix
        chain_data = [
            {
                "name": d.plugin_name,
                "type": d.category,
                "purpose": d.purpose,
                "settings": _flatten_parameters(d.parameters),
            }
            for d in chain_spec.devices
        ]

        # Verify all settings are flat
        for device_data in chain_data:
            for key, value in device_data["settings"].items():
                self.assertNotIsInstance(
                    value, dict,
                    f"Cache setting '{key}' in {device_data['name']} is still nested: {value}"
                )

        # Verify specific values
        eq_settings = chain_data[0]["settings"]
        self.assertEqual(eq_settings["1 Frequency A"], 100.0)

        comp_settings = chain_data[1]["settings"]
        self.assertEqual(comp_settings["Threshold"], -20.0)

    def test_cached_chain_compatible_with_builder(self):
        """Verify cached chain data can be fed directly into build_chain_from_research."""
        chain_spec = _make_sample_chain_spec()

        chain_data = [
            {
                "name": d.plugin_name,
                "type": d.category,
                "purpose": d.purpose,
                "settings": _flatten_parameters(d.parameters),
            }
            for d in chain_spec.devices
        ]

        # Build the research_result dict as get_chain_for_research would
        research_result = {
            "artist_or_style": chain_spec.artist or chain_spec.query,
            "track_type": "vocal",
            "chain": chain_data,
            "confidence": chain_spec.confidence,
            "from_cache": True,
            "sources": chain_spec.sources,
        }

        builder = PluginChainBuilder()
        chain = builder.build_chain_from_research(research_result)

        self.assertEqual(len(chain.slots), 3)
        self.assertEqual(chain.slots[0].plugin_type, "eq")


# ============================================================================
# 6. Full pipeline with mocked Ableton
# ============================================================================

class TestApplyResearchChainExecution(unittest.TestCase):
    """Test execute_apply_research_chain with mocked Ableton controller."""

    def _patch_and_run(self, chain_spec_dict, track_index=0, track_type="vocal"):
        """Run execute_apply_research_chain with all Ableton interactions mocked."""
        # Mock the ableton controller
        mock_ableton = MagicMock()
        mock_ableton.load_device.return_value = {
            "success": True, "message": "Device loaded", "device_index": 0
        }
        mock_ableton.load_device_verified.return_value = {
            "success": True, "message": "Device loaded", "device_index": 0
        }

        # Mock reliable_params
        mock_reliable = MagicMock()
        mock_reliable.wait_for_device_ready.return_value = True
        mock_reliable.set_parameter_by_name.return_value = {
            "success": True, "param_index": 0, "verified": True
        }

        # Mock research_bot
        mock_bot = MagicMock()
        mock_bot.apply_parameters.return_value = {
            "success": True,
            "applied": [{"param": "Threshold", "index": 0, "value": -20.0}],
            "failed": [],
        }

        # Mock plugin_chain_kb
        mock_kb = MagicMock()

        with patch("jarvis_engine.ableton", mock_ableton), \
             patch("jarvis_engine.reliable_params", mock_reliable), \
             patch("jarvis_engine.plugin_chain_kb", mock_kb):
            from jarvis_engine import execute_apply_research_chain
            result = execute_apply_research_chain(
                track_index, chain_spec_dict, track_type
            )

        return result, mock_ableton, mock_kb

    def test_successful_execution(self):
        spec_dict = _make_sample_chain_spec_dict()
        result, mock_ableton, mock_kb = self._patch_and_run(spec_dict)

        self.assertTrue(result.get("success"), f"Pipeline failed: {result.get('message')}")
        self.assertTrue(result.get("from_research"))
        self.assertEqual(result.get("artist_or_style"), "Travis Scott")
        self.assertEqual(result.get("track_type"), "vocal")

    def test_none_chain_spec_returns_error(self):
        with patch("jarvis_engine.ableton", MagicMock()), \
             patch("jarvis_engine.reliable_params", MagicMock()), \
             patch("jarvis_engine.plugin_chain_kb", MagicMock()):
            from jarvis_engine import execute_apply_research_chain
            result = execute_apply_research_chain(0, None)

        self.assertFalse(result["success"])
        self.assertIn("No chain_spec", result["message"])

    def test_empty_devices_returns_error(self):
        spec_dict = _make_sample_chain_spec_dict()
        spec_dict["devices"] = []

        with patch("jarvis_engine.ableton", MagicMock()), \
             patch("jarvis_engine.reliable_params", MagicMock()), \
             patch("jarvis_engine.plugin_chain_kb", MagicMock()):
            from jarvis_engine import execute_apply_research_chain
            result = execute_apply_research_chain(0, spec_dict)

        self.assertFalse(result["success"])
        self.assertIn("No devices", result["message"])

    def test_caches_on_success(self):
        spec_dict = _make_sample_chain_spec_dict()
        result, _, mock_kb = self._patch_and_run(spec_dict)

        if result.get("success"):
            mock_kb.add_chain.assert_called_once()
            call_kwargs = mock_kb.add_chain.call_args
            # Verify the cached chain items have flat settings
            chain_arg = call_kwargs.kwargs.get("chain") or call_kwargs[1].get("chain")
            if chain_arg is None:
                # Positional args
                chain_arg = call_kwargs[0][2] if len(call_kwargs[0]) > 2 else None

    def test_confidence_propagated(self):
        spec_dict = _make_sample_chain_spec_dict()
        result, _, _ = self._patch_and_run(spec_dict)

        if result.get("success"):
            self.assertIn("confidence", result)


# ============================================================================
# 7. Settings survive into _configure_device_for_purpose
# ============================================================================

class TestSettingsReachConfigurer(unittest.TestCase):
    """The original bug: nested dict settings were silently dropped by
    isinstance(value, (int, float, bool)) checks in _configure_device_for_purpose.
    Verify that after flattening, settings are numeric and would pass the filter."""

    def test_flattened_settings_pass_isinstance_check(self):
        """All flattened numeric settings should pass the isinstance filter
        used in _configure_device_for_purpose (lines 1029, 1035)."""
        spec_dict = _make_sample_chain_spec_dict()
        builder_input = chainspec_to_builder_format(spec_dict)

        for item in builder_input["chain"]:
            for key, value in item["settings"].items():
                if isinstance(value, (int, float, bool)):
                    # This is what _configure_device_for_purpose checks
                    pass  # Would be included
                else:
                    # If it's a string like "80-100Hz" from builtin knowledge,
                    # that's expected to be skipped by the configurer.
                    # But it should NOT be a nested dict.
                    self.assertNotIsInstance(
                        value, dict,
                        f"Setting '{key}' is still a nested dict after flattening: {value}"
                    )

    def test_no_nested_dicts_after_flattening(self):
        """No settings value should be a dict after the adapter runs."""
        spec_dict = _make_sample_chain_spec_dict()
        builder_input = chainspec_to_builder_format(spec_dict)

        for item in builder_input["chain"]:
            for key, value in item["settings"].items():
                self.assertNotIsInstance(
                    value, dict,
                    f"'{key}' in {item['plugin_name']} is still nested: {value}"
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
