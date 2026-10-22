"""Studio's server guards, with no Ableton, no Claude and no mic: who may open the socket, the index
headers, one boot at a time, a turn that throws, the turn log rotation, and the developer-only loop."""

from __future__ import annotations

import asyncio
import json

import aiohttp
import pytest
from aiohttp.test_utils import TestClient, TestServer

from livepilot_tools import friction
from studio import brain, config, server
from studio.questions import Questions


def settings(developer: bool):
    return lambda: {**config.DEFAULTS, "developer": developer}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(brain, "_handler_names", lambda: [])
    monkeypatch.setattr(config, "load", settings(False))
    monkeypatch.setattr(server.since, "items", lambda after: [])
    monkeypatch.setattr(server.workflows, "session", lambda: pytest.fail("tests must never reach Live"))


async def _no_boot(self):
    return None


def with_client(monkeypatch, check):
    """Run check(client) against a real Studio app on a free port, boot patched out."""
    monkeypatch.setattr(server.Studio, "boot", _no_boot)

    async def run():
        studio = server.Studio(with_ears=False)
        async with TestClient(TestServer(studio.app())) as client:
            await check(client)

    asyncio.run(run())


def test_socket_refuses_another_site(monkeypatch):
    async def check(client):
        with pytest.raises(aiohttp.WSServerHandshakeError) as e:
            await client.ws_connect("/ws", headers={"Origin": "https://evil.example"})
        assert e.value.status == 403
        with pytest.raises(aiohttp.WSServerHandshakeError):  # same host, another port is another site
            await client.ws_connect("/ws", headers={"Origin": f"http://127.0.0.1:{server.PORT + 1}"})

    with_client(monkeypatch, check)


def test_socket_takes_the_window_and_local_tools(monkeypatch):
    async def check(client):
        for headers in ({"Origin": f"http://127.0.0.1:{server.PORT}"}, {"Origin": f"http://localhost:{server.PORT}"}, {}):
            ws = await client.ws_connect("/ws", headers=headers)
            hello = json.loads((await ws.receive()).data)
            assert hello["type"] == "hello"
            await ws.close()

    with_client(monkeypatch, check)


def test_index_cannot_be_framed(monkeypatch):
    async def check(client):
        r = await client.get("/")
        assert r.status == 200 and "Live Pilot" in await r.text()
        assert r.headers["X-Frame-Options"] == "DENY"
        assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
        assert f"ws://127.0.0.1:{server.PORT}" in r.headers["Content-Security-Policy"]

    with_client(monkeypatch, check)


def test_two_rechecks_boot_once(monkeypatch):
    started, loops = [], []

    async def check_setup(self):
        self.setup = []
        return []

    async def slow_start(self):
        started.append(1)
        await asyncio.sleep(0.05)

    async def loop(self):
        loops.append(1)

    monkeypatch.setattr(server.Studio, "check_setup", check_setup)
    monkeypatch.setattr(brain.Brain, "start", slow_start)
    monkeypatch.setattr(server.Studio, "converse", loop)
    monkeypatch.setattr(server.Studio, "watch_live", loop)

    async def run():
        studio = server.Studio(with_ears=False)
        studio.state = "error"
        await asyncio.gather(studio.boot(), studio.boot(), studio.boot())
        await studio.boot()
        await asyncio.sleep(0.01)
        return studio

    studio = asyncio.run(run())
    assert started == [1] and len(loops) == 2 and studio.booted  # converse + watch_live, once each


def test_a_failed_start_can_be_retried(monkeypatch):
    tries = []

    async def check_setup(self):
        self.setup = []
        return []

    async def start(self):
        tries.append(1)
        if len(tries) == 1:
            raise RuntimeError("Not logged in · Please run /login")

    async def loop(self):
        return None

    monkeypatch.setattr(server.Studio, "check_setup", check_setup)
    monkeypatch.setattr(brain.Brain, "start", start)
    monkeypatch.setattr(server.Studio, "converse", loop)
    monkeypatch.setattr(server.Studio, "watch_live", loop)
    said = []

    async def run():
        studio = server.Studio(with_ears=False)
        studio.emit = said.append
        await studio.boot()
        assert studio.state == "error" and not studio.booted
        await studio.boot()
        return studio

    studio = asyncio.run(run())
    assert len(tries) == 2 and studio.booted
    assert any("install.ps1 -Login" in e.get("text", "") for e in said)


def test_one_bad_turn_does_not_stop_the_loop(monkeypatch, tmp_path):
    asked, said, logged = [], [], []

    async def ask(text, timing=None):
        asked.append(text)
        return {"heard": text, "asked": 1.0, "done": 2.0, "reply": "ok"}

    def flaky_log(turn, *a, **kw):
        logged.append(turn["heard"])
        if len(logged) == 1:
            raise OSError("disk full")

    monkeypatch.setattr(server, "log_turn", flaky_log)

    async def run():
        studio = server.Studio(with_ears=False)
        studio.brain.ask = ask
        studio.emit = said.append
        task = asyncio.ensure_future(studio.converse())
        await studio.inbox.put(("first", {}))
        await studio.inbox.put(("second", {}))
        for _ in range(100):
            if len(logged) == 2:
                break
            await asyncio.sleep(0.01)
        task.cancel()
        return studio

    studio = asyncio.run(run())
    assert asked == ["first", "second"] and logged == ["first", "second"]
    assert any(e["type"] == "say" and "went wrong" in e["text"] for e in said)
    assert not studio.busy


