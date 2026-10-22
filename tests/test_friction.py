"""Live friction detector: when Studio should stop and ask him."""
from livepilot_tools import friction
from livepilot_tools.friction import EAR_IGNORED, SAID_FRUSTRATED, LiveDetector, signature

WARP = "Warping is only available for Audio Clips"


def det(**kw):
    return LiveDetector(medians=kw.get("medians", {}), skip=kw.get("skip", set()))


def fail(d, fn="place_in_arrangement", error=WARP, now=1000.0):
    return d.on_call(fn, {}, {"success": False, "message": error}, 50, now=now)


def test_same_error_twice_in_a_row_asks_once():
    d = det()
    assert fail(d) is None
    q = fail(d)
    assert q and q["sig"] == signature("place_in_arrangement", WARP)
    assert "second time" in q["question"] and q["question"].endswith("Fix it now?")
    assert fail(d) is None  # once per signature per sitting


def test_three_in_a_sitting_even_when_not_in_a_row():
    d = det()
    ok = {"success": True}
    assert fail(d) is None
    d.on_call("dial", {}, ok, 50, now=1001)
    assert fail(d, now=1002) is None
    d.on_call("dial", {}, ok, 50, now=1003)
    assert fail(d, now=1004)["question"].startswith("That's the third time")


def test_never_list_is_skipped():
    d = det(skip={signature("place_in_arrangement", WARP)})
    fail(d)
    assert fail(d) is None


def test_new_sitting_resets_and_can_ask_again():
    d = det()
    fail(d, now=0 + 1)
    assert fail(d, now=2)
    fail(d, now=2 + friction.GAP_S + 1)
    assert fail(d, now=2 + friction.GAP_S + 2)


def test_slow_call_far_past_its_median():
    d = det(medians={"bounce": 6_000})
    assert d.on_call("bounce", {}, {"success": True, "seconds": 23.0}, 40_000) is None
    q = d.on_call("bounce", {}, {"success": True, "seconds": 23.0}, 95_000)
    assert q["sig"] == "bounce: slow"


def test_bounce_playback_is_not_friction():
    # 16 bars at 70 BPM plays 56 s; only the 4 s around it is wait.
    d = det(medians={"bounce": 5_000, "dial": 400})
    assert d.on_call("bounce", {}, {"success": True, "seconds": 56.0}, 60_000) is None
    assert friction.wait_ms("bounce", 60_000, None) is None  # old rows without played_ms are not judged
    assert friction.wait_ms("dial", 900, None) == 900
    assert friction.played_ms("dial", {"seconds": 3}) is None


def test_retry_take_still_counts_as_wait():
    d = det(medians={"bounce": 5_000})
    q = d.on_call("bounce", {}, {"success": True, "seconds": 31.0, "retried": ["silent"]}, 69_000)
    assert q and q["sig"] == "bounce: slow"


def test_ear_ignored_then_he_checks():
    d = det()
    assert d.on_turn("turn the bass down", "(ignored)") is None
    assert d.on_turn("can you hear me", "Yes.")["sig"] == EAR_IGNORED


def test_spoken_negative_blames_the_last_failure():
    d = det()
    fail(d)
    q = d.on_turn("this is so annoying", "Sorry.")
    assert q["sig"] == signature("place_in_arrangement", WARP)


def test_spoken_negative_with_nothing_failed():
    d = det()
    assert d.on_turn("ugh come on", "Okay.")["sig"] == SAID_FRUSTRATED


def test_question_carries_evidence_for_the_fix_agent():
    d = det()
    fail(d)
    q = fail(d)
    assert q["examples"] == [WARP] and len(q["recent_calls"]) == 2 and q["id"]
