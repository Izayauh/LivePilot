"""Build the zip people install from: python scripts/make_release.py

Takes the committed tree (git archive HEAD), keeps only what is on the allowlist below (the app,
the remote script, the MCP server, their tests, the installer and the docs a user reads) and writes
dist/LivePilot-<version>.zip, the thing to attach to a GitHub release. Anything new in the repo stays
out of the zip until it is added here on purpose.
"""

from __future__ import annotations

import io
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studio import __version__  # noqa: E402

# Whole folders that ship. context/, librarian/ and playbook/ are here because livepilot_tools/context_tools.py
# imports the first two and the MCP server's mix_playbook tool imports the third.
KEEP_DIRS = ("studio/", "livepilot_tools/", "ableton_remote_script/", "mcp_server/", "ableton_controls/",
             "context/", "librarian/", "playbook/", "data/recipes/", "tests/")
KEEP_FILES = frozenset({
    "scripts/install_remote_script.py", "scripts/deploy_remote_handlers.py", "scripts/make_release.py",
    "ableton_bridge.py", "run_mcp_server.py", "osc_preflight.py", "logging_config.py",
    "constraints.txt", "install.ps1", "install.cmd", "README.md", "LICENSE.md", "AGENT-CAPABILITIES.md",
    ".env.example", ".gitignore",
    # config/: only the generic tables. kontakt_favorites.json and owned_plugins.json list the author's own
    # libraries and plugins; the rest is unused by shipped code or holds the author's paths.
    "data/live_dialog_rules.json",
    "config/osc_paths.json", "config/vocal_chains.json", "config/plugin_aliases.json",
    "config/plugin_parameter_manifests.json",
})
# Tests of things that do not ship (author scripts, the author's plugin list): they would fail in the zip.
DROP_TESTS = frozenset({
    "tests/test_ux_analyzer.py", "tests/test_apply_vocal_preset_idempotency.py", "tests/test_remember_chain.py",
    "tests/test_drums_from_loop.py", "tests/test_waves_chains.py",
})
# Audio and Live sets are recordings, never product, even inside a kept folder.
DROP_EXT = (".wav", ".mp3", ".flac", ".aif", ".aiff", ".als", ".alp", ".asd")


def shipped(name: str) -> bool:
    """True for a path in the git tree that goes into the zip."""
    if name.lower().endswith(DROP_EXT) or "/__pycache__/" in f"/{name}" or name in DROP_TESTS:
        return False
    if name in KEEP_FILES or name.startswith(KEEP_DIRS):
        return True
    return "/" not in name and name.startswith("requirements") and name.endswith(".txt")


def build(out_dir: Path = ROOT / "dist") -> Path:
    raw = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=zip", "HEAD"], capture_output=True, check=True).stdout
    out_dir.mkdir(exist_ok=True)
    target = out_dir / f"LivePilot-{__version__}.zip"
    kept = 0
    with zipfile.ZipFile(io.BytesIO(raw)) as src, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            if item.is_dir() or not shipped(item.filename):
                continue
            dst.writestr(f"LivePilot-{__version__}/{item.filename}", src.read(item.filename))
            kept += 1
    print(f"wrote {target} ({kept} files, {target.stat().st_size // 1024} KB)")
    return target


if __name__ == "__main__":
    build()
