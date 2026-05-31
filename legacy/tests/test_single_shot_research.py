"""
Tests for single-shot research — verifies 1-LLM-call budget and artifact schema.
"""

import os
import sys
import json
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.single_shot_research import (
    research_chain_single_shot,
    build_fallback_artifact,
    _parse_artifact_json,
)

# Sample valid JSON the LLM would return
_VALID_LLM_RESPONSE = json.dumps({
    "artist": "Travis Scott",
    "song": "Utopia",
    "track_type": "vocal",
    "style_description": "Dark, auto-tuned vocal with heavy processing.",
    "confidence": 0.85,
    "chain": [
        {
            "plugin_name": "EQ Eight",
            "category": "eq",
            "purpose": "high_pass",
            "parameters": {"1 Frequency A": 100.0},
            "fallbacks": [],
        },
        {
            "plugin_name": "Compressor",
            "category": "compressor",
            "purpose": "dynamics",
            "parameters": {"Threshold": -18.0, "Ratio": 4.0},
            "fallbacks": ["Glue Compressor"],
        },
    ],
    "safe_ranges": {"Threshold": [-40.0, 0.0]},
    "notes": "Test chain",
})


class TestSingleShotResearch(unittest.TestCase):

    def _mock_llm_client(self, content=_VALID_LLM_RESPONSE, success=True):
        """Create a mock LLM client that returns the given content."""
        response = SimpleNamespace(
            success=success,
            content=content,
            error=None if success else "mock error",
        )
        client = MagicMock()
        client.generate = AsyncMock(return_value=response)
        return client

    # ── Single call budget ────────────────────────────────────────────
    def test_exactly_one_llm_call(self):
        client = self._mock_llm_client()
        result = asyncio.run(
            research_chain_single_shot("Travis Scott vocal chain", client)
        )
        self.assertIsNotNone(result)
        client.generate.assert_awaited_once()

    # ── Artifact schema validation ────────────────────────────────────
    def test_artifact_has_required_fields(self):
        client = self._mock_llm_client()
        artifact = asyncio.run(
            research_chain_single_shot("Travis Scott vocal chain", client)
        )
        self.assertIn("chain", artifact)
        self.assertIn("confidence", artifact)
        self.assertIn("source", artifact)
        self.assertIn("query", artifact)
        self.assertIsInstance(artifact["chain"], list)
        self.assertGreater(len(artifact["chain"]), 0)

    def test_chain_devices_have_required_fields(self):
        client = self._mock_llm_client()
        artifact = asyncio.run(
            research_chain_single_shot("Travis Scott vocal chain", client)
        )
        for dev in artifact["chain"]:
            self.assertIn("plugin_name", dev)
            self.assertIn("category", dev)
            self.assertIn("parameters", dev)

    # ── LLM failure → None ───────────────────────────────────────────
    def test_returns_none_on_failure(self):
        client = self._mock_llm_client(content="", success=False)
        result = asyncio.run(
            research_chain_single_shot("test query", client)
        )
        self.assertIsNone(result)

    def test_returns_none_on_garbage_response(self):
        client = self._mock_llm_client(content="This is not JSON at all")
        result = asyncio.run(
            research_chain_single_shot("test query", client)
        )
        self.assertIsNone(result)

    # ── Model ID pass-through ────────────────────────────────────────
    def test_model_id_passed_to_client(self):
        client = self._mock_llm_client()
        asyncio.run(
            research_chain_single_shot("test", client, model_id="custom-model")
        )
        call_kwargs = client.generate.call_args
        self.assertEqual(call_kwargs.kwargs.get("model_id"), "custom-model")


class TestParseArtifactJson(unittest.TestCase):
    def test_plain_json(self):
        result = _parse_artifact_json('{"key": "value"}')
        self.assertEqual(result, {"key": "value"})

    def test_markdown_fenced_json(self):
        result = _parse_artifact_json('```json\n{"key": "value"}\n```')
        self.assertEqual(result, {"key": "value"})

    def test_json_with_preamble(self):
        result = _parse_artifact_json('Here is the result:\n{"key": "value"}')
        self.assertEqual(result, {"key": "value"})

    def test_empty_returns_none(self):
        self.assertIsNone(_parse_artifact_json(""))
        self.assertIsNone(_parse_artifact_json(None))


class TestFallbackArtifact(unittest.TestCase):
    def test_vocal_fallback_has_chain(self):
        fb = build_fallback_artifact("test query", track_type="vocal")
        self.assertIn("chain", fb)
        self.assertGreater(len(fb["chain"]), 0)
        self.assertEqual(fb["source"], "fallback-stock")
        self.assertLess(fb["confidence"], 0.5)

    def test_non_vocal_fallback(self):
        fb = build_fallback_artifact("test", track_type="instrument")
        self.assertEqual(fb["track_type"], "instrument")


if __name__ == "__main__":
    unittest.main(verbosity=2)
