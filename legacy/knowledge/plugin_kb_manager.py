"""
Plugin Knowledge Base Manager

Provides semantic access to plugin parameter information for research-driven
vocal chain generation. Enables intent-based parameter lookup and validation.
"""

import json
import os
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass


@dataclass
class ParameterInfo:
    """Information about a single parameter"""
    name: str
    description: str
    param_type: str
    unit: Optional[str]
    min_value: float
    max_value: float
    default: float
    semantic_tags: List[str]
    typical_ranges: Optional[Dict[str, Any]] = None


@dataclass
class PluginInfo:
    """Information about a plugin"""
    name: str
    description: str
    category: str
    typical_use_cases: List[str]
    signal_flow_positions: List[str]
    parameters: Dict[str, ParameterInfo]
    production_notes: str
    common_settings: Dict[str, Any]


class PluginKnowledgeBase:
    """
    Semantic knowledge base for Ableton Live audio effects.
    
    Provides:
    - Plugin and parameter information lookup
    - Intent-based parameter discovery
    - Typical range recommendations
    - Parameter validation
    """
    
    def __init__(self, kb_path: str = None):
        """
        Initialize the knowledge base.
        
        Args:
            kb_path: Path to the knowledge base JSON file.
                     Defaults to knowledge/plugin_semantic_kb.json
        """
        if kb_path is None:
            # Get path relative to this file
            base_dir = os.path.dirname(os.path.abspath(__file__))
            kb_path = os.path.join(base_dir, "plugin_semantic_kb.json")
        
        self.kb_path = kb_path
        self._data: Dict[str, Any] = {}
        self._plugins: Dict[str, Dict] = {}
        self._intent_mapping: Dict[str, Dict] = {}
        self._signal_flow: Dict[str, List] = {}
        self._loaded = False
        
        self._load_knowledge_base()
    
    def _load_knowledge_base(self) -> bool:
        """Load the knowledge base from JSON file"""
        if not os.path.exists(self.kb_path):
            print(f"[PluginKB] Knowledge base not found: {self.kb_path}")
            return False
        
        try:
            with open(self.kb_path, 'r', encoding='utf-8') as f:
                self._data = json.load(f)
            
            self._plugins = self._data.get("plugins", {})
            self._intent_mapping = self._data.get("semantic_intent_mapping", {})
            self._signal_flow = self._data.get("signal_flow_recommendations", {})
            self._loaded = True
            
            print(f"[PluginKB] Loaded {len(self._plugins)} plugins")
            return True
            
        except Exception as e:
            print(f"[PluginKB] Error loading knowledge base: {e}")
            return False
    
    def is_loaded(self) -> bool:
        """Check if knowledge base is loaded"""
        return self._loaded
    
    def get_plugin_names(self) -> List[str]:
        """Get list of all plugin names in the knowledge base"""
        return list(self._plugins.keys())
    
    def get_plugin_info(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """
        Get full information about a plugin.
        
        Args:
            plugin_name: Name of the plugin (e.g., "EQ Eight", "Compressor")
            
        Returns:
            Dictionary with plugin metadata, parameters, and production notes,
            or None if plugin not found.
        """
        # Try exact match first
        if plugin_name in self._plugins:
            return self._plugins[plugin_name]
        
        # Try case-insensitive match
        plugin_name_lower = plugin_name.lower()
        for name, info in self._plugins.items():
            if name.lower() == plugin_name_lower:
                return info
        
        # Try partial match
        for name, info in self._plugins.items():
            if plugin_name_lower in name.lower() or name.lower() in plugin_name_lower:
                return info
        
        return None
    
    def get_parameter_info(self, plugin_name: str, param_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific parameter.
        
        Args:
            plugin_name: Name of the plugin
            param_name: Name of the parameter
            
        Returns:
            Dictionary with parameter info or None if not found
        """
        plugin_info = self.get_plugin_info(plugin_name)
        if not plugin_info:
            return None
        
        params = plugin_info.get("parameters", {})
        
        # Try exact match
        if param_name in params:
            return params[param_name]
        
        # Try case-insensitive match
        param_name_lower = param_name.lower()
        for name, info in params.items():
            if name.lower() == param_name_lower:
                return info
        
        # Try partial match
        for name, info in params.items():
            if param_name_lower in name.lower():
                return info
        
        return None
    
    def find_parameters_for_intent(self, plugin_name: str, intent: str) -> List[Dict[str, Any]]:
        """
        Find parameters that match a semantic intent.
        
        Args:
            plugin_name: Name of the plugin
            intent: Semantic intent (e.g., "cut_mud", "add_presence", "threshold")
            
        Returns:
            List of matching parameters with their info
        """
        plugin_info = self.get_plugin_info(plugin_name)
        if not plugin_info:
            return []
        
        params = plugin_info.get("parameters", {})
        matches = []
        intent_lower = intent.lower().replace("_", " ").replace("-", " ")
        intent_words = set(intent_lower.split())
        
        for param_name, param_info in params.items():
            score = 0
            
            # Check semantic tags
            tags = param_info.get("semantic_tags", [])
            for tag in tags:
                tag_lower = tag.lower()
                if intent_lower in tag_lower or tag_lower in intent_lower:
                    score += 3
                elif any(word in tag_lower for word in intent_words):
                    score += 1
            
            # Check parameter name
            param_name_lower = param_name.lower()
            if intent_lower in param_name_lower:
                score += 2
            elif any(word in param_name_lower for word in intent_words):
                score += 1
            
            # Check description
            description = param_info.get("description", "").lower()
            if intent_lower in description:
                score += 1
            
            # Check typical ranges keys
            typical_ranges = param_info.get("typical_ranges", {})
            for range_key in typical_ranges.keys():
                if intent_lower in range_key.lower():
                    score += 2
            
            if score > 0:
                matches.append({
                    "name": param_name,
                    "info": param_info,
                    "score": score
                })
        
        # Sort by score descending
        matches.sort(key=lambda x: x["score"], reverse=True)
        return matches
    
    def get_typical_range(self, plugin_name: str, param_name: str, 
                          use_case: str) -> Optional[Dict[str, Any]]:
        """
        Get typical parameter range for a specific use case.
        
        Args:
            plugin_name: Name of the plugin
            param_name: Name of the parameter
            use_case: Use case identifier (e.g., "vocal_cut_mud", "aggressive_vocal")
            
        Returns:
            Dictionary with min, max, and description, or None if not found
        """
        param_info = self.get_parameter_info(plugin_name, param_name)
        if not param_info:
            return None
        
        typical_ranges = param_info.get("typical_ranges", {})
        if not typical_ranges:
            return None
        
        # Try exact match
        if use_case in typical_ranges:
            return typical_ranges[use_case]
        
        # Try partial match
        use_case_lower = use_case.lower()
        for range_key, range_info in typical_ranges.items():
            if use_case_lower in range_key.lower() or range_key.lower() in use_case_lower:
                return range_info
        
        # Return first range as fallback
        if typical_ranges:
            return list(typical_ranges.values())[0]
        
        return None
    
    def validate_parameter_value(self, plugin_name: str, param_name: str, 
                                  value: float) -> Tuple[bool, float, str]:
        """
        Validate a parameter value and clamp if necessary.
        
        Args:
            plugin_name: Name of the plugin
            param_name: Name of the parameter
            value: Value to validate
            
        Returns:
            Tuple of (is_valid, clamped_value, message)
        """
        param_info = self.get_parameter_info(plugin_name, param_name)
        if not param_info:
            return True, value, "Parameter not found in knowledge base"
        
        min_val = param_info.get("min", float("-inf"))
        max_val = param_info.get("max", float("inf"))
        
        if value < min_val:
            return False, min_val, f"Value {value} below minimum {min_val}, clamped"
        elif value > max_val:
            return False, max_val, f"Value {value} above maximum {max_val}, clamped"
        else:
            return True, value, "Value within valid range"
    
    def get_intent_recommendation(self, intent: str) -> Optional[Dict[str, Any]]:
        """
        Get plugin and parameter recommendations for a semantic intent.
        
        Args:
            intent: Semantic intent (e.g., "cut_mud", "add_warmth", "de_ess")
            
        Returns:
            Dictionary with suggested plugin, action, and ranges
        """
        # Try exact match
        if intent in self._intent_mapping:
            return self._intent_mapping[intent]
        
        # Try partial match
        intent_lower = intent.lower().replace("-", "_")
        for key, value in self._intent_mapping.items():
            if intent_lower in key.lower() or key.lower() in intent_lower:
                return value
        
        return None
    
    def get_signal_flow_recommendation(self, chain_type: str = "standard_vocal_chain") -> List[Dict]:
        """
        Get recommended signal flow for a chain type.
        
        Args:
            chain_type: Type of chain (e.g., "standard_vocal_chain", "aggressive_vocal_chain")
            
        Returns:
            List of plugins in recommended order with purposes
        """
        if chain_type in self._signal_flow:
            return self._signal_flow[chain_type]
        
        # Try partial match
        for key, flow in self._signal_flow.items():
            if chain_type.lower() in key.lower():
                return flow
        
        # Return standard as default
        return self._signal_flow.get("standard_vocal_chain", [])
    
    def get_common_vocal_settings(self, plugin_name: str, 
                                   preset_name: str = None) -> Optional[Dict[str, Any]]:
        """
        Get common vocal settings for a plugin.
        
        Args:
            plugin_name: Name of the plugin
            preset_name: Optional specific preset name
            
        Returns:
            Dictionary with common settings or None
        """
        plugin_info = self.get_plugin_info(plugin_name)
        if not plugin_info:
            return None
        
        common_settings = plugin_info.get("common_vocal_settings", {})
        if not common_settings:
            return None
        
        if preset_name:
            # Try to find specific preset
            if preset_name in common_settings:
                return common_settings[preset_name]
            
            # Try partial match
            for key, settings in common_settings.items():
                if preset_name.lower() in key.lower():
                    return settings
        
        # Return first preset as default
        return list(common_settings.values())[0] if common_settings else None
    
    def get_plugin_by_category(self, category: str) -> List[str]:
        """
        Get plugins that match a category.
        
        Args:
            category: Category name (e.g., "eq", "compressor", "reverb")
            
        Returns:
            List of plugin names in that category
        """
        category_lower = category.lower()
        matches = []
        
        for name, info in self._plugins.items():
            plugin_category = info.get("category", "").lower()
            if category_lower == plugin_category:
                matches.append(name)
        
        return matches
    
    def search_parameters_by_tag(self, tag: str) -> List[Dict[str, Any]]:
        """
        Search all parameters across all plugins by semantic tag.
        
        Args:
            tag: Semantic tag to search for
            
        Returns:
            List of matching parameters with plugin and parameter names
        """
        tag_lower = tag.lower()
        matches = []
        
        for plugin_name, plugin_info in self._plugins.items():
            params = plugin_info.get("parameters", {})
            for param_name, param_info in params.items():
                tags = param_info.get("semantic_tags", [])
                for t in tags:
                    if tag_lower in t.lower():
                        matches.append({
                            "plugin": plugin_name,
                            "parameter": param_name,
                            "info": param_info,
                            "matched_tag": t
                        })
                        break
        
        return matches
    
    def map_research_value_to_normalized(self, plugin_name: str, param_name: str,
                                          value: float, unit: str = None) -> Optional[float]:
        """
        Map a value from research (with units) to normalized Ableton range.
        
        Args:
            plugin_name: Name of the plugin
            param_name: Name of the parameter
            value: Raw value from research
            unit: Unit of the value (dB, Hz, ms, %, etc.)
            
        Returns:
            Value ready for Ableton, or None if can't map
        """
        param_info = self.get_parameter_info(plugin_name, param_name)
        if not param_info:
            return value  # Return as-is if we don't know the parameter
        
        min_val = param_info.get("min", 0)
        max_val = param_info.get("max", 1)
        param_unit = param_info.get("unit", "")
        
        # If units match, clamp to range
        if unit and unit.lower() == param_unit.lower():
            return max(min_val, min(max_val, value))
        
        # Handle percentage normalization
        if unit == "%" or param_unit == "%":
            if min_val == 0 and max_val == 100:
                return max(0, min(100, value))
            elif min_val == 0 and max_val == 1:
                return max(0, min(1, value / 100))
        
        # Default: clamp to known range
        return max(min_val, min(max_val, value))


# Singleton instance
_plugin_kb: Optional[PluginKnowledgeBase] = None


def get_plugin_kb() -> PluginKnowledgeBase:
    """Get the singleton PluginKnowledgeBase instance"""
    global _plugin_kb
    if _plugin_kb is None:
        _plugin_kb = PluginKnowledgeBase()
    return _plugin_kb


# Convenience functions for direct use
def get_plugin_info(plugin_name: str) -> Optional[Dict[str, Any]]:
    """Get information about a plugin"""
    return get_plugin_kb().get_plugin_info(plugin_name)


def get_parameter_info(plugin_name: str, param_name: str) -> Optional[Dict[str, Any]]:
    """Get information about a parameter"""
    return get_plugin_kb().get_parameter_info(plugin_name, param_name)


def find_parameters_for_intent(plugin_name: str, intent: str) -> List[Dict[str, Any]]:
    """Find parameters matching an intent"""
    return get_plugin_kb().find_parameters_for_intent(plugin_name, intent)


def get_typical_range(plugin_name: str, param_name: str, use_case: str) -> Optional[Dict[str, Any]]:
    """Get typical range for a use case"""
    return get_plugin_kb().get_typical_range(plugin_name, param_name, use_case)


def validate_parameter_value(plugin_name: str, param_name: str, value: float) -> Tuple[bool, float, str]:
    """Validate a parameter value"""
    return get_plugin_kb().validate_parameter_value(plugin_name, param_name, value)

