"""The release zip ships only the allowlisted product: no personal notes, recordings, or author paths."""

from __future__ import annotations

import importlib
import sys
import zipfile
from pathlib import Path

import pytest

from studio import __version__

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
make_release = importlib.import_module("make_release")

pytestmark = pytest.mark.skipif(not (ROOT / ".git").exists(), reason="building a release needs a git checkout")


@pytest.fixture(scope="module")
def shipped(tmp_path_factory):
    target = make_release.build(tmp_path_factory.mktemp("dist"))
    with zipfile.ZipFile(target) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        prefix = f"LivePilot-{__version__}/"
        assert names and all(n.startswith(prefix) for n in names)
        return {n[len(prefix):]: z.read(n) for n in names}


def test_zip_keeps_the_product(shipped):
    for keep in ("README.md", "LICENSE.md", "install.ps1", "install.cmd", "constraints.txt", "requirements-studio.txt",
                 "AGENT-CAPABILITIES.md", "studio/health.py", "livepilot_tools/workflows.py",
                 "ableton_remote_script/LivePilot_base/LICENSE", "ableton_remote_script/LivePilot/server.py",
                 "config/osc_paths.json", "tests/test_make_release.py"):
        assert keep in shipped, keep
    assert {p for p in shipped if p.startswith("scripts/")} == {
        "scripts/install_remote_script.py", "scripts/deploy_remote_handlers.py", "scripts/make_release.py"}


def test_zip_drops_personal_files(shipped):
    paths = set(shipped)
    assert not {"CLAUDE.md", "ASKS.md", "VISION.md", "CONTEXT.md", ".cursorrules", "config/kontakt_favorites.json",
                "config/owned_plugins.json", "config/reference_library.json.example"} & paths
    assert not [p for p in paths if p.startswith(("docs/", "legacy/", "work/", ".claude/", ".agent/", "analysis/"))]
    assert not [p for p in paths if p.lower().endswith((".wav", ".mp3", ".flac", ".aif", ".aiff", ".als", ".alp", ".asd"))]
    assert not [p for p in paths if p.startswith("data/") and not p.startswith("data/recipes/") and p != "data/live_dialog_rules.json"]


def test_no_author_path_outside_tests(shipped):
    needles = (b"c:\\users\\isaia", b"c:/users/isaia", b"c:\\\\users\\\\isaia")
    hits = [p for p, body in shipped.items() if not p.startswith("tests/") and any(n in body.lower() for n in needles)]
    assert hits == []
