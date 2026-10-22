from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional


class LibrarianSessionContext:
    def __init__(self) -> None:
        self._active: Optional[Dict[str, Any]] = None

    def set_active(self, song_data: dict, section: str, track_index: Optional[int] = None, song_file: Optional[str] = None) -> None:
        self._active = {
            "active_song_file": song_file,
            "active_song_data": song_data,
            "active_section": section,
            "active_chain_devices": ((song_data.get("sections", {}) or {}).get(section, {}) or {}).get("chain", []),
            "loaded_at": datetime.now().isoformat(),
            "track_index": track_index,
        }

    def get_active(self) -> Optional[Dict[str, Any]]:
        return self._active

    def clear(self) -> None:
        self._active = None


_SESSION_CONTEXT_SINGLETON: Optional[LibrarianSessionContext] = None


def get_librarian_session_context() -> LibrarianSessionContext:
    global _SESSION_CONTEXT_SINGLETON
    if _SESSION_CONTEXT_SINGLETON is None:
        _SESSION_CONTEXT_SINGLETON = LibrarianSessionContext()
    return _SESSION_CONTEXT_SINGLETON
