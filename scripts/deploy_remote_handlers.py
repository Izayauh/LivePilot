"""Copy repo-owned LivePilot remote-script handlers into Ableton and hot-reload them.

    python scripts/deploy_remote_handlers.py

Copies ableton_remote_script/LivePilot/*.py (handlers plus server.py) into the LivePilot remote script
that Live actually loads, adds their import to its __init__.py (once, so they
load at startup), then asks Live to hot-reload and checks that the lp_*
commands are registered.

Live loads the copy under the install folder's MIDI Remote Scripts, not the
User Library one (verified 2026-10-13: only the install-folder copies ever
compiled to __pycache__). Copies under User Library/Remote Scripts are ignored.
Also installs ableton_remote_script/JarvisDeviceLoader, which has no hot
reload and needs a Live restart whenever it changes.
"""

import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from livepilot_tools import remote_script  # noqa: E402
from studio import config  # noqa: E402

SRC = REPO / "ableton_remote_script" / "LivePilot"
DEST = remote_script.installed_dir()  # same lookup Studio uses; None when no Live has it installed
LOADER_SRC = REPO / "ableton_remote_script" / "JarvisDeviceLoader" / "__init__.py"
LOADER_DEST = DEST.parent / "JarvisDeviceLoader" / "__init__.py" if DEST else None
REQUIRED = {"lp_chain", "lp_params", "lp_dial", "lp_set"}
IMPORT_ANCHOR = "from . import version_detect"
NOT_HANDLERS = {"server.py"}
RESTART_HINT = "Hot reload did not pick them up. Save the set and restart Live once."


def _ensure_imported(module_names) -> list[str]:
    init = DEST / "__init__.py"
    text = init.read_text(encoding="utf-8")
    added = []
    for name in module_names:
        line = f"from . import {name}  # noqa: F401  (music/live-pilot)"
        if line not in text:
            text = text.replace(IMPORT_ANCHOR, line + "\n" + IMPORT_ANCHOR, 1)
            added.append(name)
    if added:
        backup = init.with_name("__init__.py.bak-before-lp")
        if not backup.exists():
            shutil.copy2(init, backup)
        init.write_text(text, encoding="utf-8")
    return added


def _deploy_loader() -> bool:
    """Install the repo JarvisDeviceLoader. It has no hot reload: True means Live needs a restart."""
    if LOADER_DEST.exists() and LOADER_DEST.read_bytes() == LOADER_SRC.read_bytes():
        return False
    if LOADER_DEST.exists():
        shutil.copy2(LOADER_DEST, LOADER_DEST.with_name("__init__.py.bak-before-deploy"))
    shutil.copy2(LOADER_SRC, LOADER_DEST)
    return True


def stale(src: Path = SRC, dest: Path = DEST) -> list[str]:
    """Handler files (lp_*.py) whose deployed copy is missing or differs from the repo's."""
    if not dest.is_dir():
        return []
    return [f.name for f in sorted(src.glob("lp_*.py"))
            if not (dest / f.name).exists() or (dest / f.name).read_bytes() != f.read_bytes()]


def deploy() -> dict:
    if DEST is None:
        return {"success": False, "message": "The LivePilot remote script is not installed in any Ableton Live on this "
                                             "computer. Run install.ps1 (or scripts/install_remote_script.py) first."}
    if not DEST.is_dir():
        return {"success": False, "message": f"LivePilot remote script not installed at {DEST}"}
    copied = []
    server_changed = False
    for src in SRC.glob("*.py"):
        dest = DEST / src.name
        if src.name == "server.py":
            server_changed = not dest.exists() or dest.read_bytes() != src.read_bytes()
        shutil.copy2(src, dest)
        copied.append(src.name)
    # server.py is imported by __init__ already and owns the socket: never hot reloaded.
    imports_added = _ensure_imported(Path(name).stem for name in copied if name not in NOT_HANDLERS)
    loader_changed = _deploy_loader()
    remote_script.send_command("reload_handlers")
    ping = remote_script.send_command("ping")
    if not ping.get("success"):
        return {"success": False, "copied": copied, "message": f"Copied; Live not reachable: {ping.get('message')}"}
    missing = sorted(REQUIRED - set(ping.get("commands", [])))
    out = {"success": not missing, "copied": copied, "imports_added": imports_added, "missing": missing,
           "jarvis_device_loader_updated": loader_changed, "server_updated": server_changed}
    if missing:
        out["next_step"] = RESTART_HINT
    elif loader_changed or server_changed:
        out["next_step"] = ("JarvisDeviceLoader or server.py was updated; they load only at startup. "
                            "Save the set and restart Live once.")
    return out


if __name__ == "__main__":
    result = deploy()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["success"] else 1)
