import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from preferences import chain_preferences


class TestChainPreferences(unittest.TestCase):
    def test_save_then_load_overrides_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(chain_preferences, "PREFERENCES_DIR", Path(tmp)):
                overrides = {"device_2": {"Compress": 0.35, "Reverb": 0.45}}

                path = chain_preferences.save_overrides(
                    "cla_modern_pop",
                    overrides,
                    note="less compression",
                )

                self.assertTrue(path.exists())
                self.assertEqual(
                    chain_preferences.load_overrides("cla_modern_pop"),
                    overrides,
                )

    def test_merge_with_template_applies_overrides(self):
        template = [
            {"plugin_suggestions": ["CLA Vocals"], "settings": {"Compress": 0.5, "Reverb": 0.3}},
            {"plugin_suggestions": ["Vocal Rider"]},
        ]
        overrides = {"device_0": {"Compress": 0.35}}

        merged = chain_preferences.merge_with_template(template, overrides)

        self.assertEqual(merged[0]["settings"]["Compress"], 0.35)
        self.assertEqual(merged[0]["settings"]["Reverb"], 0.3)
        self.assertNotEqual(id(merged), id(template))

    def test_empty_overrides_returns_template_unchanged(self):
        template = [{"plugin_suggestions": ["CLA Vocals"], "settings": {"Compress": 0.5}}]

        merged = chain_preferences.merge_with_template(template, {})

        self.assertEqual(merged, template)
        self.assertNotEqual(id(merged), id(template))


if __name__ == "__main__":
    unittest.main()
