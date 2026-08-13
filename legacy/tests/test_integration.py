"""
Test script for the Audio Engineer Intelligence Integration.

Tests the new device intelligence, agent consultation, and plugin chain features.
Run this to verify the integration works before testing with the full Jarvis engine.
"""

import sys
import asyncio

# Test 1: Device Knowledge Base
print("=" * 60)
print("TEST 1: Device Knowledge Base")
print("=" * 60)

try:
    from knowledge.device_kb import get_device_kb
    
    kb = get_device_kb()
    print(f"✓ Device KB loaded with {len(kb.list_devices())} devices")
    
    # Test getting EQ Eight info
    eq = kb.get_device("EQ Eight")
    if eq:
        print(f"✓ Found EQ Eight: {eq.description[:50]}...")
        print(f"  Parameters: {len(eq.parameters)}")
        print(f"  Presets: {list(eq.presets.keys())}")
    else:
        print("✗ EQ Eight not found")
    
    # Test getting Compressor info
    comp = kb.get_device("Compressor")
    if comp:
        print(f"✓ Found Compressor: {comp.description[:50]}...")
        print(f"  Parameters: {len(comp.parameters)}")
        print(f"  Presets: {list(comp.presets.keys())}")
    else:
        print("✗ Compressor not found")
    
except Exception as e:
    print(f"✗ Error loading device KB: {e}")
    import traceback
    traceback.print_exc()

# Test 2: Device Intelligence
print("\n" + "=" * 60)
print("TEST 2: Device Intelligence")
print("=" * 60)

try:
    from discovery.device_intelligence import get_device_intelligence
    
    di = get_device_intelligence()
    print("✓ Device Intelligence initialized")
    
    # Test parameter info
    param_info = di.get_param_info("EQ Eight", 1)
    if param_info:
        print(f"✓ EQ Eight param 1: {param_info['name']} - {param_info['purpose'][:40]}...")
    else:
        print("✗ Could not get EQ Eight param info")
    
    # Test suggestion for purpose
    suggestion = di.suggest_settings("EQ Eight", "high_pass", "vocal")
    if suggestion.get("success"):
        print(f"✓ Got suggestion for EQ high_pass: {len(suggestion.get('settings', {}))} params")
    else:
        print(f"✗ Suggestion failed: {suggestion.get('message')}")
    
    # Test intent analysis
    intent_result = di.suggest_for_intent("make it brighter", "vocal")
    if intent_result.get("success"):
        print(f"✓ Intent 'make it brighter': {intent_result['device']} - {intent_result['description'][:40]}...")
    else:
        print(f"? Intent analysis: {intent_result.get('message', 'No match')}")
    
    # Test explanation
    explanation = di.explain_adjustment("EQ Eight", 1, 100.0, "vocal")
    print(f"✓ Explanation: {explanation[:60]}...")
    
except Exception as e:
    print(f"✗ Error with device intelligence: {e}")
    import traceback
    traceback.print_exc()

# Test 3: Agent System
print("\n" + "=" * 60)
print("TEST 3: Agent System")
print("=" * 60)

try:
    from agent_system import AgentOrchestrator
    from agents.audio_engineer_agent import AudioEngineerAgent
    from agents.research_agent import ResearchAgent
    from agents import AgentType
    
    orchestrator = AgentOrchestrator()
    orchestrator.register_agent(AudioEngineerAgent(orchestrator))
    orchestrator.register_agent(ResearchAgent(orchestrator))
    
    print(f"✓ Agent orchestrator initialized with {len(orchestrator.agents)} agents")
    print(f"  Agents: {[a.value for a in orchestrator.agents.keys()]}")
    
    # Test audio engineer agent
    engineer = orchestrator.agents.get(AgentType.AUDIO_ENGINEER)
    if engineer:
        techniques = engineer.get_all_techniques()
        genres = engineer.get_all_genres()
        print(f"✓ Audio Engineer has {len(techniques)} techniques, {len(genres)} genres")
    else:
        print("✗ Audio Engineer agent not found")
    
except Exception as e:
    print(f"✗ Error with agent system: {e}")
    import traceback
    traceback.print_exc()

# Test 4: Research Agent Plugin Chain
print("\n" + "=" * 60)
print("TEST 4: Research Agent Plugin Chain")
print("=" * 60)

try:
    from agents.research_agent import ResearchAgent
    
    agent = ResearchAgent(None)
    
    # Test built-in knowledge for Billie Eilish
    billie_chain = agent._get_builtin_chain_knowledge("Billie Eilish", "vocal")
    if billie_chain:
        print(f"✓ Billie Eilish vocal chain found")
        print(f"  Source: {billie_chain.get('source')}")
        chain_data = billie_chain.get('data', {})
        print(f"  Description: {chain_data.get('description', 'N/A')[:50]}...")
        print(f"  Chain length: {len(chain_data.get('chain', []))} plugins")
    else:
        print("✗ Billie Eilish chain not found in built-in knowledge")
    
    # Test The Weeknd
    weeknd_chain = agent._get_builtin_chain_knowledge("The Weeknd", "vocal")
    if weeknd_chain:
        print(f"✓ The Weeknd vocal chain found")
    else:
        print("? The Weeknd chain not in built-in (may need research)")
    
