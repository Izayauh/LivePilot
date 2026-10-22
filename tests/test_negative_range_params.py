"""Regression tests for negative-only range parameters (2026-09-26).

Limiter Ceiling (min -24, max 0) set to -1.0 was sent as 0.0 (passthrough
clamped it into [0, 1]), verification was skipped, and the result reported
actual_value -1.0 without reading it back. AbletonOSC reads and writes these
parameters in raw units, so the raw value must go out and be verified.
"""

import time
import unittest
from unittest.mock import patch

from ableton_controls.reliable_params import CachedDeviceInfo, ReliableParameterController

LIMITER_PARAMS = ["Device On", "Gain", "Ceiling", "Release"]


class FakeLive:
    """Stores raw values like Live does and returns them on readback."""

    def __init__(self, ignore_writes=False):
        self.values = {i: 0.0 for i in range(len(LIMITER_PARAMS))}
        self.ignore_writes = ignore_writes

    def set_device_parameter(self, track, device, param, value):
        if not self.ignore_writes:
            self.values[param] = float(value)
        return {"success": True}

    def _send_and_wait(self, addr, args, timeout=2.0):
        track, device, param = args
        return addr, [track, device, param, self.values[param]]


def make_controller(ignore_writes=False):
    live = FakeLive(ignore_writes)
    ctrl = ReliableParameterController(live)
    ctrl.default_verify_delay = 0.001
    ctrl.default_max_retries = 1
    info = CachedDeviceInfo(
        device_name="Limiter",
        param_names=LIMITER_PARAMS,
        param_mins=[0.0, -24.0, -24.0, 0.0],
        param_maxs=[1.0, 24.0, 0.0, 1.0],
        timestamp=time.time(),
    )
    ctrl.get_device_info = lambda *a, **k: info
    return ctrl, live


class TestNegativeOnlyRange(unittest.TestCase):
    def test_ceiling_lands_as_raw_db_and_verifies(self):
        ctrl, live = make_controller()
        with patch("time.sleep"):
            result = ctrl.set_parameter_verified(2, 8, 2, -1.0)
        self.assertEqual(live.values[2], -1.0)
        self.assertEqual(result["normalized_sent"], -1.0)
        self.assertTrue(result["verified"])
        self.assertTrue(result["success"])
        self.assertEqual(result["actual_value"], -1.0)

    def test_by_name_uses_same_path(self):
        ctrl, live = make_controller()
        with patch("time.sleep"):
            result = ctrl.set_parameter_by_name(2, 8, "Ceiling", -3.5)
        self.assertEqual(live.values[2], -3.5)
        self.assertTrue(result["verified"])

    def test_write_that_does_not_land_is_not_reported_as_success(self):
        ctrl, live = make_controller(ignore_writes=True)
        with patch("time.sleep"):
            result = ctrl.set_parameter_verified(2, 8, 2, -1.0)
        self.assertFalse(result["success"])
        self.assertFalse(result["verified"])
        # actual_value is what was read back, never the requested value
        self.assertEqual(result["actual_value"], 0.0)


if __name__ == "__main__":
    unittest.main()
