import unittest
from unittest.mock import patch

from scripts import remember_chain


class TestRememberChain(unittest.TestCase):
    def _patch_common(self, current_params):
        template = [
            {
                "plugin_suggestions": ["CLA Vocals"],
                "settings": {"Compress": 0.5, "Reverb": 0.3, "Delay": 0.2},
            }
        ]
        owned = {"host": {"Waves": ["CLA Vocals"], "Ableton Stock": []}}

        def execute(func_name, args):
            if func_name == "get_track_devices":
                return {"success": True, "devices": ["CLA Vocals"]}
            if func_name == "get_device_parameters":
                return {"success": True, "parameters": current_params}
            raise AssertionError(f"Unexpected bridge call: {func_name}")

        return patch.multiple(
            remember_chain,
            load_template_chain=lambda style: template,
            load_owned_plugins=lambda: owned,
            load_overrides=lambda style: {},
            _execute=execute,
        )

    def test_diff_captures_tweaked_values(self):
        with self._patch_common({"Compress": 0.35, "Reverb": 0.45, "Delay": 0.2}):
            overrides, summaries, warnings = remember_chain.diff_overrides(0, "cla_modern_pop")

        self.assertEqual(
            overrides,
            {"device_0": {"Compress": 0.35, "Reverb": 0.45}},
        )
        self.assertFalse(warnings)
        self.assertIn("Compress: 0.50 -> 0.35", summaries)
        self.assertIn("Reverb: 0.30 -> 0.45", summaries)

    def test_epsilon_filtering_omits_near_unchanged_params(self):
        with self._patch_common({"Compress": 0.509, "Reverb": 0.3, "Delay": 0.215}):
            overrides, summaries, warnings = remember_chain.diff_overrides(0, "cla_modern_pop")

        self.assertEqual(overrides, {"device_0": {"Delay": 0.215}})
        self.assertEqual(summaries, ["Delay: 0.20 -> 0.21"])
        self.assertFalse(warnings)

    def test_main_saves_computed_diff(self):
        with self._patch_common({"Compress": 0.35, "Reverb": 0.3, "Delay": 0.2}):
            with patch.object(remember_chain, "save_overrides") as save_overrides:
                with patch("sys.argv", [
                    "remember_chain.py",
                    "--track",
                    "0",
                    "--style",
                    "cla_modern_pop",
                    "--note",
                    "less compression",
                ]):
                    self.assertEqual(remember_chain.main(), 0)

        save_overrides.assert_called_once_with(
            "cla_modern_pop",
            {"device_0": {"Compress": 0.35}},
            "less compression",
        )


if __name__ == "__main__":
    unittest.main()