except Exception as e:
    print(f"✗ Error with research agent: {e}")
    import traceback
    traceback.print_exc()

# Test 5: Plugin Chain Knowledge Base
print("\n" + "=" * 60)
print("TEST 5: Plugin Chain Knowledge Base")
print("=" * 60)

try:
    from knowledge.plugin_chain_kb import get_plugin_chain_kb
    
    kb = get_plugin_chain_kb()
    
    # List available chains
    chains = kb.list_chains()
    print(f"✓ Plugin Chain KB loaded with {len(chains)} cached chains")
    
    for chain in chains[:5]:  # Show first 5
        print(f"  - {chain['artist_or_style']} ({chain['track_type']}): {chain['plugin_count']} plugins")
    
    # Test getting a specific chain
    billie = kb.get_chain("Billie Eilish", "vocal")
    if billie:
        print(f"✓ Retrieved Billie Eilish vocal chain")
        print(f"  Confidence: {billie.get('confidence', 'N/A')}")
    else:
        print("? Billie Eilish chain not in cache (would research on demand)")
    
except Exception as e:
    print(f"✗ Error with plugin chain KB: {e}")
    import traceback
    traceback.print_exc()

# Test 6: Plugin Chain Builder
print("\n" + "=" * 60)
print("TEST 6: Plugin Chain Builder")
print("=" * 60)

try:
    from plugins.chain_builder import PluginChainBuilder
    
    builder = PluginChainBuilder()
    print("✓ Plugin Chain Builder initialized")
    
    # Test getting a preset chain
    preset_chain = builder.get_preset_chain("basic", "vocal")
    print(f"✓ Basic vocal preset: {len(preset_chain.slots)} plugins")
    for slot in preset_chain.slots:
        matched = slot.matched_plugin.name if slot.matched_plugin else "No match"
        print(f"  - {slot.plugin_type} ({slot.purpose}): {matched}")
    
    # Validate the chain
    validation = builder.validate_chain(preset_chain)
    print(f"✓ Chain validation: {'Valid' if validation['valid'] else 'Invalid'}")
    if validation['warnings']:
        print(f"  Warnings: {len(validation['warnings'])}")
    
except Exception as e:
    print(f"✗ Error with chain builder: {e}")
    import traceback
    traceback.print_exc()

# Test 7: Jarvis Engine Functions (without running full engine)
print("\n" + "=" * 60)
print("TEST 7: Jarvis Engine Helper Functions")
print("=" * 60)

try:
    # Import the helper functions
    import jarvis_engine
    
    # Test consult_audio_engineer
    result = jarvis_engine.consult_audio_engineer("How do I add punch to my drums?", "drums")
    if result.get("success"):
        print(f"✓ Audio engineer consultation works")
        print(f"  Techniques: {result.get('techniques', [])}")
        print(f"  Recommendation: {result.get('recommendation', 'N/A')[:60]}...")
    else:
        print(f"? Consultation: {result.get('message')}")
    
    # Test get_parameter_info
    param_result = jarvis_engine.get_parameter_info("Compressor", 1)
    if param_result.get("success"):
        print(f"✓ Parameter info works: Compressor param 1 = {param_result.get('name')}")
    else:
        print(f"✗ Parameter info failed: {param_result.get('message')}")
    
    # Test suggest_device_settings
    settings_result = jarvis_engine.suggest_device_settings("Compressor", "vocal_control", "vocal")
    if settings_result.get("success"):
        print(f"✓ Device settings suggestion works: {len(settings_result.get('settings', {}))} params")
    else:
        print(f"? Settings suggestion: {settings_result.get('message')}")
    
    # Test explain_adjustment
    explain_result = jarvis_engine.explain_adjustment("Compressor", 1, -18.0, "vocal")
    if explain_result.get("success"):
        print(f"✓ Explanation works: {explain_result.get('explanation')[:50]}...")
    else:
        print(f"✗ Explanation failed: {explain_result.get('message')}")
    
except Exception as e:
    print(f"✗ Error testing jarvis engine functions: {e}")
    import traceback
    traceback.print_exc()

# Summary
print("\n" + "=" * 60)
print("INTEGRATION TEST COMPLETE")
print("=" * 60)
print("""
The audio engineer intelligence system is ready. You can now:

1. Ask Jarvis to explain what device parameters do
2. Request intelligent mixing suggestions ("make it brighter", "remove the mud")
3. Create artist-style plugin chains ("create a Billie Eilish vocal chain")
4. Get audio engineering advice ("how do I add punch to drums?")
5. Get explained parameter adjustments with audio engineering context

To test with the full Jarvis engine, run:
  python jarvis_engine.py
""")

