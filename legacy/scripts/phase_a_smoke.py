"""
Phase A smoke checks.

Purpose:
1. Validate critical module imports.
2. Validate research routing/schema wiring is present in source.
3. Validate offline research call path with cheap defaults.

This script avoids live API/network calls.
"""

import asyncio
import importlib
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ok(message: str):
    print(f"[PASS] {message}")


def _fail(message: str):
    print(f"[FAIL] {message}")


def _check_imports() -> bool:
    modules = [
        "research.llm_client",
        "research.youtube_research",
        "research.web_research",
        "research.research_coordinator",
        "agents.workflow_coordinator",
    ]
    success = True
    for mod in modules:
        try:
            importlib.import_module(mod)
            _ok(f"Import: {mod}")
        except Exception as exc:
            _fail(f"Import failed: {mod} ({exc})")
            success = False
    return success


def _check_source_wiring() -> bool:
    success = True

    jarvis_tools = (ROOT / "jarvis_tools.py").read_text(encoding="utf-8")
    required_tool_fields = [
        "budget_mode",
        "prefer_cache",
        "cache_max_age_days",
        "max_total_llm_calls",
    ]
    for field_name in required_tool_fields:
        if field_name in jarvis_tools:
            _ok(f"Tool schema field present: {field_name}")
        else:
            _fail(f"Tool schema field missing: {field_name}")
            success = False

    jarvis_engine = (ROOT / "jarvis_engine.py").read_text(encoding="utf-8")
    required_engine_bits = [
        'args.get("budget_mode", "balanced")',
        'args.get("prefer_cache", True)',
        'args.get("cache_max_age_days", 14)',
        'args.get("max_total_llm_calls")',
    ]
    for text in required_engine_bits:
        if text in jarvis_engine:
            _ok(f"Engine routing present: {text}")
        else:
            _fail(f"Engine routing missing: {text}")
            success = False

    coordinator = (ROOT / "research" / "research_coordinator.py").read_text(encoding="utf-8")
    if "class ResearchPolicy" in coordinator and "def _resolve_research_policy" in coordinator:
        _ok("Research policy wiring present")
    else:
        _fail("Research policy wiring missing")
        success = False

    if re.search(r"budget_mode:\s*Optional\[str\]", coordinator):
        _ok("Coordinator accepts budget_mode")
    else:
        _fail("Coordinator budget_mode argument missing")
        success = False

    return success


async def _check_offline_research_path() -> bool:
    try:
        from research.research_coordinator import ResearchCoordinator

        coordinator = ResearchCoordinator()
        result = await coordinator.research_vocal_chain(
            query="phase a smoke query",
            use_youtube=False,
            use_web=False,
            budget_mode="cheap",
            prefer_cache=False,
            max_total_llm_calls=0,
        )

        if not hasattr(result, "to_dict"):
            _fail("Offline research returned unexpected type")
            return False

        result_dict = result.to_dict()
        if "meta" not in result_dict:
            _fail("Offline research result missing meta")
            return False

        meta = result_dict.get("meta", {})
        if meta.get("budget_mode") != "cheap":
            _fail("Offline research meta missing cheap budget mode")
            return False

        _ok("Offline research path executed with cheap mode")
        return True

    except Exception as exc:
        _fail(f"Offline research path failed: {exc}")
        return False


def main() -> int:
    print("Running Phase A smoke checks...")

    os.environ.setdefault("RESEARCH_BUDGET_MODE", "cheap")

    checks = [
        _check_imports(),
        _check_source_wiring(),
        asyncio.run(_check_offline_research_path()),
    ]

    if all(checks):
        print("\nPhase A smoke checks: PASS")
        return 0

    print("\nPhase A smoke checks: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
