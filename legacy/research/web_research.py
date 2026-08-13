"""
Web Research Module

Searches production tutorial websites and extracts vocal chain settings
from articles using LLM analysis and web scraping.
"""

import os
import asyncio
import re
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
from dotenv import load_dotenv

load_dotenv()

# Get logger for this module
logger = logging.getLogger("jarvis.research.web_research")


@dataclass
class ArticleInfo:
    """Information about a web article"""
    url: str
    title: str
    snippet: str
    source_site: str
    relevance_score: float = 0.0


@dataclass
class ScrapedArticle:
    """A scraped article with content"""
    url: str
    title: str
    content: str
    source_site: str
    success: bool = True
    error: Optional[str] = None


@dataclass
class WebResearchResult:
    """Result of researching a topic on the web"""
    query: str
    articles_found: List[ArticleInfo] = field(default_factory=list)
    scraped_articles: List[ScrapedArticle] = field(default_factory=list)
    extracted_settings: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    sources: List[str] = field(default_factory=list)
    llm_extractions_used: int = 0


# Curated list of production tutorial sites
PRODUCTION_SITES = [
    {
        "name": "SoundOnSound",
        "base_url": "https://www.soundonsound.com",
        "search_url": "https://www.soundonsound.com/search?q={query}",
        "quality": 0.9
    },
    {
        "name": "MusicRadar", 
        "base_url": "https://www.musicradar.com",
        "search_url": "https://www.musicradar.com/search?searchTerm={query}",
        "quality": 0.8
    },
    {
        "name": "iZotope",
        "base_url": "https://www.izotope.com",
        "search_url": "https://www.izotope.com/en/learn.html?q={query}",
        "quality": 0.85
    },
    {
        "name": "Waves",
        "base_url": "https://www.waves.com",
        "search_url": "https://www.waves.com/search?q={query}",
        "quality": 0.8
    },
    {
        "name": "AudioTechnology",
        "base_url": "https://www.audiotechnology.com",
        "search_url": "https://www.audiotechnology.com/?s={query}",
        "quality": 0.75
    }
]


