import argparse
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from analysis.audio_capture import (
    AudioCaptureError,
    CaptureDevice,
    capture_reference_and_user,
    capture_track,
    resolve_capture_device,
)
from scripts import spectral_compare


class FakeBridge:
    def __init__(self):
        self.calls = []
        self.tracks = [
            {"index": 2, "name": "3-Group"},
            {"index": 7, "name": "Reference"},
            {"index": 8, "name": "Other"},
        ]

    def find_track_by_name(self, query):
        query = str(query).lower()
        return [
            {"index": track["index"], "name": track["name"]}
            for track in self.tracks
            if query in track["name"].lower()
        ]

    def get_track_list(self):
        self.calls.append(("get_track_list",))
        return list(self.tracks)

    def solo_track(self, track_index, soloed):
        self.calls.append(("solo_track", track_index, soloed))

    def execute(self, func_name, args):
        self.calls.append(("execute", func_name, args))
        return {"success": True}


def fake_devices(arg=None):
    devices = [
        {"name": "Loop-back 1/2 (Audient iD14)", "max_input_channels": 2, "default_samplerate": 44100.0, "hostapi": 0},
        {"name": "Loop-back 1/2 (Audient iD14)", "max_input_channels": 2, "default_samplerate": 48000.0, "hostapi": 1},
        {"name": "Analogue 1/2", "max_input_channels": 2, "default_samplerate": 48000.0, "hostapi": 1},
    ]
    if arg is None:
        return devices
    return devices[int(arg)]


def fake_hostapis(arg):
    return [{"name": "Windows WASAPI"}, {"name": "Windows DirectSound"}][int(arg)]


class TestSpectralCompareCapture(unittest.TestCase):
    def test_synthetic_silence_triggers_before_analysis(self):
        bridge = FakeBridge()

        with mock.patch(
            "analysis.audio_capture.capture_track",
            side_effect=[
                np.zeros((1024, 2), dtype=np.float32),
                np.ones((1024, 2), dtype=np.float32) * 0.25,
            ],
        ), self.assertRaises(AudioCaptureError) as ctx:
            capture_reference_and_user(
                bridge,
                reference_track=7,
                user_track=2,
                capture_device=43,
                capture_seconds=1.0,
                sample_rate=44100,
                silence_threshold_db=-60.0,
            )

        self.assertIn("Reference capture is silent", str(ctx.exception))

    def test_script_aborts_on_silence_before_spectral_analysis(self):
        args = argparse.Namespace(
            reference_track="reference",
            my_vocal_group="3-Group",
            capture_device=None,
            capture_device_index=43,
            capture_seconds=1.0,
            sample_rate=None,
            channels=2,
            silence_threshold=-60.0,
            output_dir="unused",
        )
        with mock.patch(
            "scripts.spectral_compare.setup_comparison.AbletonBridgeClient",
            return_value=FakeBridge(),
        ), mock.patch(
            "scripts.spectral_compare.resolve_capture_device",
            return_value=CaptureDevice(device=43, sample_rate=44100, label="43: Loop-back"),
        ), mock.patch(
            "analysis.audio_capture.capture_track",
            side_effect=[
                np.ones((1024, 2), dtype=np.float32) * 0.2,
                np.zeros((1024, 2), dtype=np.float32),
            ],
        ), mock.patch("scripts.spectral_compare.analyze") as analyze_mock:
            with self.assertRaises(AudioCaptureError) as ctx:
                spectral_compare.run(args)

        self.assertIn("Your vocal group capture is silent", str(ctx.exception))
        analyze_mock.assert_not_called()

    def test_non_silence_allows_script_analysis(self):
        args = argparse.Namespace(
            reference_track="reference",
            my_vocal_group="3-Group",
            capture_device="Loop-back 1/2",
            capture_device_index=43,
            capture_seconds=1.0,
            sample_rate=None,
            channels=2,
            silence_threshold=-60.0,
            output_dir=None,
        )
        with tempfile.TemporaryDirectory() as tmp:
            args.output_dir = tmp
            with mock.patch(
                "scripts.spectral_compare.setup_comparison.AbletonBridgeClient",
                return_value=FakeBridge(),
            ), mock.patch(
                "scripts.spectral_compare.resolve_capture_device",
                return_value=CaptureDevice(device=43, sample_rate=44100, label="43: Loop-back"),
            ), mock.patch(
                "analysis.audio_capture.capture_track",
                side_effect=[
                    np.ones((44100, 2), dtype=np.float32) * 0.15,
                    np.ones((44100, 2), dtype=np.float32) * 0.20,
                ],
            ):
                report, output_path = spectral_compare.run(args)

        self.assertIn("Spectral comparison", report)
        self.assertTrue(Path(output_path).name.startswith("spectral_compare_"))

    def test_capture_device_index_overrides_ambiguous_string(self):
        device = resolve_capture_device(
            capture_device="Loop-back 1/2",
            capture_device_index=1,
            query_devices=fake_devices,
            query_hostapis=fake_hostapis,
        )

        self.assertEqual(device.device, 1)
        self.assertEqual(device.sample_rate, 48000)

    def test_sample_rate_auto_detects_from_device(self):
        device = resolve_capture_device(
            capture_device_index=0,
            query_devices=fake_devices,
            query_hostapis=fake_hostapis,
        )

        self.assertEqual(device.sample_rate, 44100)

    def test_ambiguous_string_name_errors_with_indices(self):
        with self.assertRaises(AudioCaptureError) as ctx:
            resolve_capture_device(
                capture_device="Loop-back 1/2",
                query_devices=fake_devices,
                query_hostapis=fake_hostapis,
            )

        self.assertIn("ambiguous", str(ctx.exception))
        self.assertIn("[0]", str(ctx.exception))
        self.assertIn("[1]", str(ctx.exception))

    def test_capture_track_unsolos_every_track_then_solos_target(self):
        bridge = FakeBridge()
        with mock.patch(
            "analysis.audio_capture.capture_loopback",
            return_value=np.ones((128, 2), dtype=np.float32),
        ):
            capture_track(
                bridge,
                track_index=2,
                capture_device=43,
                capture_seconds=1.0,
                sample_rate=44100,
                preroll_seconds=0.0,
            )

        solo_calls = [call for call in bridge.calls if call[0] == "solo_track"]
        self.assertEqual(
            solo_calls,
            [
                ("solo_track", 2, False),
                ("solo_track", 7, False),
                ("solo_track", 8, False),
                ("solo_track", 2, True),
            ],
        )


if __name__ == "__main__":
    unittest.main()
