import asyncio
import os
import sys
import json
import logging
from research.research_coordinator import get_research_coordinator

# Fix Console encoding for Windows
try:
    sys.stdout.reconfigure(encoding='utf-8')
except:
    pass

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')

async def run_probe():
    print("--- RESEARCH AGENT PROBE ---")
    query = "Drake Vocal Chain"
    print(f"Target Query: {query}")
    
    coordinator = get_research_coordinator()
    
    try:
        # 1. Run Research
        print("Running research... (This may take 10-30 seconds)")
        result = await coordinator.research_vocal_chain(
            query=query,
            use_youtube=True,
            use_web=True,
            max_youtube_videos=1,  # Keep it fast
            max_web_articles=1
        )
        
        # 2. Output Result
        print("\n--- RESULTS ---")
        print(f"Confidence: {result.confidence}")
        print(f"Description: {result.style_description}")
        print(f"Sources: {len(result.sources)}")
        
        print("\n--- DEVICES FOUND ---")
        for i, device in enumerate(result.devices):
            print(f"\nDevice {i+1}: {device.plugin_name} ({device.category})")
            print(f"  Purpose: {device.purpose}")
            print("  Parameters:")
            for param, data in device.parameters.items():
                val = data.get('value', '?')
                unit = data.get('unit', '')
                print(f"    - {param}: {val}{unit}")

        # 3. Dump Raw JSON for inspection
        print("\n--- RAW JSON DUMP ---")
        print(json.dumps(result.to_dict(), indent=2))
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_probe())
