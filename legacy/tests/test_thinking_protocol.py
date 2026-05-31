"""
Test script to verify the Thinking Protocol is being followed by Jarvis.

This script tests:
1. CLARIFICATION step - Does Jarvis ask for missing information?
2. INVENTORY VERIFICATION - Does Jarvis check plugin availability?
3. PROPOSED CHAIN - Does Jarvis present a plan before executing?
4. STATE MANAGEMENT - Does Jarvis output [STATUS: IDLE] when done?
"""

import asyncio
import sys
import os

# Add parent directory to path to import jarvis_engine
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jarvis_engine import process_command_with_gemini

class ProtocolTestResults:
    """Track test results"""
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.results = []

    def add_result(self, test_name: str, passed: bool, expected: str, actual: str, reason: str = ""):
        self.tests_run += 1
        if passed:
            self.tests_passed += 1
        else:
            self.tests_failed += 1

        self.results.append({
            "test": test_name,
            "passed": passed,
            "expected": expected,
            "actual": actual,
            "reason": reason
        })

    def print_summary(self):
        print("\n" + "="*80)
        print("THINKING PROTOCOL TEST RESULTS")
        print("="*80)
        print(f"\nTotal Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {self.tests_failed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100) if self.tests_run > 0 else 0:.1f}%")

        print("\n" + "-"*80)
        print("DETAILED RESULTS:")
        print("-"*80)

        for i, result in enumerate(self.results, 1):
            status = "✅ PASS" if result["passed"] else "❌ FAIL"
            print(f"\n{i}. {result['test']}: {status}")
            print(f"   Expected: {result['expected']}")
            print(f"   Actual: {result['actual'][:200]}...")  # Truncate for readability
            if result['reason']:
                print(f"   Reason: {result['reason']}")


async def test_clarification_missing_era():
    """
    Test 1: CLARIFICATION - Missing Era
    Request: "Add a Kanye-style vocal chain to track 1"
    Expected: Jarvis asks "Which era?" before proceeding
    """
    print("\n" + "="*80)
    print("TEST 1: CLARIFICATION - Missing Era Information")
    print("="*80)

    user_input = "Add a Kanye-style vocal chain to track 1"
    print(f"User: {user_input}")

    # Process command
    response = await process_command_with_gemini(user_input)
    print(f"\nJarvis: {response}")

    # Check if Jarvis asked for clarification
    asked_for_era = any(keyword in response.lower() for keyword in [
        "which era", "college dropout", "yeezus", "donda", "graduation", "808s"
    ])

    return {
        "test_name": "Clarification - Missing Era",
        "passed": asked_for_era,
        "expected": "Jarvis should ask which Kanye era (e.g., 'Which era? College Dropout, Yeezus, Donda')",
        "actual": response,
        "reason": "Jarvis followed CLARIFICATION step" if asked_for_era else "Jarvis did not ask for clarification"
    }


async def test_clarification_missing_track():
    """
    Test 2: CLARIFICATION - Missing Track Number
    Request: "Make the drums sound better"
    Expected: Jarvis asks which track
    """
    print("\n" + "="*80)
    print("TEST 2: CLARIFICATION - Missing Track Number")
    print("="*80)

    user_input = "Make the drums sound better"
    print(f"User: {user_input}")

    # Process command
    response = await process_command_with_gemini(user_input)
    print(f"\nJarvis: {response}")

    # Check if Jarvis asked for track number
    asked_for_track = any(keyword in response.lower() for keyword in [
        "which track", "track number", "what track", "specify the track"
    ])

    return {
        "test_name": "Clarification - Missing Track",
        "passed": asked_for_track,
        "expected": "Jarvis should ask which track (e.g., 'Which track are you referring to?')",
        "actual": response,
        "reason": "Jarvis followed CLARIFICATION step" if asked_for_track else "Jarvis did not ask for clarification"
    }


async def test_inventory_verification():
    """
    Test 3: INVENTORY VERIFICATION - Blacklisted Plugin
    Request: "Add Waves H-Delay to track 1"
    Expected: Jarvis checks plugin availability, suggests alternative
    """
    print("\n" + "="*80)
    print("TEST 3: INVENTORY VERIFICATION - Blacklisted Plugin")
    print("="*80)

    user_input = "Add Waves H-Delay to track 1"
    print(f"User: {user_input}")

    # Process command
    response = await process_command_with_gemini(user_input)
    print(f"\nJarvis: {response}")

    # Check if Jarvis suggested native alternative or mentioned unavailability
    suggested_alternative = any(keyword in response.lower() for keyword in [
        "simple delay", "ping pong delay", "echo", "not available",
        "don't have", "not installed", "alternative", "instead"
    ])

    return {
        "test_name": "Inventory Verification - Blacklisted Plugin",
        "passed": suggested_alternative,
        "expected": "Jarvis should check plugin availability and suggest native alternative (Simple Delay, Echo)",
        "actual": response,
        "reason": "Jarvis followed INVENTORY VERIFICATION step" if suggested_alternative else "Jarvis did not verify plugin availability"
    }


