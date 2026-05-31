"""
Tests for the Research Agent System

Tests:
- LLM client functionality
- YouTube research module
- Web research module
- Research coordinator
- Result aggregation
"""

import os
import sys
import asyncio
import unittest
from unittest.mock import Mock, patch, AsyncMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.llm_client import (
    GeminiClient,
    ResearchLLMClient,
    ExtractionResult,
    LLMResponse
)
from research.youtube_research import (
    YouTubeResearcher,
    VideoInfo,
    TranscriptResult,
    YouTubeResearchResult
)
from research.web_research import (
    WebResearcher,
    ArticleInfo,
    ScrapedArticle,
    WebResearchResult
)
from research.research_coordinator import (
    ResearchCoordinator,
    ChainSpec,
    DeviceSpec
)


class TestLLMClient(unittest.TestCase):
    """Tests for LLM client"""
    
    def test_gemini_client_init(self):
        """Test GeminiClient initialization"""
        client = GeminiClient()
        # Should initialize without error even without API key
        self.assertIsNotNone(client)
    
    def test_research_llm_client_init(self):
        """Test ResearchLLMClient initialization"""
        client = ResearchLLMClient()
        self.assertIsNotNone(client)
        self.assertIsNotNone(client.client)
    
    def test_extraction_result_dataclass(self):
        """Test ExtractionResult dataclass"""
        result = ExtractionResult(
            devices=[{"name": "EQ Eight", "category": "eq"}],
            confidence=0.8,
            raw_response="test",
            source="test_source"
        )
        self.assertEqual(len(result.devices), 1)
        self.assertEqual(result.confidence, 0.8)
    
    def test_llm_response_dataclass(self):
        """Test LLMResponse dataclass"""
        response = LLMResponse(
            content="Test content",
            model="test-model",
            success=True
        )
        self.assertEqual(response.content, "Test content")
        self.assertTrue(response.success)


class TestYouTubeResearcher(unittest.TestCase):
    """Tests for YouTube research module"""
    
    def test_researcher_init(self):
        """Test YouTubeResearcher initialization"""
        researcher = YouTubeResearcher()
        self.assertIsNotNone(researcher)
    
    def test_video_info_dataclass(self):
        """Test VideoInfo dataclass"""
        video = VideoInfo(
            video_id="abc123",
            title="Test Video",
            channel="Test Channel",
            description="Test description",
            url="https://youtube.com/watch?v=abc123"
        )
        self.assertEqual(video.video_id, "abc123")
        self.assertEqual(video.title, "Test Video")
    
    def test_transcript_result_dataclass(self):
        """Test TranscriptResult dataclass"""
        result = TranscriptResult(
            video_id="abc123",
            full_text="This is a test transcript",
            success=True
        )
        self.assertEqual(result.video_id, "abc123")
        self.assertTrue(result.success)
    
    def test_youtube_research_result_dataclass(self):
        """Test YouTubeResearchResult dataclass"""
        result = YouTubeResearchResult(
            query="test query"
        )
        self.assertEqual(result.query, "test query")
        self.assertEqual(result.videos_found, [])
    
    def test_enhance_query(self):
        """Test query enhancement for better search results"""
        researcher = YouTubeResearcher()
        
        # Test query enhancement
        enhanced = researcher._enhance_query("Kanye vocal")
        self.assertIn("Kanye", enhanced)
        # Should add tutorial-related keywords
    
    def test_calculate_relevance(self):
        """Test relevance score calculation"""
        researcher = YouTubeResearcher()
        
        snippet = {
            "title": "Kanye West vocal chain tutorial mixing",
            "description": "How to mix vocals like Kanye"
        }
        
        score = researcher._calculate_relevance(snippet, "Kanye vocal chain")
        self.assertGreater(score, 0)
    
    def test_extract_artist_from_query(self):
        """Test artist extraction from query"""
        researcher = YouTubeResearcher()
        
        artist = researcher._extract_artist_from_query("Kanye Runaway vocal chain")
        # Should extract "Kanye Runaway" as the artist portion (case-insensitive check)
        self.assertIn("kanye", artist.lower() if artist else "")


