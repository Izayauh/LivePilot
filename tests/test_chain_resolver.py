import unittest

from plugins.chain_resolver import resolve_plugin


class TestChainResolver(unittest.TestCase):
    def test_picks_waves_over_stock_when_both_listed(self):
        owned = {
            "host": {
                "Waves": ["CLA-76"],
                "Ableton Stock": ["Compressor"],
            }
        }

        self.assertEqual(
            resolve_plugin(["Compressor", "CLA-76"], owned),
            ("CLA-76", "Waves"),
        )

    def test_picks_first_owned_match_when_only_stock_available(self):
        owned = {
            "host": {
                "Waves": [],
                "Ableton Stock": ["Compressor", "Glue Compressor"],
            }
        }

        self.assertEqual(
            resolve_plugin(["Limiter", "Glue Compressor", "Compressor"], owned),
            ("Glue Compressor", "Ableton Stock"),
        )

    def test_raises_when_nothing_matches_owned(self):
        owned = {
            "host": {
                "Waves": ["CLA Vocals"],
                "Ableton Stock": ["EQ Eight"],
            }
        }

        with self.assertRaises(ValueError):
            resolve_plugin(["Unknown Plugin"], owned)


if __name__ == "__main__":
    unittest.main()
