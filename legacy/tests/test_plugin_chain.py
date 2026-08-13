"""
Test Plugin Chain System

Tests for the plugin chain research, building, and loading functionality.
Run with: python -m pytest tests/test_plugin_chain.py -v
Or directly: python tests/test_plugin_chain.py
"""

import asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_vst_discovery_import():
    """Test that VST discovery can be imported"""
    from discovery.vst_discovery import VSTDiscoveryService, PluginInfo, get_vst_discovery
    
    # Create instance
    service = VSTDiscoveryService()
    assert service is not None
    print("✓ VSTDiscoveryService imported and instantiated")


def test_plugin_info():
    """Test PluginInfo matching logic"""
    from discovery.vst_discovery import PluginInfo
    
    plugin = PluginInfo(
        name="FabFilter Pro-Q 3",
        plugin_type="audio_effect",
        category="eq",
        aliases=["Pro-Q", "Pro Q", "ProQ"]
    )
    
    # Test exact match
    assert plugin.matches_query("FabFilter Pro-Q 3") == 1.0
    print("✓ Exact match works")
    
    # Test partial match
    score = plugin.matches_query("Pro-Q")
    assert score > 0.8
    print(f"✓ Partial match 'Pro-Q' score: {score}")
    
    # Test alias match
    score = plugin.matches_query("ProQ")
    assert score > 0.7
    print(f"✓ Alias match 'ProQ' score: {score}")
    
    # Test fuzzy match
    score = plugin.matches_query("fabfilter eq")
    assert score > 0.3
    print(f"✓ Fuzzy match 'fabfilter eq' score: {score}")


def test_chain_builder_import():
    """Test that chain builder can be imported"""
    from plugins.chain_builder import PluginChainBuilder, PluginChain, PluginSlot
    
    builder = PluginChainBuilder()
    assert builder is not None
    print("✓ PluginChainBuilder imported and instantiated")


def test_research_agent():
    """Test research agent plugin chain research"""
    from agents.research_agent import ResearchAgent
    
    agent = ResearchAgent(None)
    
    # Test built-in knowledge
    result = agent._get_builtin_chain_knowledge("Billie Eilish", "vocal")
    assert result is not None
    assert "chain" in result.get("data", {})
    print(f"✓ Found Billie Eilish vocal chain with {len(result['data']['chain'])} plugins")
    
    # Test default chain
    result = agent._get_builtin_chain_knowledge("unknown artist", "vocal")
    assert result is not None  # Should return default
    print("✓ Default chain returned for unknown artist")


def test_chain_building():
    """Test building a chain from research results"""
    from plugins.chain_builder import PluginChainBuilder
    
    builder = PluginChainBuilder()
    
    # Create mock research result
    research_result = {
        "artist_or_style": "test_artist",
        "track_type": "vocal",
        "chain": [
            {"type": "eq", "purpose": "high_pass"},
            {"type": "compressor", "purpose": "dynamics"},
            {"type": "reverb", "purpose": "space"},
        ],
        "confidence": 0.8
    }
    
    chain = builder.build_chain_from_research(research_result)
    
    assert chain is not None
    assert chain.name == "test_artist_vocal_chain"
    assert len(chain.slots) == 3
    print(f"✓ Built chain with {len(chain.slots)} slots")
    
    # Check that plugins were matched
    for i, slot in enumerate(chain.slots):
        print(f"  Slot {i}: {slot.plugin_type} -> {slot.matched_plugin.name if slot.matched_plugin else 'None'}")


def test_preset_chains():
    """Test preset chain generation"""
    from plugins.chain_builder import PluginChainBuilder
    
    builder = PluginChainBuilder()
    
    # Test vocal basic preset
    chain = builder.get_preset_chain("basic", "vocal")
    assert chain is not None
    assert len(chain.slots) > 0
    print(f"✓ Vocal basic preset has {len(chain.slots)} plugins")
    
    # Test drum bus preset
    chain = builder.get_preset_chain("drum_bus", "drums")
    assert chain is not None
    print(f"✓ Drum bus preset has {len(chain.slots)} plugins")
    
    # Test master preset
    chain = builder.get_preset_chain("master", "master")
    assert chain is not None
    print(f"✓ Master preset has {len(chain.slots)} plugins")