class TestWebResearcher(unittest.TestCase):
    """Tests for web research module"""
    
    def test_researcher_init(self):
        """Test WebResearcher initialization"""
        researcher = WebResearcher()
        self.assertIsNotNone(researcher)
    
    def test_article_info_dataclass(self):
        """Test ArticleInfo dataclass"""
        article = ArticleInfo(
            url="https://example.com/article",
            title="Test Article",
            snippet="Test snippet",
            source_site="example.com"
        )
        self.assertEqual(article.url, "https://example.com/article")
    
    def test_scraped_article_dataclass(self):
        """Test ScrapedArticle dataclass"""
        article = ScrapedArticle(
            url="https://example.com",
            title="Test",
            content="Test content",
            source_site="example.com",
            success=True
        )
        self.assertTrue(article.success)
    
    def test_clean_content(self):
        """Test content cleaning"""
        researcher = WebResearcher()
        
        dirty_content = """
        Short
        
        
        
        This is a longer line that should be kept because it has content
        
        
        Another longer line with useful content here
        """
        
        cleaned = researcher._clean_content(dirty_content)
        
        # Should remove excessive newlines
        self.assertNotIn("\n\n\n", cleaned)
        
        # Should keep longer lines
        self.assertIn("longer line", cleaned)


class TestResearchCoordinator(unittest.TestCase):
    """Tests for research coordinator"""
    
    def test_coordinator_init(self):
        """Test ResearchCoordinator initialization"""
        coordinator = ResearchCoordinator()
        self.assertIsNotNone(coordinator)
    
    def test_chain_spec_dataclass(self):
        """Test ChainSpec dataclass"""
        device = DeviceSpec(
            plugin_name="EQ Eight",
            category="eq",
            parameters={"1 Gain A": {"value": -3, "unit": "dB"}},
            purpose="Cut mud",
            reasoning="Standard mud removal",
            confidence=0.8
        )
        
        chain = ChainSpec(
            query="test query",
            style_description="Test style",
            devices=[device],
            confidence=0.8,
            sources=["test_source"]
        )
        
        self.assertEqual(chain.query, "test query")
        self.assertEqual(len(chain.devices), 1)
        self.assertEqual(chain.devices[0].plugin_name, "EQ Eight")
    
    def test_chain_spec_to_dict(self):
        """Test ChainSpec serialization"""
        device = DeviceSpec(
            plugin_name="Compressor",
            category="compressor",
            parameters={},
            purpose="Dynamics",
            reasoning="Test",
            confidence=0.7
        )
        
        chain = ChainSpec(
            query="test",
            style_description="desc",
            devices=[device],
            confidence=0.7,
            sources=[]
        )
        
        data = chain.to_dict()
        self.assertIsInstance(data, dict)
        self.assertEqual(data["query"], "test")
        self.assertEqual(len(data["devices"]), 1)
    
    def test_chain_spec_from_dict(self):
        """Test ChainSpec deserialization"""
        data = {
            "query": "test query",
            "style_description": "Test",
            "devices": [
                {
                    "plugin_name": "Reverb",
                    "category": "reverb",
                    "parameters": {},
                    "purpose": "Space",
                    "reasoning": "Add ambiance",
                    "confidence": 0.6,
                    "sources": []
                }
            ],
            "confidence": 0.6,
            "sources": []
        }
        
        chain = ChainSpec.from_dict(data)
        self.assertEqual(chain.query, "test query")
        self.assertEqual(len(chain.devices), 1)
        self.assertEqual(chain.devices[0].plugin_name, "Reverb")
    
    def test_normalize_category(self):
        """Test category normalization"""
        coordinator = ResearchCoordinator()
        
        self.assertEqual(coordinator._normalize_category("equalizer"), "eq")
        self.assertEqual(coordinator._normalize_category("comp"), "compressor")
        self.assertEqual(coordinator._normalize_category("dist"), "saturation")
        self.assertEqual(coordinator._normalize_category("verb"), "reverb")
        self.assertEqual(coordinator._normalize_category("unknown"), "unknown")
    
    def test_order_devices_by_signal_flow(self):
        """Test device ordering by signal flow"""
        coordinator = ResearchCoordinator()
        
        devices = [
            DeviceSpec("Reverb", "reverb", {}, "", "", 0.5),
            DeviceSpec("Compressor", "compressor", {}, "", "", 0.5),
            DeviceSpec("EQ Eight", "eq", {}, "", "", 0.5),
            DeviceSpec("Saturator", "saturation", {}, "", "", 0.5)
        ]
        
        ordered = coordinator._order_devices_by_signal_flow(devices)
        
        # EQ should come first
        self.assertEqual(ordered[0].category, "eq")
        # Reverb should come last
        self.assertEqual(ordered[-1].category, "reverb")