async def test_proposed_chain():
    """
    Test 4: PROPOSED CHAIN - Present Plan Before Execution
    Request: "Add a basic vocal chain to track 1"
    Expected: Jarvis presents a plan with plugin list
    """
    print("\n" + "="*80)
    print("TEST 4: PROPOSED CHAIN - Present Plan Before Execution")
    print("="*80)

    user_input = "Add a basic vocal chain to track 1"
    print(f"User: {user_input}")

    # Process command
    response = await process_command_with_gemini(user_input)
    print(f"\nJarvis: {response}")

    # Check if Jarvis presented a plan
    presented_plan = any(keyword in response.lower() for keyword in [
        "i plan to", "i will load", "i'll add", "here's what", "proceed",
        "eq eight", "compressor", "reverb"
    ])

    return {
        "test_name": "Proposed Chain - Present Plan",
        "passed": presented_plan,
        "expected": "Jarvis should present a plan (e.g., 'I plan to load: EQ Eight → Compressor. Proceed?')",
        "actual": response,
        "reason": "Jarvis followed PROPOSED CHAIN step" if presented_plan else "Jarvis did not present a plan"
    }


async def test_state_management():
    """
    Test 5: STATE MANAGEMENT - Output [STATUS: IDLE] When Done
    Request: "Play the track"
    Expected: Response ends with [STATUS: IDLE]
    """
    print("\n" + "="*80)
    print("TEST 5: STATE MANAGEMENT - Output [STATUS: IDLE]")
    print("="*80)

    user_input = "Play the track"
    print(f"User: {user_input}")

    # Process command
    response = await process_command_with_gemini(user_input)
    print(f"\nJarvis: {response}")

    # Check if response contains [STATUS: IDLE]
    has_idle_status = "[STATUS: IDLE]" in response

    return {
        "test_name": "State Management - [STATUS: IDLE]",
        "passed": has_idle_status,
        "expected": "Response should end with [STATUS: IDLE]",
        "actual": response,
        "reason": "Jarvis outputted [STATUS: IDLE]" if has_idle_status else "Missing [STATUS: IDLE] flag"
    }


async def run_all_tests():
    """Run all protocol tests"""
    print("\n" + "="*80)
    print("JARVIS THINKING PROTOCOL VERIFICATION TESTS")
    print("="*80)
    print("\nThis test suite verifies that Jarvis follows the 4-step Thinking Protocol:")
    print("1. Subjective Analysis")
    print("2. Clarification (ask for missing info)")
    print("3. Inventory Verification (check plugin availability)")
    print("4. Proposed Chain (present plan before execution)")
    print("\nPlus execution constraints:")
    print("- State Management ([STATUS: IDLE] when done)")
    print("- No hallucinations")
    print("- One-at-a-time execution")

    results = ProtocolTestResults()

    # Run tests sequentially
    tests = [
        test_clarification_missing_era,
        test_clarification_missing_track,
        test_inventory_verification,
        test_proposed_chain,
        test_state_management
    ]

    for test_func in tests:
        try:
            result = await test_func()
            results.add_result(
                test_name=result["test_name"],
                passed=result["passed"],
                expected=result["expected"],
                actual=result["actual"],
                reason=result["reason"]
            )
            # Wait between tests to avoid rate limits
            await asyncio.sleep(2)
        except Exception as e:
            print(f"\n❌ ERROR in {test_func.__name__}: {e}")
            results.add_result(
                test_name=test_func.__name__,
                passed=False,
                expected="Test should complete without errors",
                actual=f"Error: {str(e)}",
                reason="Test execution failed"
            )

    # Print summary
    results.print_summary()

    return results


if __name__ == "__main__":
    print("Starting Thinking Protocol Test Suite...")
    print("NOTE: This requires Jarvis to be properly configured with Gemini API key.")

    # Run tests
    results = asyncio.run(run_all_tests())

    # Exit with appropriate code
    sys.exit(0 if results.tests_failed == 0 else 1)
