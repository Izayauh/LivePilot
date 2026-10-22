"""Per-call telemetry and an optional call/token budget for the MCP server.

Every MCP tool call appends one line to data/telemetry/calls.jsonl:
{ts, session, tool, fn, ok, ms, reply_tokens, error}. reply_tokens is the
reply size / 4, the part of a call's cost this server controls. The model's
own reasoning tokens are not visible here.

One MCP server process lives as long as one Claude session, so the budget and
the "this session" counters are per session.
"""

from __future__ import annotations

import json
import statistics
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from livepilot_tools import friction

REPO_ROOT = Path(__file__).resolve().parents[1]
CALLS_PATH = REPO_ROOT / "data" / "telemetry" / "calls.jsonl"
SESSION = uuid.uuid4().hex[:8]

# Tools that never count against or get blocked by the budget.
EXEMPT = {"usage", "set_budget", "undo"}

_budget: dict[str, int | None] = {"max_calls": None, "max_tokens": None}
_used = {"calls": 0, "tokens": 0}


def reply_tokens(result: Any) -> int:
    try:
        return len(json.dumps(result, default=str)) // 4
    except Exception:
        return 0


def set_budget(max_calls: int | None = None, max_tokens: int | None = None) -> dict:
    _budget["max_calls"] = max_calls
    _budget["max_tokens"] = max_tokens
    _used["calls"] = 0
    _used["tokens"] = 0
    limits = [f"{max_calls} calls" if max_calls else None, f"~{max_tokens} reply tokens" if max_tokens else None]
    text = " / ".join(x for x in limits if x) or "no limit"
    return {"success": True, "summary": f"Budget set: {text}. Counters reset."}


def over_budget(tool: str) -> dict | None:
    if tool in EXEMPT:
        return None
    mc, mt = _budget["max_calls"], _budget["max_tokens"]
    if (mc and _used["calls"] >= mc) or (mt and _used["tokens"] >= mt):
        return {"success": False, "budget_exceeded": True,
                "message": f"Live Pilot budget reached ({_used['calls']} calls, ~{_used['tokens']} reply tokens). "
                           "Stop and tell the user what is done; they can raise it with set_budget."}
    return None


def record(tool: str, fn: str | None, result: Any, started: float) -> None:
    ok = bool(result.get("success", True)) if isinstance(result, dict) else True
    toks = reply_tokens(result)
    if tool not in EXEMPT:
        _used["calls"] += 1
        _used["tokens"] += toks
    row = {"ts": round(time.time(), 3), "session": SESSION, "tool": tool, "fn": fn or tool, "ok": ok,
           "ms": round((time.perf_counter() - started) * 1000), "reply_tokens": toks}
    played = friction.played_ms(fn or tool, result)
    if played is not None:
        row["played_ms"] = played
    if not ok and isinstance(result, dict):
        row["error"] = str(result.get("message") or result.get("error") or "")[:200]
    try:
        CALLS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CALLS_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:
        pass  # telemetry must never break a call


def _rows(days: float) -> list[dict]:
    if not CALLS_PATH.exists():
        return []
    cutoff = time.time() - days * 86400
    out = []
    for line in CALLS_PATH.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("ts", 0) >= cutoff:
            out.append(row)
    return out


def report(days: float = 7) -> dict:
    """Reliability and reply-token cost per function, plus this session's totals."""
    rows = _rows(days)
    by_fn: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_fn[r["fn"]].append(r)
    table = []
    for fn, rs in sorted(by_fn.items(), key=lambda kv: -len(kv[1])):
        fails = sum(1 for r in rs if not r["ok"])
        table.append({"fn": fn, "calls": len(rs), "fail_pct": round(100 * fails / len(rs), 1),
                      "avg_tokens": round(statistics.mean(r["reply_tokens"] for r in rs)),
                      "p50_ms": round(statistics.median(r["ms"] for r in rs))})
    errors: dict[str, int] = defaultdict(int)
    for r in rows:
        if not r["ok"]:
            errors[f"{r['fn']}: {r.get('error', '')[:90]}"] += 1
    total = len(rows)
    fails = sum(1 for r in rows if not r["ok"])
    sessions = {r["session"] for r in rows}
    return {
        "success": True,
        "days": days,
        "summary": (f"{total} calls in {len(sessions)} sessions, {100 * fails / total:.1f}% failed, "
                    f"~{sum(r['reply_tokens'] for r in rows)} reply tokens" if total else "No calls recorded yet."),
        "this_session": {"calls": _used["calls"], "reply_tokens": _used["tokens"], "budget": dict(_budget)},
        "by_function": table[:20],
        "top_errors": sorted(errors.items(), key=lambda kv: -kv[1])[:5],
    }


if __name__ == "__main__":
    import sys

    print(json.dumps(report(float(sys.argv[1]) if len(sys.argv) > 1 else 7), indent=2))
