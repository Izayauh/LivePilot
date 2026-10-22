#!/usr/bin/env python3
"""
OSC preflight guard — deterministic connectivity checks for Ableton OSC and
JarvisDeviceLoader before execution-heavy flows.

Returns structured diagnostics so callers get actionable error messages
instead of vague timeouts.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Individual check primitives
# ---------------------------------------------------------------------------

def check_osc_bridge(execute_fn: Callable[..., Dict[str, Any]],
                     attempts: int = 4,
                     delay_s: float = 1.5) -> Dict[str, Any]:
    """Verify the Ableton OSC bridge is responding.

    Args:
        execute_fn: Callable matching ``execute_ableton_function(name, args)``.
        attempts: Max retries.
        delay_s: Seconds between retries.

    Returns:
        ``{"ok": bool, "latency_ms": float|None, "attempts_used": int,
           "message": str, "last_response": dict}``
    """
    last_resp: Dict[str, Any] = {}
    for i in range(1, attempts + 1):
        t0 = time.monotonic()
        try:
            resp = execute_fn("get_track_list", {})
        except Exception as exc:
            last_resp = {"success": False, "error": str(exc)}
            if i < attempts:
                time.sleep(delay_s)
            continue
        elapsed_ms = (time.monotonic() - t0) * 1000
        last_resp = resp
        if resp.get("success"):
            return {
                "ok": True,
                "latency_ms": round(elapsed_ms, 1),
                "attempts_used": i,
                "message": f"OSC bridge responding ({elapsed_ms:.0f} ms, attempt {i}/{attempts})",
                "last_response": resp,
            }
        if i < attempts:
            time.sleep(delay_s)

    return {
        "ok": False,
        "latency_ms": None,
        "attempts_used": attempts,
        "message": f"OSC bridge unreachable after {attempts} attempts",
        "last_response": last_resp,
    }


def check_jarvis_loader() -> Dict[str, Any]:
    """Verify the JarvisDeviceLoader control surface is responding.

    Returns:
        ``{"ok": bool, "message": str}``
    """
    try:
        from discovery.vst_discovery import get_vst_discovery
        svc = get_vst_discovery()
        ok = svc.test_connection()
        return {
            "ok": ok,
            "message": (
                "JarvisDeviceLoader responding on /jarvis/test"
                if ok else
                "No response from JarvisDeviceLoader /jarvis/test (port 11002/11003)"
            ),
        }
    except Exception as exc:
        return {
            "ok": False,
            "message": f"JarvisDeviceLoader check failed: {exc}",
        }


def check_track_accessible(execute_fn: Callable[..., Dict[str, Any]],
                            track_index: int) -> Dict[str, Any]:
    """Verify a specific track index is reachable via OSC.

    Args:
        execute_fn: ``execute_ableton_function`` callable.
        track_index: 0-based track index.

    Returns:
        ``{"ok": bool, "track_count": int|None, "message": str}``
    """
    try:
        resp = execute_fn("get_track_list", {})
    except Exception as exc:
        return {"ok": False, "track_count": None,
                "message": f"get_track_list failed: {exc}"}
    if not resp.get("success"):
        return {"ok": False, "track_count": None,
                "message": f"get_track_list unsuccessful: {resp.get('message', '')}"}
    tracks = resp.get("tracks", [])
    count = len(tracks)
    if track_index >= count:
        return {
            "ok": False,
            "track_count": count,
            "message": f"track_index {track_index} out of range (project has {count} tracks)",
        }
    return {
        "ok": True,
        "track_count": count,
        "message": f"Track {track_index} accessible ({count} tracks in project)",
    }


# ---------------------------------------------------------------------------
# Composite preflight
# ---------------------------------------------------------------------------

def run_preflight(execute_fn: Callable[..., Dict[str, Any]],
                  track_index: Optional[int] = None,
                  require_loader: bool = True,
                  osc_attempts: int = 4,
                  osc_delay_s: float = 1.5) -> Dict[str, Any]:
    """Run all preflight checks and return a combined report.

    Checks are run in dependency order — later checks are skipped if an
    earlier one fails so the caller gets the *first* actionable failure.

    Args:
        execute_fn: ``execute_ableton_function`` callable.
        track_index: If given, also verify this track is reachable.
        require_loader: Whether JarvisDeviceLoader is required.
        osc_attempts: Retries for OSC check.
        osc_delay_s: Seconds between OSC retries.

    Returns:
        ``{"ok": bool, "checks": [...], "failure_type": str|None,
           "message": str}``
    """
    checks: List[Dict[str, Any]] = []
    failure_type: Optional[str] = None

    # 1. OSC bridge
    osc = check_osc_bridge(execute_fn, attempts=osc_attempts, delay_s=osc_delay_s)
    checks.append({"name": "osc_bridge", **osc})
    if not osc["ok"]:
        failure_type = "osc_unreachable_preflight"
        return _build_report(checks, failure_type)

    # 2. JarvisDeviceLoader (optional)
    if require_loader:
        loader = check_jarvis_loader()
        checks.append({"name": "jarvis_loader", **loader})
        if not loader["ok"]:
            failure_type = "jarvis_loader_unreachable_preflight"
            return _build_report(checks, failure_type)

    # 3. Track reachability (optional)
    if track_index is not None:
        track = check_track_accessible(execute_fn, track_index)
        checks.append({"name": "track_accessible", **track})
        if not track["ok"]:
            failure_type = "track_unreachable"
            return _build_report(checks, failure_type)

    return _build_report(checks, None)


def _build_report(checks: List[Dict[str, Any]],
                  failure_type: Optional[str]) -> Dict[str, Any]:
    ok = failure_type is None
    if ok:
        msg = f"All {len(checks)} preflight checks passed"
    else:
        # Find first failing check message
        failed = [c for c in checks if not c.get("ok")]
        msg = failed[0]["message"] if failed else "Unknown preflight failure"
    return {
        "ok": ok,
        "checks": checks,
        "failure_type": failure_type,
        "message": msg,
    }
