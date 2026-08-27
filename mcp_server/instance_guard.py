"""Startup guard against stale LivePilot MCP server instances.

Every Claude session spawns ``run_mcp_server.py`` and the desktop app never
reaps them, so stale instances accumulate (12 zombies observed on
2026-08-27). A stale instance that has bound UDP 11001 — the AbletonOSC
reply port, shared via SO_REUSEADDR — keeps receiving the OSC replies,
which makes the bridge look dead while Ableton is fine. The zombies keep a
live claude.exe parent and never see stdin EOF, so they cannot detect their
own staleness; the fix is for each fresh server to sweep the old ones.

``run_guard()`` is called from ``mcp_server.server.main()`` before the
stdio loop starts. It terminates other same-user python processes running
this script (skipping ones inside a grace window so simultaneous session
starts don't kill each other), then test-binds 11001 exclusively and logs
whether the port is actually free. Everything is best-effort: the guard
must never prevent the server from starting, and all output goes to stderr
because stdout carries JSON-RPC.
"""

from __future__ import annotations

import os
import socket
import sys
import time
from typing import Any

SCRIPT_BASENAMES = ("run_mcp_server.py",)
REPLY_PORT = 11001
GRACE_SECONDS = 60.0


def _log(message: str) -> None:
    print(f"[livepilot-instance-guard] {message}", file=sys.stderr, flush=True)


def _matches_target_script(cmdline: list[str] | None) -> bool:
    """True when any cmdline arg is a path to one of SCRIPT_BASENAMES."""
    for arg in cmdline or []:
        base = os.path.basename(arg.replace("\\", "/")).lower()
        if base in SCRIPT_BASENAMES:
            return True
    return False


def sweep_stale_instances(grace_seconds: float = GRACE_SECONDS) -> list[dict[str, Any]]:
    """Terminate other same-user processes running run_mcp_server.py.

    Returns a list of {pid, age_seconds, cmdline} for every process killed.
    """
    try:
        import psutil
    except ImportError:
        _log("psutil not installed; skipping stale-instance sweep")
        return []

    killed: list[dict[str, Any]] = []
    me = psutil.Process()
    try:
        my_user = me.username()
    except psutil.Error:
        my_user = None
    now = time.time()

    for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time", "username"]):
        info = proc.info
        try:
            if info["pid"] == me.pid:
                continue
            if not (info["name"] or "").lower().startswith("python"):
                continue
            if not _matches_target_script(info["cmdline"]):
                continue
            if my_user is not None and info["username"] not in (None, my_user):
                continue
            age = now - (info["create_time"] or now)
            if age < grace_seconds:
                _log(
                    f"leaving pid={info['pid']} alone "
                    f"(started {age:.0f}s ago, within {grace_seconds:.0f}s grace window)"
                )
                continue
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except psutil.TimeoutExpired:
                proc.kill()
            cmdline = " ".join(info["cmdline"] or [])
            killed.append({"pid": info["pid"], "age_seconds": round(age), "cmdline": cmdline})
            _log(f"terminated stale instance pid={info['pid']} (age {age:.0f}s): {cmdline}")
        except psutil.NoSuchProcess:
            continue
        except psutil.Error as exc:
            _log(f"could not inspect/terminate pid={info.get('pid')}: {exc}")

    if not killed:
        _log("no stale run_mcp_server.py instances found")
    return killed


def _find_port_holders(port: int) -> list[dict[str, Any]]:
    """Best-effort: name the processes bound to a UDP port."""
    try:
        import psutil
    except ImportError:
        return []

    holders: list[dict[str, Any]] = []
    try:
        for conn in psutil.net_connections(kind="udp"):
            if conn.laddr and conn.laddr.port == port and conn.pid:
                try:
                    cmdline = " ".join(psutil.Process(conn.pid).cmdline())
                except psutil.Error:
                    cmdline = "?"
                holders.append({"pid": conn.pid, "cmdline": cmdline})
    except psutil.Error as exc:
        _log(f"could not enumerate UDP endpoints: {exc}")
    return holders


def check_reply_port(port: int = REPLY_PORT) -> dict[str, Any]:
    """Exclusively test-bind the AbletonOSC reply port to see if it's free.

    The real listener binds with SO_REUSEADDR, so a plain bind would succeed
    even while a zombie still owns the port; an exclusive bind fails against
    any existing binding, which is exactly the check we want.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind(("127.0.0.1", port))
        _log(f"UDP {port} is free; OSC replies will reach this server")
        return {"free": True, "holders": []}
    except OSError as exc:
        holders = _find_port_holders(port)
        _log(f"UDP {port} still held after sweep ({exc}); holders: {holders or 'unknown'}")
        return {"free": False, "holders": holders}
    finally:
        sock.close()


def run_guard() -> None:
    """Sweep stale instances and verify the reply port. Never raises."""
    try:
        sweep_stale_instances()
        check_reply_port()
    except Exception as exc:  # pragma: no cover - guard must never break startup
        _log(f"guard failed: {exc}")