class WebResearcher:
    """
    Researches audio production tutorials on the web.
    
    Scrapes production tutorial websites and extracts settings using LLM analysis.
    """
    
    def __init__(self, timeout: int = 30):
        """
        Initialize the web researcher.
        
        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self._session = None
    
    async def _ensure_session(self):
        """Ensure we have a requests session"""
        if self._session is None:
            import requests
            self._session = requests.Session()
            self._session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            })
    
    async def search_production_sites(self, query: str, 
                                       max_results_per_site: int = 3) -> List[ArticleInfo]:
        """
        Search for production tutorials using DuckDuckGo.
        
        Uses site-specific searches for trusted production sites, then falls
        back to general search with relevance filtering.
        
        Args:
            query: Search query
            max_results_per_site: Max results per site for targeted searches
            
        Returns:
            List of ArticleInfo objects
        """
        await self._ensure_session()
        
        all_articles = []
        
        # Define keywords that indicate production content
        production_keywords = [
            'vocal chain', 'plugin', 'compressor', 'eq', 'reverb', 
            'mixing', 'tutorial', 'preset', 'settings', 'production',
            'waves', 'fabfilter', 'izotope', 'ssl', 'uad', 'analog'
        ]
        
        # Exclude domains that return irrelevant results
        excluded_domains = [
            'theguardian.com', 'nytimes.com', 'bbc.com', 'cnn.com',
            'wikipedia.org', 'twitter.com', 'facebook.com', 'instagram.com',
            'tiktok.com', 'reddit.com', 'amazon.com', 'ebay.com'
        ]
        
        # Step 1: Site-specific searches on trusted production sites
        for site in PRODUCTION_SITES[:3]:  # Top 3 trusted sites
            try:
                site_query = f"site:{site['base_url'].replace('https://', '')} {query} vocal mixing"
                logger.info(f"Searching {site['name']}: {site_query}")
                
                results = await asyncio.to_thread(self._run_serper_search, site_query, max_results=3)
                
                for r in results:
                    all_articles.append(ArticleInfo(
                        url=r.get("link"),
                        title=r.get("title"),
                        snippet=r.get("snippet", ""),
                        source_site=site['name'],
                        relevance_score=site["quality"]
                    ))
            except Exception as e:
                logger.warning(f"Site search failed for {site['name']}: {e}")
        
        # Step 2: General search with production keywords (if not enough results)
        if len(all_articles) < 3:
            try:
                general_query = f"{query} vocal chain mixing tutorial plugin settings"
                logger.info(f"Searching Serper (general): {general_query}")
                
                results = await asyncio.to_thread(self._run_serper_search, general_query, max_results=15)
                
                for r in results:
                    url = r.get("link", "")
                    title = r.get("title", "").lower()
                    snippet = r.get("snippet", "").lower()
                    domain = urlparse(url).netloc.lower()
                    
                    # Skip excluded domains
                    if any(exc in domain for exc in excluded_domains):
                        logger.debug(f"Skipping excluded domain: {domain}")
                        continue
                    
                    # Calculate relevance based on production keywords
                    keyword_matches = sum(1 for kw in production_keywords 
                                          if kw in title or kw in snippet)
                    
                    if keyword_matches < 2:
                        logger.debug(f"Skipping low-relevance: {title[:50]}")
                        continue
                    
                    # Score based on keyword density
                    score = min(0.9, 0.5 + (keyword_matches * 0.1))
                    
                    # Boost known production sites
                    for site in PRODUCTION_SITES:
                        if site["base_url"].replace('https://', '') in domain:
                            score = site["quality"]
                            break
                    
                    all_articles.append(ArticleInfo(
                        url=url,
                        title=r.get("title"),
                        snippet=r.get("body"),
                        source_site=domain,
                        relevance_score=score
                    ))
                    
            except Exception as e:
                logger.error(f"Error in general search: {e}")
        
        logger.info(f"Found {len(all_articles)} relevant articles")
        # Sort by relevance
        all_articles.sort(key=lambda a: a.relevance_score, reverse=True)
        return all_articles

    def _run_serper_search(self, query, max_results=10):
        """Run Serper (Google) search synchronously"""
        import requests
        
        api_key = os.getenv("SERPER_API_KEY")
        if not api_key:
            logger.error("SERPER_API_KEY not set! Add it to your .env file.")
            raise ValueError("SERPER_API_KEY environment variable is required for web search")
        
        try:
            response = requests.post(
                "https://google.serper.dev/search",
                headers={
                    "X-API-KEY": api_key,
                    "Content-Type": "application/json"
                },
                json={
                    "q": query,
                    "num": max_results
                },
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            # Serper returns organic results in 'organic' key
            results = data.get("organic", [])
            logger.info(f"Serper returned {len(results)} results for: {query[:50]}...")
            return results
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Serper search error: {e}")
            raise RuntimeError(f"Web search failed: {e}")

    async def _search_site(self, site: Dict, query: str, 
                           max_results: int) -> List[ArticleInfo]:
        """Legacy site search - deprecated by main search function"""
        return []
    
    async def scrape_article(self, url: str) -> ScrapedArticle:
        """
        Scrape the content of an article.
        
        Args:
            url: URL of the article to scrape
            
        Returns:
            ScrapedArticle with the extracted content
        """
        await self._ensure_session()
        
        try:
            # Fetch the page
            response = await asyncio.to_thread(
                self._fetch_page,
                url
            )
            
            if response.status_code != 200:
                return ScrapedArticle(
                    url=url,
                    title="",
                    content="",
                    source_site=urlparse(url).netloc,
                    success=False,
                    error=f"HTTP {response.status_code}"
                )
            
            # Parse the HTML
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Extract title
            title = self._extract_title(soup)
            
            # Extract main content
            content = self._extract_content(soup)
            
            return ScrapedArticle(
                url=url,
                title=title,
                content=content,
                source_site=urlparse(url).netloc,
                success=True
            )
            
        except Exception as e:
            return ScrapedArticle(
                url=url,
                title="",
                content="",
                source_site=urlparse(url).netloc,
                success=False,
                error=str(e)
            )
    
    def _fetch_page(self, url: str):
        """Fetch a page (blocking call)"""
        return self._session.get(url, timeout=self.timeout)
    
    def _extract_title(self, soup) -> str:
        """Extract the article title from HTML"""
        # Try common title patterns
        title_selectors = [
            'h1.article-title',
            'h1.entry-title',
            'h1.post-title',
            '.article-header h1',
            'article h1',
            'h1'
        ]
        
        for selector in title_selectors:
            element = soup.select_one(selector)
            if element:
                return element.get_text().strip()
        
        # Fallback to page title
        title_tag = soup.find('title')
        if title_tag:
            return title_tag.get_text().strip()
        
        return "Untitled"
    
    def _extract_content(self, soup) -> str:
        """Extract the main article content from HTML"""
        # Remove unwanted elements
        for tag in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 
                                   'aside', 'advertisement', 'iframe']):
            tag.decompose()
        
        # Try common article content patterns
        content_selectors = [
            'article .content',
            'article .entry-content',
            '.article-body',
            '.post-content',
            '.entry-content',
            'article',
            '.main-content',
            '#content'
        ]
        
        for selector in content_selectors:
            element = soup.select_one(selector)
            if element:
                # Extract text with some structure
                return self._clean_content(element.get_text(separator='\n'))
        
        # Fallback: get body text
        body = soup.find('body')
        if body:
            return self._clean_content(body.get_text(separator='\n'))
        
        return ""
    
    def _clean_content(self, text: str) -> str:
        """Clean extracted text content"""
        # Remove excessive whitespace
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line = line.strip()
            if line:
                # Skip very short lines (likely navigation)
                if len(line) > 20 or any(c.isdigit() for c in line):
                    cleaned_lines.append(line)
        
        content = '\n'.join(cleaned_lines)
        
        # Remove excessive newlines
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        # Limit length
        if len(content) > 15000:
            content = content[:15000] + "..."
        
        return content
    
    async def research_vocal_chain(
        self,
        query: str,
        max_articles: int = 3,
        urls: List[str] = None,
        max_llm_extractions: Optional[int] = None,
        article_char_limit: int = 12000,
        model_id: Optional[str] = None,
        min_confidence_for_early_stop: float = 0.95,
        allow_fallback_query: bool = True
    ) -> WebResearchResult:
        """
        Research vocal chain settings from web articles.
        
        Args:
            query: Search query
            max_articles: Maximum articles to analyze
            urls: Optional list of specific URLs to scrape (bypasses search)
            
        Returns:
            WebResearchResult with extracted settings
        """
        from .llm_client import get_research_llm
        
        result = WebResearchResult(query=query)
        llm = get_research_llm()
        max_llm_extractions = max_articles if max_llm_extractions is None else max(0, max_llm_extractions)
        article_char_limit = max(500, article_char_limit)
        
        if urls:
            # Use provided URLs directly
            articles_to_scrape = [
                ArticleInfo(
                    url=url,
                    title="",
                    snippet="",
                    source_site=urlparse(url).netloc,
                    relevance_score=1.0
                )
                for url in urls[:max_articles]
            ]
        else:
            # Search for articles
            articles_to_scrape = await self.search_production_sites(query)
            articles_to_scrape = articles_to_scrape[:max_articles]
        
        result.articles_found = articles_to_scrape
        logger.info(f"Processing {len(articles_to_scrape)} articles")

        if not articles_to_scrape:
            logger.warning(f"No articles found for: {query}")
            
            # FALLBACK LOGIC: If specific query failed, try a broader one
            # Only recurse once or twice to avoid loops
            original_query = hasattr(result, 'original_query') and result.original_query or query
            
            # Simple recursion depth check via query length comparison or a flag
            # (Here we use a simple heuristic: if query is long, try shorter)
            fallback_query = self._generate_fallback_query(query)
            
            if (
                allow_fallback_query and
                fallback_query and
                fallback_query != query and
                len(query) > len(fallback_query)
            ):
                print(f"Thinking... Specific search failed. Trying broader search: '{fallback_query}'")
                logger.info(f"Triggering fallback search: {fallback_query}")
                
                # Recursive call with the broader query
                fallback_result = await self.research_vocal_chain(
                    query=fallback_query,
                    max_articles=max_articles,
                    urls=None,
                    max_llm_extractions=max_llm_extractions,
                    article_char_limit=article_char_limit,
                    model_id=model_id,
                    min_confidence_for_early_stop=min_confidence_for_early_stop,
                    allow_fallback_query=False
                )
                
                # Preserve the original query in the result for context
                fallback_result.query = original_query
                return fallback_result
                
            return result
        
        # Scrape and extract settings from each article
        all_extractions = []
        
        for article_info in articles_to_scrape:
            if len(all_extractions) >= max_llm_extractions:
                logger.info("Reached LLM extraction budget, stopping web analysis.")
                break

            logger.info(f"Scraping: {article_info.url}")

            # Scrape the article
            scraped = await self.scrape_article(article_info.url)
            result.scraped_articles.append(scraped)

            if not scraped.success:
                logger.warning(f"Scrape failed: {scraped.error}")
                continue

            if len(scraped.content) < 200:
                logger.debug(f"Content too short, skipping")
                continue
            
            # Extract settings using LLM
            extraction = await llm.extract_vocal_chain_from_article(
                article=scraped.content[:article_char_limit],
                source_url=scraped.url,
                title=scraped.title,
                model_id=model_id
            )
            
            if extraction.devices:
                all_extractions.append({
                    "source": scraped.url,
                    "title": scraped.title,
                    "devices": extraction.devices,
                    "confidence": extraction.confidence
                })
                result.sources.append(scraped.url)
                logger.info(f"Extracted {len(extraction.devices)} devices from {scraped.title}")

                if extraction.confidence >= min_confidence_for_early_stop:
                    logger.info("High-confidence extraction found; stopping web analysis early.")
                    break
        
        # Aggregate extractions
        result.extracted_settings = self._aggregate_extractions(all_extractions)
        result.confidence = self._calculate_overall_confidence(all_extractions)
        result.llm_extractions_used = len(all_extractions)
        
        return result
    
    def _aggregate_extractions(self, extractions: List[Dict]) -> List[Dict]:
        """Aggregate and deduplicate extractions from multiple sources"""
        if not extractions:
            return []
        
        # Collect all unique devices
        device_map = {}
        
        for extraction in extractions:
            for device in extraction.get("devices", []):
                name = device.get("name", "Unknown")
                category = device.get("category", "unknown")
                key = f"{category}:{name}"
                
                if key not in device_map:
                    device_map[key] = {
                        "name": name,
                        "category": category,
                        "purpose": device.get("purpose", ""),
                        "parameter_sets": [],
                        "sources": []
                    }
                
                device_map[key]["parameter_sets"].append(device.get("parameters", {}))
                device_map[key]["sources"].append(extraction.get("source", ""))
        
        # Merge parameter sets
        aggregated = []
        for key, device_data in device_map.items():
            merged_params = self._merge_parameters(device_data["parameter_sets"])
            
            aggregated.append({
                "name": device_data["name"],
                "category": device_data["category"],
                "purpose": device_data["purpose"],
                "parameters": merged_params,
                "source_count": len(device_data["sources"]),
                "sources": list(set(device_data["sources"]))
            })
        
        return aggregated
    
    def _merge_parameters(self, param_sets: List[Dict]) -> Dict:
        """Merge multiple parameter sets"""
        if not param_sets:
            return {}
        
        if len(param_sets) == 1:
            return param_sets[0]
        
        merged = {}
        param_values = {}
        
        for params in param_sets:
            for name, info in params.items():
                if name not in param_values:
                    param_values[name] = []
                
                if isinstance(info, dict):
                    value = info.get("value")
                    if value is not None:
                        param_values[name].append({
                            "value": value,
                            "unit": info.get("unit", ""),
                            "confidence": info.get("confidence", 0.5)
                        })
                elif isinstance(info, (int, float)):
                    param_values[name].append({
                        "value": info,
                        "unit": "",
                        "confidence": 0.5
                    })
        
        for name, values in param_values.items():
            if not values:
                continue
            
            avg_value = sum(v["value"] for v in values) / len(values)
            max_confidence = max(v["confidence"] for v in values)
            
            if len(values) > 1:
                max_confidence = min(1.0, max_confidence + 0.1 * (len(values) - 1))
            
            merged[name] = {
                "value": round(avg_value, 2),
                "unit": values[0]["unit"],
                "confidence": max_confidence,
                "source_count": len(values)
            }
        
        return merged
    
    def _calculate_overall_confidence(self, extractions: List[Dict]) -> float:
        """Calculate overall confidence"""
        if not extractions:
            return 0.0
        
        confidences = [e.get("confidence", 0.5) for e in extractions]
        avg_confidence = sum(confidences) / len(confidences)
        
        source_boost = min(0.2, 0.05 * (len(extractions) - 1))
        
        return min(1.0, avg_confidence + source_boost)

    def _generate_fallback_query(self, query: str) -> Optional[str]:
        """
        Generate a broader fallback query if the specific one fails.
        Strategies:
        1. "Artist Album Song vocal chain" -> "Artist vocal chain"
        2. "Artist Song vocal chain" -> "Artist vocal chain"
        3. "Artist vocal chain" -> "Genre vocal chain" (if genre detection were easy, else skip)
        """
        query_lower = query.lower()
        
        # Strip common suffixes to get core terms
        core_search = query_lower.replace("vocal chain", "").replace("vocal mixing", "").replace("vocals", "").strip()
        
        # If query has "Album Name", try stripping it? 
        # Hard to detect album name without NLP. 
        # Simple heuristic: If multiple words, assume first 1-2 are Artist.
        
        parts = core_search.split()
        
        # Case 1: "Kanye West Vultures 1" -> "Kanye West"
        if "kanye" in query_lower:
            if "vultures" in query_lower or "back to me" in query_lower:
                return "Kanye West vocal chain mixing"
        
        # Case 2: General "Artist Song" -> "Artist"
        # If we have > 2 words (e.g. "Travis Scott Fein"), try just "Travis Scott"
        if len(parts) > 2:
            # Try taking first 2 words as artist
            potential_artist = f"{parts[0]} {parts[1]}"
            return f"{potential_artist} vocal chain"
            
        # Case 3: If it was already short (e.g. "Kanye West"), try genre?
        # Maybe too risky to guess genre here.
        
        # Case 4: Try just "How to mix vocals like [Artist]"
        if "how to" not in query_lower:
            return f"how to mix vocals like {core_search}"
            
        return None


# Singleton instance
_web_researcher: Optional[WebResearcher] = None


def get_web_researcher() -> WebResearcher:
    """Get the singleton WebResearcher instance"""
    global _web_researcher
    if _web_researcher is None:
        _web_researcher = WebResearcher()
    return _web_researcher


# Convenience functions
async def search_production_sites(query: str) -> List[ArticleInfo]:
    """Search production tutorial sites"""
    return await get_web_researcher().search_production_sites(query)


async def scrape_article(url: str) -> ScrapedArticle:
    """Scrape an article"""
    return await get_web_researcher().scrape_article(url)


async def research_vocal_chain_web(query: str, 
                                    max_articles: int = 3,
                                    urls: List[str] = None) -> WebResearchResult:
    """Research vocal chain settings from web articles"""
    return await get_web_researcher().research_vocal_chain(query, max_articles, urls)

