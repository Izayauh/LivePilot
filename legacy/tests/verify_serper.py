import os
import asyncio
import sys
from dotenv import load_dotenv

# Load .env
load_dotenv()

async def verify_serper():
    print("🔍 Verifying Serper API Configuration...")
    
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key or "your_serper_api_key_here" in api_key:
        print("\n❌ SERPER_API_KEY is missing or default in .env")
        print("Please get a key from https://serper.dev and add it to your .env file.")
        return False
        
    print(f"✅ Found SERPER_API_KEY: {api_key[:5]}...")

    # Test 1: Web Search
    print("\n🌐 Testing Web Search (replace DuckDuckGo)...")
    try:
        # Import inside try/except to catch import hangs
        from research.web_research import WebResearcher
        researcher = WebResearcher()
        
        # Add timeout to prevent hanging forever
        print("   Sending request to Serper...")
        results = await asyncio.wait_for(
            asyncio.to_thread(researcher._run_serper_search, "how to mix vocals", 3),
            timeout=10
        )
        
        if results:
            print(f"✅ Web Search Success: Found {len(results)} results")
            print(f"   Example: {results[0].get('title')}")
        else:
            print("❌ Web Search returned 0 results")
    except asyncio.TimeoutError:
        print("❌ Web Search Timed Out (Check internet connection)")
    except Exception as e:
        print(f"❌ Web Search Failed: {e}")

    # Test 2: YouTube Search (via Serper)
    print("\n📺 Testing YouTube Search (via Serper)...")
    try:
        from research.youtube_research import YouTubeResearcher
        researcher = YouTubeResearcher()
        
        print("   Sending request to Serper (Videos)...")
        results = await researcher._search_via_serper("kanye west vocal chain", 3)
        
        if results:
            print(f"✅ YouTube Search Success: Found {len(results)} videos")
            print(f"   Example: {results[0].title} (ID: {results[0].video_id})")
        else:
            print("❌ YouTube Search returned 0 videos")
            
    except Exception as e:
        print(f"❌ YouTube Search Failed: {e}")

if __name__ == "__main__":
    try:
        # Windows-specific event loop policy to prevent some hangs
        if sys.platform == 'win32':
             asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(verify_serper())
    except KeyboardInterrupt:
        print("\n⚠️ Verification cancelled by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
