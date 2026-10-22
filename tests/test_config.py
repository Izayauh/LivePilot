"""Settings live outside the repo, and everything about the machine is detected, not hardcoded."""

import importlib
import json

import pytest

from studio import config


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("LIVEPILOT_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("LIVEPILOT_REMOTE_SCRIPT_DIR", raising=False)
    importlib.reload(config)
    yield tmp_path
    monkeypatch.undo()  # the real environment back before the reload below
    importlib.reload(config)


def test_defaults_without_a_file(home):
    cfg = config.load()
    assert cfg["name"] == "" and cfg["model"] == "claude-opus-5-5" and cfg["effort"] == "low"
    assert config.owner() == "the artist"


def test_save_then_load_keeps_only_known_keys(home):
    path = config.save({"name": "Sam", "artist_name": "SAM", "junk": 1})
    assert path == config.CONFIG and path.parent == home / "home"
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert "junk" not in on_disk and on_disk["name"] == "Sam"
    assert config.load()["artist_name"] == "SAM" and config.owner() == "Sam"


def test_broken_file_is_the_defaults(home):
    config.HOME.mkdir(parents=True)
    config.CONFIG.write_text("{not json", encoding="utf-8")
    assert config.load() == config.DEFAULTS


def test_remote_script_roots_find_every_live_newest_first(home):
    pd = home / "ProgramData"
    for edition in ("Live 9 Suite", "Live 10 Suite", "Live 11 Standard", "Live 12 Suite"):
        (pd / "Ableton" / edition / "Resources" / "MIDI Remote Scripts").mkdir(parents=True)
    lib = home / "User Library"
    (lib / "Remote Scripts").mkdir(parents=True)
    roots = config.remote_script_roots(pd, lib)
    # newest by number ("Live 9" sorts above "Live 12" as text); 9 and 10 run Python 2, so they are left out
    assert [r.parts[-3] for r in roots[:2]] == ["Live 12 Suite", "Live 11 Standard"]
    assert roots[2] == lib / "Remote Scripts" and len(roots) == 3
    assert config.installed_remote_scripts(roots) == []
    (roots[0] / "LivePilot").mkdir()
    (roots[0] / "LivePilot" / "server.py").write_text("", encoding="utf-8")
    assert config.installed_remote_scripts(roots) == [roots[0] / "LivePilot"]


def test_pinned_remote_script_dir_wins(home, monkeypatch):
    monkeypatch.setenv("LIVEPILOT_REMOTE_SCRIPT_DIR", str(home / "custom" / "LivePilot"))
    assert config.remote_script_roots(home / "nowhere", home / "nowhere") == [home / "custom"]


def test_live_exes_any_edition(home):
    pd = home / "ProgramData"
    for edition in ("Live 9 Suite", "Live 11 Standard", "Live 12 Suite"):
        exe = pd / "Ableton" / edition / "Program" / f"Ableton {edition}.exe"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"")
    assert [p.name for p in config.live_exes(pd)] == ["Ableton Live 12 Suite.exe", "Ableton Live 11 Standard.exe"]
    assert config.live_exes(home / "empty") == []


def test_phone_only_when_life_os_is_there(home, monkeypatch):
    monkeypatch.setenv("SINCE_LIFEOS_DIR", str(home / "lifeos"))
    assert config.phone_dir() is None
    (home / "lifeos").mkdir()
    assert config.phone_dir() == home / "lifeos"


def test_logs_go_to_local_app_data_once(home, monkeypatch):
    monkeypatch.delenv("LIVEPILOT_HOME")
    monkeypatch.setenv("APPDATA", str(home / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(home / "Local"))
    importlib.reload(config)
    assert config.LOG_DIR == home / "Local" / "LivePilot" / "logs"
    monkeypatch.delenv("LOCALAPPDATA")
    importlib.reload(config)
    assert config.LOG_DIR == home / "Roaming" / "LivePilot" / "logs"  # not ...\LivePilot\LivePilot\logs


def test_claude_sign_in_honors_claude_config_dir(home, monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / "claude"))
    assert config.claude_signed_in() is False
    (home / "claude").mkdir()
    (home / "claude" / ".credentials.json").write_text("{}", encoding="utf-8")
    assert config.claude_signed_in() is True


def test_speech_model_counts_only_when_the_model_files_landed(home, monkeypatch):
    monkeypatch.setattr(config, "ASR_CACHE", home / "hub")
    snap = home / "hub" / config.ASR_MODEL_DIR / "snapshots" / "abc"
    snap.mkdir(parents=True)
    (snap / "config.json").write_text("{}", encoding="utf-8")
    assert config.asr_model_cached() is False  # a cut-off download: the folder is there, the model is not
    (snap / "decoder_joint-model.onnx").write_bytes(b"x")
    assert config.asr_model_cached() is False
    (snap / "encoder-model.onnx").write_bytes(b"x")
    assert config.asr_model_cached() is True


def test_mic_setting_and_lp_mic_override(home, monkeypatch):
    monkeypatch.delenv("LP_MIC", raising=False)
    assert config.mic() == ""
    config.save({"mic": "Audient"})
    assert config.mic() == "Audient"
    monkeypatch.setenv("LP_MIC", "Yeti")
    assert config.mic() == "Yeti"


def test_user_library_is_under_the_real_documents_folder():
    assert config.USER_LIBRARY.parent.parent.is_dir() and config.USER_LIBRARY.parts[-2:] == ("Ableton", "User Library")
