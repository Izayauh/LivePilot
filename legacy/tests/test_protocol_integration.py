"""
Simple unit test to verify the Thinking Protocol is properly integrated into the system prompt.

This validates that the protocol exists in the codebase and is correctly formatted.
"""

import re
import sys

def test_protocol_in_system_prompt():
    """Verify the Thinking Protocol exists in jarvis_engine.py system prompt"""
    print("="*80)
    print("TEST: Thinking Protocol Integration Check")
    print("="*80)

    with open("jarvis_engine.py", "r", encoding="utf-8") as f:
        content = f.read()

    results = {
        "thinking_protocol_header": False,
        "subjective_analysis": False,
        "clarification": False,
        "inventory_verification": False,
        "proposed_chain": False,
        "execution_constraints": False,
        "no_hallucinations": False,
        "state_management": False,
        "status_idle": False,
        "one_at_a_time": False,
    }

    # Check for protocol sections
    if "THE THINKING PROTOCOL" in content:
        results["thinking_protocol_header"] = True
        print("[PASS] Found: THE THINKING PROTOCOL header")
    else:
        print("[FAIL] Missing: THE THINKING PROTOCOL header")

    if "SUBJECTIVE ANALYSIS" in content:
        results["subjective_analysis"] = True
        print("[PASS] Found: Step 1 - SUBJECTIVE ANALYSIS")
    else:
        print("[FAIL] Missing: Step 1 - SUBJECTIVE ANALYSIS")

    if "CLARIFICATION" in content and "you MUST ask" in content:
        results["clarification"] = True
        print("[PASS] Found: Step 2 - CLARIFICATION with 'must ask' enforcement")
    else:
        print("[FAIL] Missing: Step 2 - CLARIFICATION")

    if "INVENTORY VERIFICATION" in content and "get_available_plugins" in content:
        results["inventory_verification"] = True
        print("[PASS] Found: Step 3 - INVENTORY VERIFICATION with plugin check")
    else:
        print("[FAIL] Missing: Step 3 - INVENTORY VERIFICATION")

    if "PROPOSED CHAIN" in content and "Proceed?" in content:
        results["proposed_chain"] = True
        print("[PASS] Found: Step 4 - PROPOSED CHAIN with confirmation")
    else:
        print("[FAIL] Missing: Step 4 - PROPOSED CHAIN")

    if "EXECUTION CONSTRAINTS" in content:
        results["execution_constraints"] = True
        print("[PASS] Found: EXECUTION CONSTRAINTS section")
    else:
        print("[FAIL] Missing: EXECUTION CONSTRAINTS section")

    if "NO HALLUCINATIONS" in content:
        results["no_hallucinations"] = True
        print("[PASS] Found: NO HALLUCINATIONS constraint")
    else:
        print("[FAIL] Missing: NO HALLUCINATIONS constraint")

    if "STATE MANAGEMENT" in content and "[STATUS: IDLE]" in content:
        results["state_management"] = True
        results["status_idle"] = True
        print("[PASS] Found: STATE MANAGEMENT with [STATUS: IDLE] flag")
    else:
        print("[FAIL] Missing: STATE MANAGEMENT or [STATUS: IDLE]")

    if "ONE-AT-A-TIME" in content:
        results["one_at_a_time"] = True
        print("[PASS] Found: ONE-AT-A-TIME constraint")
    else:
        print("[FAIL] Missing: ONE-AT-A-TIME constraint")

    # Calculate score
    total = len(results)
    passed = sum(results.values())
    percentage = (passed / total) * 100

    print("\n" + "="*80)
    print(f"INTEGRATION TEST RESULTS: {passed}/{total} ({percentage:.1f}%)")
    print("="*80)

    if percentage == 100:
        print("[PASS] ALL CHECKS PASSED - Protocol is properly integrated!")
        return True
    elif percentage >= 80:
        print("[WARN]  MOSTLY INTEGRATED - Some elements may be missing")
        return True
    else:
        print("[FAIL] INTEGRATION INCOMPLETE - Critical protocol elements missing")
        return False


def test_protocol_documentation():
    """Verify CLAUDE.md contains the protocol documentation"""
    print("\n" + "="*80)
    print("TEST: Protocol Documentation Check (CLAUDE.md)")
    print("="*80)

    try:
        with open("CLAUDE.md", "r", encoding="utf-8") as f:
            content = f.read()

        checks = {
            "has_title": "Master Protocol" in content,
            "has_note": "jarvis_engine.py" in content and "system prompt" in content,
            "has_4_steps": "Step 1" in content and "Step 2" in content and "Step 3" in content and "Step 4" in content,
            "has_subjective": "Subjective Analysis" in content,
            "has_clarification": "Clarification" in content,
            "has_inventory": "Inventory Verification" in content,
            "has_proposed": "Proposed Chain" in content,
        }

        for check_name, passed in checks.items():
            status = "[PASS]" if passed else "[FAIL]"
            print(f"{status} {check_name.replace('_', ' ').title()}: {passed}")

        total = len(checks)
        passed_count = sum(checks.values())
        percentage = (passed_count / total) * 100

        print(f"\nDocumentation: {passed_count}/{total} ({percentage:.1f}%)")

        return percentage >= 90

    except FileNotFoundError:
        print("[FAIL] CLAUDE.md not found!")
        return False


def check_redundancy():
    """Check if MANDATORY TRACK SPECIFICATION section was removed (redundancy check)"""
    print("\n" + "="*80)
    print("TEST: Redundancy Check (Streamlining Verification)")
    print("="*80)

    with open("jarvis_engine.py", "r", encoding="utf-8") as f:
        content = f.read()

    # This section should have been removed (it was redundant)
    has_mandatory_track_section = "MANDATORY TRACK SPECIFICATION:" in content

    if not has_mandatory_track_section:
        print("[PASS] PASSED - Redundant 'MANDATORY TRACK SPECIFICATION' section was removed")
        print("   (This guidance was consolidated into CLARIFICATION step)")
        return True
    else:
        print("[WARN]  WARNING - 'MANDATORY TRACK SPECIFICATION' section still exists")
        print("   (This is redundant with CLARIFICATION step - consider removing)")
        return False


if __name__ == "__main__":
    print("\n" + "="*80)
    print("JARVIS THINKING PROTOCOL - INTEGRATION VERIFICATION")
    print("="*80)
    print("\nThis test validates that the Thinking Protocol is properly integrated")
    print("into the Jarvis codebase and documentation.\n")

    # Run tests
    test1 = test_protocol_in_system_prompt()
    test2 = test_protocol_documentation()
    test3 = check_redundancy()

    print("\n" + "="*80)
    print("FINAL RESULTS")
    print("="*80)
    print(f"System Prompt Integration: {'[PASS] PASS' if test1 else '[FAIL] FAIL'}")
    print(f"Documentation Check: {'[PASS] PASS' if test2 else '[FAIL] FAIL'}")
    print(f"Redundancy Check: {'[PASS] PASS' if test3 else '[WARN]  WARNING'}")

    all_passed = test1 and test2 and test3

    if all_passed:
        print("\n[SUCCESS] ALL TESTS PASSED - Protocol is properly integrated!")
        print("\nNext steps:")
        print("1. Run Jarvis and test with voice commands")
        print("2. Verify Jarvis asks for clarification when info is missing")
        print("3. Verify Jarvis checks plugin availability")
        print("4. Verify Jarvis outputs [STATUS: IDLE] when done")
    else:
        print("\n[WARN]  SOME TESTS FAILED - Review integration above")

    sys.exit(0 if all_passed else 1)
