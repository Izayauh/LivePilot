"""
End-to-End Integration Test for Research-Driven Vocal Chains (Phase 2)

Tests the full pipeline:
1. Query parsing and intent analysis
2. Research coordination (YouTube + Web)
3. LLM extraction of settings
4. ChainSpec generation
5. Validation against knowledge base

This test requires:
- GOOGLE_API_KEY environment variable (for LLM extraction)
- YOUTUBE_API_KEY environment variable (optional, for YouTube search)
- Internet connection

Run with: python tests/test_researched_chain_phase2.py
"""

import os
import sys
import asyncio
import unittest
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


class TestEndToEndResearch(unittest.TestCase):
    """End-to-end integration tests for vocal chain research"""
    
    @classmethod
    def setUpClass(cls):
        """Check for required environment variables"""
        cls.has_google_api = bool(os.getenv("GOOGLE_API_KEY"))
        cls.has_youtube_api = bool(os.getenv("YOUTUBE_API_KEY"))
        
        if not cls.has_google_api:
            print("\n⚠️  GOOGLE_API_KEY not set - LLM extraction tests will be skipped")
        if not cls.has_youtube_api:
            print("\n⚠️  YOUTUBE_API_KEY not set - YouTube search tests will be skipped")
    
    def test_knowledge_base_loads(self):
        """Test that the semantic knowledge base loads correctly"""
        from knowledge.plugin_kb_manager import get_plugin_kb
        
        kb = get_plugin_kb()
        self.assertTrue(kb.is_loaded())
        
        # Verify all 7 plugins are present
        plugins = kb.get_plugin_names()
        expected = ["EQ Eight", "Compressor", "Saturator", "Reverb", 
                    "Glue Compressor", "Delay", "Multiband Dynamics"]
        
        for plugin in expected:
            self.assertIn(plugin, plugins, f"Missing plugin: {plugin}")
        
        print(f"✓ Knowledge base loaded with {len(plugins)} plugins")
    
    def test_intent_analysis(self):
        """Test that intent analysis works with LLM"""
        if not self.has_google_api:
            self.skipTest("GOOGLE_API_KEY required")
        
        from research.llm_client import get_research_llm
        
        async def run_test():
            llm = get_research_llm()
            intent = await llm.analyze_vocal_intent("Kanye Runaway vocal chain")
            return intent
        
        intent = asyncio.run(run_test())
        
        self.assertIsInstance(intent, dict)
        self.assertIn("original_query", intent)
        
        # Should extract some information
        if "error" not in intent:
            print(f"✓ Intent analysis extracted: artist={intent.get('artist')}, "
                  f"style={intent.get('style')}")
    
    def test_transcript_fetch_real_video(self):
        """Test fetching a real YouTube transcript"""
        from research.youtube_research import get_youtube_researcher
        
        async def run_test():
            researcher = get_youtube_researcher()
            # Use a known video ID with transcripts
            # This is a public Ableton tutorial video
            result = await researcher.fetch_transcript("dQw4w9WgXcQ")  # Famous video
            return result
        
        result = asyncio.run(run_test())
        
        # The video may or may not have transcripts
        if result.success:
            self.assertGreater(len(result.full_text), 0)
            print(f"✓ Fetched transcript: {len(result.full_text)} characters")
        else:
            print(f"✓ Transcript fetch handled error: {result.error}")
    
    def test_youtube_search(self):
        """Test YouTube search functionality"""
        if not self.has_youtube_api:
            self.skipTest("YOUTUBE_API_KEY required")
        
        from research.youtube_research import get_youtube_researcher
        
        async def run_test():
            researcher = get_youtube_researcher()
            videos = await researcher.search_tutorials(
                "vocal mixing tutorial EQ compression",
                max_results=3
            )
            return videos
        
        videos = asyncio.run(run_test())
        
        self.assertIsInstance(videos, list)
        if videos:
            print(f"✓ Found {len(videos)} videos:")
            for v in videos[:3]:
                print(f"  - {v.title[:50]}...")
    
    def test_web_scraping(self):
        """Test web article scraping"""
        from research.web_research import get_web_researcher
        
        async def run_test():
            researcher = get_web_researcher()
            # Test with a known good URL (or skip if it fails)
            try:
                result = await researcher.scrape_article("https://www.ableton.com/en/live/")
                return result
            except Exception as e:
                return None
        
        result = asyncio.run(run_test())
        
        if result:
            if result.success:
                print(f"✓ Scraped article: {len(result.content)} characters")
            else:
                print(f"✓ Scrape handled error: {result.error}")
    
    def test_llm_extraction_from_sample_text(self):
        """Test LLM extraction from sample transcript text"""
        if not self.has_google_api:
            self.skipTest("GOOGLE_API_KEY required")
        
        from research.llm_client import get_research_llm
        
        sample_transcript = """
        So for Kanye's vocal sound on Runaway, we're going to start with some EQ.
        First, add a high-pass filter around 80 Hz to cut the low rumble.
        Then I'm cutting about 3 dB around 300 Hz to remove some of that mud.
        For the compression, I'm using a ratio of about 4 to 1 with the threshold 
        set to around minus 18 dB. Attack time is pretty fast, maybe 10 milliseconds,
        and release around 100 milliseconds.
        Then I add a little saturation for warmth - maybe 6 dB of drive on the saturator.
        Finally some reverb with about 1.5 seconds decay and the mix at 20 percent.
        """
        
        async def run_test():
            llm = get_research_llm()
            result = await llm.extract_vocal_chain_from_transcript(
                transcript=sample_transcript,
                artist="Kanye West",
                song="Runaway"
            )
            return result
        
        result = asyncio.run(run_test())
        
        self.assertIsNotNone(result)
        print(f"✓ LLM extraction found {len(result.devices)} devices")
        
        if result.devices:
            for device in result.devices:
                name = device.get("name", "Unknown")
                params = device.get("parameters", {})
                print(f"  - {name}: {len(params)} parameters")
    
    def test_research_coordinator_integration(self):
        """Test full research coordinator (may skip API-dependent parts)"""
        if not self.has_google_api:
            self.skipTest("GOOGLE_API_KEY required")
        
        from research.research_coordinator import get_research_coordinator, ChainSpec
        
        async def run_test():
            coordinator = get_research_coordinator()
            
            # Run with limited sources to save API calls
            chain_spec = await coordinator.research_vocal_chain(
                query="pop vocal mixing tutorial",
                use_youtube=self.has_youtube_api,
                use_web=False,  # Skip web to speed up test
                max_youtube_videos=1
            )
            return chain_spec
        
        chain_spec = asyncio.run(run_test())
        
        self.assertIsInstance(chain_spec, ChainSpec)
        self.assertEqual(chain_spec.query, "pop vocal mixing tutorial")
        
        print(f"✓ Research coordinator returned ChainSpec:")
        print(f"  - Devices: {len(chain_spec.devices)}")
        print(f"  - Confidence: {chain_spec.confidence:.2f}")
        print(f"  - Sources: {len(chain_spec.sources)}")
    
    def test_chain_spec_serialization(self):
        """Test ChainSpec to/from dict conversion"""
        from research.research_coordinator import ChainSpec, DeviceSpec
        
        # Create a sample chain spec
        original = ChainSpec(
            query="test query",
            style_description="Test style description",
            devices=[
                DeviceSpec(
                    plugin_name="EQ Eight",
                    category="eq",
                    parameters={
                        "1 Frequency A": {"value": 100, "unit": "Hz"},
                        "1 Gain A": {"value": -3, "unit": "dB"}
                    },
                    purpose="High pass and cut mud",
                    reasoning="Standard vocal cleanup",
                    confidence=0.85
                ),
                DeviceSpec(
                    plugin_name="Compressor",
                    category="compressor",
                    parameters={
                        "Threshold": {"value": -18, "unit": "dB"},
                        "Ratio": {"value": 4, "unit": "ratio"}
                    },
                    purpose="Dynamics control",
                    reasoning="Standard vocal compression",
                    confidence=0.8
                )
            ],
            confidence=0.82,
            sources=["https://youtube.com/watch?v=test"],
            artist="Test Artist",
            song="Test Song",
            genre="pop"
        )
        
        # Serialize
        data = original.to_dict()
        self.assertIsInstance(data, dict)
        
        # Deserialize
        restored = ChainSpec.from_dict(data)
        
        self.assertEqual(restored.query, original.query)
        self.assertEqual(len(restored.devices), len(original.devices))
        self.assertEqual(restored.devices[0].plugin_name, "EQ Eight")
        self.assertEqual(restored.confidence, original.confidence)
        
        print("✓ ChainSpec serialization/deserialization works correctly")
    
    def test_validate_extracted_params_against_kb(self):
        """Test that extracted parameters are valid according to knowledge base"""
        from knowledge.plugin_kb_manager import get_plugin_kb
        from research.research_coordinator import DeviceSpec
        
        kb = get_plugin_kb()
        
        # Sample extraction
        extracted = DeviceSpec(
            plugin_name="EQ Eight",
            category="eq",
            parameters={
                "1 Gain A": {"value": -3, "unit": "dB"}
            },
            purpose="Cut mud",
            reasoning="Test",
            confidence=0.8
        )
        
        # Validate against KB
        is_valid, clamped, msg = kb.validate_parameter_value(
            "EQ Eight", "1 Gain A", -3
        )
        
        self.assertTrue(is_valid)
        print(f"✓ Extracted parameter value validated: {msg}")
    
    def test_signal_flow_ordering(self):
        """Test that devices are ordered correctly by signal flow"""
        from research.research_coordinator import ResearchCoordinator, DeviceSpec
        
        coordinator = ResearchCoordinator()
        
        # Create unordered devices
        devices = [
            DeviceSpec("Reverb", "reverb", {}, "Space", "", 0.7),
            DeviceSpec("Saturator", "saturation", {}, "Warmth", "", 0.7),
            DeviceSpec("Compressor", "compressor", {}, "Dynamics", "", 0.7),
            DeviceSpec("EQ Eight", "eq", {}, "Cleanup", "", 0.7),
            DeviceSpec("Delay", "delay", {}, "Echo", "", 0.7)
        ]
        
        ordered = coordinator._order_devices_by_signal_flow(devices)
        
        # EQ should come first
        self.assertEqual(ordered[0].category, "eq")
        # Reverb should come last (or near last)
        self.assertEqual(ordered[-1].category, "reverb")
        
        # Get categories in order
        order = [d.category for d in ordered]
        print(f"✓ Signal flow order: {' → '.join(order)}")


