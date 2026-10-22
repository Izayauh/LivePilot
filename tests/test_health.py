"""The setup checks say what is wrong and how to fix it, and a crash is written down and shown."""

import http.server
import logging
import socket
import sys
import threading
import types

import pytest

from studio import __version__, config, health


def test_every_check_has_a_fix_and_failing_ones_come_first(monkeypatch):
    monkeypatch.setattr(config, "claude_signed_in", lambda: False)
    monkeypatch.setattr(config, "asr_model_cached", lambda: True)
    checks = health.check(live=False)
    assert {c["id"] for c in checks} == {"deps", "remote_script", "claude", "mic", "asr", "port"}
    for c in checks:
        assert c["title"] and c["detail"] and c["fix"] and isinstance(c["ok"], bool)
    oks = [c["ok"] for c in checks]
    assert oks == sorted(oks)  # False first
    claude = next(c for c in checks if c["id"] == "claude")
    assert not claude["ok"] and "install.ps1 -Login" in claude["fix"]
    assert claude in health.problems(checks)


def test_live_check_reports_no_answer(monkeypatch):
    from livepilot_tools import remote_script

    monkeypatch.setattr(remote_script, "send_command", lambda *a, **k: {"success": False, "message": "unreachable"})
    checks = health.check(live=True)
    live = next(c for c in checks if c["id"] == "live")
    assert not live["ok"] and live["detail"] == "unreachable" and "control surface" in live["fix"]


def test_report_is_readable(monkeypatch):
    monkeypatch.setattr(config, "claude_signed_in", lambda: True)
    text = health.report([{"id": "x", "ok": False, "title": "Thing", "detail": "broken", "fix": "Do this."},
                          {"id": "y", "ok": True, "title": "Other", "detail": "fine", "fix": "n/a"}])
    assert text.splitlines()[0] == f"Live Pilot Studio {__version__}"
    assert "[FIX] Thing: broken" in text and "-> Do this." in text and "[ok] Other: fine" in text


def test_logging_goes_to_a_file_and_crashes_are_announced(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_DIR", tmp_path / "logs")
    said = []
    monkeypatch.setattr(health, "say_out_loud", lambda title, text: said.append((title, text)))
    path = health.setup_logging()
    assert path == tmp_path / "logs" / "studio.log"
    logging.getLogger("studio.test").warning("hello file")
    try:
        raise ValueError("kaboom")
    except ValueError as e:
        health._crash_hook(type(e), e, e.__traceback__)
    for h in logging.getLogger().handlers:
        h.flush()
    text = path.read_text(encoding="utf-8")
    assert "hello file" in text and "ValueError: kaboom" in text
    assert said and said[0][0] == "Live Pilot Studio stopped" and "kaboom" in said[0][1] and str(path) in said[0][1]


def _fake_sounddevice(monkeypatch, devices, default):
    def query_devices(device=None, kind=None):
        if kind == "input":
            if default is None:
                raise RuntimeError("Error querying device -1")
            return {"name": default, "max_input_channels": 2}
        return devices
    monkeypatch.setitem(sys.modules, "sounddevice", types.SimpleNamespace(query_devices=query_devices))


def test_mic_names_the_default_input(monkeypatch):
    monkeypatch.setattr(config, "mic", lambda: "")
    _fake_sounddevice(monkeypatch, [], "Microphone (USB)")
    mic = health._mic()
    assert mic["ok"] and mic["detail"] == "using Microphone (USB)"


def test_no_default_mic_says_plug_in_and_restart(monkeypatch):
    monkeypatch.setattr(config, "mic", lambda: "")
    _fake_sounddevice(monkeypatch, [{"name": "Speakers", "max_input_channels": 0}], None)
    mic = health._mic()
    assert not mic["ok"] and "no default microphone" in mic["detail"]
    assert "Plug in" in mic["fix"] and "reopen" in mic["fix"] and "--no-mic" in mic["fix"]


def test_mic_setting_that_matches_nothing_is_a_problem(monkeypatch):
    monkeypatch.setattr(config, "mic", lambda: "Yeti")
    _fake_sounddevice(monkeypatch, [{"name": "Microphone (USB)", "max_input_channels": 1}], "Microphone (USB)")
    mic = health._mic()
    assert not mic["ok"] and "Yeti" in mic["detail"] and '"mic"' in mic["fix"]
    monkeypatch.setattr(config, "mic", lambda: "usb")
    mic = health._mic()
    assert mic["ok"] and mic["detail"] == "using Microphone (USB)"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def web(monkeypatch):
    """A tiny web server on a spare port answering with the given page body; STUDIO_PORT points at it."""
    servers = []

    def serve(body: bytes):
        class Page(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), Page)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        monkeypatch.setenv("STUDIO_PORT", str(srv.server_address[1]))
        return srv.server_address[1]

    yield serve
    for srv in servers:
        srv.shutdown()
        srv.server_close()


def test_port_free(monkeypatch):
    monkeypatch.setenv("STUDIO_PORT", str(_free_port()))
    port = health._port()
    assert port["ok"] and port["detail"] == "free"


def test_port_already_live_pilot(web):
    web(b"<title>Live Pilot</title>")
    port = health._port()
    assert port["ok"] and "already running" in port["detail"]


def test_port_taken_by_something_else(web):
    web(b"<title>Some other app</title>")
    port = health._port()
    assert not port["ok"] and "another program" in port["detail"] and "STUDIO_PORT" in port["fix"]
