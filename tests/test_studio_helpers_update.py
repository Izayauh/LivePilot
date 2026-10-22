"""Studio puts changed lp_*.py handlers into Live only on the real port, and only when they differ."""
import asyncio

import pytest

pytest.importorskip("aiohttp")
from studio import server  # noqa: E402


class FakeStudio:
    busy = False
    live_lock = asyncio.Lock()

    def __init__(self):
        self.deployed = 0
        self.notes = []

    def emit(self, event):
        self.notes.append(event)

    async def deploy_handlers(self):
        self.deployed += 1
        return True, ""


def run(monkeypatch, port, stale):
    monkeypatch.setattr(server, "PORT", port)
    monkeypatch.setattr(server.deploy_script, "stale", lambda: stale)
    monkeypatch.setattr(server.workflows, "session", lambda: {"success": True})
    s = FakeStudio()
    asyncio.run(server.Studio.update_helpers(s))
    return s


def test_private_port_never_deploys(monkeypatch):
    s = run(monkeypatch, 8799, ["lp_dialcore.py"])
    assert s.deployed == 0 and s.notes == []


def test_identical_files_do_nothing(monkeypatch):
    s = run(monkeypatch, 8770, [])
    assert s.deployed == 0 and s.notes == []


def test_changed_files_deploy_once_and_say_so(monkeypatch):
    s = run(monkeypatch, 8770, ["lp_dialcore.py"])
    assert s.deployed == 1
    assert [n["text"] for n in s.notes] == ["Studio updated its Ableton helpers."]


def test_stale_compares_lp_files_only(tmp_path):
    src, dest = tmp_path / "src", tmp_path / "dest"
    src.mkdir(); dest.mkdir()
    (src / "lp_a.py").write_text("1"); (dest / "lp_a.py").write_text("1")
    (src / "lp_b.py").write_text("2"); (dest / "lp_b.py").write_text("x")
    (src / "server.py").write_text("s")
    assert server.deploy_script.stale(src, dest) == ["lp_b.py"]
