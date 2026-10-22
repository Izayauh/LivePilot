"""Load, search and grow the diagnostic playbook."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

ENTRIES = Path(__file__).resolve().parent / "entries.json"

# Words that should pull an entry even when the caller phrases it loosely.
ALIASES = {
    "muddy": "mud", "boxy": "mud", "boomy": "mud",
    "harsh": "harsh", "brittle": "harsh", "piercing": "harsh",
    "thin": "phone", "quiet": "phone", "small": "phone",
    "phone": "phone", "tiktok": "phone", "shorts": "phone", "short-form": "phone",
    "record": "record", "arm": "record", "overwrite": "record", "destroy": "record",
    "hook": "hook", "chorus": "hook", "clip": "hook",
    "stall": "automation", "hang": "automation", "dialog": "automation",
    "wrong": "unreliable", "lying": "unreliable", "disagree": "unreliable",
}


def load_entries() -> List[Dict[str, Any]]:
    with open(ENTRIES, encoding="utf-8") as f:
        return json.load(f)


def _tokens(s: str) -> set:
    return {t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if t}


def _blob(e: Dict[str, Any]) -> str:
    return json.dumps(e, ensure_ascii=False).lower()


def search(query: str, limit: int = 3) -> List[Dict[str, Any]]:
    """Rank entries against a loosely phrased problem description."""
    q = _tokens(query)
    q |= {ALIASES[t] for t in list(q) if t in ALIASES}
    scored = []
    for e in load_entries():
        blob = _blob(e)
        score = sum(1 for t in q if t in blob)
        score += 3 * sum(1 for t in q if t in e["id"].lower())
        score += 2 * sum(1 for t in q if t in e["symptom"].lower())
        if score:
            scored.append((score, e))
    scored.sort(key=lambda x: -x[0])
    return [e for _, e in scored[:limit]]


def get_entry(entry_id: str) -> Optional[Dict[str, Any]]:
    for e in load_entries():
        if e["id"] == entry_id:
            return e
    return None


def record_finding(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Append a new lesson. Refuses anything without evidence.

    An entry with no measured evidence is an opinion, and opinions are what the
    playbook exists to replace.
    """
    required = ("id", "symptom", "why", "fix", "evidence")
    missing = [k for k in required if not entry.get(k)]
    if missing:
        return {"success": False, "message": "missing required fields: " + ", ".join(missing)}
    entries = load_entries()
    if any(e["id"] == entry["id"] for e in entries):
        return {"success": False, "message": "id already exists: " + entry["id"]}
    entry.setdefault("added", date.today().isoformat())
    entry.setdefault("applies_to", [])
    entries.append(entry)
    with open(ENTRIES, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return {"success": True, "id": entry["id"], "count": len(entries)}


def brief(query: Optional[str] = None) -> str:
    """Compact text an agent can read before touching audio."""
    entries = search(query, limit=4) if query else load_entries()
    out = []
    for e in entries:
        fix = e.get("fix", {})
        out.append(
            "## {id}\nSYMPTOM: {sym}\nDETECT: {det}\nWHY: {why}\nFIX: {fix}\nVERIFY: {ver}\nEVIDENCE: {ev}".format(
                id=e["id"], sym=e["symptom"],
                det=(e.get("detect") or {}).get("method", "-"),
                why=e.get("why", "-"),
                fix=fix.get("principle", "-") if isinstance(fix, dict) else str(fix),
                ver=e.get("verify", "-"), ev=e.get("evidence", "-")))
    return "\n\n".join(out)
