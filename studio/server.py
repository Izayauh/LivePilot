"""Live Pilot Studio: the window, the conversation loop, and the turn timings.

Ears put each finished utterance (or a typed line) on one queue; the brain answers
them in order. Every event goes to the window over one websocket, and every turn
is timed into data/telemetry/studio_turns.jsonl (speech end -> change landed).

Friction is the author's self-repair loop, on only when config "developer" is true.
It is caught live (livepilot_tools.friction): after a tool call or turn that
trips it, Studio asks Fix it now / Later / Never once the transport is stopped, on the
card here and on his phone at once (studio.questions: one store, Life OS Needs you,
first answer wins), plus a Windows toast when this window isn't in front.
Fix it now runs scripts/ux_fix.py in the background (its own git worktree, tests
must pass) and reports back here and on his phone.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

from aiohttp import WSMsgType, web

from livepilot_tools import friction, workflows
from studio import __version__, config, desktop, health, since
from studio.brain import Brain, plain_error
from studio.questions import Questions

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "scripts"))
import deploy_remote_handlers as deploy_script  # noqa: E402  (its SRC/DEST are the one deploy path)
TURNS_LOG = ROOT / "data" / "telemetry" / "studio_turns.jsonl"
TURNS_LOG_MAX = 5 * 1024 * 1024  # past this the log moves to studio_turns.1.jsonl (the previous .1 is dropped)
FIX_DIR = ROOT / "data" / "telemetry" / "ux_fixes"
REAL_PORT = 8770
PORT = int(os.environ.get("STUDIO_PORT") or REAL_PORT)  # a private copy (the build checker) runs on another port
PYTHON = Path(sys.executable).with_name("python.exe")  # pythonw from the desktop icon has no stdout
# Only the window itself may open the socket: any other page in the browser could read the room
# transcript or send "say" commands. A browser always sends Origin; a missing one is a local tool.
ORIGINS = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self'; "
       f"connect-src 'self' ws://127.0.0.1:{PORT} ws://localhost:{PORT}; frame-ancestors 'none'; base-uri 'none'; "
       "form-action 'none'")
LIVE_FIX = "Open Live with the LivePilot control surface enabled"
log = logging.getLogger("studio.server")
NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
# Short spoken answers to an open question; anything longer goes to the brain as usual.
SPOKEN = [("never", re.compile(r"^\W*(never|don'?t ask)", re.I)),
          ("fix", re.compile(r"^\W*(yes|yeah|yep|sure|fix it|do it|go ahead)\b", re.I)),
          ("later", re.compile(r"^\W*(later|not now|no)\b", re.I))]


FINISHED = re.compile(r"[.?!]\W*$")  # Parakeet punctuates: no full stop usually means he paused mid-thought
HOLD_S = 2.0
MIC_BACK = "The mic is back. I can hear you again."


def log_turn(turn: dict, path: Path = TURNS_LOG, limit: int = TURNS_LOG_MAX) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.stat().st_size > limit:
        path.replace(path.with_name(f"{path.stem}.1{path.suffix}"))
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(turn, default=str) + "\n")


def spoken_answer(text: str) -> str | None:
    if len(text.split()) > 5:
        return None
    return next((choice for choice, rx in SPOKEN if rx.search(text)), None)


class Studio:
    def __init__(self, with_ears: bool = True, quit_when_closed: bool = False):
        self.with_ears = with_ears
        self.quit_when_closed = quit_when_closed
        self.sockets: set[web.WebSocketResponse] = set()
        self.inbox: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()
        self.held: tuple[str, dict] | None = None  # a typed line that arrived while a spoken one was held
        self.state = "starting"
        self.ears = None
        self.loop: asyncio.AbstractEventLoop | None = None
        # The author's self-repair loop (friction questions, Fix it now, phone cards). Off for everyone else:
        # no detector, no question store, no toasts, nothing written to Life OS.
        self.developer = bool(config.load()["developer"])
        self.brain = Brain(self.emit, self._on_call if self.developer else None)
        self.busy = False
        self.detector = friction.LiveDetector() if self.developer else None
        self.q = Questions() if self.developer else None  # caught -> open on both surfaces -> answered; survives a restart
        self.focused: dict[web.WebSocketResponse, bool] = {}
        self.toasts: dict[str, asyncio.subprocess.Process] = {}
        self.playing = False
        self.since_cutoff = since.cutoff()  # fixed for this run, so the card does not vanish after his first sentence
        self.live_lock = asyncio.Lock()    # TCP 9878 is single-client: a turn or a deploy, never both
        self.fix_lock = asyncio.Lock()     # one background fix at a time
        self.phone = self.developer and config.phone_dir() is not None  # Life OS here: questions also go to the phone
        self.boot_lock = asyncio.Lock()    # one boot at a time: two Check again clicks must not start two brains
        self.booted = False                # Claude started and the loops below are running; never twice
        self.setup: list[dict] = []        # failing health checks, shown as the Setup card until they pass
        self.mic_said = ""                 # the ears error already said out loud, so a repeat is not said again
        self.mic_silent = False            # that error was Windows sending only silence (it can come back by itself)

    # -- events to the window ------------------------------------------------
    def emit(self, event: dict) -> None:
        event.setdefault("t", time.time())
        data = json.dumps(event, default=str)
        for ws in list(self.sockets):
            asyncio.ensure_future(ws.send_str(data))

    def set_state(self, state: str) -> None:
        self.state = state
        self.emit({"type": "state", "state": state, "muted": bool(self.ears and self.ears.muted)})

    # -- ears (called from their threads) --------------------------------------
    def _ears_state(self, state: str) -> None:
        """Called from the ears threads. The reason for an "error" is read here, before ears can change it."""
        ears = self.ears
        error = ears.error if ears and state == "error" else ""
        silent = bool(ears and ears.silent_input)
        self.loop.call_soon_threadsafe(self._ears_changed, state, error, silent)

    def _ears_changed(self, state: str, error: str, silent: bool) -> None:
        """Say a mic problem once (not on every repeat), and say when a silenced mic comes back."""
        if state == "error" and error and error != self.mic_said:
            self.mic_said, self.mic_silent = error, silent
            log.warning("ears: %s", error)
            self.emit({"type": "say", "text": error})
        elif state == "listening" and self.mic_said:
            if self.mic_silent:
                log.info("ears: the mic is back")
                self.emit({"type": "say", "text": MIC_BACK})
            self.mic_said, self.mic_silent = "", False
        if not self.busy:
            self.set_state(state)

    def _ears_text(self, text: str, timing: dict) -> None:
        self.loop.call_soon_threadsafe(self.inbox.put_nowait, (text, timing))

    # -- the conversation loop -------------------------------------------------
    async def _finish_sentence(self, text: str, timing: dict) -> tuple[str, dict]:
        """Ears close a line after 0.7 s of quiet, which cut him off on every "um". Hold a spoken line
        while he keeps talking, or for HOLD_S when it doesn't end like a sentence, and join the next one."""
        while timing and self.ears:
            deadline = time.time() + (0.3 if FINISHED.search(text) else HOLD_S)
            while time.time() < deadline and self.inbox.empty() and not self.ears.talking:
                await asyncio.sleep(0.05)
            if self.inbox.empty() and not self.ears.talking:
                break
            more, more_timing = await self.inbox.get()
            if not more_timing:  # a typed line is its own turn
                self.held = (more, more_timing)
                break
            text = f"{text} {more}"
            timing = {**more_timing, "speech_s": round(timing["speech_s"] + more_timing["speech_s"], 2)}
        return text, timing

    def _idle_state(self) -> str:
        if self.ears and getattr(self.ears, "error", ""):
            return "error"  # a dead mic must not read as Listening after a typed turn
        return "muted" if self.ears and self.ears.muted else "listening" if self.ears else "ready"

    async def converse(self) -> None:
        """One line at a time, forever: a turn that throws is logged and said, and the next line still gets heard."""
        while True:
            try:
                await self._converse_once()
            except Exception as e:  # noqa: BLE001
                log.exception("a turn failed")
                self.busy = False
                self.emit({"type": "say", "text": f"That one went wrong on my side ({e}). Say it again."})
                self.set_state(self._idle_state())

    async def _converse_once(self) -> None:
        if self.held:
            (text, timing), self.held = self.held, None
        else:
            text, timing = await self.inbox.get()
        text, timing = await self._finish_sentence(text, timing)
        if self.q and (q := self.q.open()) and (choice := spoken_answer(text)):
            self.emit({"type": "heard", "text": text, "typed": not timing})
            await self.answer(q["id"], choice, "typed" if not timing else "voice")
            return
        self.busy = True
        self.emit({"type": "heard", "text": text, "typed": not timing})
        self.set_state("thinking")
        try:
            async with self.live_lock:
                turn = await self.brain.ask(text, timing)
        except Exception as e:
            self.emit({"type": "say", "text": f"Something broke on my side: {e}"})
            turn = {"heard": text, **timing, "asked": time.time(), "done": time.time(), "error": str(e)}
        self.busy = False
        self.emit({"type": "turn", **self._timings(turn)})
        log_turn(turn)
        if self.detector:
            self._queue(self.detector.on_turn(text, turn.get("reply", "")))
        self.set_state(self._idle_state())
        await self.maybe_ask()

    # -- friction: catch it, ask once the take is over, fix in the background ----
    def _on_call(self, name: str, args: dict, result: dict, ms: int) -> None:
        if self.detector:
            self._queue(self.detector.on_call(name, args, result, ms))

    def _queue(self, question: dict | None) -> None:
        if question and self.q:
            self.q.add(question)

    async def maybe_ask(self) -> None:
        """Never during a take: wait until the transport is stopped and no turn is running."""
        if not self.q or self.playing or self.busy or not (q := self.q.ask_next()):
            return
        self.emit({"type": "ask", "id": q["id"], "text": q["question"]})
        if not any(self.focused.values()):  # he's in Ableton or away from the window: get his eyes to the card
            asyncio.ensure_future(self._toast(q))

    async def _toast(self, q: dict) -> None:
        proc = self.toasts[q["id"]] = await desktop.toast(q["id"], "Live Pilot has a question", q["question"])
        out = (await proc.stdout.read()).decode("utf-8", "replace")
        self.toasts.pop(q["id"], None)
        if "clicked" in out and not await asyncio.to_thread(desktop.focus_window, "Live Pilot"):
            from studio.__main__ import open_window
            open_window(f"http://127.0.0.1:{PORT}")

    async def answer(self, qid: str, choice: str, via: str = "desktop") -> None:
        """Desktop card, a short spoken/typed yes, or his phone: the first one wins, the rest are ignored."""
        q = self.q.answer(qid, choice, via) if self.q else None
        if not q:
            return
        friction.log_fix({"id": q["id"], "sig": q["sig"], "answer": choice, "via": via})
        self.emit({"type": "answered", "id": qid, "choice": choice, "via": via})
        await self._clear_toast(qid)
        if choice == "never":
            friction.ignore(q["sig"])
            self.detector.skip.add(q["sig"])
        elif choice == "fix":
            asyncio.ensure_future(self.run_fix(q["evidence"]))
        await self.maybe_ask()  # "later" needs nothing: tonight's report still ranks it

    async def _clear_toast(self, qid: str) -> None:
        if proc := self.toasts.pop(qid, None):
            proc.kill()
            await desktop.remove(qid)

    async def watch_phone(self) -> None:
        """His tap on the Life OS card lands in its events log; the card here clears the moment it does."""
        while True:
            for kind, qid, detail in self.q.poll():
                if kind == "answer":
                    await self.answer(qid, detail, "phone")
                else:  # Life OS expired the card (8 hours): same as Later
                    self.emit({"type": "answered", "id": qid, "choice": "closed"})
                    await self._clear_toast(qid)
                    await self.maybe_ask()
            await asyncio.sleep(2.0)

    async def run_fix(self, q: dict) -> None:
        async with self.fix_lock:
            self.emit({"type": "note", "ok": True, "text": "Fixing it in the background. Keep working."})
            FIX_DIR.mkdir(parents=True, exist_ok=True)
            evidence = FIX_DIR / f"{q['id']}.json"
            evidence.write_text(json.dumps(q, indent=2, default=str), encoding="utf-8")
            proc = await asyncio.create_subprocess_exec(
                str(PYTHON), str(ROOT / "scripts" / "ux_fix.py"), str(evidence), cwd=str(ROOT),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, creationflags=NO_WINDOW)
            out, err = await proc.communicate()
            try:
                res = json.loads(out.decode("utf-8", "replace").strip().splitlines()[-1])
            except (ValueError, IndexError):
                res = {"applied": False, "text": f"The fix run crashed: {err.decode('utf-8', 'replace')[-200:]}"}
            text = res["text"].removeprefix("DONE: ").removeprefix("YOU: ")
            if res.get("applied") and "deploy" in res.get("needs", []):
                ok, detail = await self.deploy_handlers()
                if not ok:
                    text = f"Fixed, but the hot reload failed: {detail}"
                    await self.phone_text(f"YOU: Live Pilot {text}")
            self.emit({"type": "note", "ok": bool(res.get("applied")), "text": text})

    async def phone_text(self, text: str) -> None:
        """A line to the phone through the configured script, when there is one. Logged otherwise."""
        script = config.load()["telegram_script"]
        if not script or not Path(script).is_file():
            log.info("no phone script configured; would have sent: %s", text)
            return
        await asyncio.to_thread(subprocess.run, [str(PYTHON), script, "--bot", "izzy", "--text", text,
                                "--source", "lp-ux-fix"], creationflags=NO_WINDOW)

    async def deploy_handlers(self) -> tuple[bool, str]:
        while self.playing or self.busy:  # same rule as asking: never during a take or a turn
            await asyncio.sleep(2)
        async with self.live_lock:
            r = await asyncio.to_thread(subprocess.run, [str(PYTHON), str(ROOT / "scripts" / "deploy_remote_handlers.py")],
                                        cwd=str(ROOT), capture_output=True, text=True, timeout=180, creationflags=NO_WINDOW)
        return r.returncode == 0, (r.stdout + r.stderr).strip()[-200:]

    async def update_helpers(self) -> None:
        """Once Live answers, put changed lp_*.py handlers into it. Only on the real port: a private copy never touches Live."""
        if PORT != REAL_PORT:
            return
        while True:
            if not self.busy and not self.live_lock.locked():
                snap = await asyncio.to_thread(workflows.session)
                if snap.get("success"):
                    break
            await asyncio.sleep(5)
        if not await asyncio.to_thread(deploy_script.stale):
            return
        ok, detail = await self.deploy_handlers()
        self.emit({"type": "note", "ok": ok, "text": "Studio updated its Ableton helpers." if ok
                   else f"Could not update the Ableton helpers: {detail}"})

    @staticmethod
    def _timings(turn: dict) -> dict:
        start = turn.get("speech_end") or turn["asked"]

        def since(key):
            return round(turn[key] - start, 2) if turn.get(key) else None

        return {"heard_s": since("transcribed"), "first_tool_s": since("first_tool"),
                "landed_s": since("last_tool_end"), "total_s": since("done"), "cost_usd": turn.get("cost_usd")}

    async def watch_live(self) -> None:
        """Header strip: tempo, play state, bar. Polled only while nothing else is talking to Live."""
        while True:
            try:
                await self._watch_live_once()
            except Exception:  # noqa: BLE001 - one bad poll must not stop the header for the rest of the run
                log.exception("the Live header poll failed")
            await asyncio.sleep(2.0)

    async def _watch_live_once(self) -> None:
        if self.busy or self.live_lock.locked():
            return
        snap = await asyncio.to_thread(workflows.session)
        self.playing = bool(snap.get("playing"))
        ok = bool(snap.get("success"))
        self.emit({"type": "live", "ok": ok, "summary": snap.get("summary") or snap.get("message"),
                   "fix": None if ok else LIVE_FIX,
                   "playing": snap.get("playing"), "tempo": snap.get("tempo"), "bar": snap.get("bar")})
        await self.maybe_ask()

    # -- web -----------------------------------------------------------------
    async def index(self, _request) -> web.FileResponse:
        return web.FileResponse(HERE / "static" / "index.html",
                                headers={"Content-Security-Policy": CSP, "X-Frame-Options": "DENY"})

    async def socket(self, request) -> web.StreamResponse:
        origin = request.headers.get("Origin")
        if origin is not None and origin not in ORIGINS:
            log.warning("refused a socket from %s", origin)
            return web.Response(status=403, text="Only the Live Pilot window can connect here.")
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        self.sockets.add(ws)
        await ws.send_str(json.dumps({"type": "hello", "state": self.state, "mic": self.ears.device_name if self.ears else None,
                                      "muted": bool(self.ears and self.ears.muted), "version": __version__}))
        if self.setup:
            await ws.send_str(json.dumps({"type": "setup", "items": self.setup}))
        if self.q and (q := self.q.open()):  # a reload or a restart must not lose the question on screen
            await ws.send_str(json.dumps({"type": "ask", "id": q["id"], "text": q["question"]}))
        await ws.send_str(json.dumps({"type": "since", "items": since.items(self.since_cutoff)}))
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            data = json.loads(msg.data)
            if data.get("type") == "say" and data.get("text", "").strip():
                await self.inbox.put((data["text"].strip(), {}))
            elif data.get("type") == "since_seen":
                since.mark_seen(str(data.get("id")))
            elif data.get("type") == "answer":
                await self.answer(str(data.get("id")), str(data.get("choice")), "desktop")
            elif data.get("type") == "focus":
                self.focused[ws] = bool(data.get("focused"))
            elif data.get("type") == "recheck":
                await self.check_setup()
                if not self.setup and self.state == "error":
                    asyncio.ensure_future(self.boot())  # the fix landed: start for real
            elif data.get("type") == "mute" and self.ears:
                self.ears.muted = bool(data.get("muted"))
                self.set_state("muted" if self.ears.muted else "listening")
        self.sockets.discard(ws)
        self.focused.pop(ws, None)
        if self.quit_when_closed and not self.sockets:
            asyncio.ensure_future(self._quit_if_still_closed())
        return ws

    async def _quit_if_still_closed(self) -> None:
        await asyncio.sleep(5)  # a reload reconnects within a second
        if not self.sockets:
            signal.raise_signal(signal.SIGINT)  # same clean stop as Ctrl-C

    async def on_startup(self, _app) -> None:
        self.loop = asyncio.get_running_loop()
        self.loop.set_exception_handler(lambda _l, ctx: log.error("in the event loop: %s", ctx.get("message"),
                                                                    exc_info=ctx.get("exception")))
        asyncio.ensure_future(self.boot())  # the window opens while Claude and Parakeet load

    async def check_setup(self) -> list[dict]:
        """Run the health checks off the loop and show the failing ones. Live itself is polled by watch_live."""
        checks = await asyncio.to_thread(health.check, False)
        self.setup = health.problems(checks)
        if not self.with_ears:  # typing only: a missing mic or speech model is not a problem
            self.setup = [c for c in self.setup if c["id"] not in ("mic", "asr")]
        for c in self.setup:
            log.warning("setup: %s: %s", c["title"], c["detail"])
        self.emit({"type": "setup", "items": self.setup})
        return self.setup

    async def boot(self) -> None:
        """One at a time, and only until it has worked once: the loops below start once per process."""
        async with self.boot_lock:
            if self.booted:
                return
            await self.check_setup()
            if any(c["id"] in ("deps", "claude") for c in self.setup):  # nothing works without these; the card says what to do
                self.set_state("error")
                return
            try:
                await self.brain.start()
            except Exception as e:
                log.exception("Claude did not start")
                self.set_state("error")
                self.emit({"type": "say", "text": plain_error(str(e))
                           or f"Could not start Claude: {e}. Check the Setup card above, then press Check again."})
                return
            self.booted = True
            if self.with_ears:
                from studio.ears import Ears

                try:
                    self.ears = await asyncio.to_thread(Ears, self._ears_state, self._ears_text)
                except Exception as e:
                    log.exception("the mic did not start")
                    self.emit({"type": "say", "text": f"The mic did not start ({e}). You can still type below."})
                    self.set_state("ready")
                else:
                    self.ears.start()
            else:
                self.set_state("ready")
            asyncio.ensure_future(self.converse())
            asyncio.ensure_future(self.watch_live())
            if self.phone:
                asyncio.ensure_future(self.watch_phone())
            if PORT == REAL_PORT:
                asyncio.ensure_future(self.update_helpers())

    async def on_shutdown(self, _app) -> None:
        for ws in list(self.sockets):  # otherwise aiohttp waits a minute for open windows
            await ws.close()
        if self.brain.client:
            await self.brain.client.disconnect()

    def app(self) -> web.Application:
        app = web.Application()
        app.add_routes([web.get("/", self.index), web.get("/ws", self.socket),
                        web.static("/static", HERE / "static")])
        app.on_startup.append(self.on_startup)
        app.on_shutdown.append(self.on_shutdown)
        return app
