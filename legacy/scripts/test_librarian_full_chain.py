#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def norm(s: str) -> str:
    return (s or "").strip().lower()


def _wait_for_osc(execute_ableton_function, attempts: int = 8, delay_s: float = 2.0):
    last = None
    for _ in range(attempts):
        last = execute_ableton_function("get_track_list", {})
        if last.get("success"):
            return True, last
        time.sleep(delay_s)
    return False, last or {"success": False, "message": "No response"}


def _check_jarvis_loader_connection() -> tuple[bool, dict]:
    try:
        from discovery.vst_discovery import get_vst_discovery
        svc = get_vst_discovery()
        ok = svc.test_connection()
        return ok, {
            "success": ok,
            "message": "JarvisDeviceLoader responding on /jarvis/test" if ok else "No response from JarvisDeviceLoader /jarvis/test (port 11002/11003)",
        }
    except Exception as e:
        return False, {"success": False, "message": f"Jarvis loader connection check failed: {e}"}


def _run_preflight_guard(execute_ableton_function, track_index: int, root: Path) -> int | None:
    """Run composite OSC preflight guard.  Returns exit code on failure, None on success."""
    try:
        from osc_preflight import run_preflight
    except ImportError:
        return None  # Module not available; fall through to legacy checks

    report = run_preflight(
        execute_fn=execute_ableton_function,
        track_index=track_index,
        require_loader=True,
        osc_attempts=8,
        osc_delay_s=2.0,
    )
    if report["ok"]:
        for chk in report["checks"]:
            print(f"  [PASS] {chk['name']}: {chk['message']}")
        return None

    # Preflight failed — write diagnostics and return appropriate exit code
    for chk in report["checks"]:
        tag = "PASS" if chk.get("ok") else "FAIL"
        print(f"  [{tag}] {chk['name']}: {chk['message']}")

    ft = report.get("failure_type", "unknown")
    out = {
        "success": False,
        "failure_type": ft,
        "preflight_report": report,
        "message": report["message"],
    }
    out_path = root / "logs" / "librarian_full_chain_test.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"Saved report: {out_path}")

    exit_codes = {
        "osc_unreachable_preflight": 3,
        "jarvis_loader_unreachable_preflight": 4,
        "track_unreachable": 2,
    }
    return exit_codes.get(ft, 2)


