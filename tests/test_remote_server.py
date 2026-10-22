"""The main-thread LivePilot server answers in one tick, keeps order, and holds writes one tick.

Runs the repo server.py inside a throwaway package with a stub router, driven by
a fake ControlSurface whose schedule_message queues callbacks for a manual tick.
"""

import importlib
import json
import shutil
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SERVER_SRC = REPO / "ableton_remote_script" / "LivePilot" / "server.py"

ROUTER_STUB = '''
def dispatch(song, command):
    if command["type"] == "boom":
        raise RuntimeError("boom")
    return {"id": command.get("id"), "ok": True, "result": {"type": command["type"], "params": command.get("params")}}
'''
UTILS_STUB = '''
import json
def serialize_json(data):
    return json.dumps(data, separators=(",", ":")) + "\\n"
'''


class FakeCS:
    def __init__(self):
        self.pending = []
        self.logs = []

    def schedule_message(self, delay, fn):
        self.pending.append(fn)

    def song(self):
        return None

    def log_message(self, msg):
        self.logs.append(msg)

    def tick(self):
        fns, self.pending = self.pending, []
        for fn in fns:
            fn()


@pytest.fixture
def server(tmp_path):
    pkg = tmp_path / "lp_fake"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    shutil.copy(SERVER_SRC, pkg / "server.py")
    (pkg / "router.py").write_text(ROUTER_STUB)
    (pkg / "utils.py").write_text(UTILS_STUB)
    sys.path.insert(0, str(tmp_path))
    try:
        mod = importlib.import_module("lp_fake.server")
        cs = FakeCS()
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        srv = mod.LivePilotServer(cs, port=port)
        srv.start()
        yield srv, cs, port
        srv.stop()
    finally:
        sys.path.remove(str(tmp_path))
        for name in [n for n in sys.modules if n.startswith("lp_fake")]:
            del sys.modules[name]


def _ticker(cs, stop):
    while not stop.is_set():
        cs.tick()
        time.sleep(0.005)


def _roundtrip(sock, req):
    sock.sendall((json.dumps(req) + "\n").encode())
    buf = b""
    while b"\n" not in buf:
        buf += sock.recv(65536)
    return json.loads(buf.split(b"\n", 1)[0])


def test_read_answers_within_one_tick(server):
    srv, cs, port = server
    sock = socket.create_connection(("127.0.0.1", port))
    sock.setblocking(True)
    sock.sendall(b'{"id":"a","type":"ping"}\n')
    time.sleep(0.05)
    cs.tick()  # accept, read, run, answer: all in this one tick
    sock.settimeout(0.5)
    reply = json.loads(sock.recv(65536).split(b"\n")[0])
    assert reply == {"id": "a", "ok": True, "result": {"type": "ping", "params": None}}


def test_write_is_held_one_tick_and_order_kept(server):
    srv, cs, port = server
    sock = socket.create_connection(("127.0.0.1", port))
    sock.sendall(b'{"id":"w","type":"set_tempo"}\n{"id":"r","type":"ping"}\n')
    time.sleep(0.05)
    cs.tick()
    sock.settimeout(0.1)
    with pytest.raises(socket.timeout):
        sock.recv(65536)  # write reply waits for its settle tick
    cs.tick()
    time.sleep(0.02)
    cs.tick()
    sock.settimeout(0.5)
    data = b""
    while data.count(b"\n") < 2:
        data += sock.recv(65536)
    ids = [json.loads(line)["id"] for line in data.split(b"\n") if line]
    assert ids == ["w", "r"]


def test_new_connection_replaces_old_and_errors_are_replies(server):
    srv, cs, port = server
    stop = threading.Event()
    t = threading.Thread(target=_ticker, args=(cs, stop), daemon=True)
    t.start()
    try:
        first = socket.create_connection(("127.0.0.1", port))
        assert _roundtrip(first, {"id": "1", "type": "ping"})["ok"]
        second = socket.create_connection(("127.0.0.1", port))
        reply = _roundtrip(second, {"id": "2", "type": "boom"})
        assert reply["ok"] is False and reply["error"]["code"] == "INTERNAL"
        assert _roundtrip(second, {"id": "3", "type": "ping"})["id"] == "3"
        big = "x" * 300_000  # larger than one recv chunk
        assert _roundtrip(second, {"id": "4", "type": "echo", "params": {"s": big}})["result"]["params"]["s"] == big
    finally:
        stop.set()
        t.join()
