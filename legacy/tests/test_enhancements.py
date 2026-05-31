import asyncio
import os
import sys
import numpy as np
from scipy.io import wavfile

# Add project root to path
sys.path.append(os.getcwd())

from research.web_research import get_web_researcher
from research.audio_analyst import get_audio_analyst
from research.research_coordinator import get_research_coordinator

async def test_web_search():
    print("\n[TEST] Testing Web Search (DuckDuckGo)...")
    researcher = get_web_researcher()
    
    # Test with a real query
    query = "Kanye West vocal chain"
    print(f"Searching for: {query}")
    
    try:
        articles = await researcher.search_production_sites(query)
        print(f"Found {len(articles)} articles:")
        for i, a in enumerate(articles[:3]):
            print(f"  {i+1}. {a.title} ({a.source_site})")
            
        if not articles:
            print("  [FAIL] No articles found via DuckDuckGo")
        else:
            print("  [PASS] Web search successful (checking DDG connectivity)")
            
    except Exception as e:
        print(f"  [FAIL] Web search error: {e}")

async def test_audio_analysis():
    print("\n[TEST] Testing Audio Analysis...")
    
    # 1. Create dummy audio file (sine sweep)
    sample_rate = 44100
    duration = 2.0 # seconds
    t = np.linspace(0, duration, int(sample_rate * duration))
    # Sweep from 200Hz to 5000Hz (should give moderate brightness)
    freq = np.linspace(200, 5000, len(t))
    audio = 0.5 * np.sin(2 * np.pi * freq * t)
    
    filename = "test_sweep.wav"
    wavfile.write(filename, sample_rate, audio.astype(np.float32))
    print(f"Created dummy audio: {filename}")
    
    try:
        # 2. Analyze it
        analyst = get_audio_analyst()
        result = analyst.analyze_track(os.path.abspath(filename))
        
        if result["success"]:
            print("Analysis Success!")
            features = result["features"]
            print(f"  Centroid: {features['spectral_centroid_mean']:.2f} Hz")
            print(f"  RMS: {features['rms_mean']:.4f}")
            
            print("Suggestions:")
            for s in result["suggestions"]:
                print(f"  - {s['name']}: {s['reason']}")
            print("  [PASS] Audio analysis functional")
        else:
            print(f"  [FAIL] Analysis failed: {result['message']}")
            
    except Exception as e:
        print(f"  [FAIL] Audio analysis error: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        if os.path.exists(filename):
            os.remove(filename)

async def test_coordinator_integration():
    print("\n[TEST] Testing Coordinator Integration...")
    coord = get_research_coordinator()
    
    # Mock analysis call
    import os
    filename = "test_coord.wav"
    # Create empty file just for path check
    with open(filename, 'w') as f:
        f.write("dummy")
        
    try:
        # Just check if method exists
        if hasattr(coord, 'analyze_reference_track'):
             print("  [PASS] analyze_reference_track method exists on coordinator")
        else:
             print("  [FAIL] Method missing")
             
    finally:
        if os.path.exists(filename):
            os.remove(filename)

async def main():
    await test_web_search()
    await test_audio_analysis()
    await test_coordinator_integration()

if __name__ == "__main__":
    asyncio.run(main())
