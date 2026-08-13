"""
Artifact Chain Store

Manages cached vocal chain artifacts on disk as individual JSON files.
Each artifact is a self-contained, deterministic chain specification produced
by a single LLM research call. Subsequent requests for the same/similar chain
load instantly from the filesystem with zero LLM calls.

Artifact directory: knowledge/chains/
"""

import json
import os
import re
import hashlib
from collections import Counter
from datetime import datetime
from typing import Dict, List, Optional, Any


# Default directory relative to project root
_DEFAULT_CHAINS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "chains"
)


class ArtifactChainStore:
    """
    Filesystem-backed cache for researched vocal chain artifacts.

    Each artifact is a JSON file in knowledge/chains/ keyed by a normalized
    query slug.  Supports:
      - Exact and fuzzy query matching
      - Staleness detection
      - Preset listing / recall
    """

    SCHEMA_VERSION = 1

    def __init__(self, chains_dir: str = _DEFAULT_CHAINS_DIR):
        self._chains_dir = chains_dir
        os.makedirs(self._chains_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_artifact(self, query: str, artifact_data: Dict[str, Any]) -> str:
        """
        Persist a chain artifact to disk.

        Args:
            query: The original user query (e.g. "Travis Scott Utopia vocal chain")
            artifact_data: Full artifact dict (see schema in implementation_plan.md)

        Returns:
            The filesystem key used (e.g. "travis_scott_utopia_vocal_chain")
        """
        key = self._query_to_key(query)

        # Ensure metadata is present
        artifact_data.setdefault("version", self.SCHEMA_VERSION)
        artifact_data.setdefault("query", query)
        artifact_data.setdefault("created_at", datetime.now().isoformat())
        artifact_data.setdefault("confidence", 0.0)
        artifact_data.setdefault("chain", [])

        path = self._key_to_path(key)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(artifact_data, f, indent=2)

        return key

    def load_artifact(
        self,
        query: str,
        similarity_threshold: float = 0.55,
    ) -> Optional[Dict[str, Any]]:
        """
        Load an artifact by query.  Tries exact match first, then fuzzy.

        Args:
            query: User query
            similarity_threshold: Minimum similarity score for fuzzy match (0-1)

        Returns:
            Artifact dict or None if no match found
        """
        key = self._query_to_key(query)

        # 1) Exact key match
        exact = self._load_from_key(key)
        if exact is not None:
            exact["_cache_match"] = "exact"
            return exact

        # 2) Fuzzy match across all stored artifacts
        best_artifact = None
        best_score = 0.0

        for artifact_key in self._list_keys():
            stored = self._load_from_key(artifact_key)
            if stored is None:
                continue
            stored_query = stored.get("query", artifact_key)
            score = self._query_similarity(query, stored_query)
            if score > best_score:
                best_score = score
                best_artifact = stored

        if best_artifact and best_score >= similarity_threshold:
            best_artifact["_cache_match"] = "fuzzy"
            best_artifact["_cache_similarity"] = round(best_score, 4)
            return best_artifact

        return None

    def is_stale(
        self, artifact: Dict[str, Any], max_age_days: int = 30
    ) -> bool:
        """Check whether an artifact should be refreshed."""
        created = artifact.get("created_at")
        if not created:
            return True
        try:
            dt = datetime.fromisoformat(created)
            age = (datetime.now() - dt).days
            return age > max_age_days
        except (ValueError, TypeError):
            return True

    def list_artifacts(self) -> List[Dict[str, Any]]:
        """Return a summary of every cached artifact (lightweight)."""
        results = []
        for key in self._list_keys():
            artifact = self._load_from_key(key)
            if artifact is None:
                continue
            results.append({
                "key": key,
                "query": artifact.get("query", key),
                "artist": artifact.get("artist", ""),
                "track_type": artifact.get("track_type", "vocal"),
                "confidence": artifact.get("confidence", 0.0),
                "plugin_count": len(artifact.get("chain", [])),
                "created_at": artifact.get("created_at", ""),
                "source": artifact.get("source", ""),
            })
        return results

    def delete_artifact(self, query: str) -> bool:
        """Delete the artifact for a given query. Returns True if removed."""
        key = self._query_to_key(query)
        path = self._key_to_path(key)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False

    def get_artifact_for_execution(
        self, query: str, max_age_days: int = 30
    ) -> Optional[Dict[str, Any]]:
        """
        High-level convenience: load an artifact only if it exists and is fresh.

        Returns:
            Artifact dict ready for deterministic execution, or None.
        """
        artifact = self.load_artifact(query)
        if artifact is None:
            return None
        if self.is_stale(artifact, max_age_days):
            return None
        return artifact

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _query_to_key(self, query: str) -> str:
        """Normalize a query string to a filesystem-safe key."""
        text = (query or "").strip().lower()
        # Remove common filler words for better matching
        for word in ("vocal chain", "chain", "give me", "create", "make",
                     "set up", "on track", "please"):
            text = text.replace(word, "")
        text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
        # Collapse runs of underscores
        text = re.sub(r"_+", "_", text)
        return text or "unknown"

    def _key_to_path(self, key: str) -> str:
        return os.path.join(self._chains_dir, f"{key}.json")

    def _load_from_key(self, key: str) -> Optional[Dict[str, Any]]:
        path = self._key_to_path(key)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def _list_keys(self) -> List[str]:
        """List all stored artifact keys (filenames without .json)."""
        try:
            return [
                f[:-5]
                for f in os.listdir(self._chains_dir)
                if f.endswith(".json")
            ]
        except OSError:
            return []

    # ------------------------------------------------------------------
    # Lightweight similarity (reuses logic from research_coordinator)
    # ------------------------------------------------------------------

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return re.findall(r"[a-z0-9]+", (text or "").strip().lower())

    @classmethod
    def _query_similarity(cls, a: str, b: str) -> float:
        """Jaccard + overlap similarity between two query strings."""
        a_tokens = cls._tokenize(a)
        b_tokens = cls._tokenize(b)
        if not a_tokens or not b_tokens:
            return 0.0

        a_set = set(a_tokens)
        b_set = set(b_tokens)
        jaccard = len(a_set & b_set) / max(1, len(a_set | b_set))

        a_counts = Counter(a_tokens)
        b_counts = Counter(b_tokens)
        shared = sum(min(a_counts[t], b_counts[t]) for t in (a_set & b_set))
        denom = max(1, min(len(a_tokens), len(b_tokens)))
        overlap = shared / denom

        return (0.7 * jaccard) + (0.3 * overlap)


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_store: Optional[ArtifactChainStore] = None


def get_artifact_chain_store() -> ArtifactChainStore:
    """Get the singleton ArtifactChainStore instance."""
    global _store
    if _store is None:
        _store = ArtifactChainStore()
    return _store