def test_knowledge_base():
    """Test plugin chain knowledge base"""
    from knowledge.plugin_chain_kb import PluginChainKnowledge
    
    kb = PluginChainKnowledge()
    
    # Test getting cached chain
    chain = kb.get_chain("Billie Eilish", "vocal")
    if chain:
        print(f"✓ Found cached Billie Eilish chain: {chain.get('description', '')}")
    else:
        print("⚠ No cached Billie Eilish chain (normal for first run)")
    
    # Test listing chains
    chains = kb.list_chains()
    print(f"✓ Knowledge base has {len(chains)} cached chains")
    
    # Test presets
    presets = kb.list_presets()
    print(f"✓ Knowledge base has {len(presets)} presets")


def test_chain_validation():
    """Test chain validation"""
    from plugins.chain_builder import PluginChainBuilder
    
    builder = PluginChainBuilder()
    
    research_result = {
        "artist_or_style": "test",
        "track_type": "vocal",
        "chain": [
            {"type": "eq", "purpose": "high_pass"},
            {"type": "unknown_plugin_type", "purpose": "test"},  # Should warn
        ],
        "confidence": 0.5
    }
    
    chain = builder.build_chain_from_research(research_result)
    validation = builder.validate_chain(chain)
    
    print(f"✓ Validation result: valid={validation['valid']}, "
          f"issues={len(validation['issues'])}, warnings={len(validation['warnings'])}")


async def test_async_research():
    """Test async research function"""
    from agents.research_agent import research_plugin_chain
    
    result = await research_plugin_chain("Billie Eilish", "vocal")
    
    assert result is not None
    assert "chain" in result
    print(f"✓ Async research returned chain with {len(result['chain'])} plugins")
    print(f"  Confidence: {result.get('confidence', 0)}")


def test_ableton_controls_plugin_methods():
    """Test that new plugin methods exist in AbletonController"""
    from ableton_controls import AbletonController
    
    # Check methods exist
    assert hasattr(AbletonController, 'load_device')
    assert hasattr(AbletonController, 'get_available_plugins')
    assert hasattr(AbletonController, 'find_plugin')
    assert hasattr(AbletonController, 'load_plugin_chain')
    assert hasattr(AbletonController, 'refresh_plugin_list')
    
    print("✓ All plugin management methods exist on AbletonController")


def test_jarvis_tools():
    """Test that new tools are defined in jarvis_tools"""
    from jarvis_tools import ABLETON_TOOLS, get_function_name_list
    
    functions = get_function_name_list()
    
    # Check new plugin functions exist
    assert "add_plugin_to_track" in functions
    assert "create_plugin_chain" in functions
    assert "get_available_plugins" in functions
    assert "find_plugin" in functions
    assert "load_preset_chain" in functions
    assert "refresh_plugin_list" in functions
    
    print(f"✓ All plugin management functions defined ({len(functions)} total functions)")


def run_all_tests():
    """Run all tests"""
    print("\n" + "="*60)
    print("PLUGIN CHAIN SYSTEM TESTS")
    print("="*60 + "\n")
    
    tests = [
        ("VST Discovery Import", test_vst_discovery_import),
        ("PluginInfo Matching", test_plugin_info),
        ("Chain Builder Import", test_chain_builder_import),
        ("Research Agent", test_research_agent),
        ("Chain Building", test_chain_building),
        ("Preset Chains", test_preset_chains),
        ("Knowledge Base", test_knowledge_base),
        ("Chain Validation", test_chain_validation),
        ("Ableton Controls Methods", test_ableton_controls_plugin_methods),
        ("Jarvis Tools", test_jarvis_tools),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        print(f"\n--- {name} ---")
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"✗ FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    # Run async test
    print(f"\n--- Async Research ---")
    try:
        asyncio.run(test_async_research())
        passed += 1
    except Exception as e:
        print(f"✗ FAILED: {e}")
        failed += 1
    
    print("\n" + "="*60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("="*60 + "\n")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

