"""
Knowledge Base for Jarvis AI Audio Engineer

Contains:
- Audio engineering knowledge base
- Vector store for semantic search
- Technique database
- Plugin chain knowledge cache
"""

from knowledge.plugin_chain_kb import PluginChainKnowledge, get_plugin_chain_kb

__all__ = ['PluginChainKnowledge', 'get_plugin_chain_kb']

