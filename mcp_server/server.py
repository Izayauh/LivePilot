"""MCP stdio server for LivePilot.

This module is intentionally a protocol wrapper. Ableton behavior lives in
``ableton_bridge.py`` and ``livepilot_tools/`` so Claude, Hermes, and other
front doors all share the same deterministic implementation.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Keep stdio clean for JSON-RPC. Anything diagnostic goes to stderr.
logging.basicConfig(level=os.environ.get("LIVEPILOT_MCP_LOG_LEVEL", "WARNING"))
logger = logging.getLogger(__name__)

mcp = FastMCP("live-pilot")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _dispatch(function_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    from ableton_bridge import _build_dispatch

    payload = args or {}
    if not isinstance(payload, dict):
        return {"success": False, "error": "args must be a JSON object"}

    dispatch = _build_dispatch(payload)
    if function_name not in dispatch:
        return {
            "success": False,
            "error": f"Unknown LivePilot function: {function_name}",
            "available_functions": sorted(dispatch.keys()),
        }

    try:
        result = dispatch[function_name]()
    except Exception as exc:  # pragma: no cover - defensive protocol boundary
        logger.exception("LivePilot function failed: %s", function_name)
        return {"success": False, "error": str(exc)}

    if isinstance(result, dict):
        return _json_safe(result)
    if result is None:
        return {"success": True, "message": f"{function_name} executed."}
    return {"success": True, "result": _json_safe(result)}


@mcp.tool()
def list_livepilot_tools() -> dict[str, Any]:
    """List LivePilot Ableton bridge functions available through MCP."""
    from ableton_bridge import _describe_functions, list_functions

    return {
        "success": True,
        "functions": list_functions(),
        "descriptions": _describe_functions().get("functions", {}),
    }


@mcp.tool()
def call_livepilot_tool(function_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call a LivePilot Ableton bridge function by name with JSON arguments."""
    return _dispatch(function_name=function_name, args=args)


@mcp.tool()
def get_creative_context() -> dict[str, Any]:
    """Get LivePilot's structured creative context snapshot."""
    return _dispatch("get_creative_context", {})


@mcp.tool()
def get_project_intent() -> dict[str, Any]:
    """Get the persisted LivePilot project intent."""
    return _dispatch("get_project_intent", {})


@mcp.tool()
def set_project_intent(intent: dict[str, Any]) -> dict[str, Any]:
    """Persist LivePilot project intent as deterministic local JSON."""
    return _dispatch("set_project_intent", {"intent": intent})


@mcp.tool()
def plan_arrangement_move(goal: str, target_section: str | None = None) -> dict[str, Any]:
    """Create a reviewable arrangement plan from the current LivePilot context."""
    return _dispatch("plan_arrangement_move", {"goal": goal, "target_section": target_section})


def main() -> None:
    mcp.run(transport="stdio")

