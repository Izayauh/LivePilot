#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from ableton_watchdog import AbletonWatchdog


def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def run_test_script(root: Path, song: str, artist: str, section: str, track: int) -> int:
    cmd = [
        sys.executable,
        str(root / "scripts" / "test_librarian_full_chain.py"),
        "--song", song,
        "--artist", artist,
        "--section", section,
        "--track", str(track),
    ]
    return subprocess.call(cmd, cwd=str(root))


def main() -> int:
    ap = argparse.ArgumentParser(description="Jarvis E2E orchestrator")
    ap.add_argument("--mode", choices=["full", "verify-only", "resume"], default="full")
    ap.add_argument("--song", required=True)
    ap.add_argument("--artist", default="")
    ap.add_argument("--section", default="chorus")
    ap.add_argument("--track", type=int, default=0)
    ap.add_argument("--ableton-exe", default="", help="Optional full path to Ableton Live executable")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    logs = root / "logs"
    state_path = logs / "e2e_state.json"
    summary_path = logs / "e2e_summary.json"

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    state = {
        "run_id": run_id,
        "mode": args.mode,
        "step": "init",
        "status": "running",
        "song": args.song,
        "artist": args.artist,
        "section": args.section,
        "track_index": args.track,
        "updated_at": datetime.now().isoformat(),
    }
    write_json(state_path, state)

    watchdog = AbletonWatchdog(state_path=state_path, ableton_exe=args.ableton_exe)

    if args.mode in {"full", "resume"}:
        state["step"] = "ensure_ableton"
        write_json(state_path, state)
        ok = watchdog.ensure_running(max_restarts=2)
        watchdog.persist()
        if not ok:
            state["status"] = "failed"
            state["step"] = "ensure_ableton"
            write_json(state_path, state)
            write_json(summary_path, {
                "run_id": run_id,
                "success": False,
                "reason": "Ableton process unavailable",
                "watchdog": watchdog.snapshot(),
            })
            return 2

    state["step"] = "test_chain"
    write_json(state_path, state)

    try:
        rc = run_test_script(root, args.song, args.artist, args.section, args.track)
    except KeyboardInterrupt:
        state["step"] = "interrupted"
        state["status"] = "failed"
        state["updated_at"] = datetime.now().isoformat()
        write_json(state_path, state)
        write_json(summary_path, {
            "run_id": run_id,
            "success": False,
            "return_code": 130,
            "reason": "Interrupted by user",
            "song": args.song,
            "artist": args.artist,
            "section": args.section,
            "track_index": args.track,
            "watchdog": watchdog.snapshot(),
        })
        return 130

    report_path = logs / "librarian_full_chain_test.json"
    report = {}
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            report = {"parse_error": True}

    # One automatic recovery retry for OSC bridge loss/timeouts in full/resume mode
    if (args.mode in {"full", "resume"}) and rc != 0 and report.get("failure_type") in {
        "osc_unreachable_preflight", "osc_lost_during_apply", "device_load_timeout", "jarvis_loader_unreachable_preflight"
    }:
        state["step"] = "recover_and_retry"
        write_json(state_path, state)
        watchdog.ensure_running(max_restarts=3)
        watchdog.persist()
        time.sleep(6)
        rc = run_test_script(root, args.song, args.artist, args.section, args.track)
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except Exception:
                report = {"parse_error": True}

    success = (rc == 0) and bool(report.get("success", False))

    state["step"] = "done"
    state["status"] = "success" if success else "failed"
    state["updated_at"] = datetime.now().isoformat()
    write_json(state_path, state)

    summary = {
        "run_id": run_id,
        "success": success,
        "return_code": rc,
        "song": args.song,
        "artist": args.artist,
        "section": args.section,
        "track_index": args.track,
        "watchdog": watchdog.snapshot(),
        "report_path": str(report_path),
    }
    write_json(summary_path, summary)

    print(json.dumps(summary, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
