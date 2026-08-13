#!/usr/bin/env python3
"""
Unit tests for adaptive_layer.py — alias normalization, resolution, and
adaptive profile building.
"""

import os
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from adaptive_layer import (
    _normalize_key,
    resolve_alias,
    resolve_params,
    build_adaptive_profile_steps,
    DEVICE_ALIAS_REGISTRY,
)


class TestNormalizeKey(unittest.TestCase):
    """Verify key normalisation handles whitespace, hyphens, case."""

    def test_basic(self):
        self.assertEqual(_normalize_key("Air"), "air")

    def test_hyphens_to_underscores(self):
        self.assertEqual(_normalize_key("low-cut"), "low_cut")

    def test_spaces_to_underscores(self):
        self.assertEqual(_normalize_key("mud freq"), "mud_freq")

    def test_mixed(self):
        self.assertEqual(_normalize_key("  Air - Boost "), "air_boost")

    def test_already_canonical(self):
        self.assertEqual(_normalize_key("band1_freq_hz"), "band1_freq_hz")


class TestResolveAlias(unittest.TestCase):
    """Verify alias resolution for EQ Eight and Compressor."""

    # --- EQ Eight ---
    def test_eq_air_resolves(self):
        key, default = resolve_alias("EQ Eight", "air")
        self.assertEqual(key, "band4_gain_db")

    def test_eq_presence_resolves(self):
        key, _ = resolve_alias("EQ Eight", "presence")
        self.assertEqual(key, "band3_gain_db")

    def test_eq_mud_resolves(self):
        key, _ = resolve_alias("EQ Eight", "mud")
        self.assertEqual(key, "band2_gain_db")

    def test_eq_low_cut_resolves(self):
        key, _ = resolve_alias("EQ Eight", "low_cut")
        self.assertEqual(key, "band1_freq_hz")

    def test_eq_highpass_alias(self):
        key, _ = resolve_alias("EQ Eight", "high_pass")
        self.assertEqual(key, "band1_freq_hz")

    def test_eq_case_insensitive(self):
        key, _ = resolve_alias("EQ Eight", "AIR")
        self.assertEqual(key, "band4_gain_db")

    def test_eq_hyphen_normalised(self):
        key, _ = resolve_alias("EQ Eight", "low-cut")
        self.assertEqual(key, "band1_freq_hz")

    def test_eq_canonical_passthrough(self):
        key, _ = resolve_alias("EQ Eight", "band3_freq_hz")
        self.assertEqual(key, "band3_freq_hz")

    # --- Compressor ---
    def test_comp_threshold(self):
        key, _ = resolve_alias("Compressor", "threshold")
        self.assertEqual(key, "threshold_db")

    def test_comp_thresh_alias(self):
        key, _ = resolve_alias("Compressor", "thresh")
        self.assertEqual(key, "threshold_db")

    def test_comp_attack(self):
        key, _ = resolve_alias("Compressor", "attack")
        self.assertEqual(key, "attack_ms")

    def test_comp_release(self):
        key, _ = resolve_alias("Compressor", "release")
        self.assertEqual(key, "release_ms")

    def test_comp_makeup(self):
        key, _ = resolve_alias("Compressor", "makeup")
        self.assertEqual(key, "output_gain_db")

    def test_comp_mix(self):
        key, _ = resolve_alias("Compressor", "mix")
        self.assertEqual(key, "dry_wet_pct")

    # --- Unknown device / unknown alias ---
    def test_unknown_device_passthrough(self):
        key, default = resolve_alias("SomeUnknownPlugin", "foobar")
        self.assertEqual(key, "foobar")
        self.assertIsNone(default)

    def test_unknown_alias_passthrough(self):
        key, default = resolve_alias("EQ Eight", "totally_unknown_param")
        self.assertEqual(key, "totally_unknown_param")
        self.assertIsNone(default)


