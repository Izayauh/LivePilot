"""
Discovery System for Jarvis AI Audio Engineer

Contains:
- OSC Path Explorer for discovering Ableton capabilities
- Tool Registry for dynamic function management
- Learning System for improving over time
- VST Discovery Service for plugin management
"""

from discovery.vst_discovery import VSTDiscoveryService, get_vst_discovery, PluginInfo

__all__ = ['VSTDiscoveryService', 'get_vst_discovery', 'PluginInfo']