class TestMockLLMExtraction(unittest.TestCase):
    """Tests with mocked LLM responses"""
    
    def test_parse_extraction_response_valid_json(self):
        """Test parsing valid JSON response"""
        client = GeminiClient()
        
        response = '''
        {
            "devices": [
                {"name": "EQ Eight", "category": "eq", "parameters": {}}
            ],
            "confidence": 0.8
        }
        '''
        
        result = client._parse_extraction_response(response)
        self.assertEqual(len(result["devices"]), 1)
        self.assertEqual(result["confidence"], 0.8)
    
    def test_parse_extraction_response_with_markdown(self):
        """Test parsing JSON wrapped in markdown code blocks"""
        client = GeminiClient()
        
        response = '''```json
        {
            "devices": [],
            "confidence": 0.5
        }
        ```'''
        
        result = client._parse_extraction_response(response)
        self.assertEqual(result["devices"], [])
    
    def test_parse_extraction_response_invalid(self):
        """Test handling invalid JSON"""
        client = GeminiClient()
        
        response = "This is not valid JSON at all"
        
        result = client._parse_extraction_response(response)
        # Should return empty structure
        self.assertEqual(result["devices"], [])


class TestAsyncFunctions(unittest.TestCase):
    """Tests for async functions"""
    
    def test_async_youtube_fetch_transcript_error(self):
        """Test transcript fetch with invalid video ID"""
        async def run_test():
            researcher = YouTubeResearcher()
            result = await researcher.fetch_transcript("invalid_video_id_12345")
            return result
        
        result = asyncio.run(run_test())
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)


class TestAggregation(unittest.TestCase):
    """Tests for result aggregation"""
    
    def test_merge_parameters(self):
        """Test parameter merging from multiple sources"""
        researcher = YouTubeResearcher()
        
        param_sets = [
            {"threshold": {"value": -20, "unit": "dB", "confidence": 0.7}},
            {"threshold": {"value": -18, "unit": "dB", "confidence": 0.8}}
        ]
        
        merged = researcher._merge_parameters(param_sets)
        
        # Should average values
        self.assertAlmostEqual(merged["threshold"]["value"], -19, places=1)
        # Should take max confidence and boost for multiple sources
        self.assertGreaterEqual(merged["threshold"]["confidence"], 0.8)
    
    def test_calculate_overall_confidence(self):
        """Test overall confidence calculation"""
        researcher = YouTubeResearcher()
        
        extractions = [
            {"confidence": 0.7},
            {"confidence": 0.8},
            {"confidence": 0.6}
        ]
        
        confidence = researcher._calculate_overall_confidence(extractions)
        
        # Should be between individual confidences with source boost
        self.assertGreater(confidence, 0.5)
        self.assertLessEqual(confidence, 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

