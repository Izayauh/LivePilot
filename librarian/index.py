from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import json
import re

from .schema import validate_song_data


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _tokenize(s: str) -> Set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", _norm(s)) if t}


@dataclass
class IndexEntry:
    filename: str
    path: str
    title: str
    artist: str
    year: Optional[int]
    genre: Optional[str]
    global_tags: List[str]
    section_keys: List[str]
    confidence: float
    title_normalized: str
    artist_normalized: str
    tags_set: Set[str]


class LibraryIndex:
    def __init__(self, base_dir: Optional[str] = None) -> None:
        project_root = Path(__file__).resolve().parents[1]
        self.base_dir = Path(base_dir) if base_dir else project_root / "docs" / "Research"
        self.entries: List[IndexEntry] = []
        self._by_path: Dict[str, IndexEntry] = {}
        self.reload()

    def reload(self) -> int:
        self.entries = []
        self._by_path = {}
        if not self.base_dir.exists():
            return 0

        for p in sorted(self.base_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            ok, _ = validate_song_data(data)
            if not ok:
                continue

            song = data.get("song", {})
            title = song.get("title", "")
            artist = song.get("artist", "")
            tags = [str(t).strip().lower() for t in data.get("global_tags", []) if str(t).strip()]
            entry = IndexEntry(
                filename=p.name,
                path=str(p),
                title=title,
                artist=artist,
                year=song.get("year"),
                genre=song.get("genre"),
                global_tags=tags,
                section_keys=list((data.get("sections") or {}).keys()),
                confidence=float(data.get("confidence", 0.0)),
                title_normalized=_norm(title),
                artist_normalized=_norm(artist),
                tags_set=set(tags),
            )
            self.entries.append(entry)
            self._by_path[str(p)] = entry

        return len(self.entries)

    def list_all(self) -> List[IndexEntry]:
        return list(self.entries)

    def search_by_song(self, title: str, artist: str = "") -> Optional[IndexEntry]:
        title_n = _norm(title)
        artist_n = _norm(artist)
        if not title_n:
            return None

        exact = [
            e for e in self.entries
            if e.title_normalized == title_n and (not artist_n or e.artist_normalized == artist_n)
        ]
        if exact:
            return sorted(exact, key=lambda e: e.confidence, reverse=True)[0]

        fuzzy = [
            e for e in self.entries
            if title_n in e.title_normalized or e.title_normalized in title_n
        ]
        if artist_n:
            fuzzy = [e for e in fuzzy if artist_n in e.artist_normalized or e.artist_normalized in artist_n]

        if not fuzzy:
            return None
        return sorted(fuzzy, key=lambda e: e.confidence, reverse=True)[0]

    def search_by_tags(self, tags: List[str]) -> List[Tuple[IndexEntry, int]]:
        q = {t.strip().lower() for t in tags if str(t).strip()}
        if not q:
            return []
        scored: List[Tuple[IndexEntry, int]] = []
        for e in self.entries:
            overlap = len(e.tags_set & q)
            if overlap > 0:
                scored.append((e, overlap))
        return sorted(scored, key=lambda x: (x[1], x[0].confidence), reverse=True)

    def search_by_vibe(self, query: str) -> List[Tuple[IndexEntry, float]]:
        q = _tokenize(query)
        if not q:
            return []
        scored: List[Tuple[IndexEntry, float]] = []
        for e in self.entries:
            pool = e.tags_set | _tokenize(e.title) | _tokenize(e.artist)
            overlap = len(q & pool)
            if overlap:
                score = overlap / max(1, len(q)) + (0.05 * e.confidence)
                scored.append((e, score))
        return sorted(scored, key=lambda x: x[1], reverse=True)
