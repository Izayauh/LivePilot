"""
Tests for ArtifactChainStore — filesystem-backed vocal chain cache.
"""

import os
import sys
import json
import shutil
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge.artifact_chain_store import ArtifactChainStore


def _sample_artifact(query="Travis Scott Utopia vocal chain", confidence=0.85):
    return {
        "artist": "Travis Scott",
        "song": "Utopia",
        "track_type": "vocal",
        "style_description": "Dark, processed, heavily auto-tuned vocal",
        "confidence": confidence,
        "source": "test",
        "chain": [
            {
                "plugin_name": "EQ Eight",
                "category": "eq",
                "purpose": "high_pass_cleanup",
                "parameters": {"1 Frequency A": 100.0},
                "fallbacks": [],
            },
            {
                "plugin_name": "Compressor",
                "category": "compressor",
                "purpose": "dynamics_control",
                "parameters": {"Threshold": -18.0, "Ratio": 4.0},
                "fallbacks": ["Glue Compressor"],
            },
        ],
    }


class TestArtifactChainStore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.store = ArtifactChainStore(self._tmp)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    # ── Save / Load Round-Trip ────────────────────────────────────────
    def test_save_and_load_exact(self):
        query = "Travis Scott Utopia vocal chain"
        artifact = _sample_artifact(query)
        key = self.store.save_artifact(query, artifact)

        loaded = self.store.load_artifact(query)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["artist"], "Travis Scott")
        self.assertEqual(len(loaded["chain"]), 2)
        self.assertEqual(loaded["_cache_match"], "exact")
        self.assertEqual(loaded["version"], 1)
        self.assertIn("created_at", loaded)

    # ── Fuzzy Matching ────────────────────────────────────────────────
    def test_fuzzy_match_similar_query(self):
        self.store.save_artifact(
            "Travis Scott Utopia vocal chain",
            _sample_artifact(),
        )
        # Slightly different phrasing
        loaded = self.store.load_artifact("travis scott utopia vocal")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["_cache_match"], "fuzzy")

    def test_fuzzy_match_too_different_returns_none(self):
        self.store.save_artifact(
            "Travis Scott Utopia vocal chain",
            _sample_artifact(),
        )
        loaded = self.store.load_artifact("jazz piano reverb")
        self.assertIsNone(loaded)

    # ── Staleness ─────────────────────────────────────────────────────
    def test_fresh_artifact_not_stale(self):
        artifact = _sample_artifact()
        self.store.save_artifact("test", artifact)
        loaded = self.store.load_artifact("test")
        self.assertFalse(self.store.is_stale(loaded, max_age_days=30))

    def test_old_artifact_is_stale(self):
        artifact = _sample_artifact()
        artifact["created_at"] = "2020-01-01T00:00:00"
        self.store.save_artifact("test", artifact)
        loaded = self.store.load_artifact("test")
        self.assertTrue(self.store.is_stale(loaded, max_age_days=30))

    # ── get_artifact_for_execution ────────────────────────────────────
    def test_execution_returns_none_for_stale(self):
        artifact = _sample_artifact()
        artifact["created_at"] = "2020-01-01T00:00:00"
        self.store.save_artifact("stale query", artifact)
        result = self.store.get_artifact_for_execution("stale query", max_age_days=30)
        self.assertIsNone(result)

    def test_execution_returns_fresh_artifact(self):
        self.store.save_artifact("fresh query", _sample_artifact())
        result = self.store.get_artifact_for_execution("fresh query")
        self.assertIsNotNone(result)

    # ── List & Delete ─────────────────────────────────────────────────
    def test_list_artifacts(self):
        self.store.save_artifact("query 1", _sample_artifact("query 1"))
        self.store.save_artifact("query 2", _sample_artifact("query 2"))
        items = self.store.list_artifacts()
        self.assertEqual(len(items), 2)
        for item in items:
            self.assertIn("key", item)
            self.assertIn("plugin_count", item)

    def test_delete_artifact(self):
        self.store.save_artifact("to delete", _sample_artifact())
        self.assertTrue(self.store.delete_artifact("to delete"))
        self.assertIsNone(self.store.load_artifact("to delete"))

    def test_delete_missing_returns_false(self):
        self.assertFalse(self.store.delete_artifact("nonexistent"))


class TestQuerySimilarity(unittest.TestCase):
    def test_identical(self):
        score = ArtifactChainStore._query_similarity(
            "travis scott vocal", "travis scott vocal"
        )
        self.assertAlmostEqual(score, 1.0)

    def test_subset(self):
        score = ArtifactChainStore._query_similarity(
            "travis scott", "travis scott utopia vocal chain"
        )
        self.assertGreater(score, 0.3)

    def test_completely_unrelated(self):
        score = ArtifactChainStore._query_similarity(
            "travis scott", "jazz piano reverb"
        )
        self.assertLess(score, 0.2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
