"""Client for the LivePilot remote script's JSON-over-TCP server.

The remote script (Ableton User Library/Remote Scripts/LivePilot/server.py)
listens on 127.0.0.1:9878, reads newline-delimited JSON requests
``{"id", "type", "params"}``, runs them on Live's main thread, and answers
``{"id", "ok", "result"}`` or ``{"id", "ok": false, "error": {"code", "message"}}``.

The server is single-client and a new connection replaces the current one, so
this process only ever holds one socket. Two sockets from one process kick each
other mid-request: writes land in Live but their replies are lost (seen live
2026-10-13).

By default a call opens a fresh connection, which then becomes the shared one,
and is never resent. ``persistent=True`` reuses the shared connection (about
0.4 s faster per call) and reconnects and resends once if another client bumped
it; only use it for commands that are safe to send twice (reads and absolute
sets), because a request can land just before the server drops the old connection.
"""

import json
import os
import re
import socket
import threading
import uuid
from pathlib import Path

HOST = "127.0.0.1"
PORT = 9878
# A folder to read handlers from. None means handler_dirs() finds them (tests pin this).
REMOTE_SCRIPT_DIR = None
REPO_SCRIPT = Path(__file__).resolve().parents[1] / "ableton_remote_script"


def installed_dir():
    """The LivePilot folder Live runs: LIVEPILOT_REMOTE_SCRIPT_DIR, then the remote_script_dir
    setting, then the newest Live that has it installed. None when nothing is installed."""
    from studio import config  # here, not at the top: studio.config must never import livepilot_tools

    pinned = os.environ.get("LIVEPILOT_REMOTE_SCRIPT_DIR") or config.load()["remote_script_dir"]
    if pinned:
        return Path(pinned)
    installed = config.installed_remote_scripts()
    return installed[0] if installed else None


def handler_dirs():
    """Where handler source is read from: the installed copy (what Live runs), or, when Live
    has none, the repo's own two folders the installer assembles it from (the same files)."""
    if REMOTE_SCRIPT_DIR:
        return [Path(REMOTE_SCRIPT_DIR)]
    installed = installed_dir()
    if installed and installed.is_dir():
        return [installed]
    return [REPO_SCRIPT / "LivePilot_base", REPO_SCRIPT / "LivePilot"]


_conn = None
_conn_lock = threading.Lock()


def _exchange(sock, payload):
    sock.sendall(payload)
    buf = bytearray()
    while b"\n" not in buf:
        chunk = sock.recv(65536)
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf).split(b"\n", 1)[0]


def _send(payload, timeout, persistent):
    global _conn
    with _conn_lock:
        if not persistent and _conn is not None:
            _conn.close()
            _conn = None
        for attempt in ((0, 1) if persistent else (1,)):
            try:
                if _conn is None:
                    _conn = socket.create_connection((HOST, PORT), timeout=timeout)
                _conn.settimeout(timeout)
                line = _exchange(_conn, payload)
                if line:
                    return line
                raise OSError("connection closed by the remote script")
            except OSError:
                if _conn is not None:
                    _conn.close()
                _conn = None
                if attempt == 1:
                    raise
    return b""


def send_command(cmd_type, params=None, timeout=5.0, persistent=False):
    """Send one command and return ``{"success": True, **result}`` or an error dict."""
    request = {"id": uuid.uuid4().hex[:8], "type": cmd_type, "params": params or {}}
    payload = (json.dumps(request) + "\n").encode("utf-8")
    try:
        line = _send(payload, timeout, persistent)
    except OSError as e:
        return {"success": False,
                "message": f"LivePilot remote script unreachable on {HOST}:{PORT}: {e}"}

    if not line:
        return {"success": False, "message": f"{cmd_type}: remote script closed without a response"}
    try:
        resp = json.loads(line.decode("utf-8"))
    except ValueError as e:
        return {"success": False, "message": f"{cmd_type}: bad JSON from remote script: {e}"}

    if not resp.get("ok"):
        err = resp.get("error") or {}
        return {"success": False, "code": err.get("code"),
                "message": err.get("message", f"{cmd_type} failed")}
    return {"success": True, **(resp.get("result") or {})}


def get_track_meters(track_index=None, include_stereo=False):
    """Output meter levels (0.0-1.0, Live's meter scale) for one track or all tracks."""
    params = {"include_stereo": bool(include_stereo)}
    if track_index is not None:
        params["track_index"] = int(track_index)
    return send_command("get_track_meters", params)


def get_master_meters():
    """Master output meter levels: level, left, right (0.0-1.0, Live's meter scale)."""
    return send_command("get_master_meters")


_REGISTER = re.compile(r'^@register\("([a-z0-9_]+)"\)', re.M)


def handlers(directory=None):
    """Every handler registered in the deployed remote script: name -> {doc, params, file}.

    ``doc`` is the handler docstring; ``params`` every key its body reads, since many
    docstrings do not name them (the docstring says which are required, when it does).
    Read from source, so it needs no round trip to Live.
    """
    files = {}  # a later folder's file replaces an earlier one's, as the installer does
    for folder in ([Path(directory)] if directory else handler_dirs()):
        files.update({p.name: p for p in folder.glob("*.py")})
    out = {}
    for _, path in sorted(files.items()):
        src = path.read_text(encoding="utf-8", errors="ignore")
        marks = list(_REGISTER.finditer(src))
        for i, mark in enumerate(marks):
            body = src[mark.end():marks[i + 1].start() if i + 1 < len(marks) else len(src)]
            doc = re.search(r'^\s*def [^\n]*\n\s*(?:"""|\'\'\')(.*?)(?:"""|\'\'\')', body, re.S)
            keys = re.findall(r'params(?:\[|\.get\(\s*)["\'](\w+)["\']', body)
            out[mark.group(1)] = {"doc": " ".join(doc.group(1).split()) if doc else "",
                                  "params": list(dict.fromkeys(keys)), "file": path.name}
    return out