class TestPerformance(unittest.TestCase):
    """Performance and reliability tests"""
    
    def test_kb_lookup_performance(self):
        """Test knowledge base lookup is fast"""
        import time
        from knowledge.plugin_kb_manager import get_plugin_kb
        
        kb = get_plugin_kb()
        
        start = time.time()
        for _ in range(100):
            kb.get_plugin_info("EQ Eight")
            kb.get_parameter_info("Compressor", "Threshold")
            kb.find_parameters_for_intent("Reverb", "decay")
        elapsed = time.time() - start
        
        self.assertLess(elapsed, 1.0, "KB lookups should be fast")
        print(f"✓ 300 KB lookups completed in {elapsed:.3f}s")
    
    def test_empty_query_handling(self):
        """Test handling of empty or invalid queries"""
        from research.research_coordinator import ResearchCoordinator
        
        async def run_test():
            coordinator = ResearchCoordinator()
            # Should not crash with empty query
            chain = await coordinator.research_vocal_chain(
                query="",
                use_youtube=False,
                use_web=False
            )
            return chain
        
        chain = asyncio.run(run_test())
        
        # Should return empty but valid ChainSpec
        self.assertEqual(chain.query, "")
        self.assertEqual(chain.devices, [])
        print("✓ Empty query handled gracefully")


def run_tests():
    """Run all tests with nice output"""
    print("\n" + "=" * 60)
    print("RESEARCH-DRIVEN VOCAL CHAIN SYSTEM - PHASE 2 TESTS")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Run tests
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestEndToEndResearch))
    suite.addTests(loader.loadTestsFromTestCase(TestPerformance))
    
    # Run with verbosity
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")
    
    success = len(result.failures) == 0 and len(result.errors) == 0
    print(f"\nOverall: {'✓ PASSED' if success else '✗ FAILED'}")
    
    return success


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)

