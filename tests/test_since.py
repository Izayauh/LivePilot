import json
import time

import pytest

from studio import since

NOW = time.time()
TEXT = ("Your hummed bass is now a real bass. It's on a new track called \"Bass from hum\" with an Upright Bass "
        "sound loaded, and the set is saved. Play from bar 4 and tell Studio \"try a different bass\" if it "
        "doesn't fit.\n\n- **The reopen is no longer needed.** Live had been closed.")


def lines(*events):
    return "\n".join(json.dumps(e) if isinstance(e, dict) else e for e in events) + "\n"


def route(ask, state, label, ts, text=None):
    e = {"kind": "route", "ask_id": ask, "state": state, "label": label, "ts": ts}
    if text:
        e["text"] = text
    return e


@pytest.fixture
def env(tmp_path, monkeypatch):
    life = tmp_path / "lifeos"
    life.mkdir()
    monkeypatch.setenv("SINCE_LIFEOS_DIR", str(life))
    monkeypatch.setattr(since, "TURNS_LOG", tmp_path / "studio_turns.jsonl")
    monkeypatch.setattr(since, "SEEN", tmp_path / "since_seen.json")
    (life / "improver.json").write_text(json.dumps({"rounds": []}), encoding="utf-8")

    def write(*events, rounds=None):
        (life / "events.jsonl").write_text(lines(*events), encoding="utf-8")
        if rounds is not None:
            (life / "improver.json").write_text(json.dumps({"rounds": rounds}), encoding="utf-8")
    return write


def set_events(label="mcp__live-pilot__chain", ts=NOW - 3600):
    return [{"kind": "ask", "id": "ask-z7st9m", "question": "q", "ts": ts - 10},
            route("ask-z7st9m", "working", label, ts - 5),
            route("ask-z7st9m", "done", "Done", ts, TEXT)]


def test_set_item_exact(env):
    env("not json", *set_events())
    [it] = since.items(NOW - 86400)
    assert it["id"] == "set:ask-z7st9m" and it["kind"] == "set"
    assert it["head"] == "Your hummed bass is now a real bass."
    assert it["more"] == "It's on a new track called \"Bass from hum\" with an Upright Bass sound loaded, and the set is saved."
    assert it["say"] == "try a different bass"


def test_read_only_labels_not_shown(env):
    env(*set_events(label="mcp__live-pilot__session"), route("ask-z7st9m", "working", "rack check get_x", NOW))
    assert since.items(NOW - 86400) == []


def test_before_cutoff_hidden_and_missing_turns_falls_back_to_a_week(env):
    env(*set_events(ts=NOW - 7200))
    assert since.items(NOW - 3600) == []
    assert not since.TURNS_LOG.exists()
    assert abs(since.cutoff() - (time.time() - 7 * 86400)) < 5
    assert len(since.items(since.cutoff())) == 1
    env(*set_events(ts=NOW - 8 * 86400))
    assert since.items(since.cutoff()) == []


def test_cutoff_uses_done_then_asked(env):
    since.TURNS_LOG.write_text(json.dumps({"asked": NOW - 500, "done": NOW - 400}) + "\n", encoding="utf-8")
    assert since.cutoff() == NOW - 400
    since.TURNS_LOG.write_text(json.dumps({"asked": NOW - 500}) + "\n", encoding="utf-8")
    assert since.cutoff() == NOW - 500


def test_mark_seen_hides_and_items_never_writes(env):
    env(*set_events())
    since.items(NOW - 86400)
    assert not since.SEEN.exists()
    since.mark_seen("set:ask-z7st9m")
    assert since.items(NOW - 86400) == []
    assert json.loads(since.SEEN.read_text()) == ["set:ask-z7st9m"]


def live_ask(job, ts=NOW - 60):
    return {"kind": "ask", "id": "ask-test01", "question": "Live now, test it: Studio opens on what changed.", "job": job, "ts": ts}


def test_studio_item(env):
    env(live_ask("improve-t-1"), rounds=[{"id": "t", "screen": "studio", "job": "improve-t-1"}])
    [it] = since.items(NOW - 86400)
    assert it["id"] == "studio:ask-test01" and it["kind"] == "studio"
    assert it["head"] == "Studio opens on what changed" and it["say"] is None


def test_non_studio_round_not_shown(env):
    env(live_ask("improve-t-1"), rounds=[{"id": "t", "screen": "other", "job": "improve-t-1"}])
    assert since.items(NOW - 86400) == []


def test_decimal_is_not_a_sentence_end():
    assert since._sentences("It took 1.2s to load. Done.") == ["It took 1.2s to load.", "Done."]


def test_bad_files_give_nothing(env):
    assert since.items(NOW - 86400) == []


def test_cutoff_reads_the_rotated_log_too(env):
    older = since.TURNS_LOG.with_name("studio_turns.1.jsonl")
    older.write_text(json.dumps({"asked": NOW - 900, "done": NOW - 800}) + "\n", encoding="utf-8")
    assert since.cutoff() == NOW - 800  # the live file is not there yet: the rotated one still counts
    since.TURNS_LOG.write_text(json.dumps({"asked": NOW - 300, "done": NOW - 200}) + "\n", encoding="utf-8")
    assert since.cutoff() == NOW - 200  # the live file is newer, so it wins
