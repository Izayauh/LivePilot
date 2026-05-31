"""
Tests for research budget controls and cache-aware behavior.
"""

import os
import sys
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.research_coordinator import ResearchCoordinator, ChainSpec, DeviceSpec


class TestResearchBudgetControls(unittest.TestCase):
    def _make_coordinator(self) -> ResearchCoordinator:
        coordinator = ResearchCoordinator()
        coordinator._audio_analyst = object()
        coordinator._llm_client = SimpleNamespace(
            analyze_vocal_intent=AsyncMock(return_value={"artist": "Test", "style": "Hip Hop"}),
            generate_chain_reasoning=AsyncMock(return_value="Reasoned chain")
        )
        coordinator._youtube_researcher = SimpleNamespace(
            research_vocal_chain=AsyncMock(return_value=SimpleNamespace(
                extracted_settings=[],
                sources=[],
                confidence=0.0,
                llm_extractions_used=0
            ))
        )
        coordinator._web_researcher = SimpleNamespace(
            research_vocal_chain=AsyncMock(return_value=SimpleNamespace(
                extracted_settings=[],
                sources=[],
                confidence=0.0,
                llm_extractions_used=0
            ))
        )
        return coordinator

    def test_policy_resolution_cheap(self):
        coordinator = self._make_coordinator()

        policy = coordinator._resolve_research_policy(
            budget_mode="cheap",
            max_sources=5,
            max_total_llm_calls=3,
            prefer_cache=True,
            cache_max_age_days=21
        )

        self.assertEqual(policy.mode, "cheap")
        self.assertEqual(policy.max_llm_calls, 3)
        self.assertFalse(policy.enable_intent_analysis)
        self.assertFalse(policy.enable_chain_reasoning)
        self.assertEqual(policy.cache_max_age_days, 21)

    def test_cheap_mode_skips_intent_llm_when_sources_disabled(self):
        coordinator = self._make_coordinator()

        chain = asyncio.run(
            coordinator.research_vocal_chain(
                query="test query",
                use_youtube=False,
                use_web=False,
                budget_mode="cheap",
                prefer_cache=False
            )
        )

        coordinator._llm_client.analyze_vocal_intent.assert_not_awaited()
        coordinator._llm_client.generate_chain_reasoning.assert_not_awaited()
        self.assertEqual(chain.meta.get("budget_mode"), "cheap")
        self.assertEqual(len(chain.devices), 0)

    def test_cheap_mode_runs_parallel_sources_without_short_circuit(self):
        coordinator = self._make_coordinator()

        coordinator._youtube_researcher = SimpleNamespace(
            research_vocal_chain=AsyncMock(return_value=SimpleNamespace(
                extracted_settings=[
                    {
                        "name": "EQ Eight",
                        "category": "eq",
                        "purpose": "Cleanup",
                        "parameters": {"1 Gain A": {"value": -2.5, "unit": "dB", "confidence": 0.8}},
                        "sources": ["https://youtube.com/watch?v=test"]
                    }
                ],
                sources=["https://youtube.com/watch?v=test"],
                confidence=0.95,
                llm_extractions_used=1
            ))
        )
        coordinator._web_researcher = SimpleNamespace(
            research_vocal_chain=AsyncMock(return_value=SimpleNamespace(
                extracted_settings=[
                    {
                        "name": "Compressor",
                        "category": "compressor",
                        "purpose": "Control",
                        "parameters": {"Threshold": {"value": -18, "unit": "dB", "confidence": 0.8}},
                        "sources": ["https://example.com/article"]
                    }
                ],
                sources=["https://example.com/article"],
                confidence=0.8,
                llm_extractions_used=1
            ))
        )

        chain = asyncio.run(
            coordinator.research_vocal_chain(
                query="artist vocal chain",
                use_youtube=True,
                use_web=True,
                budget_mode="cheap",
                max_total_llm_calls=2,
                prefer_cache=False
            )
        )

        coordinator._web_researcher.research_vocal_chain.assert_awaited_once()
        self.assertGreater(len(chain.devices), 0)
        self.assertEqual(chain.meta.get("budget_mode"), "cheap")

    def test_cache_hit_bypasses_live_research(self):
        coordinator = self._make_coordinator()
        cached = ChainSpec(
            query="cached query",
            style_description="Cached result",
            devices=[
                DeviceSpec(
                    plugin_name="EQ Eight",
                    category="eq",
                    parameters={},
                    purpose="Cleanup",
                    reasoning="Cached",
                    confidence=0.8
                )
            ],
            confidence=0.8,
            sources=["cache://plugin_chain_kb"],
            meta={"cache_hit": True}
        )

        coordinator._get_fresh_cached_chain = Mock(return_value=cached)

        chain = asyncio.run(
            coordinator.research_vocal_chain(
                query="cached query",
                use_youtube=True,
                use_web=True,
                budget_mode="balanced",
                prefer_cache=True
            )
        )

        self.assertTrue(chain.meta.get("cache_hit"))
        coordinator._youtube_researcher.research_vocal_chain.assert_not_awaited()
        coordinator._web_researcher.research_vocal_chain.assert_not_awaited()


if __name__ == "__main__":
    unittest.main(verbosity=2)
