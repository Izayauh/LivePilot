import json
import math
import unittest

import numpy as np

from analysis.spectral import (
    BandPower,
    ComparisonReport,
    SpectralReport,
    analyze,
    compare,
    crest_factor,
    format_report,
)


SAMPLE_RATE = 48000


def sine(freq, seconds=1.0, amplitude=1.0):
    t = np.arange(int(SAMPLE_RATE * seconds)) / SAMPLE_RATE
    return amplitude * np.sin(2.0 * np.pi * freq * t)


class TestSpectralAnalysis(unittest.TestCase):
    def test_synthetic_sine_lands_in_expected_band(self):
        report = analyze(sine(100.0), SAMPLE_RATE)
        bands = {band.label: band.normalized_db for band in report.bands}

        self.assertGreater(bands["80-160 Hz"], bands["320-630 Hz"] + 30.0)
        self.assertGreater(bands["80-160 Hz"], bands["2.5-5k"] + 30.0)

    def test_identical_reports_compare_to_zero_with_no_suggestions(self):
        report = analyze(sine(1000.0), SAMPLE_RATE)
        comparison = compare(report, report)

        for diff in comparison.band_differences_db.values():
            self.assertAlmostEqual(diff, 0.0, places=6)
        self.assertAlmostEqual(comparison.crest_factor_difference_db, 0.0, places=6)
        self.assertEqual(comparison.suggestions, [])

    def test_known_band_difference_creates_directional_suggestion(self):
        yours = _manual_report({"320-630 Hz": -8.0})
        reference = _manual_report({"320-630 Hz": -12.0})

        comparison = compare(yours, reference)

        self.assertAlmostEqual(comparison.band_differences_db["320-630 Hz"], 4.0)
        eq_suggestions = [s for s in comparison.suggestions if s.category == "EQ"]
        self.assertTrue(any(s.target == "320-630 Hz" and s.action == "Cut" for s in eq_suggestions))

    def test_crest_factor_matches_known_peak_rms_ratio(self):
        audio = sine(1000.0)

        self.assertAlmostEqual(crest_factor(audio), 20.0 * math.log10(math.sqrt(2.0)), places=2)

    def test_json_serialization_round_trip(self):
        yours = analyze(sine(1000.0), SAMPLE_RATE)
        reference = analyze(sine(2000.0), SAMPLE_RATE)
        comparison = compare(yours, reference, matched_lufs=-18.0, capture_seconds=6.0)
        comparison.saved_to = "logs/spectral_compare_demo.json"

        encoded = json.dumps(comparison.to_dict())
        decoded = ComparisonReport.from_dict(json.loads(encoded))

        self.assertEqual(decoded.matched_lufs, -18.0)
        self.assertEqual(decoded.saved_to, "logs/spectral_compare_demo.json")
        self.assertEqual(len(decoded.yours.third_octave_bands), len(yours.third_octave_bands))

    def test_format_report_includes_required_sections(self):
        comparison = compare(
            analyze(sine(800.0), SAMPLE_RATE),
            analyze(sine(3000.0), SAMPLE_RATE),
            matched_lufs=-18.0,
            capture_seconds=6.0,
        )
        comparison.saved_to = "logs/spectral_compare_demo.json"

        report = format_report(comparison)

        self.assertIn("Spectral comparison (matched at -18 LUFS, 6s capture):", report)
        self.assertIn("Frequency balance", report)
        self.assertIn("Dynamics:", report)
        self.assertIn("Stereo:", report)
        self.assertIn("Brightness", report)
        self.assertIn("Saved to: logs/spectral_compare_demo.json", report)


def _manual_report(overrides):
    labels = [
        "60-80 Hz",
        "80-160 Hz",
        "160-320 Hz",
        "320-630 Hz",
        "630-1.25k",
        "1.25-2.5k",
        "2.5-5k",
        "5-10k",
        "10-16k",
    ]
    bands = [
        BandPower(0.0, 0.0, label, overrides.get(label, -10.0), overrides.get(label, -10.0))
        for label in labels
    ]
    return SpectralReport(
        sample_rate=SAMPLE_RATE,
        duration_seconds=1.0,
        total_power_db=-3.0,
        crest_factor_db=10.0,
        spectral_centroid_hz=2000.0,
        spectral_bandwidth_hz=1000.0,
        mid_side_ratio=0.8,
        bands=bands,
        third_octave_bands=bands,
    )


if __name__ == "__main__":
    unittest.main()

