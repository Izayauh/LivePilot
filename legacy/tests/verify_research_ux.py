import asyncio
import sys
import os
import logging

# Setup logging to see our "Thinking..." outputs if they go through logger
logging.basicConfig(level=logging.INFO)

# Ensure we can import from local modules
sys.path.append(os.getcwd())

from research.research_coordinator import research_vocal_chain

async def run_verification():
    print("\n" + "="*50)
    print("VERIFYING RESEARCH FALLBACK & UX")
    print("="*50 + "\n")
    
    query = "Kanye Vultures 1 vocal chain"
    print(f"[TEST] 1. Running specific query: '{query}'")
    print("[TEST] Expectation: Should fail specific search, print 'Thinking... trying broader', and then succeed with broader search.\n")
    
    try:
        # We need to simulate the environment where web_research works. 
        # It uses duckduckgo_search.
        
        result = await research_vocal_chain(
            query=query,
            use_youtube=False, # Focus on web for fallback test
            use_web=True,
            max_web_articles=2
        )
        
        print("\n" + "="*50)
        print("[TEST] RESULT:")
        print(f"Confidence: {result.confidence}")
        print(f"Style Description: {result.style_description}")
        print(f"Sources: {result.sources}")
        print(f"Devices Found: {len(result.devices)}")
        
        if result.devices:
            print("\n[SUCCESS] Found devices despite specific query!")
        else:
            print("\n[FAIL] No devices found.")
            
        if "Fallback" in result.style_description and "builtin" in result.sources:
             print("[NOTE] Used builtin fallback (acceptable if web search fully failed)")
        
    except Exception as e:
        print(f"\n[ERROR] Verification failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_verification())
