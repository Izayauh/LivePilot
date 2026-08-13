"""
Plugins Module

Contains the plugin chain builder and related functionality for
researching, matching, and creating plugin chains in Ableton Live.
"""

# Import after module is fully loaded to avoid circular imports
def get_chain_builder():
    """Get a PluginChainBuilder instance"""
    from plugins.chain_builder import PluginChainBuilder
    return PluginChainBuilder()

__all__ = ['get_chain_builder']

