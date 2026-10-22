"""What changed in his set while he was away: the card Studio shows when it opens.

Two real sources, nothing invented: set changes he asked for from his phone (events.jsonl) and Studio
builds that went live (a "Live now" ask whose job is a screen=studio round in improver.json).
Any read error gives no items; Studio must still open.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TURNS_LOG = ROOT / "data" / "telemetry" / "studio_turns.jsonl"  # rotated to studio_turns.1.jsonl at 5 MB
SEEN = ROOT / "data" / "telemetry" / "since_seen.json"
WEEK = 7 * 86400
LIVE_TOOLS = ("mcp__live-pilot__chain", "mcp__live-pilot__dial", "mcp__live-pilot__audition", "mcp__live-pilot__undo")
MAX_ITEMS = 3


def _lifeos() -> Path:
    return Path(os.environ.get("SINCE_LIFEOS_DIR") or Path.home() / ".claude" / "channels" / "lifeos")


def cutoff() -> float:
    """The last time he talked to Studio; a week ago when there is no record."""
    floor = time.time() - WEEK
    try:
        older = TURNS_LOG.with_name(f"{TURNS_LOG.stem}.1{TURNS_LOG.suffix}")
        lines = [ln for f in (older, TURNS_LOG) if f.is_file()
                 for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]
        last = json.loads(lines[-1])
        return max(float(last.get("done") or last["asked"]), floor)
    except Exception:
        return floor


def _clean(text: str) -> str:
    return text.replace("**", "").replace("`", "").strip()


def _sentences(text: str) -> list[str]:
    """Split at '. ', '! ', '? ' or a newline. A period inside 1.2s is not followed by a space, so it stays."""
    result = []
    for line in _clean(text).splitlines():
        line = line.strip()
        start = 0
        for i, ch in enumerate(line):
            if ch in ".!?" and i + 1 < len(line) and line[i + 1] == " ":
                result.append(line[start:i + 1].strip())
                start = i + 1
        if line[start:].strip():
            result.append(line[start:].strip())
    return result


def _say(text: str) -> str | None:
    flat = _clean(text)
    at = flat.lower().find("tell studio")
    if at < 0:
        return None
    rest = flat[at:]
    quotes = "\"“”"
    first = next((i for i, c in enumerate(rest) if c in quotes), -1)
    if first < 0:
        return None
    end = next((i for i in range(first + 1, len(rest)) if rest[i] in quotes), -1)
    if end < 0:
        return None
    phrase = rest[first + 1:end].strip().rstrip(".,!?;: ")
    return phrase[:60] or None


def _events(lifeos: Path) -> list[dict]:
    out = []
    for line in (lifeos / "events.jsonl").read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if isinstance(e, dict):
            out.append(e)
    return out


def _set_items(events: list[dict], after: float) -> list[dict]:
    labels: dict[str, list[tuple[int, str]]] = {}
    for n, e in enumerate(events):
        if e.get("kind") == "route":
            labels.setdefault(e.get("ask_id"), []).append((n, str(e.get("label") or "")))
    newest: dict[str, tuple[int, dict]] = {}
    for n, e in enumerate(events):
        if (e.get("kind") == "route" and e.get("state") == "done" and e.get("text") and e.get("ask_id")
                and float(e.get("ts") or 0) > after):
            prev = newest.get(e["ask_id"])
            if not prev or float(e["ts"]) >= float(prev[1]["ts"]):
                newest[e["ask_id"]] = (n, e)
    items = []
    for ask_id, (n, e) in newest.items():
        if not any(m != n and any(t in lab for t in LIVE_TOOLS) for m, lab in labels.get(ask_id, [])):
            continue
        parts = _sentences(e["text"])
        if not parts:
            continue
        items.append({"id": "set:" + ask_id, "kind": "set", "head": parts[0][:140],
                      "more": parts[1][:160] if len(parts) > 1 else "", "say": _say(e["text"]), "ts": float(e["ts"])})
    return items


def _studio_items(events: list[dict], lifeos: Path, after: float) -> list[dict]:
    data = json.loads((lifeos / "improver.json").read_text(encoding="utf-8"))
    jobs = {r["job"] for r in data.get("rounds", []) if r.get("screen") == "studio" and r.get("job")}
    items = []
    for e in events:
        q = str(e.get("question") or "")
        if e.get("kind") == "ask" and e.get("job") in jobs and q.startswith("Live now") and float(e.get("ts") or 0) > after:
            head = q.split(": ", 1)[1] if ": " in q else q
            items.append({"id": "studio:" + e["id"], "kind": "studio", "head": _clean(head).rstrip(".")[:140],
                          "more": "Studio got this update.", "say": None, "ts": float(e["ts"])})
    return items


def _seen() -> set[str]:
    try:
        return set(json.loads(SEEN.read_text(encoding="utf-8")))
    except Exception:
        return set()


def items(after: float) -> list[dict]:
    after = max(after, time.time() - WEEK)
    found: list[dict] = []
    try:
        lifeos = _lifeos()
        events = _events(lifeos)
        found += _set_items(events, after)
        try:
            found += _studio_items(events, lifeos, after)
        except Exception:
            pass
    except Exception:
        return []
    seen = _seen()
    return sorted((i for i in found if i["id"] not in seen), key=lambda i: -i["ts"])[:MAX_ITEMS]


def mark_seen(item_id: str) -> None:
    try:
        ids = sorted(_seen() | {str(item_id)})
        SEEN.parent.mkdir(parents=True, exist_ok=True)
        SEEN.write_text(json.dumps(ids), encoding="utf-8")
    except Exception:
        pass