def test_turn_log_rotates(tmp_path):
    log = tmp_path / "studio_turns.jsonl"
    old = tmp_path / "studio_turns.1.jsonl"
    old.write_text("older\n", encoding="utf-8")
    for i in range(3):
        server.log_turn({"n": i}, log, limit=5)
    assert old.read_text(encoding="utf-8") == '{"n": 1}\n'  # the previous .1 was replaced
    assert log.read_text(encoding="utf-8") == '{"n": 2}\n'
    server.log_turn({"n": 3}, log, limit=10_000)
    assert len(log.read_text(encoding="utf-8").splitlines()) == 2


def test_strangers_get_no_self_repair_loop(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "phone_dir", lambda: tmp_path)  # even with a Life OS folder around
    studio = server.Studio(with_ears=False)
    assert not studio.developer and studio.detector is None and studio.q is None and not studio.phone
    assert studio.brain.on_call is None
    studio._queue({"id": "q1", "sig": "s", "question": "Fix it now?"})
    studio._on_call("dial", {}, {"success": False, "message": "boom"}, 5)
    monkeypatch.setattr(server.desktop, "toast", lambda *a: pytest.fail("no toasts for strangers"))
    asyncio.run(studio.maybe_ask())
    asyncio.run(studio.answer("q1", "fix"))
    assert not list(tmp_path.iterdir())


def test_developer_keeps_the_loop(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "load", settings(True))
    monkeypatch.setattr(config, "phone_dir", lambda: tmp_path)
    monkeypatch.setattr(server, "Questions", lambda: Questions(tmp_path / "q.json", tmp_path / "events.jsonl"))
    detector = friction.LiveDetector
    monkeypatch.setattr(friction, "LiveDetector", lambda: detector(medians={}, skip=set()))
    studio = server.Studio(with_ears=False)
    assert studio.developer and studio.phone and studio.brain.on_call == studio._on_call
    for _ in range(2):
        studio._on_call("dial", {}, {"success": False, "message": "boom"}, 5)
    sent = []

    async def no_toast(q):
        sent.append(q["id"])

    studio._toast = no_toast
    studio.emit = lambda e: sent.append(e["type"])

    async def run():
        await studio.maybe_ask()
        await asyncio.sleep(0)

    asyncio.run(run())
    assert "ask" in sent and studio.q.open() is not None
    assert (tmp_path / "events.jsonl").is_file()


def test_port_check_tells_studio_from_another_program():
    import http.server
    import socket
    import threading

    from studio.__main__ import already_running

    def serve(body: bytes):
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free = s.getsockname()[1]
    assert already_running(free) is None
    for body, want in ((b"<title>Live Pilot</title>", True), (b"<title>Some other app</title>", False)):
        srv = serve(body)
        try:
            assert already_running(srv.server_address[1]) is want
        finally:
            srv.shutdown()
            srv.server_close()


class FakeEars:
    """Just the fields the server reads from Ears."""
    muted = talking = silent_input = False
    error = ""
    device_name = "Test mic"


def test_ears_errors_are_said_once_and_a_silenced_mic_coming_back_is_said(monkeypatch):
    said = []

    async def run():
        studio = server.Studio(with_ears=False)
        studio.loop = asyncio.get_running_loop()
        studio.ears = ears = FakeEars()
        studio.emit = said.append

        def ears_say(state, error="", silent=False):  # what Ears does from its thread: set the fields, then call
            ears.error, ears.silent_input = error, silent
            studio._ears_state(state)

        ears_say("listening")
        privacy = "The microphone is sending only silence. Windows may be blocking it."
        ears_say("error", privacy, silent=True)
        ears_say("error", privacy, silent=True)  # the same message again: not said twice
        ears_say("listening")                    # real sound came back
        ears_say("listening")                    # and stays: "back" only once
        ears_say("error", "I could not make out that last part. Say it again.")
        ears_say("listening")                    # not a silenced mic: no "back" line
        await asyncio.sleep(0.01)
        return studio

    studio = asyncio.run(run())
    says = [e["text"] for e in said if e["type"] == "say"]
    assert says == ["The microphone is sending only silence. Windows may be blocking it.", server.MIC_BACK,
                    "I could not make out that last part. Say it again."]
    states = [e["state"] for e in said if e["type"] == "state"]
    assert states == ["listening", "error", "error", "listening", "listening", "error", "listening"]
    assert studio.mic_said == "" and studio.state == "listening"


def test_one_bad_live_poll_does_not_stop_the_header(monkeypatch):
    polls, said = [], []

    def session():
        polls.append(1)
        if len(polls) == 1:
            raise RuntimeError("socket closed")
        return {"success": True, "playing": False, "tempo": 120.0, "bar": 1}

    real_sleep = asyncio.sleep
    monkeypatch.setattr(server.workflows, "session", session)

    async def run():
        studio = server.Studio(with_ears=False)
        studio.emit = said.append
        monkeypatch.setattr(server.asyncio, "sleep", lambda s: real_sleep(0))
        task = asyncio.ensure_future(studio.watch_live())
        for _ in range(200):
            if len(polls) >= 2:
                break
            await real_sleep(0.01)
        task.cancel()

    asyncio.run(run())
    assert len(polls) >= 2 and any(e["type"] == "live" and e["ok"] for e in said)
