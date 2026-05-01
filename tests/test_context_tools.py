import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from context.session_manager import SessionManager
from librarian.session_context import LibrarianSessionContext
from livepilot_tools.context_tools import (
    analyze_clip_context,
    get_creative_context,
    get_project_intent,
    set_project_intent,
)


class FakeController:
    def get_tempo(self):
        return {"success": True, "tempo": 92.0}

    def get_track_list(self):
        return {
            "success": True,
            "tracks": [
                {"index": 0, "number": 1, "name": "Piano", "armed": False},
                {"index": 1, "number": 2, "name": "Lead Vocal", "muted": False, "armed": True},
            ],
        }

    def get_num_scenes(self):
        return {"success": True, "num_scenes": 8}


class FakeMidiClipController(FakeController):
    def get_clip_info(self, track_index, clip_index):
        return {
            "success": True,
            "clip": {
                "name": f"Clip {track_index}:{clip_index}",
                "length_beats": 4.0,
            },
        }

    def get_clip_notes(self, track_index, clip_index):
        return {
            "success": True,
            "notes": [
                {"pitch": 60, "start": 0.0, "duration": 1.0, "velocity": 80},
                {"pitch": 64, "start": 1.0, "duration": 0.5, "velocity": 100},
                {"pitch": 67, "start": 2.5, "duration": 1.5, "velocity": 90},
            ],
        }


