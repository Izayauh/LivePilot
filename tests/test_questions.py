"""The friction question store: open on both surfaces, the first answer wins, the other surface clears."""

import json

from studio.questions import CLOSED_HERE, Questions


def flagged(qid="q1", sig="err:dial:x"):
    return {"id": qid, "sig": sig, "question": "dial failed twice. Fix it now?", "examples": ["dial -> boom"]}


def lines(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def phone_says(path, ev):
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(ev) + "\n")


def make(tmp_path):
    return Questions(tmp_path / "ux_questions.json", tmp_path / "events.jsonl"), tmp_path / "events.jsonl"


def test_open_goes_to_the_phone_once(tmp_path):
    qs, log = make(tmp_path)
    qs.add(flagged("q1"))
    qs.add(flagged("q2", "err:chain:y"))
    q = qs.ask_next()
    assert q["id"] == "q1" and qs.ask_next() is None  # one open at a time
    (ask,) = lines(log)
    assert ask["kind"] == "ask" and ask["id"] == "ask-lp-q1" and ask["prompt"] == "livepilot"
    assert ask["options"] == ["Fix it now", "Not now", "Never"]


def test_desktop_answer_wins_and_clears_the_phone(tmp_path):
    qs, log = make(tmp_path)
    qs.add(flagged())
    qs.ask_next()
    assert qs.answer("q1", "fix", "desktop")["answered_via"] == "desktop"
    assert lines(log)[-1] == {**lines(log)[-1], "kind": "close", "ask_id": "ask-lp-q1", "why": CLOSED_HERE}
    phone_says(log, {"kind": "answer", "ask_id": "ask-lp-q1", "choice": "Never"})  # a late tap
    assert qs.poll() == []
    assert qs.answer("q1", "never", "phone") is None
    assert qs.get("q1")["choice"] == "fix"


def test_phone_answer_comes_back(tmp_path):
    qs, log = make(tmp_path)
    qs.add(flagged())
    qs.ask_next()
    phone_says(log, {"kind": "answer", "ask_id": "ask-lp-q1", "choice": "Fix it now"})
    assert qs.poll() == [("answer", "q1", "fix")]
    qs.answer("q1", "fix", "phone")
    assert [e["kind"] for e in lines(log)] == ["ask", "answer"]  # no close line: Life OS already closed it
    assert qs.poll() == []


def test_typed_line_and_expiry(tmp_path):
    qs, log = make(tmp_path)
    qs.add(flagged("q1"))
    qs.ask_next()
    phone_says(log, {"kind": "answer", "ask_id": "ask-lp-q1", "choice": "hmm not sure"})
    assert qs.poll() == [("answer", "q1", "later")]
    qs.answer("q1", "later", "phone")
    qs.add(flagged("q2", "err:chain:y"))
    qs.ask_next()
    phone_says(log, {"kind": "close", "ask_id": "ask-lp-q2", "why": "older than 8 hours"})
    assert qs.poll() == [("closed", "q2", "older than 8 hours")]
    assert qs.get("q2")["status"] == "closed"


def test_no_life_os_writes_nothing(tmp_path):
    lifeos = tmp_path / "channels" / "lifeos" / "events.jsonl"
    qs = Questions(tmp_path / "ux_questions.json", lifeos)
    qs.add(flagged())
    assert qs.ask_next()["id"] == "q1"
    assert qs.answer("q1", "fix", "desktop")["choice"] == "fix"
    assert not (tmp_path / "channels").exists()  # no folder made, so config.phone_dir() stays None
    assert qs.poll() == []


def test_a_tap_while_studio_was_closed_still_counts(tmp_path):
    qs, log = make(tmp_path)
    qs.add(flagged())
    qs.ask_next()
    phone_says(log, {"kind": "answer", "ask_id": "ask-lp-q1", "choice": "Never"})
    again = Questions(tmp_path / "ux_questions.json", log)  # Studio relaunched
    assert again.open()["id"] == "q1"
    assert again.poll() == [("answer", "q1", "never")]
