import asyncio
import sys
import os
from typing import Dict, Any

# Ensure we can import from local modules
sys.path.append(os.getcwd())

from agents.research_agent import ResearchAgent
from plugins.chain_builder import PluginChainBuilder, get_plugin_preferences
from agent_system import AgentMessage, AgentType

class MockOrchestrator:
    """Simple mock orchestrator for testing"""
    def get_agent(self, agent_type):
        return None

async def run_test():
    print("\n" + "="*50)
    print("TESTING RESEARCH -> CHAIN PIPELINE")
    print("="*50 + "\n")
    
    # 1. Initialize Research Agent
    print("[TEST] Initializing Research Agent...")
    orchestrator = MockOrchestrator()
    researcher = ResearchAgent(orchestrator)
    
    # 2. Simulate Research Request
    query = "Kanye Runaway vocal chain"
    print(f"\n[TEST] Sending query: '{query}'")
    
    # We call the method directly to test the internal logic, 
    # mirroring what _execute_complex_workflow triggers
    message = AgentMessage(
        sender=AgentType.AUDIO_ENGINEER,
        recipient=AgentType.RESEARCHER,
        content={
            "action": "research_plugin_chain",
            "artist_or_style": "Kanye West",  # In a real flow, this is extracted first
            "track_type": "vocal"
        }
    )
    
    # For a more realistic test, let's use the actual research methods
    try:
        print("\n[TEST] 1. STARTING RESEARCH...")
        # Direct call to the method used by the agent
        research_result = await researcher._research_plugin_chain(
            artist_or_style="Kanye West",
            track_type="vocal"
        )
        
        print(f"\n[TEST] Research Result: Found {len(research_result.get('chain', []))} plugins")
        
    except Exception as e:
        print(f"[TEST] Research Failed: {e}")
        return

    # 3. Initialize Chain Builder
    print("\n[TEST] 2. BUILDING PLUGIN CHAIN...")
    try:
        builder = PluginChainBuilder()
        
        # Build the chain object
        chain = builder.build_chain_from_research(research_result)
        
        print(f"\n[TEST] Chain Built: '{chain.name}'")
        print(f"[TEST] Logic Source: {chain.source}")
        print(f"[TEST] Confidence: {chain.confidence:.2f}")
        
        print("\n[TEST] 3. CHAIN CONTENTS:")
        for i, slot in enumerate(chain.slots):
            status = "MATCHED" if slot.matched_plugin else "MISSING"
            plugin_name = slot.matched_plugin.name if slot.matched_plugin else "None"
            print(f"  {i+1}. [{slot.plugin_type}] {slot.purpose}")
            print(f"     Desired: {slot.desired_plugin}")
            print(f"     Actual:  {plugin_name} ({status})")
            print(f"     Settings: {slot.settings}")
            print("-" * 30)
            
        # 4. Validate Chain
        print("\n[TEST] 4. VALIDATION:")
        validation = builder.validate_chain(chain)
        if validation["valid"]:
            print("  [OK] Chain is valid and ready to load")
        else:
            print(f"  [WARN] Chain issues: {validation['issues']}")
            
        if validation["warnings"]:
            print("  Warning/Notes:")
            for w in validation["warnings"]:
                print(f"   - {w}")

    except Exception as e:
        print(f"[TEST] Chain Building Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_test())
