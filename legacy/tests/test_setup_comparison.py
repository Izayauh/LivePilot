import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import setup_comparison


class FakeBridge:
    def __init__(self):
        self.calls = []
        self.next_track = 10
        self.tracks = [
            {"index": 0, "name": "frerence"},
            {"index": 2, "name": "Lead Vocal"},
        ]

    def create_audio_track(self, name):
        self.calls.append(("create_audio_track", name))
        track = self.next_track
        self.next_track += 1
        return track

    def set_clip_path(self, track_index, clip_index, audio_path):
        self.calls.append(("set_clip_path", track_index, clip_index, audio_path))

    def get_clip_audio_path(self, track_index, clip_index=0):
        self.calls.append(("get_clip_audio_path", track_index, clip_index))
        return "reference.wav" if track_index == 0 else "user.wav"

    def add_utility_device(self, track_index, gain_db, name):
        self.calls.append(("add_utility_device", track_index, gain_db, name))
        return {"success": True}

    def set_track_pan(self, track_index, pan):
        self.calls.append(("set_track_pan", track_index, pan))

    def set_clip_detune(self, track_index, clip_index, cents):
        self.calls.append(("set_clip_detune", track_index, clip_index, cents))
        return {"success": True}

    def solo_track(self, track_index, soloed):
        self.calls.append(("solo_track", track_index, soloed))

    def find_track_by_name(self, query):
        self.calls.append(("find_track_by_name", query))
        query = query.lower()
        return [
            {"index": track["index"], "name": track["name"], "score": 100}
            for track in self.tracks
            if query in track["name"].lower()
        ]

    def get_track_list(self):
        self.calls.append(("get_track_list",))
        return list(self.tracks)


class TestSetupComparison(unittest.TestCase):
    def test_loudness_math_normalizes_both_tracks_to_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref = Path(tmp) / "ref.wav"
            ref.write_bytes(b"fake")
            bridge = FakeBridge()

            def fake_measure(path):
                return -8.0 if Path(path).name == "ref.wav" else -16.0

            summary = setup_comparison.setup_comparison(
                str(ref),
                my_vocal_track=2,
                bridge=bridge,
                measure_func=fake_measure,
                target_lufs=-10.0,
            )

        utility_calls = [call for call in bridge.calls if call[0] == "add_utility_device"]
        self.assertIn(("add_utility_device", 2, 6.0, "LOUDNESS-MATCH (do not adjust)"), utility_calls)
        self.assertIn(("add_utility_device", 10, -2.0, "REF LOUDNESS-MATCH (do not adjust)"), utility_calls)
        self.assertEqual(summary["my_vocal_gain_db"], 6.0)
        self.assertEqual(summary["reference_gain_db"], -2.0)

    @mock.patch("scripts.setup_comparison._run_apply_vocal_preset")
    def test_simulate_doubles_creates_two_extra_tracks(self, preset_mock):
        with tempfile.TemporaryDirectory() as tmp:
            ref = Path(tmp) / "ref.wav"
            ref.write_bytes(b"fake")
            bridge = FakeBridge()
            setup_comparison.setup_comparison(
                str(ref),
                my_vocal_track=2,
                simulate_doubles=True,
                bridge=bridge,
                measure_func=lambda path: -10.0,
                target_lufs=-10.0,
            )

        created = [call[1] for call in bridge.calls if call[0] == "create_audio_track"]
        self.assertEqual(created, ["REF: ref.wav", "MY VOX (Double L)", "MY VOX (Double R)"])
        self.assertEqual(preset_mock.call_count, 2)

    def test_reference_key_resolves_library_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref = Path(tmp) / "Jackie.wav"
            ref.write_bytes(b"fake")
            library = Path(tmp) / "reference_library.json"
            library.write_text(
                json.dumps({
                    "schemaVersion": "live-pilot/reference-library.v1",
                    "entries": {
                        "jackie_brown": {
                            "title": "Jackie Brown",
                            "artist": "Brent Faiyaz",
                            "path": str(ref),
                            "lufs": -9.7,
                            "addedAt": "2026-05-08T22:00:00Z",
                        }
                    },
                }),
                encoding="utf-8",
            )

            resolved = setup_comparison.resolve_reference(None, "jackie_brown", library)

        self.assertEqual(resolved["path"], str(ref))
        self.assertEqual(resolved["lufs"], -9.7)

    def test_reference_resolves_from_loaded_reference_track(self):
        bridge = FakeBridge()

        resolved = setup_comparison.resolve_reference(
            None,
            None,
            bridge=bridge,
            reference_track="frerence",
        )

        self.assertEqual(resolved["path"], "reference.wav")
        self.assertEqual(resolved["source_track"], 0)
        self.assertIn(("get_clip_audio_path", 0, 0), bridge.calls)

    def test_existing_reference_track_is_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref = Path(tmp) / "reference.wav"
            ref.write_bytes(b"fake")
            bridge = FakeBridge()
            summary = setup_comparison.setup_comparison(
                str(ref),
                my_vocal_track=2,
                reference_track=0,
                bridge=bridge,
                measure_func=lambda path: -10.0,
                target_lufs=-10.0,
            )

        self.assertEqual(summary["reference_track"], 0)
        self.assertNotIn(("create_audio_track", "REF: reference.wav"), bridge.calls)
        self.assertNotIn(("set_clip_path", 0, 0, str(ref)), bridge.calls)

    def test_existing_vocal_stack_gets_same_loudness_utility_and_solo(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref = Path(tmp) / "ref.wav"
            ref.write_bytes(b"fake")
            bridge = FakeBridge()
            summary = setup_comparison.setup_comparison(
                str(ref),
                my_vocal_track=2,
                my_vocal_tracks=[2, 3, 4],
                bridge=bridge,
                measure_func=lambda path: -12.0 if Path(path).name == "user.wav" else -10.0,
                target_lufs=-10.0,
            )

        self.assertEqual(summary["my_vocal_tracks"], [2, 3, 4])
        utility_calls = [call for call in bridge.calls if call[0] == "add_utility_device"]
        self.assertIn(("add_utility_device", 2, 2.0, "LOUDNESS-MATCH (do not adjust)"), utility_calls)
        self.assertIn(("add_utility_device", 3, 2.0, "LOUDNESS-MATCH (do not adjust)"), utility_calls)
        self.assertIn(("add_utility_device", 4, 2.0, "LOUDNESS-MATCH (do not adjust)"), utility_calls)
        self.assertIn(("solo_track", 2, True), bridge.calls)
        self.assertIn(("solo_track", 3, True), bridge.calls)
        self.assertIn(("solo_track", 4, True), bridge.calls)

    def test_missing_reference_file_does_not_mutate_ableton(self):
        bridge = FakeBridge()
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.wav"
            with self.assertRaises(setup_comparison.ComparisonSetupError):
                setup_comparison.setup_comparison(
                    str(missing),
                    my_vocal_track=2,
                    bridge=bridge,
                    measure_func=lambda path: -10.0,
                )

        self.assertEqual(bridge.calls, [])


if __name__ == "__main__":
    unittest.main()
