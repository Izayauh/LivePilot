"""Brain: one warm Claude session (the user's subscription) whose tools are Live Pilot's hands.

The session starts once and stays open, so a turn costs one model reply, not a CLI
start. Tools run in this process and talk straight to the LivePilot remote script
(TCP 9878) through livepilot_tools.workflows; each one reports to the window.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

import anyio
from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, TextBlock,
                              create_sdk_mcp_server, tool)

from livepilot_tools import audio_to_midi, live_app, plugin_recipes, remote_script, telemetry, workflows
from studio import config

if sys.platform == "win32":
    # Started from the desktop icon there is no console, so Windows opens a terminal
    # window for the Claude CLI the SDK spawns. Spawn it windowless instead.
    _open_process = anyio.open_process

    async def _open_hidden(*args, **kwargs):
        kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
        return await _open_process(*args, **kwargs)

    anyio.open_process = _open_hidden

log = logging.getLogger("studio.brain")

SYSTEM = """You are the engineer at the desk in {owner}'s Ableton Live session.{stage}
They talk to you out loud; their words arrive transcribed, so expect slips ("to dB" means "two dB",
"base" means "bass"). Fix them silently, never mention them. Each message starts with a snapshot of the set taken a moment ago; trust it.

- The mic is always on and hears the whole room. If a line is not an instruction or question
  for you about this session (they are talking to someone else, dictating to another app, singing,
  a song playing), touch nothing and reply with exactly: (ignored)
- Routine moves (levels, pan, sends, mute, solo, arm, add or remove a device, play from a spot,
  tempo, undo): do them right away with the tools. Never ask permission; everything is undoable.
- Ask one short question only when you truly cannot tell which track or what they mean.
- Taste calls (mix, arrangement, sound): give your take in two or three sentences, then act if they asked.
- Reply in one short sentence for routine moves, saying what changed (before -> after).
  Plain words, no markdown, no lists, no em dashes. They read it at a glance while working.
- "Template", "preset", "chain" or "settings" named after a song or sound usually means their saved
  recipes: check recipe first, never the Ableton browser.
- "Replace my hummed bass / beatboxed hats with a real one" means audio_to_midi, then give the new
  track a sound (live_command find_and_load_device or the browser handlers, with an instrument this
  Live edition has) and check the notes against the key.
- Use dial, chain, audition, transport, undo, recipe first. For anything else, find a handler with
  list_commands and run it with live_command (track_index is the number in the snapshot).
- Saving, opening, restarting or closing Live and answering its pop-ups: use live. Never tell them to do it by hand."""


SUITE_ONLY = ("Operator", "Analog", "Wavetable", "Collision", "Tension", "Electric", "Sampler")


def edition_note(live: str | None) -> str:
    """Which stock instruments this Live has, from session()'s "live" field ('Live 12.1 Suite')."""
    edition = (live or "").split(" ")[-1]
    if edition == "Suite":
        return f"This is {live}, so {', '.join(SUITE_ONLY[:-1])} and {SUITE_ONLY[-1]} are all there."
    if edition in ("Standard", "Intro", "Lite"):
        return f"This is {live}, so no {', '.join(SUITE_ONLY[:-1])} or {SUITE_ONLY[-1]}."
    known = f"This is {live}, edition unknown" if live else "The Live edition is unknown"
    return f"{known}, so check with list_commands or the browser before assuming a stock instrument exists."


def system_prompt(cfg: dict) -> str:
    artist = cfg.get("artist_name", "").strip()
    return SYSTEM.format(owner=cfg.get("name", "").strip() or "the artist",
                         stage=f" Their artist name is {artist}." if artist else "")


def _handler_names() -> list[str]:
    return sorted(remote_script.handlers())


