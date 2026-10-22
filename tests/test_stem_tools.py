import unittest
from unittest.mock import MagicMock, call

from livepilot_tools.stem_tools import normalize_full_length_stems


class TestNormalizeFullLengthStems(unittest.TestCase):
    def test_normalizes_each_clip_and_restarts_scene(self):
        controller = MagicMock()
        controller.set_tempo.return_value = {"success": True}
        controller.set_audio_clip_warping.return_value = {"success": True}
        controller.set_audio_clip_looping.return_value = {"success": True}
        controller.set_audio_clip_start_marker.return_value = {"success": True}
        controller.set_audio_clip_loop_start.return_value = {"success": True}
        controller.set_audio_clip_end_marker.return_value = {"success": True}
        controller.set_audio_clip_loop_end.return_value = {"success": True}
        controller.fire_scene.return_value = {"success": True}

        result = normalize_full_length_stems(
            bpm=152,
            track_indices=[1, 2, 3],
            clip_index=0,
            duration_seconds=170.1547,
            scene_index=0,
            controller=controller,
        )

        self.assertTrue(result["success"])
        controller.set_tempo.assert_called_once_with(152.0)
        controller.set_audio_clip_warping.assert_has_calls(
            [call(1, 0, False), call(2, 0, False), call(3, 0, False)]
        )
        controller.set_audio_clip_looping.assert_has_calls(
            [call(1, 0, False), call(2, 0, False), call(3, 0, False)]
        )
        controller.set_audio_clip_start_marker.assert_has_calls(
            [call(1, 0, 0.0), call(2, 0, 0.0), call(3, 0, 0.0)]
        )
        controller.set_audio_clip_loop_start.assert_has_calls(
            [call(1, 0, 0.0), call(2, 0, 0.0), call(3, 0, 0.0)]
        )
        controller.set_audio_clip_end_marker.assert_has_calls(
            [
                call(1, 0, 170.1547),
                call(2, 0, 170.1547),
                call(3, 0, 170.1547),
            ]
        )
        controller.set_audio_clip_loop_end.assert_has_calls(
            [
                call(1, 0, 170.1547),
                call(2, 0, 170.1547),
                call(3, 0, 170.1547),
            ]
        )
        controller.fire_scene.assert_called_once_with(0)

    def test_rejects_duplicate_tracks(self):
        with self.assertRaises(ValueError):
            normalize_full_length_stems(
                bpm=152,
                track_indices=[1, 1],
                controller=MagicMock(),
            )

    def test_stops_after_failed_tempo_change(self):
        controller = MagicMock()
        controller.set_tempo.return_value = {"success": False}

        result = normalize_full_length_stems(
            bpm=152,
            track_indices=[1],
            controller=controller,
        )

        self.assertFalse(result["success"])
        controller.set_audio_clip_warping.assert_not_called()


if __name__ == "__main__":
    unittest.main()
