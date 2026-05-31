import os
import sys
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.guardrail import LLMGuardrail, LLMCallBlocked
from research.research_coordinator import ResearchCoordinator
from research.single_shot_research import research_chain_single_shot


class _InMemoryArtifactStore:
    def __init__(self, artifact=None):
        self.artifact = artifact

    def get_artifact_for_execution(self, query, max_age_days=14):
        return self.artifact

    def save_artifact(self, query, artifact):
        self.artifact = artifact
        return "saved"


class TestStrictArtifactCutover(unittest.IsolatedAsyncioTestCase):
    def _make_coordinator(self, artifact=None):
        c = ResearchCoordinator()
        c._artifact_store = _InMemoryArtifactStore(artifact=artifact)
        c._audio_analyst = object()
        c._youtube_researcher = SimpleNamespace(research_vocal_chain=AsyncMock())
        c._web_researcher = SimpleNamespace(research_vocal_chain=AsyncMock())
        return c

    async def test_cached_chain_uses_zero_llm_calls(self):
        artifact = {
            "style_description": "Cached chain",
            "confidence": 0.9,
            "chain": [{"plugin_name": "EQ Eight", "category": "eq", "parameters": {}, "purpose": "cleanup"}],
        }
        c = self._make_coordinator(artifact=artifact)
        generate = AsyncMock()
        c._llm_client = SimpleNamespace(client=SimpleNamespace(generate=generate))

        result = await c.perform_research("travis vocal chain", prefer_cache=True)

        self.assertTrue(result["cache_hit"])
        self.assertEqual(generate.await_count, 0)
        self.assertEqual(result["chain_spec"].meta.get("llm_calls_used"), 0)

    async def test_first_cache_miss_uses_at_most_one_llm_call(self):
        c = self._make_coordinator(artifact=None)
        response = SimpleNamespace(
            success=True,
            content='{"style_description":"fresh","confidence":0.8,"chain":[{"plugin_name":"EQ Eight","category":"eq","purpose":"cleanup","parameters":{},"fallbacks":[]}]}',
        )
        generate = AsyncMock(return_value=response)
        c._llm_client = SimpleNamespace(client=SimpleNamespace(generate=generate))

        result = await c.perform_research("new artist vocal chain", prefer_cache=True, deep_research=False)

        self.assertFalse(result["cache_hit"])
        self.assertLessEqual(generate.await_count, 1)
        self.assertEqual(result["chain_spec"].meta.get("llm_calls_used"), 1)

    async def test_deep_research_only_runs_when_explicit_true(self):
        c = self._make_coordinator(artifact=None)
        response = SimpleNamespace(
            success=True,
            content='{"style_description":"fresh","confidence":0.8,"chain":[{"plugin_name":"EQ Eight","category":"eq","purpose":"cleanup","parameters":{},"fallbacks":[]}]}',
        )
        c._llm_client = SimpleNamespace(client=SimpleNamespace(generate=AsyncMock(return_value=response)))

        await c.perform_research("future vocal chain", use_youtube=True, use_web=True, deep_research=False)
        c._youtube_researcher.research_vocal_chain.assert_not_awaited()
        c._web_researcher.research_vocal_chain.assert_not_awaited()

        # Explicit deep_research=True should allow legacy multi-source path.
        c.call_cheap_llm = AsyncMock(side_effect=[
            '{"artist":"x","song":"","style":"","route":"complex_technique"}',
            "yt summary",
            "web summary",
        ])
        c.call_expensive_llm = AsyncMock(return_value="synthesized")
        c._youtube_researcher.research_vocal_chain = AsyncMock(return_value=SimpleNamespace(
            extracted_settings=[], sources=[], confidence=0.0, llm_extractions_used=0
        ))
        c._web_researcher.research_vocal_chain = AsyncMock(return_value=SimpleNamespace(
            extracted_settings=[], sources=[], confidence=0.0, llm_extractions_used=0
        ))

        await c.perform_research("future vocal chain", use_youtube=True, use_web=True, deep_research=True, prefer_cache=False)
        c._youtube_researcher.research_vocal_chain.assert_awaited_once()
        c._web_researcher.research_vocal_chain.assert_awaited_once()

    async def test_execute_phase_blocks_llm_calls_fail_closed(self):
        guardrail = LLMGuardrail()
        llm = SimpleNamespace(generate=AsyncMock())

        with self.assertRaises(LLMCallBlocked):
            with guardrail.block_phase("execute"):
                await research_chain_single_shot("any vocal chain", llm)

        self.assertEqual(llm.generate.await_count, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
