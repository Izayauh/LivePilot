"""Friction: what makes Isaiah stop, spotted the same way live and nightly.

One copy of the rules. Studio runs LiveDetector after every tool call and ear
turn and asks him in the moment (Fix it now / Later / Never). The nightly
scripts/ux_analyzer.py ranks whatever is left over a week.

  ux_ignore.json   signatures he answered Never to; neither side raises them again
  ux_fixes.jsonl   his answers, and what each live fix changed, so the nightly
                   report can say whether a fixed problem came back
"""
from __future__ import annotations

import json
import re
import statistics
import time
import uuid
from collections import Counter, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEL = ROOT / "data" / "telemetry"
CALLS = TEL / "calls.jsonl"
IGNORE = TEL / "ux_ignore.json"
FIXES = TEL / "ux_fixes.jsonl"

GAP_S = 30 * 60          # silence longer than this starts a new sitting
SLOW_MS = 15_000         # nightly: a function whose median wait is past this is a bottleneck
REALTIME = {"bounce"}    # plays and records `seconds` of audio on purpose; only the wait past that is friction

POSITIVE = re.compile(r"\b(fire|love (it|that)|that'?s (it|hard|crazy|perfect)|perfect|hell yeah|sounds (good|great|clean)|nice)\b", re.I)
NEGATIVE = re.compile(r"\b(annoying|frustrat\w*|broken|not working|doesn'?t work|didn'?t work|why (is|did|won'?t)|ignoring|disregard\w*|stuck|wasting|ugh|come on|you'?re not)\b", re.I)
EAR_CHECK = re.compile(r"\b(can you hear|are you (there|listening)|did you (hear|get) that|hello\??$)", re.I)

EAR_IGNORED = "ear: ignored him and he had to check it heard"
SAID_FRUSTRATED = "said: frustrated, nothing had failed"


def jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def signature(fn: str, error: str) -> str:
    e = re.sub(r"'[^']*'|\"[^\"]*\"", "'…'", error or "unknown")
    # "Room Size raw range..." and "Speed raw range..." are one problem, not two.
    e = re.sub(r"^[\w ]+?(?= raw range| cannot reach| options:)", "<param>", e)
    e = re.sub(r"-?\d+(\.\d+)?", "N", e)
    return f"{fn}: {e.split('.')[0][:80]}"


def slow_signature(fn: str) -> str:
    return f"{fn}: slow"


def played_ms(fn: str, result) -> int | None:
    """Playback a real-time call sits through on purpose (one take; a retry's second take still counts as wait)."""
    s = result.get("seconds") if fn in REALTIME and isinstance(result, dict) else None
    return round(float(s) * 1000) if isinstance(s, (int, float)) else None


def wait_ms(fn: str, ms: int, played: int | None) -> int | None:
    """The part of a call's time that is friction. None for a real-time call logged without
    played_ms (calls.jsonl before 2026-10-21): its playback length is unknown, so it cannot be judged."""
    if fn not in REALTIME:
        return ms
    return None if played is None else ms - played


