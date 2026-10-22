#!/usr/bin/env python3
"""
Unit tests for osc_preflight.py — preflight guard checks.
"""

import os
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from osc_preflight import (
    check_osc_bridge,
    check_track_accessible,
    run_preflight,
)


# ---------------------------------------------------------------------------
# Mock execute_fn helpers
# ---------------------------------------------------------------------------

def _mock_execute_ok(func_name, args):
    """Simulates a working Ableton OSC bridge."""
    if func_name == "get_track_list":
        return {
            "success": True,
            "tracks": [
                {"index": 0, "name": "Lead Vocal"},
                {"index": 1, "name": "Guitar"},
                {"index": 2, "name": "Drums"},
            ],
        }
    return {"success": True}


def _mock_execute_fail(func_name, args):
    """Simulates an unreachable Ableton OSC bridge."""
    return {"success": False, "message": "No response from Ableton"}


def _mock_execute_flaky(func_name, args, _state={"calls": 0}):
    """Fails first 2 calls, succeeds on third."""
    _state["calls"] += 1
    if _state["calls"] <= 2:
        return {"success": False, "message": "Timeout"}
    return {
        "success": True,
        "tracks": [{"index": 0, "name": "Track 1"}],
    }


class TestCheckOscBridge(unittest.TestCase):
    """Test OSC bridge check."""

    def test_pass_on_first_attempt(self):
        result = check_osc_bridge(_mock_execute_ok, attempts=3, delay_s=0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["attempts_used"], 1)
        self.assertIsNotNone(result["latency_ms"])
        self.assertIn("responding", result["message"])

    def test_fail_after_all_attempts(self):
        result = check_osc_bridge(_mock_execute_fail, attempts=2, delay_s=0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["attempts_used"], 2)
        self.assertIsNone(result["latency_ms"])
        self.assertIn("unreachable", result["message"])

    def test_recovers_on_retry(self):
        state = {"calls": 0}
        def flaky(fn, args):
            state["calls"] += 1
            if state["calls"] <= 2:
                return {"success": False, "message": "Timeout"}
            return {"success": True, "tracks": []}

        result = check_osc_bridge(flaky, attempts=4, delay_s=0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["attempts_used"], 3)

    def test_exception_handled(self):
        def exploding(fn, args):
            raise ConnectionError("socket dead")

        result = check_osc_bridge(exploding, attempts=2, delay_s=0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["attempts_used"], 2)


class TestCheckTrackAccessible(unittest.TestCase):
    """Test track reachability check."""

    def test_valid_track(self):
        result = check_track_accessible(_mock_execute_ok, track_index=0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["track_count"], 3)

    def test_out_of_range_track(self):
        result = check_track_accessible(_mock_execute_ok, track_index=99)
        self.assertFalse(result["ok"])
        self.assertIn("out of range", result["message"])

    def test_bridge_failure(self):
        result = check_track_accessible(_mock_execute_fail, track_index=0)
        self.assertFalse(result["ok"])

    def test_exception_in_execute(self):
        def boom(fn, args):
            raise RuntimeError("boom")
        result = check_track_accessible(boom, track_index=0)
        self.assertFalse(result["ok"])
        self.assertIn("boom", result["message"])


class TestRunPreflight(unittest.TestCase):
    """Test composite preflight runner."""

    def test_all_pass_no_loader(self):
        result = run_preflight(
            _mock_execute_ok,
            track_index=0,
            require_loader=False,
            osc_attempts=1,
            osc_delay_s=0,
        )
        self.assertTrue(result["ok"])
        self.assertIsNone(result["failure_type"])
        self.assertGreaterEqual(len(result["checks"]), 2)  # osc + track

    def test_osc_failure_stops_early(self):
        result = run_preflight(
            _mock_execute_fail,
            track_index=0,
            require_loader=False,
            osc_attempts=1,
            osc_delay_s=0,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["failure_type"], "osc_unreachable_preflight")
        # Should have only 1 check (OSC), track check should be skipped
        self.assertEqual(len(result["checks"]), 1)

    def test_track_out_of_range(self):
        result = run_preflight(
            _mock_execute_ok,
            track_index=99,
            require_loader=False,
            osc_attempts=1,
            osc_delay_s=0,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["failure_type"], "track_unreachable")

    def test_no_track_check_when_none(self):
        result = run_preflight(
            _mock_execute_ok,
            track_index=None,
            require_loader=False,
            osc_attempts=1,
            osc_delay_s=0,
        )
        self.assertTrue(result["ok"])
        # Only OSC check, no track check
        self.assertEqual(len(result["checks"]), 1)

    def test_report_structure(self):
        result = run_preflight(
            _mock_execute_ok,
            track_index=0,
            require_loader=False,
            osc_attempts=1,
            osc_delay_s=0,
        )
        self.assertIn("ok", result)
        self.assertIn("checks", result)
        self.assertIn("failure_type", result)
        self.assertIn("message", result)
        for chk in result["checks"]:
            self.assertIn("name", chk)
            self.assertIn("ok", chk)
            self.assertIn("message", chk)


if __name__ == "__main__":
    unittest.main()
