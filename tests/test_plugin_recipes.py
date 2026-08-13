import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from livepilot_tools import plugin_recipes


class TestPluginRecipes(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_dir = plugin_recipes.RECIPES_DIR
        plugin_recipes.RECIPES_DIR = Path(self._tmpdir.name)

    def tearDown(self):
        plugin_recipes.RECIPES_DIR = self._orig_dir
        self._tmpdir.cleanup()

    def test_list_empty(self):
        result = plugin_recipes.list_plugin_recipes()
        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 0)

    def test_save_and_load_round_trip(self):
        controller = MagicMock()
        controller.get_device_parameters_name_sync.return_value = {
            "success": True,
            "names": ["Volume", "Device On"],
        }
        controller.get_device_parameter_value_sync.side_effect = [
            {"success": True, "value": 0.75},
            {"success": True, "value": 1.0},
        ]
        controller.get_device_name.return_value = {"success": True, "name": "Kontakt"}
        controller.get_device_class_name.return_value = {
            "success": True,
            "class_name": "PluginDevice",
        }

        saved = plugin_recipes.save_plugin_recipe(
            "test-piano",
            track_index=0,
            device_index=1,
            controller=controller,
            note="unit test",
        )
        self.assertTrue(saved["success"])
        self.assertEqual(saved["param_count"], 2)

        loaded = plugin_recipes.load_plugin_recipe("test-piano")
        self.assertTrue(loaded["success"])
        self.assertEqual(loaded["recipe"]["params"]["Volume"], 0.75)

        listed = plugin_recipes.list_plugin_recipes()
        self.assertEqual(listed["count"], 1)

    def test_apply_calls_reliable(self):
        recipe_path = plugin_recipes.RECIPES_DIR / "apply-me.json"
        recipe_path.write_text(
            json.dumps(
                {
                    "schema": plugin_recipes.RECIPE_SCHEMA,
                    "name": "apply-me",
                    "params": {"Volume": 0.5},
                }
            ),
            encoding="utf-8",
        )

        reliable = MagicMock()
        reliable.set_parameters_by_name.return_value = {
            "success": True,
            "verified": 1,
        }

        result = plugin_recipes.apply_plugin_recipe(
            "apply-me",
            track_index=2,
            device_index=0,
            reliable=reliable,
        )
        self.assertTrue(result["success"])
        reliable.set_parameters_by_name.assert_called_once_with(
            2, 0, {"Volume": 0.5}
        )


if __name__ == "__main__":
    unittest.main()
