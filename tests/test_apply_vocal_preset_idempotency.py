import unittest
from unittest.mock import patch

from scripts import apply_vocal_preset


class TestVerifiedDeviceLoad(unittest.TestCase):
    def test_load_succeeds_when_count_increments_by_one(self):
        device_snapshots = [
            ["EQ Eight"],
            ["EQ Eight", "CLA Vocals"],
        ]

        def fake_execute(func_name, args):
            if func_name == "get_track_devices":
                return {"success": True, "devices": device_snapshots.pop(0)}
            if func_name == "add_plugin_to_track":
                return {"success": True, "message": "ok"}
            raise AssertionError(f"Unexpected call: {func_name}")

        with patch.object(apply_vocal_preset, "_execute", side_effect=fake_execute):
            with patch.object(apply_vocal_preset.time, "time", side_effect=[0, 0]):
                result = apply_vocal_preset._load_device_verified(
                    0, "CLA Vocals", timeout_sec=1, poll_interval_sec=0
                )

        self.assertTrue(result["success"])
        self.assertEqual(result["device_index"], 1)
        self.assertEqual(result["actual_count"], 2)

    def test_duplicate_count_raises_duplicate_device_error(self):
        device_snapshots = [
            ["EQ Eight"],
            ["EQ Eight", "Clarity Vx", "Clarity Vx"],
        ]

        def fake_execute(func_name, args):
            if func_name == "get_track_devices":
                return {"success": True, "devices": device_snapshots.pop(0)}
            if func_name == "add_plugin_to_track":
                return {"success": True, "message": "ok"}
            raise AssertionError(f"Unexpected call: {func_name}")

        with patch.object(apply_vocal_preset, "_execute", side_effect=fake_execute):
            with patch.object(apply_vocal_preset.time, "time", side_effect=[0, 0]):
                with self.assertRaises(apply_vocal_preset.DuplicateDeviceError):
                    apply_vocal_preset._load_device_verified(
                        0, "Clarity Vx", timeout_sec=1, poll_interval_sec=0
                    )

    def test_timeout_load_succeeds_when_poll_sees_increment(self):
        device_snapshots = [
            [],
            ["Clarity Vx"],
        ]

        def fake_execute(func_name, args):
            if func_name == "get_track_devices":
                return {"success": True, "devices": device_snapshots.pop(0)}
            if func_name == "add_plugin_to_track":
                return {"success": False, "message": "Timeout waiting for response"}
            raise AssertionError(f"Unexpected call: {func_name}")

        with patch.object(apply_vocal_preset, "_execute", side_effect=fake_execute):
            with patch.object(apply_vocal_preset.time, "time", side_effect=[0, 0]):
                result = apply_vocal_preset._load_device_verified(
                    0, "Clarity Vx", timeout_sec=1, poll_interval_sec=0
                )

        self.assertTrue(result["success"])
        self.assertEqual(result["device_index"], 0)

    def test_timeout_load_fails_when_count_never_increments(self):
        device_snapshots = [
            [],
            [],
        ]

        def fake_execute(func_name, args):
            if func_name == "get_track_devices":
                return {"success": True, "devices": device_snapshots.pop(0)}
            if func_name == "add_plugin_to_track":
                return {"success": False, "message": "Timeout waiting for response"}
            raise AssertionError(f"Unexpected call: {func_name}")

        with patch.object(apply_vocal_preset, "_execute", side_effect=fake_execute):
            with patch.object(apply_vocal_preset.time, "time", side_effect=[0, 0, 2]):
                with patch.object(apply_vocal_preset.time, "sleep"):
                    result = apply_vocal_preset._load_device_verified(
                        0, "Clarity Vx", timeout_sec=1, poll_interval_sec=0
                    )

        self.assertFalse(result["success"])
        self.assertEqual(result["exit_code"], apply_vocal_preset.LOAD_FAILURE_EXIT_CODE)
        self.assertIn("Timed out", result["message"])


class TestFullChainAbort(unittest.TestCase):
    def test_parameter_setting_not_attempted_after_duplicate(self):
        chain = [
            {"plugin_name": "Clarity Vx", "parameters": {}},
            {"plugin_name": "CLA Vocals", "parameters": {"Compress": 0.5}},
        ]
        duplicate = apply_vocal_preset.DuplicateDeviceError(
            "Clarity Vx", expected_count=1, actual_count=2, track_index=0
        )

        with patch.object(apply_vocal_preset, "_get_track_devices", return_value=[]):
            with patch.object(apply_vocal_preset, "_load_device_verified", side_effect=duplicate):
                with patch.object(apply_vocal_preset, "set_params_only") as set_params:
                    result = apply_vocal_preset.apply_chain(0, chain)

        self.assertTrue(result["aborted"])
        self.assertEqual(result["exit_code"], apply_vocal_preset.DUPLICATE_DEVICE_EXIT_CODE)
        set_params.assert_not_called()

    def test_parameter_setting_not_attempted_after_load_failure(self):
        chain = [
            {"plugin_name": "Clarity Vx", "parameters": {}},
            {"plugin_name": "CLA Vocals", "parameters": {"Compress": 0.5}},
        ]
        load_failure = {
            "success": False,
            "message": "Timed out waiting for device",
            "exit_code": apply_vocal_preset.LOAD_FAILURE_EXIT_CODE,
        }

        with patch.object(apply_vocal_preset, "_get_track_devices", return_value=[]):
            with patch.object(apply_vocal_preset, "_load_device_verified", return_value=load_failure):
                with patch.object(apply_vocal_preset, "set_params_only") as set_params:
                    result = apply_vocal_preset.apply_chain(0, chain)

        self.assertTrue(result["aborted"])
        self.assertEqual(result["exit_code"], apply_vocal_preset.LOAD_FAILURE_EXIT_CODE)
        set_params.assert_not_called()


if __name__ == "__main__":
    unittest.main()
