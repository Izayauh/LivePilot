"""Handler discovery works on any machine: installed copy first, else the repo's own source."""

import importlib.util
import json
from pathlib import Path

import pytest

from livepilot_tools import remote_script
from studio import config

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def nothing_installed(tmp_path, monkeypatch):
    """A machine with no Live and no settings: every lookup points into an empty temp folder."""
    monkeypatch.delenv("LIVEPILOT_REMOTE_SCRIPT_DIR", raising=False)
    monkeypatch.setattr(config, "CONFIG", tmp_path / "config.json")
    monkeypatch.setattr(config, "PROGRAMDATA", tmp_path / "ProgramData")
    monkeypatch.setattr(config, "USER_LIBRARY", tmp_path / "User Library")
    monkeypatch.setattr(remote_script, "REMOTE_SCRIPT_DIR", None)
    return tmp_path


def _install(root: Path) -> Path:
    dest = root / "LivePilot"
    dest.mkdir(parents=True)
    (dest / "server.py").write_text("", encoding="utf-8")
    (dest / "mine.py").write_text('@register("only_here")\ndef only_here(song, params):\n    return {}\n', encoding="utf-8")
    return dest


def test_no_live_reads_the_repo_source(nothing_installed):
    assert remote_script.installed_dir() is None
    assert remote_script.handler_dirs() == [REPO / "ableton_remote_script" / "LivePilot_base",
                                            REPO / "ableton_remote_script" / "LivePilot"]
    found = remote_script.handlers()
    assert len(found) > 150 and "lp_dial" in found and "get_track_meters" in found


def test_installed_copy_wins(nothing_installed):
    dest = _install(nothing_installed / "ProgramData" / "Ableton" / "Live 12 Suite" / "Resources" / "MIDI Remote Scripts")
    assert remote_script.installed_dir() == dest
    assert list(remote_script.handlers()) == ["only_here"]


def test_env_then_setting_pin_the_folder(nothing_installed, monkeypatch):
    pinned = _install(nothing_installed / "custom")
    config.CONFIG.write_text(json.dumps({"remote_script_dir": str(pinned)}), encoding="utf-8")
    assert remote_script.installed_dir() == pinned
    monkeypatch.setenv("LIVEPILOT_REMOTE_SCRIPT_DIR", str(nothing_installed / "elsewhere" / "LivePilot"))
    assert remote_script.installed_dir() == nothing_installed / "elsewhere" / "LivePilot"
    assert len(remote_script.handlers()) > 150  # pinned folder missing: fall back to the repo source


def test_deploy_refuses_when_nothing_is_installed(nothing_installed):
    spec = importlib.util.spec_from_file_location("deploy_remote_handlers", REPO / "scripts" / "deploy_remote_handlers.py")
    deploy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deploy)
    assert deploy.DEST is None and deploy.LOADER_DEST is None
    result = deploy.deploy()
    assert result["success"] is False and "not installed in any Ableton Live" in result["message"]
