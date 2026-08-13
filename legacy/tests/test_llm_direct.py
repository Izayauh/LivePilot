"""Direct test of the LLM client to see if Gemini is actually responding."""
import asyncio
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except:
    pass

async def main():
    from research.llm_client import get_research_llm
    
    llm = get_research_llm()
    
    # Test 1: Simple generation
    print("=== TEST 1: Basic Generation ===")
    response = await llm.client.generate("Say 'hello world' and nothing else.")
    print(f"Success: {response.success}")
    print(f"Content: {response.content[:200]}")
    print(f"Error: {response.error}")
    
    # Test 2: Intent analysis
    print("\n=== TEST 2: Intent Analysis ===")
    intent = await llm.analyze_vocal_intent("Drake vocal chain")
    print(f"Intent: {intent}")
    
    # Test 3: Extraction from fake transcript
    print("\n=== TEST 3: Extraction ===")
    fake_transcript = """
    For the Drake vocal sound, start with an EQ. Cut at 200Hz with a high-pass filter.
    Boost around 3kHz by 2dB for presence. Then add a compressor with threshold at -18dB,
    ratio 4:1, attack 10ms, release 50ms. Add a de-esser at 6kHz. 
    For reverb, use a plate reverb with a 1.5 second decay, mix at 15%.
    Finally add a stereo delay, quarter note, feedback 20%, mix 10%.
    """
    result = await llm.extract_vocal_chain_from_transcript(fake_transcript, artist="Drake")
    print(f"Devices found: {len(result.devices)}")
    print(f"Confidence: {result.confidence}")
    print(f"Error: {result.error}")
    if result.devices:
        for d in result.devices:
            print(f"  - {d.get('name', '?')} ({d.get('category', '?')})")
    else:
        print(f"Raw response (first 500 chars): {result.raw_response[:500]}")

if __name__ == "__main__":
    asyncio.run(main())
