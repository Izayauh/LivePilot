from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional
import json

from .extractor import to_chainspec_format
from .index import LibraryIndex
from .session_context import get_librarian_session_context


class LibrarianAgent:
    def __init__(self, base_dir: Optional[str] = None) -> None:
        self.index = LibraryIndex(base_dir=base_dir)
        self.session_context = get_librarian_session_context()

    def list_library(self) -> Dict:
        items = self.index.list_all()
        songs = [
            {
                "title": e.title,
                "artist": e.artist,
                "year": e.year,
                "genre": e.genre,
                "tags": e.global_tags,
                "file": e.filename,
            }
            for e in items
        ]
        return {"success": True, "count": len(songs), "songs": songs}

    def search_by_vibe(self, tags: List[str]) -> Dict:
        results = self.index.search_by_tags(tags)
        return {
            "success": True,
            "count": len(results),
            "matches": [
                {
                    "title": e.title,
                    "artist": e.artist,
                    "file": e.filename,
                    "confidence": e.confidence,
                    "tag_overlap": overlap,
                    "tags": e.global_tags,
                }
                for e, overlap in results
            ],
        }

    async def lookup(
        self,
        query: str,
        section: Optional[str] = None,
        artist: Optional[str] = None,
        song_title: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> dict:
        section_name = (section or "verse").strip().lower()
        if section_name in {"all", "whole", "full", "all_sections"}:
            section_name = "verse"

        entry = None
        if song_title or artist:
            entry = self.index.search_by_song(song_title or query, artist or "")
        if entry is None and tags:
            tag_matches = self.index.search_by_tags(tags)
            entry = tag_matches[0][0] if tag_matches else None
        if entry is None:
            vibe_matches = self.index.search_by_vibe(query)
            entry = vibe_matches[0][0] if vibe_matches else None

        if entry is None:
            avail = [f"{e.title} - {e.artist}" for e in self.index.list_all()[:10]]
            return {
                "success": False,
                "message": f"'{query}' is not in the local library. Available songs: {avail}. Use generate_song_data.py to add it.",
                "query": query,
                "source": "local_library_miss",
            }

        p = Path(entry.path)
        song_data = json.loads(p.read_text(encoding="utf-8"))
        section_map = song_data.get("sections", {}) or {}
        if section_name not in section_map:
            section_name = "verse"

        chain_spec = to_chainspec_format(song_data, section_name, query=query)
        self.session_context.set_active(song_data, section_name, song_file=entry.filename)

        return {
            "success": True,
            "chain_spec": chain_spec,
            "message": f"Found in library: {entry.title} ({section_name})",
            "query": query,
            "confidence": float(song_data.get("confidence", 0.7)),
            "source": "local_library",
            "song_file": entry.filename,
            "section": section_name,
            "param_why_available": True,
            "style_description": ((section_map.get(section_name) or {}).get("intent", "")),
            "cache_hit": True,
            "research_meta": {
                "cache_hit": True,
                "cache_type": "local_library",
                "llm_calls_used": 0,
            },
            "next_step": "Present the found devices to the user for confirmation, then call apply_research_chain.",
        }


_LIBRARIAN_SINGLETON: Optional[LibrarianAgent] = None


def get_librarian_agent() -> LibrarianAgent:
    global _LIBRARIAN_SINGLETON
    if _LIBRARIAN_SINGLETON is None:
        _LIBRARIAN_SINGLETON = LibrarianAgent()
    return _LIBRARIAN_SINGLETON
