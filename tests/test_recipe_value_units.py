"""Regression tests for the 2026-09-25 Compressor recipe bugs.

1. "Auto Release On/Off" = 1.0 was converted as 1 ms -> 0.0, leaving it Off.
2. Recipe values are already normalized (Release 0.28) but were read as ms,
   and the result still said verified because readback matched the converted value.
"""

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from ableton_controls.reliable_params import (
    CachedDeviceInfo,
    ReliableParameterController,
    smart_normalize_parameter,
)
from livepilot_tools import plugin_recipes

COMPRESSOR_PARAMS = ["Device On", "Threshold", "Ratio", "Attack", "Release",
                     "Auto Release On/Off", "Model", "Gain", "Dry/Wet"]


class FakeLive:
    """Stores what was sent and returns it on readback, like a stock device."""

    def __init__(self, names):
        self.values = {i: 0.0 for i in range(len(names))}

    def set_device_parameter(self, track, device, param, value):
        self.values[param] = float(value)
        return {"success": True}

    def _send_and_wait(self, addr, args, timeout=2.0):
        track, device, param = args
        return addr, [track, device, param, self.values[param]]


def make_controller():
    live = FakeLive(COMPRESSOR_PARAMS)
    ctrl = ReliableParameterController(live)
    ctrl.default_verify_delay = 0.001
    ctrl.default_max_retries = 1
    info = CachedDeviceInfo(
        device_name="Compressor",
        param_names=COMPRESSOR_PARAMS,
        param_mins=[0.0] * len(COMPRESSOR_PARAMS),
        param_maxs=[1.0] * len(COMPRESSOR_PARAMS),
        timestamp=time.time(),
    )
    ctrl.get_device_info = lambda *a, **k: info
    return ctrl, live


class TestToggleNotConvertedAsTime(unittest.TestCase):
    def test_auto_release_toggle_passes_through(self):
        value, method = smart_normalize_parameter("Auto Release On/Off", 1.0, "Compressor")
        self.assertEqual((value, method), (1.0, "toggle_raw"))

    def test_release_in_ms_still_converts(self):
        value, method = smart_normalize_parameter("Release", 50.0, "Compressor")
        self.assertEqual(method, "release_log")
        self.assertGreater(value, 0.0)

    def test_auto_release_toggle_lands_on(self):
        ctrl, live = make_controller()
        with patch("time.sleep"):
            result = ctrl.set_parameter_by_name(0, 0, "Auto Release On/Off", 1.0)
        self.assertEqual(live.values[5], 1.0)
        self.assertTrue(result["verified"])


class TestNormalizedValueVerification(unittest.TestCase):
    def test_normalized_release_read_as_ms_does_not_verify(self):
        ctrl, live = make_controller()
        with patch("time.sleep"):
            result = ctrl.set_parameter_by_name(0, 0, "Release", 0.28)
        self.assertFalse(result["verified"])
        self.assertFalse(result["success"])
        self.assertTrue(result["units_ambiguous"])

    def test_raw_mode_sends_value_unchanged(self):
        ctrl, live = make_controller()
        with patch("time.sleep"):
            result = ctrl.set_parameter_by_name(0, 0, "Release", 0.28, raw=True)
        self.assertEqual(live.values[4], 0.28)
        self.assertTrue(result["verified"])

    def test_raw_mode_fails_when_readback_differs(self):
        ctrl, live = make_controller()
        live.set_device_parameter = lambda *a: {"success": True}  # write is dropped
        with patch("time.sleep"):
            result = ctrl.set_parameter_by_name(0, 0, "Attack", 0.12, raw=True)
        self.assertFalse(result["verified"])
        self.assertFalse(result["success"])


class TestNormalizedRecipe(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_dir = plugin_recipes.RECIPES_DIR
        plugin_recipes.RECIPES_DIR = Path(self._tmpdir.name)

    def tearDown(self):
        plugin_recipes.RECIPES_DIR = self._orig_dir
        self._tmpdir.cleanup()

    def _write(self, name, params, **extra):
        payload = {"schema": plugin_recipes.RECIPE_SCHEMA, "name": name,
                   "plugin_name": "Compressor", "params": params, **extra}
        (plugin_recipes.RECIPES_DIR / f"{name}.json").write_text(
            json.dumps(payload), encoding="utf-8")

    def test_gambino_style_recipe_lands_exact_values(self):
        params = {"Device On": 1.0, "Threshold": 0.32, "Ratio": 0.65, "Attack": 0.12,
                  "Release": 0.28, "Auto Release": 1.0, "Model": 0.0,
                  "Gain": 0.45, "Dry/Wet": 1.0}
        self._write("gambino", params)
        ctrl, live = make_controller()
        with patch("time.sleep"):
            result = plugin_recipes.apply_plugin_recipe("gambino", 0, 0, reliable=ctrl)
        self.assertTrue(result["success"], result["message"])
        for name, value in params.items():
            index = ctrl.find_parameter_index(0, 0, name)
            self.assertAlmostEqual(live.values[index], value, msg=name)

    def test_unknown_value_units_rejected(self):
        self._write("bad", {"Release": 0.28}, value_units="ms")
        ctrl, _ = make_controller()
        result = plugin_recipes.apply_plugin_recipe("bad", 0, 0, reliable=ctrl)
        self.assertFalse(result["success"])


if __name__ == "__main__":
    unittest.main()