class TestResolveParams(unittest.TestCase):
    """Verify batch alias resolution."""

    def test_mixed_aliases_and_canonical(self):
        params = {
            "air": 2.0,
            "band1_freq_hz": 100,
            "mud": -3.0,
        }
        resolved = resolve_params("EQ Eight", params)
        self.assertEqual(resolved["band4_gain_db"], 2.0)
        self.assertEqual(resolved["band1_freq_hz"], 100)
        self.assertEqual(resolved["band2_gain_db"], -3.0)

    def test_compressor_params(self):
        params = {"thresh": -20, "ratio": 4, "attack": 10}
        resolved = resolve_params("Compressor", params)
        self.assertEqual(resolved["threshold_db"], -20)
        self.assertEqual(resolved["ratio"], 4)
        self.assertEqual(resolved["attack_ms"], 10)

    def test_empty_params(self):
        self.assertEqual(resolve_params("EQ Eight", {}), {})


class TestBuildAdaptiveProfileSteps(unittest.TestCase):
    """Verify profile step building for vocal profiles."""

    def _standard_device_map(self):
        return {0: "EQ Eight", 1: "Compressor", 7: "EQ Eight"}

    def test_airy_melodic_returns_steps(self):
        steps = build_adaptive_profile_steps("airy_melodic", self._standard_device_map())
        self.assertIsNotNone(steps)
        self.assertTrue(len(steps) >= 2)
        # First step should be EQ Eight on device 0
        self.assertEqual(steps[0]["device_index"], 0)
        self.assertEqual(steps[0]["device_name"], "EQ Eight")
        self.assertIn("band1_on", steps[0]["params"])

    def test_punchy_rap_returns_steps(self):
        steps = build_adaptive_profile_steps("punchy_rap", self._standard_device_map())
        self.assertIsNotNone(steps)
        # Punchy should include compressor step
        comp_steps = [s for s in steps if s["device_name"] == "Compressor"]
        self.assertEqual(len(comp_steps), 1)
        self.assertIn("ratio", comp_steps[0]["params"])

    def test_unknown_profile_returns_none(self):
        result = build_adaptive_profile_steps("unknown_profile", self._standard_device_map())
        self.assertIsNone(result)

    def test_missing_device_skips_step(self):
        # Only EQ on device 0, no compressor, no second EQ
        steps = build_adaptive_profile_steps("punchy_rap", {0: "EQ Eight"})
        self.assertIsNotNone(steps)
        # Should only have the EQ step, compressor and second EQ skipped
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["device_index"], 0)

    def test_airy_no_compressor_step(self):
        """Airy melodic profile should not include compressor params."""
        steps = build_adaptive_profile_steps("airy_melodic", self._standard_device_map())
        comp_steps = [s for s in steps if s["device_name"] == "Compressor"]
        self.assertEqual(len(comp_steps), 0)

    def test_all_params_are_numeric(self):
        """All parameter values should be numeric (int or float)."""
        steps = build_adaptive_profile_steps("airy_melodic", self._standard_device_map())
        for step in steps:
            for k, v in step["params"].items():
                self.assertIsInstance(v, (int, float),
                                     f"Param {k} has non-numeric value: {v!r}")


class TestDeviceAliasRegistryCoverage(unittest.TestCase):
    """Ensure alias registry has minimum viable coverage."""

    def test_eq_eight_registered(self):
        self.assertIn("EQ Eight", DEVICE_ALIAS_REGISTRY)

    def test_compressor_registered(self):
        self.assertIn("Compressor", DEVICE_ALIAS_REGISTRY)

    def test_eq_eight_has_core_aliases(self):
        aliases = DEVICE_ALIAS_REGISTRY["EQ Eight"]
        for alias in ("air", "presence", "mud", "low_cut"):
            self.assertIn(alias, aliases, f"EQ Eight missing core alias '{alias}'")

    def test_compressor_has_core_aliases(self):
        aliases = DEVICE_ALIAS_REGISTRY["Compressor"]
        for alias in ("threshold", "ratio", "attack", "release"):
            self.assertIn(alias, aliases, f"Compressor missing core alias '{alias}'")


if __name__ == "__main__":
    unittest.main()
