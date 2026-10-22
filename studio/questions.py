"""Friction questions: one store, asked on two surfaces at once, the first answer wins.

data/telemetry/ux_questions.json is the one record: [{id, sig, question, evidence, status, answered_via, ...}].
status: waiting (caught, held until the take is over) -> open (on the Studio card and on his phone)
-> answered (fix / later / never, from desktop, voice or phone) or closed (the phone card expired).

The phone half is Life OS's Needs-you feed, which he already uses: an "ask" line in
~/.claude/channels/lifeos/events.jsonl becomes a card there plus a push. With "prompt" set, his tap
comes straight back as an "answer" line (agent.py /answer), never through agy. An answer on the
desktop writes a "close" line, so the phone card goes away. Only an open question takes an answer.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "telemetry" / "ux_questions.json"
LIFEOS = Path.home() / ".claude" / "channels" / "lifeos" / "events.jsonl"
# Life OS adds its own Later (a snooze on the phone only), so our "later" is labelled Not now there.
PHONE = {"Fix it now": "fix", "Not now": "later", "Never": "never"}
CLOSED_HERE = "answered in Live Pilot Studio"


class Questions:
    def __init__(self, store: Path | None = None, lifeos: Path | None = None):
        self.store = store or STORE
        self.lifeos = lifeos or LIFEOS
        self.pos = 0  # the first poll reads the whole log: a tap made while Studio was closed still counts
        try:
            self.items: list[dict] = json.loads(self.store.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.items = []

    def _save(self) -> None:
        self.store.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.items, indent=1, default=str), encoding="utf-8")
        tmp.replace(self.store)

    def _phone(self, ev: dict) -> None:
        """Only on a machine that has Life OS: never create its folder, or the next start thinks Life OS is here."""
        if not self.lifeos.parent.is_dir():
            return
        with self.lifeos.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({**ev, "ts": time.time()}, ensure_ascii=False) + "\n")

    def get(self, qid: str) -> dict | None:
        return next((q for q in self.items if q["id"] == qid), None)

    def open(self) -> dict | None:
        return next((q for q in self.items if q["status"] == "open"), None)

    def add(self, evidence: dict) -> None:
        self.items.append({"id": evidence["id"], "sig": evidence["sig"], "question": evidence["question"],
                           "evidence": evidence, "status": "waiting", "caught": time.time()})
        self._save()

    def ask_next(self) -> dict | None:
        """Opens the oldest waiting question on both surfaces. None if one is already open or none wait."""
        if self.open():
            return None
        q = next((q for q in self.items if q["status"] == "waiting"), None)
        if not q:
            return None
        q.update(status="open", asked=time.time(), ask_id=f"ask-lp-{q['id']}")
        self._phone({"kind": "ask", "id": q["ask_id"], "question": f"Live Pilot: {q['question']}",
                     "options": list(PHONE), "detail": "\n".join(q["evidence"].get("examples") or [])[:2000],
                     "prompt": "livepilot", "session_title": "Live Pilot"})
        self._save()
        return q

    def answer(self, qid: str, choice: str, via: str) -> dict | None:
        """Records the first answer to an open question; any later one (or one for another id) returns None."""
        q = self.get(qid)
        if not q or q["status"] != "open" or choice not in ("fix", "later", "never"):
            return None
        q.update(status="answered", choice=choice, answered_via=via, answered=time.time())
        if via != "phone":
            self._phone({"kind": "close", "ask_id": q["ask_id"], "why": CLOSED_HERE})
        self._save()
        return q

    def poll(self) -> list[tuple[str, str, str]]:
        """What happened on the phone since the last poll: [("answer", id, choice)] or [("closed", id, why)]."""
        try:
            size = self.lifeos.stat().st_size
            if size < self.pos:  # Life OS trimmed the log
                self.pos = 0
            with self.lifeos.open("rb") as fh:
                fh.seek(self.pos)
                chunk = fh.read()
        except OSError:
            return []
        chunk = chunk[:chunk.rfind(b"\n") + 1]  # a line still being written waits for the next poll
        self.pos += len(chunk)
        mine = {q["ask_id"]: q for q in self.items if q["status"] == "open"}
        out = []
        for raw in chunk.decode("utf-8", "ignore").splitlines():
            try:
                ev = json.loads(raw)
            except ValueError:
                continue
            q = mine.get(ev.get("ask_id"))
            if not q:
                continue
            if ev.get("kind") == "answer":  # a typed line closes the card too; it is not a yes, so it counts as Not now
                out.append(("answer", q["id"], PHONE.get(ev.get("choice"), "later")))
            elif ev.get("kind") == "close" and ev.get("why") != CLOSED_HERE:
                q.update(status="closed", closed=time.time(), why=ev.get("why", ""))
                self._save()
                out.append(("closed", q["id"], ev.get("why", "")))
            mine.pop(ev.get("ask_id"), None)  # first event per card wins
        return out
