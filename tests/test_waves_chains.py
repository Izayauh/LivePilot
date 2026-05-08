import json
import os
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestWavesChains(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(REPO_ROOT, "knowledge", "plugin_chains.json"), encoding="utf-8") as f:
            cls.chain_data = json.load(f)
        with open(os.path.join(REPO_ROOT, "config", "owned_plugins.json"), encoding="utf-8") as f:
            cls.owned_data = json.load(f)

    def test_four_templates_parse_cleanly(self):
        chains = self.chain_data.get("waves_vocal_chains", {})

        self.assertEqual(
            set(chains),
            {
                "cla_modern_pop",
                "greg_wells_pop_ballad",
                "eddie_kramer_rock_rap",
                "clean_modern_neutral",
            },
        )

        for style, style_data in chains.items():
            with self.subTest(style=style):
                self.assertIn("description", style_data)
                self.assertIn("track_type", style_data)
                self.assertIn("chain", style_data)
                self.assertEqual(len(style_data["chain"]), 5)
                for step in style_data["chain"]:
                    self.assertIn("type", step)
                    self.assertIn("purpose", step)
                    self.assertIn("plugin_suggestions", step)
                    self.assertTrue(step["plugin_suggestions"])

    def test_plugin_suggestions_match_owned_inventory(self):
        owned = set()
        for plugins in self.owned_data.get("host", {}).values():
            owned.update(plugins)

        for style, style_data in self.chain_data["waves_vocal_chains"].items():
            for step in style_data["chain"]:
                for suggestion in step["plugin_suggestions"]:
                    with self.subTest(style=style, suggestion=suggestion):
                        self.assertIn(suggestion, owned)


if __name__ == "__main__":
    unittest.main()
