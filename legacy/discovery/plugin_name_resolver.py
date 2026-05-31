"""
Plugin Name Resolver

Provides tiered resolution strategy for matching user plugin requests
to exact device names required by Ableton.

Resolution Tiers:
1. Exact Match - Direct case-insensitive match against installed plugins
2. Alias Map - Check plugin_aliases.json for known mappings
3. Fuzzy Match - Use difflib to find closest matches above threshold
4. (Future) LLM Fallback - Use LLM to disambiguate when above methods fail
"""

import json
import os
from difflib import SequenceMatcher, get_close_matches
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass


@dataclass
class ResolveResult:
    """Result of plugin name resolution"""
    resolved_name: Optional[str]
    original_query: str
    resolution_tier: str  # "exact", "alias", "fuzzy", "llm", "not_found"
    confidence: float  # 0.0-1.0
    alternatives: List[str]  # Other possible matches

    def to_dict(self) -> Dict:
        return {
            "resolved_name": self.resolved_name,
            "original_query": self.original_query,
            "resolution_tier": self.resolution_tier,
            "confidence": self.confidence,
            "alternatives": self.alternatives
        }


class PluginNameResolver:
    """
    Resolves user plugin name queries to exact Ableton device names.

    Uses a tiered approach for robust matching:
    1. Exact match (fastest, most reliable)
    2. Alias lookup (handles known variations)
    3. Fuzzy matching (handles typos and minor variations)
    """

    def __init__(self,
                 aliases_file: str = "config/plugin_aliases.json",
                 installed_plugins_file: str = "config/vst_cache.json"):
        """
        Initialize the resolver.

        Args:
            aliases_file: Path to plugin aliases JSON config
            installed_plugins_file: Path to cached installed plugins list
        """
        self.aliases_file = aliases_file
        self.installed_plugins_file = installed_plugins_file

        # Alias mappings: alias -> canonical name
        self._alias_to_canonical: Dict[str, str] = {}
        # Canonical name -> all aliases
        self._canonical_to_aliases: Dict[str, List[str]] = {}
        # Learned aliases (user corrections)
        self._learned_aliases: Dict[str, str] = {}

        # Installed plugin names (ground truth)
        self._installed_plugins: List[str] = []
        self._installed_plugins_lower: Dict[str, str] = {}  # lower -> actual

        # Fuzzy matching thresholds
        self.fuzzy_threshold_high = 0.85  # High confidence match
        self.fuzzy_threshold_medium = 0.70  # Acceptable match
        self.fuzzy_threshold_low = 0.55  # Suggest but warn

        # Load data
        self._load_aliases()
        self._load_installed_plugins()

    def _load_aliases(self) -> bool:
        """Load alias mappings from config file"""
        if not os.path.exists(self.aliases_file):
            print(f"[PluginResolver] No alias file found at {self.aliases_file}")
            return False

        try:
            with open(self.aliases_file, 'r') as f:
                data = json.load(f)

            aliases_section = data.get("aliases", {})

            for canonical, info in aliases_section.items():
                # Store canonical -> aliases mapping
                all_aliases = info.get("aliases", []) + info.get("learned_aliases", [])
                self._canonical_to_aliases[canonical] = all_aliases

                # Build reverse mapping: alias -> canonical
                canonical_name = info.get("canonical", canonical)
                for alias in all_aliases:
                    self._alias_to_canonical[alias.lower()] = canonical_name

                # Also map canonical name to itself
                self._alias_to_canonical[canonical.lower()] = canonical_name
                self._alias_to_canonical[canonical_name.lower()] = canonical_name

            print(f"[PluginResolver] Loaded {len(self._alias_to_canonical)} alias mappings")
            return True

        except Exception as e:
            print(f"[PluginResolver] Error loading aliases: {e}")
            return False

    def _load_installed_plugins(self) -> bool:
        """Load installed plugins from cache file"""
        if not os.path.exists(self.installed_plugins_file):
            print(f"[PluginResolver] No installed plugins cache at {self.installed_plugins_file}")
            return False

        try:
            with open(self.installed_plugins_file, 'r') as f:
                data = json.load(f)

            plugins = data.get("plugins", [])
            self._installed_plugins = [p.get("name", "") for p in plugins if p.get("name")]

            # Build case-insensitive lookup
            self._installed_plugins_lower = {
                name.lower(): name for name in self._installed_plugins
            }

            print(f"[PluginResolver] Loaded {len(self._installed_plugins)} installed plugins")
            return True

        except Exception as e:
            print(f"[PluginResolver] Error loading installed plugins: {e}")
            return False

    def reload(self):
        """Reload aliases and installed plugins from files"""
        self._alias_to_canonical.clear()
        self._canonical_to_aliases.clear()
        self._installed_plugins.clear()
        self._installed_plugins_lower.clear()

        self._load_aliases()
        self._load_installed_plugins()

    # ==================== TIER 1: EXACT MATCH ====================

    def _exact_match(self, query: str) -> Optional[str]:
        """
        Tier 1: Try exact case-insensitive match against installed plugins.

        Returns:
            Exact plugin name if found, None otherwise
        """
        query_lower = query.lower().strip()

        # Direct lookup in installed plugins
        if query_lower in self._installed_plugins_lower:
            return self._installed_plugins_lower[query_lower]

        return None

    # ==================== TIER 2: ALIAS LOOKUP ====================

    def _alias_lookup(self, query: str) -> Optional[str]:
        """
        Tier 2: Look up query in alias mappings.

        Returns:
            Canonical plugin name if alias found, None otherwise
        """
        query_lower = query.lower().strip()

        # Direct alias lookup
        if query_lower in self._alias_to_canonical:
            canonical = self._alias_to_canonical[query_lower]
            # Verify canonical name is actually installed
            canonical_lower = canonical.lower()
            if canonical_lower in self._installed_plugins_lower:
                return self._installed_plugins_lower[canonical_lower]
            # Return canonical anyway (might be a native device)
            return canonical

        # Check if query is contained in any alias
        for alias, canonical in self._alias_to_canonical.items():
            if query_lower in alias or alias in query_lower:
                # Verify installed
                canonical_lower = canonical.lower()
                if canonical_lower in self._installed_plugins_lower:
                    return self._installed_plugins_lower[canonical_lower]
                return canonical

        # Check learned aliases
        if query_lower in self._learned_aliases:
            return self._learned_aliases[query_lower]

        return None

    # ==================== TIER 3: FUZZY MATCH ====================

    def _fuzzy_match(self, query: str, threshold: float = None) -> Tuple[Optional[str], float, List[str]]:
        """
        Tier 3: Use fuzzy matching to find closest plugin names.

        Args:
            query: The plugin name to search for
            threshold: Minimum similarity score (0.0-1.0), defaults to medium threshold

        Returns:
            Tuple of (best_match, confidence, alternatives)
        """
        if threshold is None:
            threshold = self.fuzzy_threshold_medium

        query_lower = query.lower().strip()

        # Collect all searchable names (installed + aliases)
        all_names = list(self._installed_plugins)

        # Score each candidate
        scored_matches: List[Tuple[float, str]] = []

        for name in all_names:
            # Calculate similarity using multiple methods
            score = self._calculate_similarity(query_lower, name.lower())
            if score >= threshold:
                scored_matches.append((score, name))

        # Sort by score descending
        scored_matches.sort(key=lambda x: x[0], reverse=True)

        if not scored_matches:
            return (None, 0.0, [])

        best_score, best_match = scored_matches[0]
        alternatives = [name for _, name in scored_matches[1:4]]  # Top 3 alternatives

        return (best_match, best_score, alternatives)

    def _calculate_similarity(self, query: str, candidate: str) -> float:
        """
        Calculate similarity score between query and candidate.

        Uses multiple heuristics:
        1. Exact substring matching (high confidence)
        2. Token-based matching (handles reordering)
        3. Sequence matching (handles typos)
        """
        # Normalize strings
        query = query.lower().strip()
        candidate = candidate.lower().strip()

        # Exact match
        if query == candidate:
            return 1.0

        # Substring matching
        if query in candidate:
            # "Pro-Q" in "FabFilter Pro-Q 3" should score high
            ratio = len(query) / len(candidate)
            return max(0.85, ratio * 0.95)

        if candidate in query:
            ratio = len(candidate) / len(query)
            return max(0.75, ratio * 0.9)

        # Token-based matching (handles "Pro Q 3" vs "Pro-Q 3")
        query_tokens = set(self._tokenize(query))
        candidate_tokens = set(self._tokenize(candidate))

        if query_tokens and candidate_tokens:
            common_tokens = query_tokens & candidate_tokens
            token_score = len(common_tokens) / max(len(query_tokens), len(candidate_tokens))

            # Boost score if significant token overlap
            if token_score >= 0.5:
                return max(0.7, token_score * 0.95)

        # Sequence matching (handles typos)
        seq_ratio = SequenceMatcher(None, query, candidate).ratio()

        # Also try with tokens sorted (handles reordering)
        query_sorted = ' '.join(sorted(query_tokens))
        candidate_sorted = ' '.join(sorted(candidate_tokens))
        sorted_ratio = SequenceMatcher(None, query_sorted, candidate_sorted).ratio()

        # Return best of sequence ratios
        return max(seq_ratio, sorted_ratio)

    def _tokenize(self, text: str) -> List[str]:
        """Split text into tokens, handling common separators"""
        import re
        # Split on spaces, hyphens, underscores, and transition from letter to number
        tokens = re.split(r'[\s\-_]+|(?<=[a-z])(?=[0-9])|(?<=[0-9])(?=[a-z])', text.lower())
        return [t for t in tokens if t]  # Remove empty strings

    # ==================== MAIN RESOLVE METHOD ====================

    def resolve(self, query: str, strict: bool = False) -> ResolveResult:
        """
        Resolve a plugin name query using tiered strategy.

        Args:
            query: The plugin name to resolve (e.g., "EQ8", "FabFilter Pro-Q", "compressor")
            strict: If True, only return high-confidence matches

        Returns:
            ResolveResult with resolved name and metadata
        """
        query = query.strip()

        # Tier 1: Exact Match
        exact = self._exact_match(query)
        if exact:
            return ResolveResult(
                resolved_name=exact,
                original_query=query,
                resolution_tier="exact",
                confidence=1.0,
                alternatives=[]
            )

        # Tier 2: Alias Lookup
        alias_match = self._alias_lookup(query)
        if alias_match:
            return ResolveResult(
                resolved_name=alias_match,
                original_query=query,
                resolution_tier="alias",
                confidence=0.95,
                alternatives=[]
            )

        # Tier 3: Fuzzy Match
        threshold = self.fuzzy_threshold_high if strict else self.fuzzy_threshold_medium
        fuzzy_match, confidence, alternatives = self._fuzzy_match(query, threshold)

        if fuzzy_match:
            return ResolveResult(
                resolved_name=fuzzy_match,
                original_query=query,
                resolution_tier="fuzzy",
                confidence=confidence,
                alternatives=alternatives
            )

        # No match found
        # Get suggestions for the user
        _, _, suggestions = self._fuzzy_match(query, self.fuzzy_threshold_low)

        return ResolveResult(
            resolved_name=None,
            original_query=query,
            resolution_tier="not_found",
            confidence=0.0,
            alternatives=suggestions
        )

    def resolve_with_category(self,
                               query: str,
                               category: Optional[str] = None,
                               installed_plugins: Optional[List[Dict]] = None) -> ResolveResult:
        """
        Resolve a plugin name, optionally filtering by category.

        Args:
            query: Plugin name to resolve
            category: Optional category filter (eq, compressor, reverb, etc.)
            installed_plugins: Optional list of plugin dicts with 'name' and 'category' keys

        Returns:
            ResolveResult with best match in category
        """
        # First try standard resolution
        result = self.resolve(query)

        if result.resolved_name and not category:
            return result

        # If category specified, verify match is in category or find better
        if category and installed_plugins:
            category_lower = category.lower()
            category_plugins = [
                p['name'] for p in installed_plugins
                if p.get('category', '').lower() == category_lower
            ]

            if category_plugins:
                # Fuzzy match within category
                query_lower = query.lower()
                best_match = None
                best_score = 0.0

                for name in category_plugins:
                    score = self._calculate_similarity(query_lower, name.lower())
                    if score > best_score:
                        best_score = score
                        best_match = name

                if best_match and best_score >= self.fuzzy_threshold_medium:
                    return ResolveResult(
                        resolved_name=best_match,
                        original_query=query,
                        resolution_tier="fuzzy",
                        confidence=best_score,
                        alternatives=[n for n in category_plugins if n != best_match][:3]
                    )

        return result

    # ==================== LEARNING / FEEDBACK ====================

    def learn_alias(self, alias: str, canonical_name: str) -> bool:
        """
        Learn a new alias mapping from user correction.

        Args:
            alias: The name the user used
            canonical_name: The correct plugin name

        Returns:
            True if alias was added
        """
        alias_lower = alias.lower().strip()

        # Don't override existing mappings
        if alias_lower in self._alias_to_canonical:
            return False

        # Add to runtime learned aliases
        self._learned_aliases[alias_lower] = canonical_name
        self._alias_to_canonical[alias_lower] = canonical_name

        # Persist to file
        self._save_learned_alias(alias, canonical_name)

        print(f"[PluginResolver] Learned: '{alias}' -> '{canonical_name}'")
        return True

    def _save_learned_alias(self, alias: str, canonical_name: str):
        """Save a learned alias to the config file"""
        try:
            if not os.path.exists(self.aliases_file):
                return

            with open(self.aliases_file, 'r') as f:
                data = json.load(f)

            # Find or create entry for canonical name
            aliases_section = data.get("aliases", {})

            if canonical_name in aliases_section:
                learned = aliases_section[canonical_name].get("learned_aliases", [])
                if alias not in learned:
                    learned.append(alias)
                    aliases_section[canonical_name]["learned_aliases"] = learned
            else:
                # Create new entry
                aliases_section[canonical_name] = {
                    "canonical": canonical_name,
                    "aliases": [],
                    "learned_aliases": [alias]
                }

            data["aliases"] = aliases_section

            with open(self.aliases_file, 'w') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            print(f"[PluginResolver] Error saving learned alias: {e}")

    # ==================== UTILITY METHODS ====================

    def get_all_aliases(self, plugin_name: str) -> List[str]:
        """Get all known aliases for a plugin name"""
        return self._canonical_to_aliases.get(plugin_name, [])

    def get_installed_plugins(self) -> List[str]:
        """Get list of all installed plugin names"""
        return self._installed_plugins.copy()

    def is_installed(self, plugin_name: str) -> bool:
        """Check if a plugin is installed"""
        return plugin_name.lower() in self._installed_plugins_lower

    def suggest_corrections(self, query: str, limit: int = 5) -> List[Tuple[str, float]]:
        """
        Get suggested corrections for a query.

        Returns:
            List of (plugin_name, confidence) tuples
        """
        _, _, alternatives = self._fuzzy_match(query, threshold=0.3)

        results = []
        for alt in alternatives[:limit]:
            score = self._calculate_similarity(query.lower(), alt.lower())
            results.append((alt, score))

        return sorted(results, key=lambda x: x[1], reverse=True)


# Singleton instance
_resolver_instance: Optional[PluginNameResolver] = None


def get_plugin_resolver() -> PluginNameResolver:
    """Get the singleton PluginNameResolver instance"""
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = PluginNameResolver()
    return _resolver_instance