def run(song: str, artist: str | None, section: str, track_index: int):
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))

    from jarvis_engine import (
        execute_lookup_song_chain,
        execute_apply_research_chain,
        execute_ableton_function,
    )

    # -- Composite preflight guard (OSC + loader + track reachability) --
    print("[0/5] Preflight checks (OSC bridge, JarvisDeviceLoader, track)")
    preflight_rc = _run_preflight_guard(execute_ableton_function, track_index, root)
    if preflight_rc is not None:
        return preflight_rc

    # Legacy fallback paths kept for backwards-compat when osc_preflight
    # module is unavailable (the guard returns None and we proceed).
    osc_ready, osc_probe = _wait_for_osc(execute_ableton_function, attempts=1)
    if not osc_ready:
        print("  OSC preflight failed:", osc_probe)
        out = {
            "success": False,
            "failure_type": "osc_unreachable_preflight",
            "osc_probe": osc_probe,
            "message": "Ableton OSC not responding before test start",
        }
        out_path = root / "logs" / "librarian_full_chain_test.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"Saved report: {out_path}")
        return 3

    print("[0.5/5] Preflight JarvisDeviceLoader connectivity")
    loader_ok, loader_probe = _check_jarvis_loader_connection()
    if not loader_ok:
        print("  Jarvis loader preflight failed:", loader_probe)
        out = {
            "success": False,
            "failure_type": "jarvis_loader_unreachable_preflight",
            "osc_probe": osc_probe,
            "jarvis_loader_probe": loader_probe,
            "message": "JarvisDeviceLoader is not responding. Enable JarvisDeviceLoader control surface in Ableton preferences.",
        }
        out_path = root / "logs" / "librarian_full_chain_test.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"Saved report: {out_path}")
        return 4

    print(f"[1/5] Lookup local chain: {song} ({section})")
    lookup = execute_lookup_song_chain(song_title=song, artist=artist, section=section)
    if not lookup.get("success"):
        print(json.dumps(lookup, indent=2))
        return 1

    chain_spec = lookup.get("chain_spec", {})
    expected_plugins = [d.get("plugin_name", "") for d in chain_spec.get("devices", [])]
    print(f"  Found chain devices: {expected_plugins}")

    print(f"[2/5] Apply chain to track {track_index + 1}")
    try:
        apply_res = execute_apply_research_chain(track_index=track_index, chain_spec_dict=chain_spec, track_type="vocal")
    except KeyboardInterrupt:
        out = {
            "success": False,
            "failure_type": "interrupted",
            "message": "Run interrupted by user during apply step",
        }
        out_path = root / "logs" / "librarian_full_chain_test.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print("  Interrupted during apply step.")
        print(f"Saved report: {out_path}")
        return 130
    print(f"  Apply success={apply_res.get('success')} message={apply_res.get('message')}")

    print("[3/5] Verify plugin load results")
    loaded = apply_res.get("plugins_loaded", [])
    failed_plugins = apply_res.get("plugins_failed", [])
    if failed_plugins:
        print("  Plugin load failures:")
        print(json.dumps(failed_plugins, indent=2))

    loaded_names = [p.get("name", "") for p in loaded]
    missing_expected = [p for p in expected_plugins if norm(p) not in {norm(x) for x in loaded_names}]

    print("[4/5] Verify track device list from Ableton OSC")
    track_devices_res = execute_ableton_function("get_track_devices", {"track_index": track_index})
    track_device_names = []
    bridge_lost = False
    if track_devices_res.get("success"):
        track_device_names = [d.get("name", "") for d in (track_devices_res.get("devices") or [])]
    else:
        print("  Warning: could not fetch track devices", track_devices_res)
        bridge_lost = "no response" in (track_devices_res.get("message", "").lower())

    for p in expected_plugins:
        exists = any(norm(p) in norm(td) or norm(td) in norm(p) for td in track_device_names)
        print(f"   - expected '{p}' present on track: {exists}")

    print("[5/5] Verify parameter application summary")
    params_configured = apply_res.get("params_configured", [])
    print(f"  params_configured={len(params_configured)}")

    success = bool(apply_res.get("success")) and not missing_expected and not failed_plugins and not bridge_lost
    print("\n=== FINAL VERDICT ===")
    print(f"SUCCESS={success}")
    if missing_expected:
        print(f"Missing expected plugins in loaded result: {missing_expected}")

    failure_type = None
    if bridge_lost:
        failure_type = "osc_lost_during_apply"
    elif failed_plugins and any("timeout waiting for response" in (f.get("reason", "").lower()) for f in failed_plugins):
        failure_type = "device_load_timeout"

    out = {
        "lookup": lookup,
        "apply": apply_res,
        "track_devices": track_devices_res,
        "expected_plugins": expected_plugins,
        "loaded_plugins": loaded_names,
        "missing_expected": missing_expected,
        "bridge_lost": bridge_lost,
        "failure_type": failure_type,
        "success": success,
    }
    out_path = root / "logs" / "librarian_full_chain_test.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Saved report: {out_path}")

    return 0 if success else 2


def main():
    ap = argparse.ArgumentParser(description="End-to-end librarian test (lookup -> apply -> verify).")
    ap.add_argument("--song", required=True)
    ap.add_argument("--artist", default=None)
    ap.add_argument("--section", default="verse")
    ap.add_argument("--track", type=int, default=0, help="0-based track index")
    args = ap.parse_args()
    raise SystemExit(run(song=args.song, artist=args.artist, section=args.section, track_index=args.track))


if __name__ == "__main__":
    main()
