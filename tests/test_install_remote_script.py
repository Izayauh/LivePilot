"""The installer assembles one LivePilot folder (connector plus Live Pilot files) into each Live install."""

import importlib
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
install_remote_script = importlib.import_module("install_remote_script")


@pytest.fixture(autouse=True)
def backups(tmp_path, monkeypatch):
    """Backups go to a temp folder, never the real %LOCALAPPDATA%."""
    folder = tmp_path / "backup"
    monkeypatch.setattr(install_remote_script, "BACKUPS", folder)
    return folder


def test_sources_merge_base_and_live_pilot_files():
    names = [name for _, name in install_remote_script.source_files()]
    assert {"__init__.py", "server.py", "lp_workflows.py", "lp_dialcore.py", "tracks.py"} <= set(names)
    assert "LICENSE" not in names and "README.md" not in names and len(names) == len(set(names))
    server = next(p for p, name in install_remote_script.source_files() if name == "server.py")
    assert server.parent.name == "LivePilot"  # Live Pilot's server wins over the base copy, if any


def test_install_into_fresh_then_update(tmp_path, backups):
    root = tmp_path / "MIDI Remote Scripts"
    root.mkdir()
    first = install_remote_script.install_into(root)
    dest = root / "LivePilot"
    assert first["dir"] == str(dest) and (dest / "server.py").is_file() and (dest / "LICENSE").is_file()
    assert first["changed"] and first["backup"] is None and not backups.exists()
    again = install_remote_script.install_into(root)
    assert again["changed"] == [] and again["backup"] is None
    (dest / "server.py").write_text("# someone edited this", encoding="utf-8")
    third = install_remote_script.install_into(root)
    assert third["changed"] == ["server.py"]
    saved = Path(third["backup"])
    assert saved.parent == backups and saved.name.startswith("LivePilot-")
    assert (saved / "server.py").read_text(encoding="utf-8") == "# someone edited this"
    assert sorted(p.name for p in root.iterdir()) == ["LivePilot"]  # nothing else for Live to list
    assert (dest / "server.py").read_bytes() == (ROOT / "ableton_remote_script" / "LivePilot" / "server.py").read_bytes()


def test_user_library_is_only_a_fallback(tmp_path):
    bundled = tmp_path / "Live 12 Suite" / "Resources" / "MIDI Remote Scripts"
    user = tmp_path / "User Library" / "Remote Scripts"
    assert install_remote_script.targets([bundled, user]) == [bundled]
    assert install_remote_script.targets([user]) == [user]


def test_install_to_a_given_folder_and_to_nothing(tmp_path, monkeypatch):
    out = install_remote_script.install(tmp_path / "Remote Scripts")
    assert out["success"] and "Restart Ableton Live" in out["message"] and len(out["installed"]) == 1
    monkeypatch.setattr(install_remote_script.config, "remote_script_roots", lambda: [])
    none = install_remote_script.install()
    assert not none["success"] and "No Ableton Live found" in none["message"]


def test_fresh_is_true_only_for_a_first_install(tmp_path):
    root = tmp_path / "MIDI Remote Scripts"
    assert install_remote_script.install_into(root)["fresh"] is True
    assert install_remote_script.install_into(root)["fresh"] is False


def test_a_pin_installs_into_the_pinned_livepilot_folder(tmp_path, monkeypatch):
    pinned = tmp_path / "Remote Scripts" / "LivePilot"
    monkeypatch.setenv("LIVEPILOT_REMOTE_SCRIPT_DIR", str(pinned))
    out = install_remote_script.install()
    assert out["success"] and [i["dir"] for i in out["installed"]] == [str(pinned)]
    assert (pinned / "server.py").is_file()


def test_a_pin_not_named_livepilot_is_refused_in_plain_words(tmp_path, monkeypatch):
    monkeypatch.setenv("LIVEPILOT_REMOTE_SCRIPT_DIR", str(tmp_path / "Remote Scripts" / "MyScripts"))
    out = install_remote_script.install()
    assert not out["success"] and r"has to end in \LivePilot" in out["message"]
    assert not (tmp_path / "Remote Scripts").exists()


def test_an_old_backup_inside_live_is_moved_out(tmp_path, backups):
    root = tmp_path / "MIDI Remote Scripts"
    (root / "LivePilot.bak").mkdir(parents=True)
    (root / "LivePilot.bak" / "server.py").write_text("# old copy", encoding="utf-8")
    install_remote_script.install_into(root)
    assert not (root / "LivePilot.bak").exists()
    assert [(p / "server.py").read_text(encoding="utf-8") for p in backups.iterdir()] == ["# old copy"]


def test_two_backups_in_the_same_second_do_not_collide(backups):
    first = install_remote_script.backup_dir()
    first.mkdir()
    assert install_remote_script.backup_dir() != first


def test_the_result_says_where_the_replaced_copy_went(tmp_path):
    root = tmp_path / "Remote Scripts"
    install_remote_script.install(root)
    (root / "LivePilot" / "server.py").write_text("# edited", encoding="utf-8")
    out = install_remote_script.install(root)
    assert out["success"] and out["installed"][0]["backup"] in out["message"]


def test_a_failed_copy_is_reported_in_plain_words(tmp_path, monkeypatch):
    def broken(root):
        raise shutil.Error([("a", "b", "file is in use")])
    monkeypatch.setattr(install_remote_script, "install_into", broken)
    out = install_remote_script.install(tmp_path / "Remote Scripts")
    assert not out["success"] and "Close Ableton Live" in out["message"]
