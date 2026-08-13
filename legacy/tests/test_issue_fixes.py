"""
Test script for the three issue fixes:
1. Status "idle" reporting (removed from system prompt)
2. Armed track detection (new methods and tools)
3. Track reference resolution (fuzzy name matching)
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

print("=" * 80)
print("Testing Issue Fixes")
print("=" * 80)

# Test 1: Verify idle status removed from prompts
print("\n[TEST 1] Verify '[STATUS: IDLE]' removed from system prompt")
print("-" * 80)

with open(project_root / "jarvis_engine.py", "r", encoding="utf-8") as f:
    content = f.read()

    # Check if the old aggressive idle prompts are gone
    if "output [STATUS: IDLE] and stop generating" in content:
        print("[FAIL] Found old aggressive idle status instruction")
    else:
        print("[PASS] Old aggressive idle status instruction removed")

    if "output [STATUS: IDLE] to signal completion" in content:
        print("[FAIL] Found old completion idle status instruction")
    else:
        print("[PASS] Old completion idle status instruction removed")

    # Check new wording
    if "Do not loop or continue generating after completing the user's request" in content:
        print("[PASS] New state management instruction found")
    else:
        print("[FAIL] New state management instruction not found")

# Test 2: Verify armed track detection tools exist
print("\n[TEST 2] Verify armed track detection methods and tools")
print("-" * 80)

# Check controller.py has new methods
with open(project_root / "ableton_controls" / "controller.py", "r", encoding="utf-8") as f:
    controller_content = f.read()

    methods_to_check = [
        ("get_track_mute", "Get track mute status"),
        ("get_track_solo", "Get track solo status"),
        ("get_track_arm", "Get track arm status")
    ]

    for method_name, description in methods_to_check:
        if f"def {method_name}(self, track_index):" in controller_content:
            print(f"[+] PASS: Found {method_name} method in controller.py")
        else:
            print(f"[X] FAIL: Missing {method_name} method in controller.py")

# Check jarvis_tools.py has new tool declarations
with open(project_root / "jarvis_tools.py", "r", encoding="utf-8") as f:
    tools_content = f.read()

    tools_to_check = [
        ("get_track_mute", "Get the mute status"),
        ("get_track_solo", "Get the solo status"),
        ("get_track_arm", "Get the arm status"),
        ("get_track_status", "Get the complete status"),
        ("get_armed_tracks", "Get a list of all currently armed tracks")
    ]

    for tool_name, description_fragment in tools_to_check:
        if f'name="{tool_name}"' in tools_content and description_fragment in tools_content:
            print(f"[+] PASS: Found {tool_name} tool declaration in jarvis_tools.py")
        else:
            print(f"[X] FAIL: Missing {tool_name} tool declaration in jarvis_tools.py")

# Check jarvis_engine.py has helper functions
with open(project_root / "jarvis_engine.py", "r", encoding="utf-8") as f:
    engine_content = f.read()

    functions_to_check = [
        ("get_track_status_combined", "Get combined status (mute, solo, arm)"),
        ("get_armed_tracks_list", "Get a list of all currently armed tracks")
    ]

    for func_name, description in functions_to_check:
        if f"def {func_name}(" in engine_content:
            print(f"[+] PASS: Found {func_name} function in jarvis_engine.py")
        else:
            print(f"[X] FAIL: Missing {func_name} function in jarvis_engine.py")

# Test 3: Verify track reference resolution
print("\n[TEST 3] Verify track reference resolution tool")
print("-" * 80)

# Check jarvis_tools.py has find_track_by_name
if 'name="find_track_by_name"' in tools_content:
    print("[+] PASS: Found find_track_by_name tool declaration in jarvis_tools.py")
else:
    print("[X] FAIL: Missing find_track_by_name tool declaration in jarvis_tools.py")

# Check jarvis_engine.py has find_track_by_name function
if "def find_track_by_name(query: str):" in engine_content:
    print("[+] PASS: Found find_track_by_name function in jarvis_engine.py")
else:
    print("[X] FAIL: Missing find_track_by_name function in jarvis_engine.py")

# Check for fuzzy matching logic
if "query_normalized" in engine_content and "score" in engine_content:
    print("[+] PASS: Found fuzzy matching logic in find_track_by_name")
else:
    print("[X] FAIL: Missing fuzzy matching logic in find_track_by_name")

# Check tool mapping
mapping_checks = [
    ('"get_track_mute":', "get_track_mute mapping"),
    ('"get_track_solo":', "get_track_solo mapping"),
    ('"get_track_arm":', "get_track_arm mapping"),
    ('"get_track_status":', "get_track_status mapping"),
    ('"get_armed_tracks":', "get_armed_tracks mapping"),
    ('"find_track_by_name":', "find_track_by_name mapping")
]

print("\n[TEST 4] Verify tool function mappings in jarvis_engine.py")
print("-" * 80)

for mapping_str, mapping_name in mapping_checks:
    if mapping_str in engine_content:
        print(f"[+] PASS: Found {mapping_name}")
    else:
        print(f"[X] FAIL: Missing {mapping_name}")

print("\n" + "=" * 80)
print("Test Complete!")
print("=" * 80)
print("\nSummary:")
print("- Issue 1 (Idle Status): System prompt updated to be less aggressive")
print("- Issue 2 (Armed Track Detection): Added get_track_mute/solo/arm methods and tools")
print("- Issue 3 (Track Reference): Added find_track_by_name with fuzzy matching")
print("\nNext Steps:")
print("1. Start Jarvis and test with real Ableton instance")
print("2. Try: 'Which track is armed?'")
print("3. Try: 'Add EQ to the vocal track' (tests fuzzy matching)")
print("4. Verify that Jarvis doesn't output [STATUS: IDLE] after every action")
