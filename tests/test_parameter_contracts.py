import os
import sys
import unittest


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from livepilot_tools.parameter_contracts import (  # noqa: E402
    ManifestStore,
    build_parameter_attempt,
    execute_parameter_contract,
)


class FakeReliableController:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def set_parameter_by_name(self, track_index, device_index, parameter_name, value, **kwargs):
        self.calls.append(
            {
                "track_index": track_index,
                "device_index": device_index,
                "parameter_name": parameter_name,
                "value": value,
                "kwargs": kwargs,
            }
        )
        return self.responses.get(
            parameter_name,
            {
                "success": False,
                "verified": False,
                "message": f"Parameter '{parameter_name}' not found",
            },
        )


class TestParameterContracts(unittest.TestCase):
    def test_resolves_plugin_and_parameter_aliases(self):
        plan = build_parameter_attempt("SSL EV2", "lmf cut", -2.5)

        self.assertTrue(plan["success"])
        self.assertEqual(plan["status"], "planned")
        self.assertEqual(plan["plugin"], "SSL EV2 Channel Stereo")
        self.assertEqual(plan["parameter_key"], "lmf_gain")
        self.assertEqual(plan["effective_value"], -2.5)
        self.assertEqual(plan["method_plan"][0], "ableton_lom")
        self.assertIn("LMF Gain", plan["lom_name_candidates"])

    def test_clamps_unsafe_values_inside_manifest_range(self):
        plan = build_parameter_attempt(
            "Renaissance Equalizer Stereo",
            "rumble cutoff",
            "20 Hz",
        )

        self.assertTrue(plan["success"])
        self.assertEqual(plan["parameter_key"], "hp_freq")
        self.assertEqual(plan["value_status"], "clamped")
        self.assertEqual(plan["clamped_from"], 20.0)
        self.assertEqual(plan["effective_value"], 45.0)

    def test_unknown_plugin_is_explicitly_unsupported(self):
        plan = build_parameter_attempt("Mystery Piano Widener", "width", 20)

        self.assertFalse(plan["success"])
        self.assertFalse(plan["verified"])
        self.assertEqual(plan["status"], "unsupported_plugin")
        self.assertIn("REQ 6 Stereo", plan["available_plugins"])

    def test_execute_tries_lom_candidates_until_verified(self):
        reliable = FakeReliableController(
            {
                "Low Mid Gain": {
                    "success": True,
                    "verified": True,
                    "actual_value": -2.5,
                    "message": "verified",
                }
            }
        )

        result = execute_parameter_contract(
            reliable=reliable,
            track_index=0,
            device_index=2,
            plugin_name="SSL EV2 Channel",
            parameter_name="low mid gain",
            value=-2.5,
            max_retries=2,
        )

        self.assertTrue(result["success"])
        self.assertTrue(result["verified"])
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["used_parameter_name"], "Low Mid Gain")
        self.assertEqual(
            [call["parameter_name"] for call in reliable.calls],
            ["LMF Gain", "Low Mid Gain"],
        )
        self.assertEqual(reliable.calls[0]["kwargs"]["max_retries"], 2)

    def test_success_without_readback_stays_unverified_by_default(self):
        reliable = FakeReliableController(
            {
                "LMF Gain": {
                    "success": True,
                    "verified": False,
                    "actual_value": -2.1,
                    "message": "accepted with relaxed tolerance",
                }
            }
        )

        result = execute_parameter_contract(
            reliable=reliable,
            track_index=0,
            device_index=2,
            plugin_name="SSL EV2",
            parameter_name="lmf",
            value=-2.5,
        )

        self.assertFalse(result["success"])
        self.assertFalse(result["verified"])
        self.assertEqual(result["status"], "attempted_unverified")
        self.assertEqual(result["used_parameter_name"], "LMF Gain")

    def test_manifest_store_lists_available_parameters(self):
        store = ManifestStore()

        parameters = store.available_parameters("REQ6")

        self.assertIn("Band 1 Frequency", parameters)
        self.assertIn("Band 5 Gain", parameters)


if __name__ == "__main__":
    unittest.main()
