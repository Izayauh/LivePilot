"""Return/master device routing: track_kind sends device work to the TCP 9878 script."""

import unittest
from unittest.mock import patch

import pytest

import ableton_bridge as bridge

REVERB_PARAMS = {"success": True, "parameters": [
    {"index": 0, "name": "Device On", "value": 1.0, "min": 0.0, "max": 1.0, "value_string": "On"},
    {"index": 32, "name": "Dry/Wet", "value": 1.0, "min": 0.0, "max": 1.0, "value_string": "100 %"},
]}


def run(name, args):
    return bridge._build_dispatch(args)[name]()


class TestRsTrackIndex(unittest.TestCase):
    def test_return_zero_is_minus_one(self):
        self.assertEqual(bridge._rs_track_index("return", 0), -1)
        self.assertEqual(bridge._rs_track_index("return", 1), -2)

    def test_master_ignores_index(self):
        self.assertEqual(bridge._rs_track_index("master", None), -1000)

    def test_bad_kind_and_negative_return_raise(self):
        with self.assertRaises(ValueError):
            bridge._rs_track_index("retrun", 0)
        with self.assertRaises(ValueError):
            bridge._rs_track_index("return", -1)


@pytest.mark.usefixtures("offline_ableton")
class TestRouting(unittest.TestCase):
    def test_return_devices_use_track_info(self):
        with patch.object(bridge.remote_script, "send_command",
                          return_value={"success": True, "name": "A-Reverb",
                                        "devices": [{"name": "Reverb", "class_name": "Reverb"}]}) as sc:
            res = run("get_track_devices", {"track_kind": "return", "track_index": 0})
        sc.assert_called_once_with("get_track_info", {"track_index": -1})
        self.assertEqual(res["devices"], ["Reverb"])

    def test_master_devices_use_get_master_track(self):
        with patch.object(bridge.remote_script, "send_command",
                          return_value={"success": True, "name": "Master", "devices": []}) as sc:
            res = run("get_track_devices", {"track_kind": "master"})
        sc.assert_called_once_with("get_master_track")
        self.assertTrue(res["success"])

    def test_regular_track_stays_on_osc(self):
        with patch.object(bridge.remote_script, "send_command") as sc, \
             patch.object(bridge.ableton, "get_track_devices_sync",
                          return_value={"success": True, "devices": ["EQ Eight"]}) as osc:
            run("get_track_devices", {"track_index": 3})
        sc.assert_not_called()
        osc.assert_called_once_with(3)

    def test_set_by_name_writes_raw_and_verifies(self):
        calls = []

        def fake(cmd, params=None):
            calls.append((cmd, params))
            if cmd == "get_device_parameters":
                return REVERB_PARAMS
            return {"success": True, "value": params["value"], "value_string": "40 %"}

        with patch.object(bridge.remote_script, "send_command", side_effect=fake):
            res = run("set_device_parameter_by_name", {"track_kind": "return", "track_index": 1,
                                                       "device_index": 0, "param_name": "dry/wet",
                                                       "value": 0.4})
        self.assertTrue(res["verified"])
        self.assertEqual(calls[-1], ("set_device_parameter", {"track_index": -2, "device_index": 0,
                                                              "parameter_index": 32, "value": 0.4}))

    def test_out_of_range_is_refused_without_writing(self):
        with patch.object(bridge.remote_script, "send_command", return_value=REVERB_PARAMS) as sc:
            res = run("set_device_parameter", {"track_kind": "master", "device_index": 0,
                                               "param_index": 32, "value": 40})
        self.assertFalse(res["success"])
        self.assertEqual([c.args[0] for c in sc.call_args_list], ["get_device_parameters"])

    def test_add_plugin_passes_kind_and_position(self):
        with patch.object(bridge.ableton, "load_device", return_value={"success": False}) as ld:
            run("add_plugin_to_track", {"track_kind": "return", "track_index": 0,
                                        "plugin_name": "EQ Eight", "position": 0})
        ld.assert_called_once_with(0, "EQ Eight", 0, None, track_kind="return")


if __name__ == "__main__":
    unittest.main()
