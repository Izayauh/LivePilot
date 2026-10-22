"""Install the LivePilot remote script into Ableton Live: python scripts/install_remote_script.py [--to DIR]

Live runs ableton_remote_script/LivePilot_base (the connector, BSL-1.1) plus the three Live Pilot
files in ableton_remote_script/LivePilot, together as one folder named LivePilot inside Live's
MIDI Remote Scripts. This copies that folder into every Live install found (or --to one folder),
saves a copy it replaces under %LOCALAPPDATA%/LivePilot/backup (outside Live's folders, so Live never lists
it as a second control surface), and prints what it did. Live reads the folder when it starts:
if Live is open, restart it, then pick LivePilot as a Control Surface in Preferences.

For a hot reload of handler edits while developing, use scripts/deploy_remote_handlers.py instead.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studio import config  # noqa: E402

BASE = ROOT / "ableton_remote_script" / "LivePilot_base"
EXTRA = ROOT / "ableton_remote_script" / "LivePilot"
SKIP = {"__pycache__", "LICENSE", "README.md"}
# Same rule as install.ps1's log folder, so -Uninstall removes the backups with the logs.
BACKUPS = Path(os.environ.get("LIVEPILOT_HOME") or Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "LivePilot") / "backup"


def source_files() -> list[tuple[Path, str]]:
    """(source file, name inside the LivePilot folder). Live Pilot's files win over the base."""
    files = {p.name: p for p in BASE.iterdir() if p.name not in SKIP and p.is_file()}
    files.update({p.name: p for p in EXTRA.iterdir() if p.name not in SKIP and p.is_file()})
    return sorted((p, name) for name, p in files.items())


def backup_dir() -> Path:
    """A new, unused folder under BACKUPS for one replaced copy."""
    BACKUPS.mkdir(parents=True, exist_ok=True)
    stem = BACKUPS / f"LivePilot-{time.strftime('%Y%m%d-%H%M%S')}"
    path, n = stem, 1
    while path.exists():
        n += 1
        path = stem.with_name(f"{stem.name}-{n}")
    return path


def install_into(root: Path) -> dict:
    """Copy the assembled folder to <root>/LivePilot. Returns what changed and where a replaced copy went."""
    dest = root / "LivePilot"
    old_bak = root / "LivePilot.bak"  # where older installers kept it, inside Live's own folder
    if old_bak.exists():
        shutil.move(str(old_bak), str(backup_dir()))
    fresh = not dest.exists()
    files = source_files()
    changed = []
    for src, name in files:
        target = dest / name
        if target.exists() and target.read_bytes() == src.read_bytes():
            continue
        changed.append(name)
    backup = None
    if dest.exists() and changed:
        backup = backup_dir()
        shutil.copytree(dest, backup, ignore=shutil.ignore_patterns("__pycache__"))
    dest.mkdir(parents=True, exist_ok=True)
    for src, name in files:
        shutil.copy2(src, dest / name)
    (dest / "LICENSE").write_bytes((BASE / "LICENSE").read_bytes())
    return {"dir": str(dest), "files": len(files), "changed": changed, "fresh": fresh,
            "backup": str(backup) if backup else None}


def targets(roots: list[Path]) -> list[Path]:
    """Live's own folders when there are any; the User Library only as a fallback, so Live never sees two copies."""
    bundled = [r for r in roots if r.parent.name == "Resources"]
    return bundled or roots


def install(to: Path | None = None) -> dict:
    pinned = "" if to else os.environ.get("LIVEPILOT_REMOTE_SCRIPT_DIR") or config.load()["remote_script_dir"]
    if pinned and Path(pinned).name.lower() != "livepilot":
        # A pin names the LivePilot folder itself (config.remote_script_roots uses its parent), and Live lists
        # a control surface by its folder name, so any other name would install somewhere the pin does not say.
        return {"success": False, "installed": [],
                "message": f"The remote script folder you set is {pinned}, but it has to end in \\LivePilot "
                           "(Live lists control surfaces by folder name). Change remote_script_dir in config.json "
                           "(or LIVEPILOT_REMOTE_SCRIPT_DIR) to end in \\LivePilot, then run the installer again."}
    roots = [to] if to else targets(config.remote_script_roots())
    if not roots:
        return {"success": False, "installed": [],
                "message": f"No Ableton Live found under {config.PROGRAMDATA / 'Ableton'}. Install Live 11 or 12 and run "
                           "the installer again. If Live is installed somewhere else, set remote_script_dir in "
                           f"{config.CONFIG} to that Live's ...\\Resources\\MIDI Remote Scripts\\LivePilot folder, "
                           "then run the installer again."}
    try:
        results = [install_into(r) for r in roots]
    except PermissionError as e:
        return {"success": False, "installed": [], "message": f"Windows would not let me write there ({e}). "
                                                              "Run PowerShell as administrator, or install to the User Library with --to."}
    except shutil.Error as e:
        return {"success": False, "installed": [], "message": f"Some files could not be copied ({e}). Close Ableton Live "
                                                              "and run the installer again; if it repeats, run it as administrator."}
    restart = any(r["changed"] for r in results)
    saved = [r["backup"] for r in results if r["backup"]]
    return {"success": True, "installed": results,
            "message": ("Installed. " if restart else "Already up to date. ") +
                       ("Restart Ableton Live, then choose LivePilot as a Control Surface in "
                        "Options > Preferences > Link, Tempo & MIDI." if restart else "") +
                       (f" The copy it replaced is saved in {', '.join(saved)}." if saved else "")}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--to", type=Path, help="a MIDI Remote Scripts folder; default: every Live install found")
    args = ap.parse_args()
    result = install(args.to)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["success"] else 1)
