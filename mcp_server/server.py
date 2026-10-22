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

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # mcp 2.x renamed it; the decorator API is the same
    from mcp.server.mcpserver import MCPServer as FastMCP


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ``discovery`` moved under legacy/ in the reorg; controller.py still imports
# it top-level, so keep legacy/ importable.
LEGACY_ROOT = REPO_ROOT / "legacy"
if str(LEGACY_ROOT) not in sys.path:
    sys.path.insert(0, str(LEGACY_ROOT))

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
        import difflib

        close = difflib.get_close_matches(function_name, list(dispatch), n=5, cutoff=0.4)
        return {
            "success": False,
            "error": f"Unknown LivePilot function: {function_name}",
            "did_you_mean": close,
            "hint": "list_livepilot_tools() lists every name.",
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


def _run(tool: str, fn: str | None, thunk) -> dict[str, Any]:
    """Run one tool call under the budget and record it in data/telemetry/calls.jsonl."""
    import time
    from livepilot_tools import telemetry

    blocked = telemetry.over_budget(tool)
    if blocked:
        return blocked
    started = time.perf_counter()
    try:
        result = thunk()
    except Exception as exc:  # pragma: no cover - defensive protocol boundary
        logger.exception("LivePilot tool failed: %s", tool)
        result = {"success": False, "error": str(exc)}
    if isinstance(result, dict) and result.get("success") is False and tool != "live":
        # A Live pop-up stalls the bridge; answer it if a rule knows it, else show the agent.
        from livepilot_tools import live_app
        blocked = live_app.dialog_check()
        if blocked and blocked["handled"] and not blocked["open"]:
            try:  # a rule cleared the pop-up that froze the bridge: the call gets one more try
                result = thunk()
            except Exception as exc:  # pragma: no cover
                result = {"success": False, "error": str(exc)}
        if blocked and isinstance(result, dict):
            result["live_dialog"] = blocked
    result = _json_safe(result)
    telemetry.record(tool, fn, result, started)
    return result


def _workflows():
    from livepilot_tools import workflows

    if workflows.plugin_name is None:
        from discovery.vst_discovery import get_vst_discovery

        def plugin_name(name: str) -> str:
            found = get_vst_discovery().find_plugin(name)
            return found.name if found else name

        workflows.plugin_name = plugin_name
    return workflows


# -- Everyday workflows: use these first. One call each, names not indices. --

@mcp.tool()
def session() -> dict[str, Any]:
    """What is in the set right now: tempo, play state, bar, tracks [M/S/R flags], returns. Small reply."""
    return _run("session", None, lambda: _workflows().session())


@mcp.tool()
def dial(track: str, param: str, to: Any = None, by: Any = None, device: str | None = None) -> dict[str, Any]:
    """Set one knob or fader by name and read it back, in one call.

    track: name, or the number as a string ("4" is the 4th track); an integer is the snapshot index; 'master'; 'return A'. device: name (e.g. 'EQ Eight') or slot;
    omit for the mixer (param 'volume', 'pan', 'send A'). param: name, fuzzy.
    to: display value ('-6 dB', '310 ms', '2.5 kHz', '40 %', '30L', 'On') or a raw number.
    by: relative change ('+2 dB', '-10 %'). Neither: read the value. Undo with undo().
    """
    return _run("dial", None, lambda: _workflows().dial(track, param, to=to, by=by, device=device))


@mcp.tool()
def chain(track: str, add: str | None = None, remove: str | None = None, position: int = -1) -> dict[str, Any]:
    """Show a track's device chain, or add one plugin by name (position -1 = end) or remove one.

    track: name, or the number as a string ("4" is the 4th track); an integer is the snapshot index.
    Returns the chain after the change. Undo with undo() (a removed device comes back with its settings).
    """
    return _run("chain", None, lambda: _workflows().chain(track, add=add, remove=remove, position=position))


@mcp.tool()
def audition(tracks: Any = None, at: Any = None, play: bool = True, stop: bool = False) -> dict[str, Any]:
    """Solo track(s) (name or list), jump to `at` (bar number, 'beat 64', or locator name), and play.

    audition(stop=True) stops and restores every solo to how it was.
    """
    return _run("audition", None, lambda: _workflows().audition(tracks, at=at, play=play, stop=stop))


@mcp.tool()
def bounce(at: Any = 1, bars: float = 8, name: str = "bounce") -> dict[str, Any]:
    """Render a passage to a WAV: play `bars` from `at` (bar number or locator) and record the master
    through the Audient loop-back. Returns path, peak/rms dBFS and a silence flag. Use this, not resampling:
    Ableton locks its own recorded files."""
    return _run("bounce", None, lambda: _workflows().bounce(at=at, bars=bars, name=name))


@mcp.tool()
def undo(steps: int = 1) -> dict[str, Any]:
    """Revert the last `steps` changes made by dial/chain, with readback. Not Live's own undo stack."""
    return _run("undo", None, lambda: _workflows().undo(steps))


@mcp.tool()
def live(action: str = "status", button: str | None = None, path: str | None = None, force: bool = False,
         rule: dict[str, Any] | None = None) -> dict[str, Any]:
    """Ableton the application, no clicking and no keyboard focus: status | save | open | close | restart |
    dialogs | press | add_rule.

    status: running, set, unsaved, dialogs_open, bridge. save: File > Save (skips if already saved);
    save with `path` (a new .als) does Save As there, required for an Untitled set, never overwrites.
    open: launch the last set (or `path`) and wait for the bridge. close: save, quit, wait (force kills a hang).
    restart: close then open. Known pop-ups are answered from data/live_dialog_rules.json; an unknown one
    comes back as {text, buttons}: answer it with press(button='Yes') and teach it with
    add_rule(rule={'name','match':[phrases],'press','why'}) so no agent asks again.
    """
    from livepilot_tools import live_app

    kwargs: dict[str, Any] = {}
    if action == "press":
        kwargs["button"] = button or "enter"
    elif action in ("open", "restart", "save"):
        kwargs["path"] = path
    elif action == "close":
        kwargs["force"] = force
    elif action == "add_rule":
        kwargs = dict(rule or {})
    return _run("live", action, lambda: live_app.run(action, **kwargs))


@mcp.tool()
def rack(als: str, track: str, out: str, macros: list[dict[str, Any]] | None = None, name: str | None = None,
         overwrite: bool = False) -> dict[str, Any]:
    """Save a track's whole device chain as a rack preset (.adg) with mapped macros, from a saved .als.

    track: name, or the number Live shows ("4" or "4-Audio"). out: .adg path, e.g. User Library\\Presets\\Instruments\\Instrument
    Rack\\X.adg. MIDI track -> Instrument Rack, else Audio Effect Rack. macros: up to 16 of {name, device
    (0-based chain slot), param (Live name like 'Threshold', '1 Frequency A', or XML path; 'Device On' maps a
    plugin's power), min, max (raw values), value (0-127 start)}. Save the set first. Live lists the new .adg
    after a rescan or restart; load it with live_command('load_browser_item', {track_index, uri: browser_uri}).
    """
    from livepilot_tools import rack_builder

    def thunk():
        try:
            return rack_builder.build_rack(als, track, out, macros, name=name, overwrite=overwrite)
        except rack_builder.RackError as exc:
            return {"success": False, "error": str(exc)}
    return _run("rack", None, thunk)


@mcp.tool()
def usage(days: float = 7) -> dict[str, Any]:
    """Live Pilot reliability and reply-token cost per function, plus this session's totals and budget."""
    from livepilot_tools import telemetry
    return _run("usage", None, lambda: telemetry.report(days))


@mcp.tool()
def set_budget(max_calls: int | None = None, max_tokens: int | None = None) -> dict[str, Any]:
    """Cap Live Pilot calls / reply tokens for the rest of this session; calls past the cap are refused.

    Omit both to remove the cap. Counters reset when set.
    """
    from livepilot_tools import telemetry
    return _run("set_budget", None, lambda: telemetry.set_budget(max_calls, max_tokens))


# -- Full bridge surface: for anything the workflows above do not cover. --

@mcp.tool()
def list_livepilot_tools(function: str | None = None) -> dict[str, Any]:
    """Names of all bridge functions (small). Pass `function` to get that one's argument schema."""
    def thunk():
        from ableton_bridge import _describe_functions, list_functions

        if function:
            desc = _describe_functions().get("functions", {}).get(function)
            if desc is None:
                return {"success": False, "error": f"Unknown function: {function}", "functions": list_functions()}
            return {"success": True, "function": function, **desc}
        return {"success": True, "functions": list_functions(),
                "hint": "Prefer session/dial/chain/audition/undo. Call with function=<name> for a schema."}
    return _run("list_livepilot_tools", function, thunk)


@mcp.tool()
def call_livepilot_tool(function_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call a LivePilot Ableton bridge function by name with JSON arguments."""
    return _run("call_livepilot_tool", function_name, lambda: _dispatch(function_name=function_name, args=args))


@mcp.tool()
def list_commands(filter: str | None = None) -> dict[str, Any]:
    """The ~200 LivePilot handlers running inside Live (clips, notes, automation, browser, scenes...).

    No filter: names only. With a word ('clip', 'automation', 'browser'): each matching handler's
    docstring and every param key it reads. Run one with live_command.
    """
    from livepilot_tools import remote_script

    def thunk():
        found = remote_script.handlers()
        if not found:
            return {"success": False, "error": f"No handlers found in {', '.join(str(d) for d in remote_script.handler_dirs())}"}
        if not filter:
            return {"success": True, "count": len(found), "commands": sorted(found)}
        word = filter.lower()
        hits = {name: {"doc": info["doc"], "params": info["params"]}
                for name, info in sorted(found.items()) if word in name}
        return {"success": True, "count": len(hits), "commands": hits}
    return _run("list_commands", filter, thunk)


@mcp.tool()
def live_command(type: str, params: dict[str, Any] | None = None, timeout: float = 15.0) -> dict[str, Any]:
    """Run any LivePilot handler inside Live by name over TCP 9878, e.g. type='set_tempo',
    params={'tempo': 92}. Find names and params with list_commands. Raw: no name resolution, no undo journal."""
    from livepilot_tools import remote_script
    return _run("live_command", type, lambda: remote_script.send_command(type, params or {}, timeout=timeout))


@mcp.tool()
def jev_command(command: str, execute: bool = False) -> dict[str, Any]:
    """Fast path for transport and mixer commands via TypeSafe Jev (~0.5 s).

    Plain language in ("mute the vocals and set the tempo to 128"), a typed
    plan out: one bridge function per clause with confidence. With
    ``execute=True`` the ready steps run through the bridge with verify=True.
    Steps marked ``escalate`` were below the confidence gate and are never run;
    handle those the normal way. Device work: "bypass the eq on the vocal",
    "set the threshold on the comp to -20" (explicit values only; the device
    and parameter are picked from what is really on the track). Not creative.
    """
    from livepilot_tools.jev_dispatch import execute_plan, plan_command

    def thunk():
        track_list = _dispatch("get_track_list")
        if not track_list.get("success"):
            return {"success": False, "error": "could not read track list", "detail": track_list}
        song = _dispatch("get_song_status")
        plan = plan_command(command, track_list.get("tracks", []),
                            song.get("data") if song.get("success") else None, dispatch=_dispatch)
        out: dict[str, Any] = {"success": True, "plan": plan}
        if execute:
            out["execution"] = execute_plan(plan, _dispatch)
        return out
    return _run("jev_command", None, thunk)


@mcp.tool()
def get_creative_context() -> dict[str, Any]:
    """Get LivePilot's structured creative context snapshot."""
    return _run("get_creative_context", None, lambda: _dispatch("get_creative_context", {}))


@mcp.tool()
def get_project_intent() -> dict[str, Any]:
    """Get the persisted LivePilot project intent."""
    return _run("get_project_intent", None, lambda: _dispatch("get_project_intent", {}))


@mcp.tool()
def set_project_intent(intent: dict[str, Any]) -> dict[str, Any]:
    """Persist LivePilot project intent as deterministic local JSON."""
    return _run("set_project_intent", None, lambda: _dispatch("set_project_intent", {"intent": intent}))


@mcp.tool()
def plan_arrangement_move(goal: str, target_section: str | None = None) -> dict[str, Any]:
    """Create a reviewable arrangement plan from the current LivePilot context."""
    return _run("plan_arrangement_move", None, lambda: _dispatch("plan_arrangement_move", {"goal": goal, "target_section": target_section}))


@mcp.tool()
def mix_playbook(problem: str | None = None) -> dict[str, Any]:
    """Diagnose an audio problem before touching Live.

    Call this FIRST whenever something sounds wrong, before adding a device or
    cutting a frequency, and before any operation that records into the
    arrangement. Returns entries that give the measurement to run, the fix, how
    to verify it, and the evidence behind it.

    Describe the problem in plain words, e.g. "the vocals sound muddy",
    "it sounds thin on a phone", "about to record into the arrangement",
    "a state read looks wrong". Omit `problem` to get the whole playbook.

    These entries exist because each one was learned by getting it wrong on
    real songs. Reading the relevant one costs a few seconds; rediscovering it
    costs a wasted bounce cycle, or a destroyed vocal take.
    """
    from playbook import brief, search, load_entries

    def thunk():
        entries = search(problem, limit=4) if problem else load_entries()
        return {"success": True, "count": len(entries), "ids": [e["id"] for e in entries],
                "brief": brief(problem), "entries": entries}
    return _run("mix_playbook", problem, thunk)


@mcp.tool()
def record_mix_finding(entry: dict[str, Any]) -> dict[str, Any]:
    """Add a lesson to the playbook so it is never learned the hard way twice.

    Required: id, symptom, why, fix, evidence. `evidence` must cite what was
    actually measured or observed, with numbers where they exist - an entry
    without evidence is an opinion, and opinions are what the playbook replaces.
    Optional: applies_to, detect, verify.
    """
    from playbook import record_finding
    return _run("record_mix_finding", None, lambda: record_finding(entry))


def main() -> None:
    from mcp_server.instance_guard import run_guard

    run_guard()
    # Load native audio modules before the stdio reader thread starts. Loading numpy's DLL
    # while that thread blocks reading stdin deadlocks on Windows (bounce hung, 2026-10-14).
    try:
        import numpy, sounddevice, soundfile  # noqa: F401
    except Exception as exc:  # bounce reports the missing module itself
        logger.warning("Audio modules unavailable: %s", exc)
    mcp.run(transport="stdio")