class CreativeContextTests(unittest.TestCase):
    def test_creative_context_combines_session_controller_and_librarian(self):
        manager = SessionManager()
        manager.project_name = "Trust Me Sketch"
        manager.detected_genre = "rnb"
        manager.mixing_stage = "arrangement"
        manager.update_transport(is_playing=True, is_recording=False, tempo=76.0, position=32.0)
        manager.state.loop_enabled = True
        manager.state.loop_start = 16.0
        manager.state.loop_length = 8.0
        manager.state.selected_track = 1
        manager.state.selected_scene = 2
        manager.update_track(0, name="Cached Piano", has_clips=True)
        manager.record_action("set_tempo", {"bpm": 76})

        librarian = LibrarianSessionContext()
        librarian.set_active(
            {
                "song": "Trust Me",
                "artist": "The Fray",
                "sections": {
                    "verse": {
                        "chain": [
                            {"name": "EQ Eight", "type": "eq", "why": "clear piano mud"},
                        ]
                    }
                },
            },
            "verse",
            track_index=1,
            song_file="trust_me.json",
        )

        context = get_creative_context(
            controller=FakeController(),
            session_manager=manager,
            librarian_context=librarian,
            project_intent_path=Path("missing-test-intent.json"),
        )

        self.assertEqual(context["transport"]["tempo"], 92.0)
        self.assertTrue(context["transport"]["playing"])
        self.assertEqual(context["loop"]["start_beats"], 16.0)
        self.assertEqual(context["tracks"]["count"], 2)
        self.assertEqual(context["selected"]["track"]["name"], "Lead Vocal")
        self.assertEqual(context["active_librarian"]["song"], "Trust Me")
        self.assertEqual(context["active_librarian"]["section"], "verse")
        self.assertEqual(context["active_librarian"]["chain"][0]["name"], "EQ Eight")
        self.assertEqual(context["recent_actions"][0]["action"], "set_tempo")
        self.assertEqual(context["project"]["num_scenes"], 8)

    def test_analyze_clip_context_summarizes_accessible_midi_notes(self):
        result = analyze_clip_context(
            track_index=0,
            clip_index=1,
            controller=FakeMidiClipController(),
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["track_index"], 0)
        self.assertEqual(result["clip_index"], 1)
        self.assertEqual(result["clip_name"], "Clip 0:1")
        self.assertEqual(result["clip_length_beats"], 4.0)
        self.assertEqual(result["note_count"], 3)
        self.assertEqual(result["pitch_min"], 60)
        self.assertEqual(result["pitch_max"], 67)
        self.assertEqual(result["pitch_range"], 7)
        self.assertEqual(result["velocity_min"], 80.0)
        self.assertEqual(result["velocity_max"], 100.0)
        self.assertEqual(result["average_velocity"], 90.0)
        self.assertEqual(result["note_start_min"], 0.0)
        self.assertEqual(result["note_end_max"], 4.0)
        self.assertEqual(result["density_notes_per_beat"], 0.75)
        self.assertEqual(result["missing_fields"], [])
        self.assertEqual(result["limitations"], [])

    def test_analyze_clip_context_reports_missing_controller_fields(self):
        result = analyze_clip_context(
            track_index=0,
            clip_index=0,
            controller=FakeController(),
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["track_index"], 0)
        self.assertEqual(result["clip_index"], 0)
        self.assertIsNone(result["note_count"])
        self.assertIn("clip_name", result["missing_fields"])
        self.assertIn("note_count", result["missing_fields"])
        self.assertIn("density_notes_per_beat", result["missing_fields"])
        self.assertIn("Current controller exposes no MIDI note reader for clips.", result["limitations"])

    def test_creative_context_includes_selected_clip_context(self):
        manager = SessionManager()
        manager.state.selected_track = 0
        manager.state.selected_scene = 1

        context = get_creative_context(
            controller=FakeMidiClipController(),
            session_manager=manager,
            librarian_context=LibrarianSessionContext(),
            project_intent_path=Path("missing-test-intent.json"),
        )

        self.assertEqual(context["selected_clip"]["track_index"], 0)
        self.assertEqual(context["selected_clip"]["clip_index"], 1)
        self.assertEqual(context["selected_clip"]["note_count"], 3)
        self.assertEqual(context["selected_clip"]["pitch_range"], 7)

    def test_creative_context_reports_missing_live_fields_without_controller(self):
        manager = SessionManager()
        manager.update_track(0, name="Piano", muted=True)

        context = get_creative_context(
            session_manager=manager,
            librarian_context=LibrarianSessionContext(),
            project_intent_path=Path("missing-test-intent.json"),
        )

        self.assertEqual(context["tracks"]["items"][0]["name"], "Piano")
        self.assertIn("live_tracks", context["known_limitations"]["missing_fields"])
        self.assertIn("active_librarian", context["known_limitations"]["missing_fields"])
        self.assertEqual(context["active_librarian"]["chain"], [])

    def test_project_intent_persists_and_merges_into_creative_context(self):
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "project_intent.json"
            result = set_project_intent(
                {
                    "genre": "rnb",
                    "mood": "intimate",
                    "references": ["Trust Me - The Fray"],
                    "arrangement_goal": "preserve groove while improving emotional lift",
                    "prefer": ["warm piano"],
                    "avoid": ["fake listening claims", "overbusy low end"],
                    "notes": "Keep the vocal lane open.",
                },
                storage_path=path,
            )

            self.assertTrue(result["success"])
            self.assertTrue(path.exists())
            self.assertEqual(result["project_intent"]["genre"], "rnb")
            self.assertIsNotNone(result["project_intent"]["updated_at"])

            loaded = get_project_intent(storage_path=path)
            self.assertTrue(loaded["success"])
            self.assertEqual(loaded["project_intent"]["mood"], "intimate")

            context = get_creative_context(
                session_manager=SessionManager(),
                librarian_context=LibrarianSessionContext(),
                project_intent_path=path,
            )
            self.assertEqual(context["project_intent"]["references"], ["Trust Me - The Fray"])
            self.assertNotIn("project_intent", context["known_limitations"]["missing_fields"])

    def test_set_project_intent_rejects_non_dict(self):
        result = set_project_intent(["not", "a", "dict"])

        self.assertFalse(result["success"])
        self.assertIn("dict", result["message"])


if __name__ == "__main__":
    unittest.main()
