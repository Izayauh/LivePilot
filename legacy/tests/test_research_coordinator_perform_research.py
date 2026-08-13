import os
import sys
import time
import asyncio
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.research_coordinator import ChainSpec, DeviceSpec, ResearchCoordinator  # noqa: E402


class TestPerformResearch(unittest.IsolatedAsyncioTestCase):
    def _make_coordinator(self) -> ResearchCoordinator:
        coordinator = ResearchCoordinator()
        coordinator._audio_analyst = object()
        coordinator._llm_client = SimpleNamespace(client=None)
        coordinator._youtube_researcher = SimpleNamespace(
            research_vocal_chain=AsyncMock()
        )
        coordinator._web_researcher = SimpleNamespace(
            research_vocal_chain=AsyncMock()
        )
        coordinator._cache_chain_spec = Mock()
        return coordinator

    async def test_perform_research_cache_hit_returns_immediately(self):
        coordinator = self._make_coordinator()
        with tempfile.TemporaryDirectory() as tmp:
            coordinator._research_cache_path = os.path.join(tmp, "research_cache.json")
            coordinator._store_cached_synthesized_answer(
                "How To Mix 808s",
                "Cached synthesized answer."
            )

            cached_chain = ChainSpec(
                query="How to mix 808s",
                style_description="Old answer",
                devices=[
                    DeviceSpec(
                        plugin_name="EQ Eight",
                        category="eq",
                        parameters={},
                        purpose="cleanup",
                        reasoning="cached",
                        confidence=0.7
                    )
                ],
                confidence=0.7,
                sources=["cache://kb"]
            )
            coordinator._get_fresh_cached_chain = Mock(return_value=cached_chain)

            result = await coordinator.perform_research("  how to mix 808s  ")

            self.assertTrue(result["cache_hit"])
            self.assertEqual(result["synthesized_answer"], "Cached synthesized answer.")
            self.assertEqual(result["chain_spec"].style_description, "Cached synthesized answer.")
            coordinator._youtube_researcher.research_vocal_chain.assert_not_awaited()
            coordinator._web_researcher.research_vocal_chain.assert_not_awaited()

    async def test_perform_research_parallel_fetch_and_model_routing(self):
        coordinator = self._make_coordinator()
        with tempfile.TemporaryDirectory() as tmp:
            coordinator._research_cache_path = os.path.join(tmp, "research_cache.json")

            async def youtube_job(**kwargs):
                await asyncio.sleep(0.2)
                return SimpleNamespace(
                    extracted_settings=[
                        {
                            "name": "EQ Eight",
                            "category": "eq",
                            "purpose": "cleanup",
                            "parameters": {"1 Gain A": {"value": -3.0, "unit": "dB", "confidence": 0.8}},
                            "sources": ["yt://1"],
                        }
                    ],
                    sources=["yt://1"],
                    confidence=0.7,
                    llm_extractions_used=1,
                )

            async def web_job(**kwargs):
                await asyncio.sleep(0.2)
                return SimpleNamespace(
                    extracted_settings=[
                        {
                            "name": "Compressor",
                            "category": "compressor",
                            "purpose": "control",
                            "parameters": {"Threshold": {"value": -18.0, "unit": "dB", "confidence": 0.8}},
                            "sources": ["web://1"],
                        }
                    ],
                    sources=["web://1"],
                    confidence=0.7,
                    llm_extractions_used=1,
                )

            coordinator._youtube_researcher.research_vocal_chain.side_effect = youtube_job
            coordinator._web_researcher.research_vocal_chain.side_effect = web_job

            coordinator.call_cheap_llm = AsyncMock(side_effect=[
                '{"artist":"Kanye","song":"","style":"hip hop","route":"complex_technique"}',
                "YouTube summary",
                "Web summary",
            ])
            coordinator.call_expensive_llm = AsyncMock(return_value="Final synthesized answer")

            start = time.monotonic()
            result = await coordinator.perform_research(
                "Kanye vocal chain",
                use_youtube=True,
                use_web=True,
                prefer_cache=False
            )
            elapsed = time.monotonic() - start

            # If fetches were sequential this would be around 0.4s+.
            self.assertLess(elapsed, 0.35)
            coordinator._youtube_researcher.research_vocal_chain.assert_awaited_once()
            coordinator._web_researcher.research_vocal_chain.assert_awaited_once()
            coordinator.call_expensive_llm.assert_awaited_once()

            self.assertFalse(result["cache_hit"])
            self.assertEqual(result["synthesized_answer"], "Final synthesized answer")
            self.assertEqual(result["chain_spec"].style_description, "Final synthesized answer")
            self.assertGreater(len(result["chain_spec"].devices), 0)
            self.assertIn("youtube", result["source_summaries"])
            self.assertIn("web", result["source_summaries"])


if __name__ == "__main__":
    unittest.main()
