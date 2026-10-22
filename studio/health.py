"""What has to be true before Studio can work, said in plain words with the fix next to it.

check() is shown in the window as a Setup card when anything fails and printed by
`python -m studio --check`. setup_logging() sends every log line and every uncaught error to
%LOCALAPPDATA%\\LivePilot\\logs\\studio.log and, when there is no console, puts the error in a
message box, so a crash never ends in a window that silently closed.
"""

from __future__ import annotations

import ctypes
import importlib
import logging
import logging.handlers
import os
import sys
import threading
import traceback
import urllib.request
from pathlib import Path

from studio import __version__, config

log = logging.getLogger("studio")

INSTALL = "Run install.ps1 in the Live Pilot folder (right click, Run with PowerShell)."
MODULES = ("aiohttp", "claude_agent_sdk", "onnx_asr", "sounddevice", "numpy", "psutil", "win32gui", "PIL", "winrt.windows.media.ocr")


def _deps() -> dict:
    missing = []
    for name in MODULES:
        try:
            importlib.import_module(name)
        except Exception:  # noqa: BLE001 - any import failure means the same thing to the user
            missing.append(name)
    return {"id": "deps", "ok": not missing, "title": "Python packages",
            "detail": "all installed" if not missing else "missing: " + ", ".join(missing), "fix": INSTALL}


def _remote_script() -> dict:
    roots = config.remote_script_roots()
    found = config.installed_remote_scripts(roots)
    if not roots:
        return {"id": "remote_script", "ok": False, "title": "Ableton Live",
                "detail": "no Ableton Live install found under " + str(config.PROGRAMDATA / "Ableton"),
                "fix": "Install Ableton Live 11 or 12 (any edition), then run install.ps1 again."}
    return {"id": "remote_script", "ok": bool(found), "title": "LivePilot remote script",
            "detail": "installed in " + str(found[0]) if found else "not in " + str(roots[0]),
            "fix": INSTALL + " Then in Live: Options > Preferences > Link, Tempo & MIDI, choose LivePilot as a Control Surface."}


def _live() -> dict:
    from livepilot_tools import remote_script

    ping = remote_script.send_command("ping", timeout=2.0)
    ok = bool(ping.get("success"))
    return {"id": "live", "ok": ok, "title": "Ableton Live is answering",
            "detail": f"{len(ping.get('commands', []))} commands ready" if ok else ping.get("message", "no answer"),
            "fix": "Open Ableton Live with the LivePilot control surface enabled (Options > Preferences > Link, Tempo & MIDI). "
                   "If Live just opened, wait for the set to finish loading."}


def _claude() -> dict:
    ok = config.claude_signed_in()
    return {"id": "claude", "ok": ok, "title": "Signed in to Claude",
            "detail": "credentials found" if ok else "no Claude sign-in on this computer",
            "fix": "Run install.ps1 -Login and sign in with your Claude account (Pro or Max), or put ANTHROPIC_API_KEY in your environment."}


MIC_FIX = ("Plug in a microphone and make it the default input (Windows Settings > System > Sound > Input), "
           "then close and reopen Live Pilot Studio: it only looks for microphones when it starts. "
           "Or start Studio with --no-mic and type instead.")


def _mic() -> dict:
    """The input Studio will listen on: the device named by the "mic" setting, else the Windows default."""
    wanted = config.mic()
    named, name = [], ""
    try:
        import sounddevice as sd

        if wanted:
            named = [d["name"] for d in sd.query_devices() if d["max_input_channels"] > 0 and wanted.lower() in d["name"].lower()]
        name = named[0] if named else sd.query_devices(kind="input")["name"]
    except Exception:  # noqa: BLE001 - PortAudio raises when there is no default input
        pass
    if wanted and not named:
        return {"id": "mic", "ok": False, "title": "Microphone",
                "detail": f'no microphone matches the "mic" setting "{wanted}"' + (f", using {name}" if name else ""),
                "fix": f"Change \"mic\" in {config.CONFIG} to part of your microphone's name, or blank it to use the "
                       "Windows default. " + MIC_FIX}
    return {"id": "mic", "ok": bool(name), "title": "Microphone",
            "detail": f"using {name}" if name else "no default microphone on this computer",
            "fix": MIC_FIX}


