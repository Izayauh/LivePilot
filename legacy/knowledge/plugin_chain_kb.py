"""
Plugin Chain Knowledge Base

Manages cached plugin chain configurations from research results.
Provides quick lookup for previously researched chains.
"""

import json
import os
from typing import Dict, List, Optional, Any
from datetime import datetime


class PluginChainKnowledge:
    """
    Knowledge base for plugin chain configurations
    
    Stores and retrieves researched plugin chains for various
    artists, styles, and track types.
    """
    
    def __init__(self, knowledge_file: str = "knowledge/plugin_chains.json"):
        """
        Initialize the plugin chain knowledge base
        
        Args:
            knowledge_file: Path to the JSON knowledge file
        """
        self.knowledge_file = knowledge_file
        self._chains: Dict[str, Dict] = {}
        self._presets: Dict[str, List[str]] = {}
        self._loaded = False
        
        self._load_knowledge()
    
    def _load_knowledge(self) -> bool:
        """Load knowledge from file"""
        if not os.path.exists(self.knowledge_file):
            return False
        
        try:
            with open(self.knowledge_file, 'r') as f:
                data = json.load(f)
            
            self._chains = data.get('chains', {})
            self._presets = data.get('presets', {})
            self._loaded = True
            
            return True
        except Exception as e:
            print(f"[PluginChainKB] Error loading knowledge: {e}")
            return False
    
    def _save_knowledge(self):
        """Save knowledge to file"""
        try:
            os.makedirs(os.path.dirname(self.knowledge_file), exist_ok=True)
            
            data = {
                "version": "1.0",
                "description": "Cached plugin chain research results for Jarvis",
                "last_updated": datetime.now().isoformat(),
                "chains": self._chains,
                "presets": self._presets
            }
            
            with open(self.knowledge_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            print(f"[PluginChainKB] Error saving knowledge: {e}")
    
    def get_chain(self, artist_or_style: str, track_type: str = "vocal") -> Optional[Dict]:
        """
        Get a cached plugin chain
        
        Args:
            artist_or_style: Artist name or style
            track_type: Type of track
            
        Returns:
            Chain configuration dict or None
        """
        # Normalize key
        key = self._normalize_key(artist_or_style, track_type)
        
        # Try exact match
        if key in self._chains:
            return self._chains[key]
        
        # Try partial match
        for chain_key, chain_data in self._chains.items():
            chain_artist = chain_data.get('artist_or_style', '').lower()
            chain_type = chain_data.get('track_type', '').lower()
            
            if (artist_or_style.lower() in chain_artist or 
                chain_artist in artist_or_style.lower()):
                if track_type.lower() == chain_type:
                    return chain_data
        
        return None
    
    def _normalize_key(self, artist_or_style: str, track_type: str) -> str:
        """Normalize a key for storage/lookup"""
        artist_normalized = artist_or_style.lower().replace(' ', '_').replace('-', '_')
        return f"{artist_normalized}_{track_type.lower()}"
    
    def add_chain(self, 
                  artist_or_style: str,
                  track_type: str,
                  chain: List[Dict],
                  sources: List[str] = None,
                  description: str = "",
                  confidence: float = 0.5) -> str:
        """
        Add a new chain to the knowledge base
        
        Args:
            artist_or_style: Artist name or style
            track_type: Type of track
            chain: List of plugin configurations
            sources: Where this chain came from
            description: Description of the chain
            confidence: Confidence score 0-1
            
        Returns:
            The key used to store the chain
        """
        key = self._normalize_key(artist_or_style, track_type)
        
        self._chains[key] = {
            "artist_or_style": artist_or_style,
            "track_type": track_type,
            "researched_date": datetime.now().strftime("%Y-%m-%d"),
            "sources": sources or ["user_added"],
            "description": description,
            "chain": chain,
            "confidence": confidence
        }
        
        self._save_knowledge()
        return key
    
    def update_chain(self, key: str, updates: Dict) -> bool:
        """
        Update an existing chain
        
        Args:
            key: Chain key
            updates: Dict of updates to apply
            
        Returns:
            True if successful
        """
        if key not in self._chains:
            return False
        
        self._chains[key].update(updates)
        self._chains[key]["last_modified"] = datetime.now().isoformat()
        
        self._save_knowledge()
        return True
    
    def delete_chain(self, key: str) -> bool:
        """Delete a chain from the knowledge base"""
        if key not in self._chains:
            return False
        
        del self._chains[key]
        self._save_knowledge()
        return True
    
    def get_preset(self, preset_name: str, track_type: str = "vocal") -> Optional[List[str]]:
        """
        Get a preset chain configuration
        
        Args:
            preset_name: Preset name (basic, full, minimal)
            track_type: Track type
            
        Returns:
            List of plugin types in the chain
        """
        key = f"{track_type}_{preset_name}"
        return self._presets.get(key)
    
    def list_chains(self, track_type: Optional[str] = None) -> List[Dict]:
        """
        List all available chains
        
        Args:
            track_type: Optional filter by track type
            
        Returns:
            List of chain summaries
        """
        chains = []
        
        for key, chain_data in self._chains.items():
            if track_type and chain_data.get('track_type', '').lower() != track_type.lower():
                continue
            
            chains.append({
                "key": key,
                "artist_or_style": chain_data.get('artist_or_style'),
                "track_type": chain_data.get('track_type'),
                "description": chain_data.get('description', ''),
                "confidence": chain_data.get('confidence', 0.5),
                "plugin_count": len(chain_data.get('chain', []))
            })
        
        return chains
    
    def list_presets(self) -> Dict[str, List[str]]:
        """Get all available presets"""
        return self._presets.copy()
    
    def search_chains(self, query: str) -> List[Dict]:
        """
        Search for chains matching a query
        
        Args:
            query: Search query
            
        Returns:
            List of matching chains
        """
        query_lower = query.lower()
        matches = []
        
        for key, chain_data in self._chains.items():
            score = 0
            
            # Check artist/style
            artist = chain_data.get('artist_or_style', '').lower()
            if query_lower in artist or artist in query_lower:
                score += 2
            
            # Check description
            description = chain_data.get('description', '').lower()
            if query_lower in description:
                score += 1
            
            # Check track type
            track_type = chain_data.get('track_type', '').lower()
            if query_lower in track_type:
                score += 1
            
            if score > 0:
                matches.append({
                    "key": key,
                    "score": score,
                    "data": chain_data
                })
        
        # Sort by score descending
        matches.sort(key=lambda x: x['score'], reverse=True)
        return matches
    
    def get_chain_for_research(self, artist_or_style: str, track_type: str) -> Optional[Dict]:
        """
        Get chain data formatted for research agent use
        
        Returns the chain in the format expected by ResearchAgent
        """
        chain_data = self.get_chain(artist_or_style, track_type)
        
        if not chain_data:
            return None
        
        return {
            "artist_or_style": chain_data.get("artist_or_style"),
            "track_type": chain_data.get("track_type"),
            "chain": chain_data.get("chain", []),
            "confidence": chain_data.get("confidence", 0.5),
            "from_cache": True,
            "sources": chain_data.get("sources", [])
        }
    
    def record_successful_load(self, key: str, track_index: int, plugins_loaded: List[str]):
        """
        Record that a chain was successfully loaded
        
        This can be used for learning/optimization
        """
        if key not in self._chains:
            return
        
        if "load_history" not in self._chains[key]:
            self._chains[key]["load_history"] = []
        
        self._chains[key]["load_history"].append({
            "timestamp": datetime.now().isoformat(),
            "track_index": track_index,
            "plugins_loaded": plugins_loaded
        })
        
        # Keep only last 10 loads
        self._chains[key]["load_history"] = self._chains[key]["load_history"][-10:]
        
        self._save_knowledge()


# Singleton instance
_plugin_chain_kb = None


def get_plugin_chain_kb() -> PluginChainKnowledge:
    """Get the singleton PluginChainKnowledge instance"""
    global _plugin_chain_kb
    if _plugin_chain_kb is None:
        _plugin_chain_kb = PluginChainKnowledge()
    return _plugin_chain_kb