def ignored() -> set[str]:
    try:
        return set(json.loads(IGNORE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def ignore(sig: str) -> None:
    IGNORE.parent.mkdir(parents=True, exist_ok=True)
    IGNORE.write_text(json.dumps(sorted(ignored() | {sig}), indent=2), encoding="utf-8")


def log_fix(row: dict) -> None:
    FIXES.parent.mkdir(parents=True, exist_ok=True)
    with FIXES.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": round(time.time(), 3), **row}, default=str) + "\n")


def applied_fixes() -> list[dict]:
    return [r for r in jsonl(FIXES) if r.get("applied")]


def typical_ms(days: float = 30, min_calls: int = 5) -> dict[str, float]:
    """Median wait (ms past any playback) of successful calls per function, from calls.jsonl."""
    cutoff = time.time() - days * 86400
    by_fn: dict[str, list[float]] = {}
    for r in jsonl(CALLS):
        if r.get("ts", 0) >= cutoff and r.get("ok") and r.get("ms"):
            fn = r.get("fn") or r.get("tool")
            w = wait_ms(fn, r["ms"], r.get("played_ms"))
            if w is not None:
                by_fn.setdefault(fn, []).append(w)
    return {fn: statistics.median(ms) for fn, ms in by_fn.items() if len(ms) >= min_calls}


def _nth(n: int) -> str:
    return {2: "second", 3: "third", 4: "fourth", 5: "fifth"}.get(n, f"{n}th")


class LiveDetector:
    """Watches one Studio run. on_call and on_turn return a question worth asking, or None.

    Triggers: the same error twice in a row or three times in a sitting; a call far
    past its usual time; the ear ignoring him and him checking it heard; him saying
    something like "this is annoying". At most one question per signature per sitting.
    """

    def __init__(self, medians: dict[str, float] | None = None, skip: set[str] | None = None):
        self.medians = typical_ms() if medians is None else medians
        self.skip = ignored() if skip is None else skip
        self.calls: deque[dict] = deque(maxlen=12)
        self.turns: deque[dict] = deque(maxlen=6)
        self._reset()
        self.last_ts = 0.0

    def _reset(self) -> None:
        self.counts: Counter[str] = Counter()
        self.examples: dict[str, list[str]] = {}
        self.asked: set[str] = set()
        self.prev_sig, self.run = None, 0

    def _tick(self, now: float) -> None:
        if self.last_ts and now - self.last_ts > GAP_S:
            self._reset()
        self.last_ts = now

    def on_call(self, fn: str, args: dict, result: dict, ms: int, now: float | None = None) -> dict | None:
        now = now or time.time()
        self._tick(now)
        ok = bool(result.get("success", True))
        error = "" if ok else str(result.get("message") or result.get("error") or "")[:300]
        self.calls.append({"fn": fn, "args": args, "ok": ok, "ms": ms, "error": error})
        if ok:
            self.prev_sig, self.run = None, 0
            med = self.medians.get(fn)
            w = wait_ms(fn, ms, played_ms(fn, result))
            if med and w is not None and w >= max(3 * med, med + 5000):
                return self._flag(slow_signature(fn), f"{fn} took {w / 1000:.0f} s; it usually takes "
                                  f"{med / 1000:.1f} s. Want me to look at why?", f"{w} ms vs median {med:.0f} ms")
            return None
        sig = signature(fn, error)
        self.counts[sig] += 1
        self.run = self.run + 1 if sig == self.prev_sig else 1
        self.prev_sig = sig
        ex = self.examples.setdefault(sig, [])
        if len(ex) < 2 and error not in ex:
            ex.append(error)
        n = self.counts[sig]
        if self.run >= 2 or n >= 3:
            return self._flag(sig, f"That's the {_nth(n)} time {fn} failed the same way: {error[:90]}. Fix it now?",
                              *self.examples[sig])
        return None

    def on_turn(self, heard: str, reply: str, now: float | None = None) -> dict | None:
        now = now or time.time()
        self._tick(now)
        prev = self.turns[-1] if self.turns else None
        self.turns.append({"heard": heard, "reply": reply})
        if prev and prev["reply"] == "(ignored)" and (EAR_CHECK.search(heard) or NEGATIVE.search(heard)):
            return self._flag(EAR_IGNORED, "I tuned out your last line and you had to check I heard you. "
                              "Want me to fix how I decide what's for me?", f"heard {prev['heard'][:70]!r}, then {heard[:70]!r}")
        if NEGATIVE.search(heard):
            failed = next((c for c in reversed(list(self.calls)[-5:]) if not c["ok"]), None)
            if failed:
                sig = signature(failed["fn"], failed["error"])
                return self._flag(sig, f"You said {heard[:60]!r} right after {failed['fn']} failed: "
                                  f"{failed['error'][:80]}. Fix it now?", failed["error"], f"he said {heard[:120]!r}")
            return self._flag(SAID_FRUSTRATED, f"You said {heard[:60]!r}. Want me to look at what just happened?",
                              f"he said {heard[:120]!r}")
        return None

    def _flag(self, sig: str, question: str, *examples: str) -> dict | None:
        if sig in self.skip or sig in self.asked:
            return None
        self.asked.add(sig)
        return {"id": uuid.uuid4().hex[:8], "sig": sig, "question": question, "examples": list(examples),
                "recent_calls": list(self.calls), "recent_turns": list(self.turns), "ts": time.time()}
