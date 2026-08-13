import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research_bot import ResearchBot  # noqa: E402


class TestResearchBotCalibration(unittest.IsolatedAsyncioTestCase):
    async def test_dynamic_mapping_prefers_calibration_curve(self):
        bot = ResearchBot()

        mock_rpc = Mock()
        mock_rpc.get_device_info.return_value = SimpleNamespace(
            param_names=["Frequency"],
            param_mins=[0.0],
            param_maxs=[1.0],
        )
        mock_rpc.set_parameter_by_name.return_value = {"success": True}

        bot._load_vst_param_cache = Mock(
            return_value={
                "Test Plugin|1": {
                    "param_map": {
                        "cutoff": {
                            "param_name": "Frequency",
                            "param_index": 0,
                            "normalized_value": 0.9,
                        }
                    }
                }
            }
        )
        bot._calibration_store = Mock()
        bot._calibration_store.get_curve.return_value = {
            "curve_model": "LOGARITHMIC",
            "unit": "Hz",
            "range": {"min": 20.0, "max": 20000.0},
            "points": [],
        }

        with patch(
            "ableton_controls.reliable_params.get_reliable_controller",
            return_value=mock_rpc,
        ):
            result = await bot._discover_and_map_vst_params(
                track_index=0,
                device_index=0,
                plugin_name="Test Plugin",
                desired_settings={"cutoff": "500 Hz"},
            )

        self.assertTrue(result["success"])
        sent_value = mock_rpc.set_parameter_by_name.call_args[0][3]
        self.assertNotAlmostEqual(sent_value, 0.9, places=3)
        self.assertTrue(0.40 <= sent_value <= 0.55)
        self.assertEqual(result["applied"][0]["source"], "calibration")

    async def test_dynamic_mapping_uses_llm_value_without_calibration(self):
        bot = ResearchBot()

        mock_rpc = Mock()
        mock_rpc.get_device_info.return_value = SimpleNamespace(
            param_names=["Frequency"],
            param_mins=[0.0],
            param_maxs=[1.0],
        )
        mock_rpc.set_parameter_by_name.return_value = {"success": True}

        bot._load_vst_param_cache = Mock(
            return_value={
                "Test Plugin|1": {
                    "param_map": {
                        "cutoff": {
                            "param_name": "Frequency",
                            "param_index": 0,
                            "normalized_value": 0.77,
                        }
                    }
                }
            }
        )
        bot._calibration_store = Mock()
        bot._calibration_store.get_curve.return_value = None

        with patch(
            "ableton_controls.reliable_params.get_reliable_controller",
            return_value=mock_rpc,
        ):
            result = await bot._discover_and_map_vst_params(
                track_index=0,
                device_index=0,
                plugin_name="Test Plugin",
                desired_settings={"cutoff": 500.0},
            )

        self.assertTrue(result["success"])
        sent_value = mock_rpc.set_parameter_by_name.call_args[0][3]
        self.assertAlmostEqual(sent_value, 0.77, places=4)
        self.assertEqual(result["applied"][0]["source"], "llm_mapping")


if __name__ == "__main__":
    unittest.main()
