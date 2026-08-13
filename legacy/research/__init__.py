"""
Research module for web-based audio engineering research.

This module provides tools for:
- Scraping YouTube tutorials for plugin chains and settings
- Parsing audio engineering articles
- Extracting specific settings from text
- LLM-based extraction of plugin parameters
- Research coordination across multiple sources
"""

from .youtube_parser import YouTubeSettingsParser, parse_settings_from_text
from .llm_client import (
    ResearchLLMClient, 
    GeminiClient, 
    get_research_llm, 
    extract_settings_from_text as llm_extract_settings
)
from .youtube_research import (
    YouTubeResearcher,
    get_youtube_researcher,
    search_youtube_tutorials,
    fetch_transcript,
    research_vocal_chain_youtube,
    VideoInfo,
    TranscriptResult,
    YouTubeResearchResult
)
from .web_research import (
    WebResearcher,
    get_web_researcher,
    search_production_sites,
    scrape_article,
    research_vocal_chain_web,
    ArticleInfo,
    ScrapedArticle,
    WebResearchResult
)
from .research_coordinator import (
    ResearchCoordinator,
    get_research_coordinator,
    research_vocal_chain,
    ChainSpec,
    DeviceSpec,
    ResearchPolicy
)

__all__ = [
    # Legacy parser
    'YouTubeSettingsParser', 
    'parse_settings_from_text',
    # LLM client
    'ResearchLLMClient',
    'GeminiClient',
    'get_research_llm',
    'llm_extract_settings',
    # YouTube research
    'YouTubeResearcher',
    'get_youtube_researcher',
    'search_youtube_tutorials',
    'fetch_transcript',
    'research_vocal_chain_youtube',
    'VideoInfo',
    'TranscriptResult',
    'YouTubeResearchResult',
    # Web research
    'WebResearcher',
    'get_web_researcher',
    'search_production_sites',
    'scrape_article',
    'research_vocal_chain_web',
    'ArticleInfo',
    'ScrapedArticle',
    'WebResearchResult',
    # Research coordinator
    'ResearchCoordinator',
    'get_research_coordinator',
    'research_vocal_chain',
    'ChainSpec',
    'DeviceSpec',
    'ResearchPolicy'
]

