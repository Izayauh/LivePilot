"""The prompt Studio's Claude starts with, and the Live edition it is told about. No TCP: every
call to the remote script is faked."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from livepilot_tools import remote_script, workflows
from studio import brain, config


def no_tcp(*args, **kwargs):
    raise AssertionError("tests must never reach port 9878")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(remote_script, "send_command", no_tcp)
    monkeypatch.setattr(workflows, "send", no_tcp)
    monkeypatch.setattr(workflows, "_live_labels", {})


def installs(monkeypatch, *names):
    monkeypatch.setattr(config, "live_exes", lambda: [Path(f"C:/ProgramData/Ableton/x/Program/{n}.exe") for n in names])


def test_blank_name_is_the_artist():
    text = brain.system_prompt({"name": " ", "artist_name": ""})
    assert "in the artist's Ableton Live session." in text and "artist name" not in text
    assert "Live 11 Standard" not in text


def test_name_and_artist_name():
    text = brain.system_prompt({"name": "Sam", "artist_name": "Zed"})
    assert "in Sam's Ableton Live session. Their artist name is Zed." in text


def test_suite_has_the_instruments():
    note = brain.edition_note("Live 12.1 Suite")
    assert note.startswith("This is Live 12.1 Suite") and "Operator" in note and "Sampler are all there" in note


def test_standard_lacks_them():
    note = brain.edition_note("Live 11.3 Standard")
    assert "so no Operator, Analog, Wavetable, Collision, Tension, Electric or Sampler" in note


def test_unknown_edition_says_check_first():
    for live in (None, "Live 12.1"):
        assert "check with list_commands or the browser before assuming" in brain.edition_note(live)


def test_label_from_version_and_exe(monkeypatch):
    installs(monkeypatch, "Ableton Live 12 Suite", "Ableton Live 11 Standard")
    assert workflows.live_label("12.1.10") == "Live 12.1 Suite"
    assert workflows.live_label("11.3.43") == "Live 11.3 Standard"
    assert workflows.live_label(None) is None  # two majors installed, no version: unknown


def test_label_without_version_uses_the_only_install(monkeypatch):
    installs(monkeypatch, "Ableton Live 11 Lite")
    assert workflows.live_label("") == "Live 11 Lite"


def test_label_failure_never_breaks_session(monkeypatch):
    def broken():
        raise OSError("no ProgramData")
    monkeypatch.setattr(config, "live_exes", broken)
    monkeypatch.setattr(workflows, "send", lambda cmd, params=None, **kw: {
        "success": True, "tempo": 92.0, "live_version": "12.1.10", "tracks": [], "return_tracks": []})
    res = workflows.session()
    assert res["success"] and "live" not in res


class FakeClient:
    def __init__(self):
        self.prompts = []

    async def query(self, prompt):
        self.prompts.append(prompt)

    async def receive_response(self):
        return
        yield


def test_ask_sends_the_edition_once_then_on_change(monkeypatch):
    monkeypatch.setattr(brain, "_handler_names", lambda: [])
    snaps = iter([{"live": "Live 12.1 Suite"}, {"live": "Live 12.1 Suite"}, {"live": "Live 11.3 Standard"}])
    monkeypatch.setattr(workflows, "session", lambda: {"success": True, "summary": "92 BPM", "tracks": [],
                                                        "returns": [], **next(snaps)})
    b = brain.Brain(emit=lambda e: None)
    b.client = FakeClient()
    for _ in range(3):
        asyncio.run(b.ask("turn the bass up"))
    first, second, third = b.client.prompts
    assert first.startswith("[This is Live 12.1 Suite") and second.startswith("[Set now:")
    assert third.startswith("[This is Live 11.3 Standard, so no Operator")
