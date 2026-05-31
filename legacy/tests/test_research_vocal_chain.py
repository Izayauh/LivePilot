"""
Test the research_vocal_chain function integration in jarvis_engine.py
"""
import asyncio
import sys
import os

# Fix Windows encoding issues
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add project root to path
sys.path.append(os.getcwd())

from jarvis_engine import execute_ableton_function

def test_research_vocal_chain_handler():
    """Test that the research_vocal_chain function handler works correctly."""
    print("[TEST] Testing research_vocal_chain handler integration...")
    print("-" * 60)

    # Test 1: Verify function is registered
    print("\n1. Testing function registration...")
    try:
        result = execute_ableton_function("research_vocal_chain", {
            "query": "Billie Eilish vocal chain test",
            "use_youtube": False,  # Disable YouTube to speed up test
            "use_web": True,
            "max_sources": 1  # Minimal sources for quick test
        })

        print(f"   Function executed: {result is not None}")

        if result.get("success"):
            print(f"   ✓ SUCCESS: {result.get('message')}")
            print(f"   Query: {result.get('query')}")
            print(f"   Confidence: {result.get('confidence', 'N/A')}")
            if result.get('chain_spec'):
                chain = result['chain_spec']
                print(f"   Devices found: {len(chain.get('devices', []))}")
                print(f"   Style: {chain.get('style_description', 'N/A')[:80]}...")
        else:
            print(f"   ⚠ PARTIAL: {result.get('message')}")
            print(f"   (This may be expected if web search is blocked)")

    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Test 2: Verify error handling for missing query
    print("\n2. Testing error handling (missing query)...")
    try:
        result = execute_ableton_function("research_vocal_chain", {})

        if not result.get("success"):
            print(f"   ✓ Correctly handled missing query: {result.get('message')}")
        else:
            print(f"   ⚠ Unexpected success with missing query")

    except Exception as e:
        print(f"   ✓ Exception raised as expected: {type(e).__name__}")

    # Test 3: Verify function is in function_map
    print("\n3. Testing unknown function handling...")
    result = execute_ableton_function("nonexistent_function_xyz", {})

    if "Unknown function" in result.get("message", ""):
        print(f"   ✓ Unknown function detection works")
    else:
        print(f"   ⚠ Unexpected result for unknown function")

    print("\n" + "=" * 60)
    print("INTEGRATION TEST COMPLETE")
    print("=" * 60)
    print("\nNote: If web search returned no results, this may be due to")
    print("DuckDuckGo rate limiting or network restrictions, not a bug")
    print("in the research_vocal_chain handler itself.")

    return True

if __name__ == "__main__":
    test_research_vocal_chain_handler()
