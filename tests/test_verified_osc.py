#!/usr/bin/env python3
"""
Unit tests for the _verified_set() verification loop and verify= kwarg
on track-level setter methods.

Mock-based — no Ableton required.  Pattern follows tests/test_osc_preflight.py.

Run with:
    python -m pytest tests/test_verified_osc.py -v
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch, call

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from ableton_controls.controller import AbletonController


# ---------------------------------------------------------------------------
# Helper: build a controller with mocked OSC transport
# ---------------------------------------------------------------------------

def _make_controller():
    """Create an AbletonController with mocked socket/client so no real
    UDP traffic is generated.
    """
    with patch("ableton_controls.controller.AbletonController._start_response_listener"):
        ctrl = AbletonController.__new__(AbletonController)
        ctrl.ip = "127.0.0.1"
        ctrl.port = 11000
        ctrl.response_port = 11001
        ctrl.client = MagicMock()
        ctrl.connected = False
        ctrl.osc_paths = None
        ctrl._resp_sock = MagicMock()
        ctrl._resp_thread = None
        ctrl._resp_running = False
        ctrl._resp_lock = MagicMock()
        ctrl._resp_cv = MagicMock()
        ctrl._last_response = {}
        ctrl._param_range_cache = {}
    return ctrl


# ---------------------------------------------------------------------------
# Tests for _verified_set
# ---------------------------------------------------------------------------

class TestVerifiedSetFirstAttempt(unittest.TestCase):
    """1. Verified mute succeeds on first attempt."""

    def test_mute_verified_first_try(self):
        ctrl = _make_controller()

        # _send_and_wait returns the expected mute value on first call
        ctrl._send_and_wait = MagicMock(return_value=("/live/track/get/mute", [0, 1]))

        result = ctrl._verified_set(
            "/live/track/set/mute", [0, 1],
            "/live/track/get/mute", [0],
            1, "muted",
            retries=3, base_delay=0.001, max_delay=0.01, timeout=0.1,
        )

        self.assertTrue(result["success"])
        self.assertTrue(result["verified"])
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["actual"], 1)
        # SET was called once
        ctrl.client.send_message.assert_called_once_with("/live/track/set/mute", [0, 1])


class TestVerifiedSetRetry(unittest.TestCase):
    """2. Verified mute retries on GET mismatch, succeeds on attempt 3."""

    def test_mute_verified_after_retries(self):
        ctrl = _make_controller()

        # First two GET readbacks return wrong value (0), third returns correct (1)
        ctrl._send_and_wait = MagicMock(side_effect=[
            ("/live/track/get/mute", [0, 0]),  # mismatch
            ("/live/track/get/mute", [0, 0]),  # mismatch
            ("/live/track/get/mute", [0, 1]),  # match!
        ])

        result = ctrl._verified_set(
            "/live/track/set/mute", [0, 1],
            "/live/track/get/mute", [0],
            1, "muted",
            retries=3, base_delay=0.001, max_delay=0.01, timeout=0.1,
        )

        self.assertTrue(result["success"])
        self.assertTrue(result["verified"])
        self.assertEqual(result["attempts"], 3)
        # SET called 3 times (once per attempt)
        self.assertEqual(ctrl.client.send_message.call_count, 3)


class TestVerifiedSetExhausted(unittest.TestCase):
    """3. Verified mute fails after max retries exhausted."""

    def test_mute_unverified_after_max_retries(self):
        ctrl = _make_controller()

        # All readbacks return wrong value
        ctrl._send_and_wait = MagicMock(return_value=("/live/track/get/mute", [0, 0]))

        result = ctrl._verified_set(
            "/live/track/set/mute", [0, 1],
            "/live/track/get/mute", [0],
            1, "muted",
            retries=3, base_delay=0.001, max_delay=0.01, timeout=0.1,
        )

        # success=True (SET went out), verified=False (readback never matched)
        self.assertTrue(result["success"])
        self.assertFalse(result["verified"])
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(result["actual"], 0)


class TestVerifyFalseFireAndForget(unittest.TestCase):
    """4. verify=False never calls _send_and_wait (fire-and-forget preserved)."""

    def test_mute_no_verify(self):
        ctrl = _make_controller()
        ctrl._send_and_wait = MagicMock()

        result = ctrl.mute_track(0, 1, verify=False)

        self.assertTrue(result["success"])
        # _send_and_wait should NOT be called (fire-and-forget)
        ctrl._send_and_wait.assert_not_called()
        # client.send_message called once for the SET
        ctrl.client.send_message.assert_called_once_with("/live/track/set/mute", [0, 1])


class TestFloatTolerance(unittest.TestCase):
    """5. Float tolerance: volume 0.5 verified against readback of 0.501."""

    def test_volume_float_tolerance(self):
        ctrl = _make_controller()

        # Readback returns 0.501 (within 0.02 tolerance of 0.5)
        ctrl._send_and_wait = MagicMock(
            return_value=("/live/track/get/volume", [0, 0.501])
        )

        result = ctrl._verified_set(
            "/live/track/set/volume", [0, 0.5],
            "/live/track/get/volume", [0],
            0.5, "volume",
            retries=3, base_delay=0.001, max_delay=0.01, timeout=0.1,
        )

        self.assertTrue(result["verified"])
        self.assertAlmostEqual(result["actual"], 0.501, places=3)


class TestSendVerification(unittest.TestCase):
    """6. Send with extra send_index arg in both SET and GET."""

    def test_send_verified(self):
        ctrl = _make_controller()

        ctrl._send_and_wait = MagicMock(
            return_value=("/live/track/get/send", [0, 0, 0.75])
        )

        result = ctrl._verified_set(
            "/live/track/set/send", [0, 0, 0.75],
            "/live/track/get/send", [0, 0],
            0.75, "level",
            retries=3, base_delay=0.001, max_delay=0.01, timeout=0.1,
        )

        self.assertTrue(result["verified"])
        self.assertEqual(result["attempts"], 1)
        ctrl.client.send_message.assert_called_with("/live/track/set/send", [0, 0, 0.75])


@pytest.mark.usefixtures("offline_ableton")
class TestBridgeVerifyPassthrough(unittest.TestCase):
    """7. Bridge passes verify=True through dispatch correctly."""

    def test_bridge_dispatch_verify(self):
        # Import the bridge module
        import ableton_bridge

        # Build dispatch with verify=True
        args = {"track_index": 0, "muted": 1, "verify": True}
        dispatch = ableton_bridge._build_dispatch(args)

        # Patch ableton object's mute_track to capture kwargs
        with patch.object(ableton_bridge.ableton, "mute_track",
                          return_value={"success": True}) as mock_mute:
            dispatch["mute_track"]()
            mock_mute.assert_called_once_with(0, 1, verify=True)

        # Build dispatch with verify=False (default)
        args_no_verify = {"track_index": 0, "muted": 1}
        dispatch_nv = ableton_bridge._build_dispatch(args_no_verify)

        with patch.object(ableton_bridge.ableton, "mute_track",
                          return_value={"success": True}) as mock_mute2:
            dispatch_nv["mute_track"]()
            mock_mute2.assert_called_once_with(0, 1, verify=False)


if __name__ == "__main__":
    unittest.main()