def _recipes() -> dict:
    rows = []
    for path in sorted(plugin_recipes.RECIPES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        rows.append(f"{path.stem} [{data.get('plugin_name') or 'device unknown'}]: {(data.get('notes') or '')[:160]}")
    return {"success": True, "recipes": rows, "summary": f"{len(rows)} recipes"}


def _apply_recipe(track, name: str, device: str | None) -> dict:
    """Load the recipe's device at the end of the track's chain, then set every saved value.
    Undo removes the device, which takes the recipe with it."""
    loaded = plugin_recipes.load_plugin_recipe(name)
    if not loaded["success"]:
        return loaded
    recipe = loaded["recipe"]
    device = device or recipe.get("plugin_name")
    if not device:
        return {"success": False, "message": f"{name} does not say which device it is for; pass device."}
    if recipe.get("value_units", "raw") != "raw":
        return {"success": False, "message": f"{name} is in display units; dial it instead."}
    before = remote_script.send_command("lp_chain", {"track": track})
    if not before.get("success"):
        return before
    added = workflows.chain(track, add=device)
    if not added.get("success"):
        return added
    values = [{"name_or_index": k, "value": v} for k, v in recipe["params"].items()]
    res = remote_script.send_command("batch_set_parameters", {"track_index": before["track_index"],
                                     "device_index": len(before["devices"]), "parameters": values}, timeout=15.0)
    if not res.get("success"):
        return {**res, "message": f"Added {device} but the recipe failed: {res.get('message')}"}
    return {"success": True, "undo_id": added["undo_id"],
            "summary": f"{name} on {before['track_name']}: {device} with {len(values)} values"}


def _clean(args: dict) -> dict:
    return {k: v for k, v in args.items() if v is not None and v != ""}


def _schema(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


# What the Claude CLI says when it cannot answer, and what the person should do about it.
# code is AssistantMessage.error when the CLI sets it; the text patterns catch the plain CLI lines.
CLAUDE_ERRORS = [
    ("login", {"authentication_failed"},
     re.compile(r"not logged in|run /login|login expired|invalid api key|oauth token (has )?expired", re.I),
     "Claude is not signed in on this computer. Run install.ps1 -Login, then reopen Live Pilot."),
    ("model", set(),
     re.compile(r"issue with the selected model|api model not found|may not exist or you may not have access"
                r"|model \S+ is not available", re.I),
     "Your Claude plan does not include the model Live Pilot is set to. Change model in "
     "%APPDATA%\\LivePilot\\config.json to one your plan includes, then reopen Live Pilot."),
    ("limit", {"rate_limit", "billing_error"},
     re.compile(r"usage limit|you'?ve hit your [\w ]{0,20}limit|\b(5-hour|weekly|spend) limit|limit reached\s*[|\u00b7\u2219]", re.I),
     "Your Claude plan's usage limit is reached; it resets on its own, see claude.ai for when."),
]
# The bundled CLI runs for this app only: no usage reports or other background traffic from it.
QUIET_CLI = {"DISABLE_TELEMETRY": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}


def plain_error(text: str | None, code: str | None = None) -> str | None:
    """The fix, in plain words, for a Claude error line; None when the text is not one of the known ones."""
    for _kind, codes, rx, fix in CLAUDE_ERRORS:
        if code in codes or rx.search(text or ""):
            return fix
    return None


ANY = {"type": ["string", "number"]}
STR = {"type": "string"}


class Brain:
    def __init__(self, emit: Callable[[dict], None], on_call: Callable[[str, dict, dict, int], None] | None = None):
        self.emit = emit
        self.on_call = on_call  # the live friction detector
        self.handlers = _handler_names()
        self.client: ClaudeSDKClient | None = None
        self.turn: dict = {}
        self.edition = ""  # the edition note last sent; resent only when it changes

    async def _run(self, name: str, args: dict, fn: Callable[[], dict]) -> dict:
        args = _clean(args)
        started = time.time()
        clock = time.perf_counter()
        self.turn.setdefault("first_tool", started)
        self.emit({"type": "tool_start", "name": name, "args": args})
        try:
            result = await asyncio.to_thread(fn)
        except Exception as e:  # a tool must answer the model, never crash the session
            log.exception("tool %s failed", name)
            result = {"success": False, "message": f"{type(e).__name__}: {e}"}
        telemetry.record(name, name, result, clock)  # same calls.jsonl the UX analyzer reads
        ms = round((time.time() - started) * 1000)
        self.turn["last_tool_end"] = time.time()
        ok = bool(result.get("success", True))
        summary = result.get("summary") or result.get("message") or ("done" if ok else "failed")
        self.emit({"type": "tool_end", "name": name, "args": args, "ok": ok, "summary": summary, "ms": ms})
        if self.on_call:
            self.on_call(name, args, result, ms)
        return {"content": [{"type": "text", "text": json.dumps(result, default=str)}], "is_error": not ok}

    def _tools(self) -> list:
        b = self

        @tool("dial", "Set or read one knob or fader in display units, read back and undoable. "
                      "to='-6 dB' absolute, by='+2 dB' relative; neither = read. Omit device for the mixer "
                      "(param: volume, pan, send A). track: name, or the number they say as a string ('4' is the 4th track); an integer is the snapshot index.",
              _schema({"track": ANY, "param": ANY, "to": ANY, "by": ANY, "device": ANY}, ["track", "param"]))
        async def dial(a):
            return await b._run("dial", a, lambda: workflows.dial(a["track"], a["param"], a.get("to"), a.get("by"), a.get("device")))

        @tool("chain", "Show a track's device chain, or add/remove one device (stock Ableton names like "
                       "'EQ Eight', 'Compressor', or an installed plugin's exact name). track: name, or the number they say as a string ('4' is the 4th track); an integer is the snapshot index.",
              _schema({"track": ANY, "add": STR, "remove": ANY, "position": {"type": "integer"}}, ["track"]))
        async def chain(a):
            return await b._run("chain", a, lambda: workflows.chain(a["track"], a.get("add"), a.get("remove"), a.get("position", -1)))

        @tool("audition", "Solo tracks (name or list) and play from a bar number or locator name. "
                          "stop=true stops and restores every solo.",
              _schema({"tracks": {"type": ["string", "array"], "items": STR}, "at": ANY, "stop": {"type": "boolean"}}))
        async def audition(a):
            return await b._run("audition", a, lambda: workflows.audition(a.get("tracks"), a.get("at"), stop=bool(a.get("stop"))))

        @tool("transport", "Play (from the start marker), continue (from where it stopped) or stop.",
              _schema({"action": {"type": "string", "enum": ["play", "continue", "stop"]}}, ["action"]))
        async def transport(a):
            cmd = {"play": "start_playback", "continue": "continue_playback", "stop": "stop_playback"}[a["action"]]
            return await b._run("transport", a, lambda: {**remote_script.send_command(cmd), "summary": a["action"]})

        @tool("undo", "Undo the last N dial/chain changes made here, with readback.",
              _schema({"steps": {"type": "integer"}}))
        async def undo(a):
            return await b._run("undo", a, lambda: workflows.undo(int(a.get("steps") or 1)))

        @tool("session", "Fresh snapshot of the set (only needed after you add, delete or rename tracks).", _schema({}))
        async def session(a):
            return await b._run("session", a, workflows.session)

        @tool("recipe", "Saved device settings (vocal chains matched to reference songs, bass sounds). "
                        "No name: list them with notes. name + track: add that device to the end of the track "
                        "and dial in every saved value. A chain is several recipes in slot order; ones marked "
                        "'return' go on a return track. track: name, or the number they say as a string ('4' is the 4th track); an integer is the snapshot index.",
              _schema({"name": STR, "track": ANY, "device": STR}))
        async def recipe(a):
            if not a.get("name"):
                return await b._run("recipe", a, _recipes)
            return await b._run("recipe", a, lambda: _apply_recipe(a.get("track"), a["name"], a.get("device")))

        @tool("audio_to_midi", "Turn a hummed or beatboxed audio clip into MIDI on a new track right after it "
                               "(the audio is left alone). kind 'melody' for a one-voice line (hummed bass, sung "
                               "melody), 'hits' for beatboxed drums (drum_pitch 42 hat, 36 kick, 38 snare). "
                               "clip = arrangement clip index; octave shifts the notes (-1/-2 for a hum that "
                               "should be bass); grid 0.25 snaps to 16ths, 0 keeps their timing; key e.g. 'E minor' "
                               "reports notes outside it. If it says the recording is locked, ask them before "
                               "calling again with reopen=true (Live closes and reopens the set, about a minute). track: name, or the number they say as a string ('4' is the 4th track); an integer is the snapshot index.",
              _schema({"track": ANY, "clip": {"type": "integer"}, "kind": {"type": "string", "enum": ["melody", "hits"]},
                       "octave": {"type": "integer"}, "grid": {"type": "number"}, "key": STR, "name": STR,
                       "drum_pitch": {"type": "integer"}, "reopen": {"type": "boolean"}}, ["track", "kind"]))
        async def to_midi(a):
            def run():
                track, _ = workflows.resolve_track(a["track"])
                return audio_to_midi.convert(track, int(a.get("clip") or 0), a["kind"], int(a.get("octave") or 0),
                                             float(a.get("grid", 0.25)), a.get("key"), a.get("name"),
                                             int(a.get("drum_pitch") or 42), bool(a.get("reopen")))
            return await b._run("audio_to_midi", a, run)

        @tool("list_commands", "Names of every LivePilot handler running inside Live, filtered by a word "
                               "(e.g. 'clip', 'tempo', 'automation', 'browser').",
              _schema({"filter": STR}))
        async def list_commands(a):
            word = (a.get("filter") or "").lower()
            hits = [n for n in b.handlers if word in n]
            return await b._run("list_commands", a, lambda: {"success": True, "commands": hits, "summary": f"{len(hits)} commands"})

        @tool("live_command", "Run any LivePilot handler by name with its params "
                              "(e.g. type='set_tempo', params={'tempo': 92}).",
              _schema({"type": STR, "params": {"type": "object"}}, ["type"]))
        async def live_command(a):
            return await b._run(a["type"], a, lambda: remote_script.send_command(a["type"], a.get("params") or {}, timeout=15.0))

        @tool("live", "The Live app itself: save the set (only if unsaved; path = Save As to a new .als), open a set "
                      "(path) or the last one, restart Live, close it, or check and answer pop-ups. "
                      "action: status | save | open | restart | close | dialogs | press. "
                      "press takes button (a label, 'enter' or 'escape').",
              _schema({"action": {"type": "string", "enum": ["status", "save", "open", "restart", "close", "dialogs", "press"]},
                       "path": STR, "button": STR}, ["action"]))
        async def live(a):
            kwargs = {}
            if a["action"] == "press":
                kwargs["button"] = a.get("button") or "enter"
            elif a["action"] in ("open", "restart", "save"):
                kwargs["path"] = a.get("path") or None
            return await b._run("live", a, lambda: live_app.run(a["action"], **kwargs))

        return [dial, chain, audition, transport, undo, session, recipe, to_midi, list_commands, live_command, live]

    async def start(self) -> None:
        tools = self._tools()
        cfg = config.load()
        log.info("starting Claude %s (effort %s) for %s", cfg["model"], cfg["effort"], cfg["name"] or "the artist")
        options = ClaudeAgentOptions(
            model=cfg["model"],
            system_prompt=system_prompt(cfg),
            mcp_servers={"lp": create_sdk_mcp_server("lp", "1.0.0", tools)},
            strict_mcp_config=True,
            setting_sources=[],
            tools=[],
            allowed_tools=[f"mcp__lp__{t.name}" for t in tools],
            permission_mode="bypassPermissions",
            extra_args={"effort": cfg["effort"]},
            cwd=str(Path(__file__).resolve().parents[1]),
            env=QUIET_CLI,
        )
        client = ClaudeSDKClient(options)
        await client.connect()
        self.client = client  # only a connected one: a failed start leaves nothing half open for the next try

    async def ask(self, text: str, timing: dict | None = None) -> dict:
        """One turn. Streams text and tool events through emit; returns the turn's timings."""
        self.turn = {"heard": text, **(timing or {}), "asked": time.time()}
        snap = await asyncio.to_thread(workflows.session)
        if snap.get("success"):
            prompt = (f"[Set now: {snap['summary']}. Tracks: {', '.join(snap['tracks'])}. "
                      f"Returns: {', '.join(snap['returns']) or 'none'}]\n{text}")
            note = edition_note(snap.get("live"))
            if note != self.edition:
                self.edition = note
                prompt = f"[{note}]\n{prompt}"
        else:
            prompt = f"[Live is not answering: {snap.get('message')}]\n{text}"
        self.turn["snapshot_ms"] = round((time.time() - self.turn["asked"]) * 1000)
        await self.client.query(prompt)
        reply = []
        fixed = None  # the plain-words fix already said for a Claude error, so it is said once
        async for msg in self.client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock) and block.text.strip():
                        text_ = block.text.strip()
                        if fix := plain_error(text_, getattr(msg, "error", None)):
                            self.turn["error"] = text_
                            if fix != fixed:
                                fixed = fix
                                self.emit({"type": "say", "text": fix})
                            continue
                        self.turn.setdefault("first_text", time.time())
                        reply.append(text_)
                        self.emit({"type": "say", "text": text_})
            elif isinstance(msg, ResultMessage):
                total = msg.total_cost_usd or 0.0
                self.turn["cost_usd"] = round(total - getattr(self, "spent", 0.0), 4)  # this turn, not the session
                self.spent = total
                if msg.is_error and not fixed:
                    detail = msg.result or "; ".join(msg.errors or []) or msg.subtype
                    self.turn["error"] = detail
                    if fixed := plain_error(detail):
                        self.emit({"type": "say", "text": fixed})
                    elif not reply:
                        self.emit({"type": "say", "text": f"Claude could not answer that one: {str(detail)[:200]}"})
        self.turn["done"] = time.time()
        self.turn["reply"] = " ".join(reply)
        return self.turn
