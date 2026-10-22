"""Settings and machine facts for Live Pilot Studio.

Settings live outside the repo in %APPDATA%\\LivePilot\\config.json (LIVEPILOT_HOME moves the
folder, which the tests use), logs in %LOCALAPPDATA%\\LivePilot\\logs. Everything about this
machine (where Live keeps its MIDI Remote Scripts, which Live is installed, whether the
Life OS phone app is around) is detected here, never hardcoded anywhere else.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

APP = "LivePilot"
HOME = Path(os.environ.get("LIVEPILOT_HOME") or Path(os.environ.get("APPDATA") or Path.home()) / APP)
CONFIG = HOME / "config.json"
_LOCAL = os.environ.get("LOCALAPPDATA")
LOG_DIR = (Path(_LOCAL) / APP if _LOCAL and not os.environ.get("LIVEPILOT_HOME") else HOME) / "logs"

DEFAULTS = {
    "name": "",                  # what Studio calls you; blank means "the artist"
    "artist_name": "",           # optional, mentioned once so it knows your stage name
    "model": "claude-opus-5-5",  # any Claude model your plan allows
    "effort": "low",             # low is fastest for routine moves
    "mic": "",                   # part of the input device's name; blank means the Windows default
    "remote_script_dir": "",     # where LivePilot's remote script is installed; blank means auto-detect
    "telegram_script": "",       # optional: a script that pushes a question to your phone (Isaiah's rail)
    "developer": False,          # the author's self-repair loop (friction questions, Fix it now, phone cards)
}


def _documents() -> Path:
    """The real Documents folder: OneDrive often moves it away from the home folder."""
    try:
        import ctypes

        folder_id = ctypes.create_string_buffer(uuid.UUID("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}").bytes_le, 16)
        found = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(folder_id, 0, None, ctypes.byref(found)) == 0:
            try:
                return Path(found.value)
            finally:
                ctypes.windll.ole32.CoTaskMemFree(found)
    except (AttributeError, OSError):  # not Windows
        pass
    return Path.home() / "Documents"


PROGRAMDATA = Path(os.environ.get("PROGRAMDATA") or r"C:\ProgramData")
USER_LIBRARY = _documents() / "Ableton" / "User Library"
OLDEST_LIVE = 11  # Live 9 and 10 run Python 2, which cannot load the remote script
LIFEOS = Path.home() / ".claude" / "channels" / "lifeos"
ASR_CACHE = Path(os.environ.get("HF_HUB_CACHE") or Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface") / "hub")
ASR_MODEL_DIR = "models--istupakov--parakeet-tdt-0.6b-v2-onnx"


def load() -> dict:
    """Settings with defaults filled in. A missing or broken file is the defaults."""
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}


def save(cfg: dict) -> Path:
    HOME.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps({k: cfg.get(k, v) for k, v in DEFAULTS.items()}, indent=2), encoding="utf-8")
    return CONFIG


def owner() -> str:
    return load()["name"].strip() or "the artist"


def remote_script_roots(programdata: Path | None = None, user_library: Path | None = None) -> list[Path]:
    """Every MIDI Remote Scripts folder Live reads on this machine, newest Live first.

    Live loads bundled scripts from <install>\\Resources\\MIDI Remote Scripts and user ones from
    User Library\\Remote Scripts. A LIVEPILOT_REMOTE_SCRIPT_DIR or a configured remote_script_dir
    names the LivePilot folder itself and wins over detection.
    """
    pinned = os.environ.get("LIVEPILOT_REMOTE_SCRIPT_DIR") or load()["remote_script_dir"]
    if pinned:
        return [Path(pinned).parent]
    roots = _newest_first(((programdata or PROGRAMDATA) / "Ableton").glob("Live */Resources/MIDI Remote Scripts"))
    user = (user_library or USER_LIBRARY) / "Remote Scripts"
    if user.is_dir():
        roots.append(user)
    return roots


def _live_version(path: Path) -> int:
    """12 for ".../Live 12 Suite/Program/x.exe": the number after "Live " in the install folder's name."""
    m = re.match(r"Live (\d+)", path.parts[-3])
    return int(m.group(1)) if m else 0


def _newest_first(paths) -> list[Path]:
    """Paths two levels inside a Live install folder: Live 11 and newer only, newest first by number, not text."""
    return sorted((p for p in paths if _live_version(p) >= OLDEST_LIVE),
                  key=lambda p: (_live_version(p), p.parts[-3]), reverse=True)


def installed_remote_scripts(roots: list[Path] | None = None) -> list[Path]:
    """The LivePilot remote script folders that are installed (have the TCP server in them)."""
    return [r / "LivePilot" for r in (roots if roots is not None else remote_script_roots()) if (r / "LivePilot" / "server.py").is_file()]


def live_exes(programdata: Path | None = None) -> list[Path]:
    """Installed Ableton Live executables (any edition or version), newest first."""
    return _newest_first(((programdata or PROGRAMDATA) / "Ableton").glob("Live */Program/Ableton Live *.exe"))


def phone_dir() -> Path | None:
    """The Life OS phone channel, when this machine has it. None means questions stay on the desktop."""
    d = Path(os.environ.get("SINCE_LIFEOS_DIR") or LIFEOS)
    return d if d.is_dir() else None


def claude_signed_in() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        return True
    claude_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    return (claude_dir / ".credentials.json").is_file()


def asr_model_cached() -> bool:
    """The model's files finished downloading. A cut-off download leaves the folder with no model in it."""
    snapshots = ASR_CACHE / ASR_MODEL_DIR / "snapshots"
    return any(snapshots.rglob("encoder-model*.onnx")) and any(snapshots.rglob("decoder_joint-model*.onnx"))


def mic() -> str:
    """Part of the microphone's name to listen on (LP_MIC wins over the "mic" setting). Blank: the Windows default."""
    return (os.environ.get("LP_MIC") or load()["mic"]).strip()
