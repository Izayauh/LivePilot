"""
YouTube Research Module

Searches YouTube for audio production tutorials and extracts vocal chain settings
from video transcripts using LLM analysis.
"""

import re
import os
import requests
import json
import asyncio
from urllib.parse import urlparse, parse_qs
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class VideoInfo:
    """Information about a YouTube video"""
    video_id: str
    title: str
    channel: str
    description: str
    url: str
    published_at: str = ""
    view_count: int = 0
    relevance_score: float = 0.0


@dataclass
class TranscriptSegment:
    """A segment of a video transcript"""
    text: str
    start: float  # Start time in seconds
    duration: float


@dataclass
class TranscriptResult:
    """Result of fetching a transcript"""
    video_id: str
    full_text: str
    segments: List[TranscriptSegment] = field(default_factory=list)
    language: str = "en"
    success: bool = True
    error: Optional[str] = None


@dataclass
class YouTubeResearchResult:
    """Result of researching a topic on YouTube"""
    query: str
    videos_found: List[VideoInfo] = field(default_factory=list)
    transcripts: Dict[str, TranscriptResult] = field(default_factory=dict)
    extracted_settings: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    sources: List[str] = field(default_factory=list)
    llm_extractions_used: int = 0


class YouTubeResearcher:
    """
    Researches audio production tutorials on YouTube.
    
    Uses YouTube Data API v3 for search and youtube-transcript-api for transcripts.
    """
    
    def __init__(self, api_key: str = None):
        """
        Initialize the YouTube researcher.
        
        Args:
            api_key: YouTube Data API key. Defaults to YOUTUBE_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("YOUTUBE_API_KEY")
        self._youtube_client = None
        self._initialized = False
        
        if not self.api_key:
            print("[YouTubeResearch] Warning: No API key found. Set YOUTUBE_API_KEY env var.")
            print("[YouTubeResearch] YouTube search will be disabled, but transcript fetching will work.")
    
    def _ensure_initialized(self):
        """Lazily initialize the YouTube client"""
        if not self._initialized and self.api_key:
            try:
                from googleapiclient.discovery import build
                self._youtube_client = build('youtube', 'v3', developerKey=self.api_key)
                self._initialized = True
                print("[YouTubeResearch] YouTube client initialized successfully")
            except Exception as e:
                print(f"[YouTubeResearch] Failed to initialize YouTube client: {e}")
                print("[YouTubeResearch] Check that YOUTUBE_API_KEY is set correctly in .env")
    
    async def search_tutorials(self, query: str, max_results: int = 5) -> List[VideoInfo]:
        """Search YouTube for audio production tutorials."""
        self._ensure_initialized()
        
        # Enhance query for audio production content
        enhanced_query = self._enhance_query(query)
        print(f"[YOUTUBE] Searching for: \"{enhanced_query}\"")
        
        # Try API first, but catch ALL exceptions to trigger fallback
        try:
            if not self._youtube_client:
                raise RuntimeError("Client not initialized")
                
            # Run the search in a thread pool
            search_response = await asyncio.to_thread(
                self._execute_search,
                enhanced_query,
                max_results
            )
            
            videos = []
            for item in search_response.get('items', []):
                if item['id'].get('kind') == 'youtube#video':
                    snippet = item['snippet']
                    video_id = item['id']['videoId']
                    
                    video = VideoInfo(
                        video_id=video_id,
                        title=snippet.get('title', ''),
                        channel=snippet.get('channelTitle', ''),
                        description=snippet.get('description', ''),
                        url=f"https://www.youtube.com/watch?v={video_id}",
                        published_at=snippet.get('publishedAt', ''),
                        relevance_score=self._calculate_relevance(snippet, query)
                    )
                    videos.append(video)
            
            # Sort by relevance
            videos.sort(key=lambda v: v.relevance_score, reverse=True)
            return videos[:max_results]
            
        except Exception as e:
            print(f"[YouTubeResearch] YouTube API Error: {e}")
            print(f"[YouTubeResearch] Falling back to Serper (Google) search...")
            try:
                return await self._search_via_serper(query, max_results)
            except Exception as serper_e:
                 print(f"[YouTubeResearch] Serper fallback failed: {serper_e}")
                 return []

    async def _search_via_serper(self, query: str, max_results: int) -> List[VideoInfo]:
        """
        Search for YouTube videos using Serper API.
        This bypasses the need for a YouTube Data API key.
        """
        api_key = os.getenv("SERPER_API_KEY")
        if not api_key:
            print("[YouTubeResearch] ⚠️ SERPER_API_KEY not found in .env")
            return []
            
        print(f"[YouTubeResearch] Searching via Serper: {query}")
        
        try:
            # We use the 'videos' search type for better results
            response = requests.post(
                "https://google.serper.dev/search",
                headers={
                    "X-API-KEY": api_key,
                    "Content-Type": "application/json"
                },
                json={
                    "q": f"site:youtube.com {query}",
                    "num": max_results + 5, # Fetch a few extra to filter
                    "tbs": "qdr:y" # Filter by past year to get fresh tutorials
                },
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            # Serper sometimes puts video results in 'videos' or 'organic'
            results = data.get("organic", [])
            
            # Check for 'videos' key if organic is empty or as supplement
            video_results = data.get("videos", [])
            if video_results:
                results.extend(video_results)
            
            if not results:
                print(f"[YouTubeResearch] Serper returned no results. Raw: {str(data)[:200]}...")
                return []

            videos = []
            
            for result in results:
                link = result.get("link", "")
                title = result.get("title", "")
                snippet = result.get("snippet", "")
                
                # Extract Video ID
                video_id = self._extract_video_id(link)
                if not video_id:
                    continue
                    
                # Deduplicate
                if any(v.video_id == video_id for v in videos):
                    continue

                videos.append(VideoInfo(
                    video_id=video_id,
                    title=title,
                    channel=result.get("channel", "YouTube"), # Serper sometimes provides channel
                    description=snippet,
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    relevance_score=1.0 # Assume high relevance if Serper returned it
                ))
                
                if len(videos) >= max_results:
                    break
            
            print(f"[YouTubeResearch] Found {len(videos)} videos via Serper")
            return videos
            
        except Exception as e:
            print(f"[YouTubeResearch] Serper search error: {e}")
            raise e

    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from URL"""
        try:
            parsed = urlparse(url)
            if 'youtube.com' in parsed.netloc:
                return parse_qs(parsed.query).get('v', [None])[0]
            elif 'youtu.be' in parsed.netloc:
                return parsed.path[1:]
        except:
            pass
        return None
    
    def _execute_search(self, query: str, max_results: int) -> Dict:
        """Execute the YouTube search (blocking call)"""
        return self._youtube_client.search().list(
            q=query,
            part='snippet',
            maxResults=max_results * 2,  # Get extra for filtering
            type='video',
            videoDuration='medium',  # 4-20 minutes (tutorial length)
            relevanceLanguage='en',
            safeSearch='none'
        ).execute()
    
    def _enhance_query(self, query: str) -> str:
        """Enhance the query for better audio production results"""
        query_lower = query.lower()
        
        # Add context if not already present
        enhancements = []
        
        if 'vocal' in query_lower:
            if 'tutorial' not in query_lower and 'how to' not in query_lower:
                enhancements.append('mixing tutorial')
        elif 'chain' in query_lower:
            enhancements.append('tutorial')
        else:
            enhancements.append('vocal mixing tutorial')
        
        if 'settings' not in query_lower and 'plugin' not in query_lower:
            enhancements.append('plugin settings')
        
        enhanced = query + ' ' + ' '.join(enhancements)
        return enhanced.strip()
    
    def _calculate_relevance(self, snippet: Dict, original_query: str) -> float:
        """Calculate relevance score for a video"""
        score = 0.0
        query_words = set(original_query.lower().split())
        
        title = snippet.get('title', '').lower()
        description = snippet.get('description', '').lower()
        
        # Check title matches
        for word in query_words:
            if word in title:
                score += 2.0
            if word in description:
                score += 0.5
        
        # Boost for tutorial-related keywords
        tutorial_keywords = ['tutorial', 'how to', 'mixing', 'vocal', 'chain', 
                            'settings', 'eq', 'compression', 'plugin']
        for keyword in tutorial_keywords:
            if keyword in title:
                score += 1.0
            if keyword in description:
                score += 0.3
        
        # Penalize for unrelated content
        negative_keywords = ['reaction', 'cover', 'karaoke', 'lyrics', 'live']
        for keyword in negative_keywords:
            if keyword in title:
                score -= 2.0
        
        return max(0.0, score)
    
    async def fetch_transcript(self, video_id: str) -> TranscriptResult:
        """
        Fetch the transcript for a YouTube video.
        
        Args:
            video_id: YouTube video ID
            
        Returns:
            TranscriptResult with the transcript text
        """
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            
            # Create API instance and fetch transcript in thread pool
            def _fetch():
                ytt_api = YouTubeTranscriptApi()
                return ytt_api.fetch(video_id)
            
            transcript_data = await asyncio.to_thread(_fetch)
            
            # Convert to segments - the new API returns a FetchedTranscript object
            segments = []
            texts = []
            
            for item in transcript_data:
                segments.append(TranscriptSegment(
                    text=item.text,
                    start=item.start,
                    duration=item.duration
                ))
                texts.append(item.text)
            
            full_text = ' '.join(texts)
            
            return TranscriptResult(
                video_id=video_id,
                full_text=full_text,
                segments=segments,
                success=True
            )
            
        except Exception as e:
            error_msg = str(e)
            
            # Handle specific errors
            if 'TranscriptsDisabled' in error_msg:
                error_msg = "Transcripts are disabled for this video"
            elif 'NoTranscriptFound' in error_msg:
                error_msg = "No English transcript available"
            elif 'VideoUnavailable' in error_msg:
                error_msg = "Video is unavailable"
            elif 'NoTranscriptAvailable' in error_msg:
                error_msg = "No transcript available for this video"
            
            return TranscriptResult(
                video_id=video_id,
                full_text="",
                success=False,
                error=error_msg
            )
    
    async def research_vocal_chain(
        self,
        query: str,
        max_videos: int = 3,
        max_llm_extractions: Optional[int] = None,
        transcript_char_limit: int = 12000,
        model_id: Optional[str] = None,
        min_confidence_for_early_stop: float = 0.95
    ) -> YouTubeResearchResult:
        """
        Research vocal chain settings from YouTube tutorials.
        """
        from .llm_client import get_research_llm
        
        result = YouTubeResearchResult(query=query)
        llm = get_research_llm()
        max_llm_extractions = max_videos if max_llm_extractions is None else max(0, max_llm_extractions)
        transcript_char_limit = max(500, transcript_char_limit)
        
        # Search for videos
        videos = await self.search_tutorials(query, max_results=max_videos + 2)
        
        if not videos:
            print(f"[YouTubeResearch] No videos found for: {query}")
            return result # RETURN EMPTY RESULT OBJECT, NOT NONE
        
        print(f"[YOUTUBE] Found {len(videos)} videos")
        result.videos_found = videos
        
        # Fetch transcripts and extract settings
        all_extractions = []
        
        for video in videos[:max_videos]:
            if len(all_extractions) >= max_llm_extractions:
                print("[YOUTUBE] Reached LLM extraction budget, stopping YouTube analysis.")
                break

            print(f"[YOUTUBE] Analyzing video: {video.title}")
            
            # Fetch transcript
            transcript = await self.fetch_transcript(video.video_id)
            result.transcripts[video.video_id] = transcript
            
            if not transcript.success:
                print(f"[YouTubeResearch] Transcript failed: {transcript.error}")
                continue
            
            # Extract settings using LLM
            extraction = await llm.extract_vocal_chain_from_transcript(
                transcript=transcript.full_text[:transcript_char_limit],
                artist=self._extract_artist_from_query(query),
                song=self._extract_song_from_query(query),
                model_id=model_id
            )
            
            if extraction.devices:
                all_extractions.append({
                    "source": video.url,
                    "title": video.title,
                    "devices": extraction.devices,
                    "confidence": extraction.confidence
                })
                result.sources.append(video.url)
                print(f"[YOUTUBE] Extracted {len(extraction.devices)} devices from {video.title}")

                if extraction.confidence >= min_confidence_for_early_stop:
                    print("[YOUTUBE] High-confidence extraction found, stopping early.")
                    break
        
        # Aggregate and deduplicate extractions
        result.extracted_settings = self._aggregate_extractions(all_extractions)
        result.confidence = self._calculate_overall_confidence(all_extractions)
        result.llm_extractions_used = len(all_extractions)
        
        return result
    
    def _extract_artist_from_query(self, query: str) -> str:
        """Try to extract artist name from query"""
        # Simple heuristic: words before common keywords
        query_lower = query.lower()
        for keyword in ['vocal', 'voice', 'chain', 'mixing', 'style', 'type']:
            if keyword in query_lower:
                parts = query_lower.split(keyword)
                if parts[0].strip():
                    return parts[0].strip().title()
        return ""
    
    def _extract_song_from_query(self, query: str) -> str:
        """Try to extract song name from query"""
        # Look for patterns like "Song Name vocal" or "Artist - Song"
        if ' - ' in query:
            parts = query.split(' - ')
            if len(parts) >= 2:
                return parts[1].split()[0] if parts[1] else ""
        return ""
    
    def _aggregate_extractions(self, extractions: List[Dict]) -> List[Dict]:
        """Aggregate and deduplicate extractions from multiple sources"""
        if not extractions:
            return []
        
        # Collect all unique devices
        device_map = {}  # device_name -> list of parameter sets
        
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
        
        # Merge parameter sets (average values, take highest confidence)
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
        """Merge multiple parameter sets, averaging values"""
        if not param_sets:
            return {}
        
        if len(param_sets) == 1:
            return param_sets[0]
        
        merged = {}
        param_values = {}  # param_name -> list of values
        
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
        
        # Average the values
        for name, values in param_values.items():
            if not values:
                continue
            
            avg_value = sum(v["value"] for v in values) / len(values)
            max_confidence = max(v["confidence"] for v in values)
            
            # Boost confidence if multiple sources agree
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
        """Calculate overall confidence from multiple extractions"""
        if not extractions:
            return 0.0
        
        # Base confidence from individual extractions
        confidences = [e.get("confidence", 0.5) for e in extractions]
        avg_confidence = sum(confidences) / len(confidences)
        
        # Boost for multiple sources
        source_boost = min(0.2, 0.05 * (len(extractions) - 1))
        
        return min(1.0, avg_confidence + source_boost)


# Singleton instance
_youtube_researcher: Optional[YouTubeResearcher] = None


def get_youtube_researcher() -> YouTubeResearcher:
    """Get the singleton YouTubeResearcher instance"""
    global _youtube_researcher
    if _youtube_researcher is None:
        _youtube_researcher = YouTubeResearcher()
    return _youtube_researcher


# Convenience functions
async def search_youtube_tutorials(query: str, max_results: int = 5) -> List[VideoInfo]:
    """Search for YouTube tutorials"""
    return await get_youtube_researcher().search_tutorials(query, max_results)


async def fetch_transcript(video_id: str) -> TranscriptResult:
    """Fetch a video transcript"""
    return await get_youtube_researcher().fetch_transcript(video_id)


async def research_vocal_chain_youtube(query: str, max_videos: int = 3) -> YouTubeResearchResult:
    """Research vocal chain settings from YouTube"""
    return await get_youtube_researcher().research_vocal_chain(query, max_videos)