def _asr() -> dict:
    ok = config.asr_model_cached()
    return {"id": "asr", "ok": ok, "title": "Speech model",
            "detail": "downloaded" if ok else "not downloaded yet (2.4 GB, first start will fetch it)",
            "fix": "install.ps1 downloads it; or start Studio once with the mic on and wait."}


def _port() -> dict:
    """Studio's window port is free, or already Live Pilot (a Studio that is running)."""
    port = int(os.environ.get("STUDIO_PORT") or 8770)
    # Read the listening sockets instead of test-binding: a test bind could take the port from a Studio starting up.
    try:
        import psutil

        free = not any(c.status == psutil.CONN_LISTEN and c.laddr and c.laddr.port == port
                       for c in psutil.net_connections("tcp"))
    except ImportError:  # the Python packages check reports it
        free = True
    ours = False
    if not free:
        try:
            direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never through a proxy
            with direct.open(f"http://127.0.0.1:{port}/", timeout=2) as r:
                ours = "Live Pilot" in r.read(65536).decode("utf-8", "ignore")
        except Exception:  # noqa: BLE001 - not answering HTTP means it is some other program
            ours = False
    return {"id": "port", "ok": free or ours, "title": f"Window port {port}",
            "detail": "free" if free else "Live Pilot Studio is already running there" if ours else "another program is using it",
            "fix": f"Close the program using port {port}, or set STUDIO_PORT in your environment to another number "
                   "(for example 8771) and start Studio again."}


def check(live: bool = True) -> list[dict]:
    """Every check, failing ones first. live=False skips talking to Live (the window polls that itself)."""
    checks = [_deps(), _remote_script(), _claude(), _mic(), _asr(), _port()]
    if live:
        checks.insert(2, _live())
    return sorted(checks, key=lambda c: c["ok"])


def problems(checks: list[dict]) -> list[dict]:
    return [c for c in checks if not c["ok"]]


def report(checks: list[dict]) -> str:
    lines = [f"Live Pilot Studio {__version__}"]
    for c in checks:
        lines.append(f"[{'ok' if c['ok'] else 'FIX'}] {c['title']}: {c['detail']}")
        if not c["ok"]:
            lines.append(f"      -> {c['fix']}")
    return "\n".join(lines)


# -- logging and crashes -------------------------------------------------------

def log_path() -> Path:
    return config.LOG_DIR / "studio.log"


def setup_logging() -> Path:
    """File log (5 x 2 MB) plus console when there is one. Uncaught errors go to both and, headless, to a message box."""
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        fh = logging.handlers.RotatingFileHandler(log_path(), maxBytes=2_000_000, backupCount=5, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(fh)
        if sys.stderr is not None and sys.stderr.isatty():
            sh = logging.StreamHandler()
            sh.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
            root.addHandler(sh)
    root.setLevel(logging.INFO)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)  # one line per poll would bury the real entries
    sys.excepthook = _crash_hook
    threading.excepthook = lambda a: _crash_hook(a.exc_type, a.exc_value, a.exc_traceback)
    log.info("Live Pilot Studio %s starting, log at %s", __version__, log_path())
    return log_path()


def _crash_hook(exc_type, exc, tb) -> None:
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    log.critical("crash:\n%s", text)
    say_out_loud("Live Pilot Studio stopped", f"{exc_type.__name__}: {exc}\n\nThe full error is in\n{log_path()}")


def say_out_loud(title: str, text: str) -> None:
    """A message box when there is no console to read; otherwise stderr. Never raises."""
    try:
        if sys.platform == "win32" and (sys.stderr is None or not sys.stderr.isatty()):
            ctypes.windll.user32.MessageBoxW(0, text, title, 0x10 | 0x1000)  # MB_ICONERROR | MB_SYSTEMMODAL
        else:
            print(f"{title}\n{text}", file=sys.stderr)
    except Exception:  # noqa: BLE001
        pass
