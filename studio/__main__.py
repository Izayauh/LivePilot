"""Start Live Pilot Studio and open its window: python -m studio

--no-mic      type only
--no-window   don't open a window, and keep running when windows close (for testing)
--check       print the setup checks and exit
--version     print the version and exit
Closing the window stops the app. Launching again while it runs just opens another window.
"""

import logging
import os
import socket
import subprocess
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from studio import __version__, health  # noqa: E402

PF = [os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
      os.environ.get("LOCALAPPDATA", "")]
# Any Chromium browser can show the window as an app (no tabs, no address bar); the default browser is the fallback.
BROWSERS = [str(Path(base) / sub) for sub in (r"BraveSoftware\Brave-Browser\Application\brave.exe",
                                               r"Google\Chrome\Application\chrome.exe",
                                               r"Microsoft\Edge\Application\msedge.exe") for base in PF if base]
log = logging.getLogger("studio.main")


def open_window(url: str) -> None:
    for exe in BROWSERS:
        if Path(exe).exists():
            subprocess.Popen([exe, f"--app={url}", "--window-size=1100,760"])
            return
    webbrowser.open(url)


def already_running(port: int) -> bool | None:
    """None: the port is free. True: Live Pilot answers there. False: some other program holds the port."""
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", port)) != 0:
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never through a proxy, even if one is set
    try:
        with opener.open(f"http://127.0.0.1:{port}/", timeout=2) as r:
            return "Live Pilot" in r.read(65536).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001  anything that is not our page is someone else's program
        return False


def main() -> int:
    if "--version" in sys.argv:
        print(__version__)
        return 0
    if "--check" in sys.argv:
        print(health.report(health.check()))
        return 0
    health.setup_logging()
    from aiohttp import web

    from studio.server import PORT, Studio

    url = f"http://127.0.0.1:{PORT}"
    window = "--no-window" not in sys.argv
    running = already_running(PORT)
    if running:
        log.info("already running on %s; opening another window", url)
        if window:
            open_window(url)
        return 0
    if running is False:
        log.error("port %s is held by another program", PORT)
        health.say_out_loud("Live Pilot could not start",
                            f"Another program is using port {PORT}, which Live Pilot needs for its window. "
                            f"Close that program, or set STUDIO_PORT=8771 in your environment variables to "
                            f"move Live Pilot to another port, then open Live Pilot again.")
        return 1
    if window:
        threading.Timer(1.0, open_window, [url]).start()
    studio = Studio(with_ears="--no-mic" not in sys.argv, quit_when_closed=window)
    web.run_app(studio.app(), host="127.0.0.1", port=PORT, print=None)
    log.info("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
