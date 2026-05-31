import os
import sys
import tempfile
import unittest


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calibration_utils import (  # noqa: E402
    CalibrationStore,
    coerce_target_to_base_value,
    detect_curve_model,
    parse_display_value,
    value_to_normalized_from_curve,
)


class TestCalibrationParsing(unittest.TestCase):
    def test_parse_khz_to_hz(self):
        parsed = parse_display_value("19.9 kHz")
        self.assertEqual(parsed["base_unit"], "Hz")
        self.assertAlmostEqual(parsed["base_value"], 19900.0, places=4)

    def test_parse_db(self):
        parsed = parse_display_value("-12 dB")
        self.assertEqual(parsed["base_unit"], "dB")
        self.assertAlmostEqual(parsed["base_value"], -12.0, places=4)

    def test_coerce_target_string(self):
        value = coerce_target_to_base_value("1.5 kHz")
        self.assertAlmostEqual(value, 1500.0, places=4)

    def test_coerce_target_time(self):
        value = coerce_target_to_base_value("2 s")
        self.assertAlmostEqual(value, 2000.0, places=4)


class TestCalibrationCurveModel(unittest.TestCase):
    def test_detect_linear_curve(self):
        points = [
            {"normalized": 0.0, "base_value": 0.0},
            {"normalized": 0.5, "base_value": 50.0},
            {"normalized": 1.0, "base_value": 100.0},
        ]
        fit = detect_curve_model(points)
        self.assertEqual(fit["curve_model"], "LINEAR")

    def test_detect_log_curve(self):
        min_hz = 20.0
        max_hz = 20000.0
        points = []
        for n in (0.0, 0.25, 0.5, 0.75, 1.0):
            hz = min_hz * ((max_hz / min_hz) ** n)
            points.append({"normalized": n, "base_value": hz})
        fit = detect_curve_model(points)
        self.assertEqual(fit["curve_model"], "LOGARITHMIC")

    def test_value_to_normalized_linear(self):
        curve = {
            "curve_model": "LINEAR",
            "range": {"min": -15.0, "max": 15.0},
            "points": [],
        }
        norm = value_to_normalized_from_curve(0.0, curve)
        self.assertAlmostEqual(norm, 0.5, places=4)

    def test_value_to_normalized_log(self):
        curve = {
            "curve_model": "LOGARITHMIC",
            "range": {"min": 20.0, "max": 20000.0},
            "points": [],
        }
        norm = value_to_normalized_from_curve(200.0, curve)
        self.assertTrue(0.30 <= norm <= 0.40)


class TestCalibrationStore(unittest.TestCase):
    def test_store_and_lookup_curve_case_insensitive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "calibration.json")
            store = CalibrationStore(path)
            store.upsert_plugin_calibration(
                "FabFilter Pro-Q 3",
                {
                    "parameters": {
                        "Frequency": {
                            "param_index": 1,
                            "curve_model": "LOGARITHMIC",
                            "unit": "Hz",
                            "range": {"min": 20.0, "max": 20000.0},
                            "points": [],
                        }
                    }
                },
            )

            curve = store.get_curve("fabfilter pro-q 3", "frequency")
            self.assertIsNotNone(curve)
            self.assertEqual(curve["curve_model"], "LOGARITHMIC")


if __name__ == "__main__":
    unittest.main()
