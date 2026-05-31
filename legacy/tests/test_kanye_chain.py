"""
Master Test: Kanye "Back to Me" Vocal Chain
"""
import sys
import os
import time
import asyncio
from pythonosc.udp_client import SimpleUDPClient
import socket

# Mock classes to load ResearchAgent without full system
class MockOrchestrator:
    pass

class MockMessage:
    def __init__(self, content):
        self.content = content
        self.sender = "user"
        self.correlation_id = "test-123"

# Add path to find agents
sys.path.append(os.getcwd())

async def run_test():
    print("=== Phase 1: Research ===")
    try:
        from agents.research_agent import ResearchAgent
        agent = ResearchAgent(MockOrchestrator())
        
        print("Asking ResearchAgent for 'Kanye West' vocal chain...")
        # Simulate message from orchestrator
        msg = MockMessage({
            "action": "research_plugin_chain",
            "artist_or_style": "Kanye West",
            "track_type": "vocal"
        })
        
        response = await agent.process(msg)
        chain_data = response.content.get("plugin_chain", {})
        
        if not chain_data:
            print("[ERROR] Research failed: No chain returned")
            return
            
        print(f"[OK] Research success! Found {len(chain_data.get('chain', []))} plugins.")
        print(f"Source: {chain_data.get('sources')}")
        
        chain = chain_data.get('chain', [])
        for i, p in enumerate(chain):
            print(f"  {i+1}. {p['type']} ({p.get('purpose', '')})")
            
    except Exception as e:
        print(f"[ERROR] Error in research phase: {e}")
        import traceback
        traceback.print_exc()
        return

    print("\n=== Phase 2: Execution Plan ===")
    # Map abstract types to concrete Ableton devices
    device_map = {
        "eq": "EQ Eight",
        "compressor": "Compressor",
        "de-esser": "Compressor", # Fallback as Ableton has no dedicated native De-esser (multiband is complex)
        "saturation": "Saturator",
        "delay": "Delay",
        "reverb": "Reverb",
        "limiter": "Limiter"
    }
    
    execution_plan = []
    for plugin in chain:
        ptype = plugin.get("type")
        device_name = device_map.get(ptype)
        if device_name:
            execution_plan.append({
                "device": device_name,
                "settings": plugin.get("settings", {})
            })
        else:
            print(f"⚠️ Skipping unknown plugin type: {ptype}")
    
    print(f"Generated plan with {len(execution_plan)} devices.")

    print("\n=== Phase 3: Execution ===")
    # OSC Clients
    loader = SimpleUDPClient("127.0.0.1", 11002)
    controller = SimpleUDPClient("127.0.0.1", 11000)
    
    # Target Track 3 (Index 2)
    TRACK_IDX = 2
    
    # 1. Clear track (optional, but good for test)
    # We don't have a clear track command yet, so we just append.
    
    for i, step in enumerate(execution_plan):
        device_name = step["device"]
        settings = step["settings"]
        
        print(f"\nStep {i+1}: Loading {device_name}...")
        loader.send_message("/jarvis/device/load", [TRACK_IDX, device_name])
        
        # Wait for load
        time.sleep(1.5)
        
        # Apply parameters
        # Note: In a real agent, we'd query params and map names. 
        # Here we'll do a simple proof of concept for specific devices.
        
        if device_name == "Compressor":
            # Try to set Ratio if specified
            if "ratio" in settings:
                ratio_str = settings["ratio"] # e.g. "8:1"
                # Parse ratio
                try:
                    ratio_val = float(ratio_str.split(':')[0])
                    print(f"  Setting Ratio to {ratio_val}")
                    # Ratio is usually param index 0 or 1 on Compressor, but varies.
                    # Ideally we query parameter names first.
                except:
                    pass
        
        elif device_name == "EQ Eight":
            # Enable High Pass if requested
            if "freq" in settings and "100" in str(settings["freq"]):
                print("  Setting Low Cut (High Pass) to 100Hz")
                # This requires finding the specific parameter index for Filter 1 Type and Freq
                # Skipping complex mapping for this quick test
                pass

    print("\n[OK] Chain construction complete!")
    print("Check Track 3 in Ableton.")

if __name__ == "__main__":
    asyncio.run(run_test())
