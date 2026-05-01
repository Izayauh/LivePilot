import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from context.session_manager import SessionManager
from librarian.session_context import LibrarianSessionContext
from livepilot_tools.context_tools import get_creative_context, get_project_intent, set_project_intent


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
