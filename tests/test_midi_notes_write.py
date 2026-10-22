"""add_clip_notes is one lp_notes_write call, verifies the whole clip, and keeps replies small."""

from livepilot_tools.midi_tools import add_clip_notes


class FakeClip:
    def __init__(self, notes):
        self.notes = [list(n) for n in notes]
        self.calls = 0

    def send(self, cmd, params, timeout=5.0):
        assert cmd == "lp_notes_write"
        self.calls += 1
        before = [list(n) for n in self.notes]
        if params["mode"] == "replace":
            self.notes = []
        self.notes += [list(n) for n in params["notes"]]
        return {"success": True, "before": before, "after": [list(n) for n in self.notes]}


NOTE = {"pitch": 60, "start_time": 0.0, "duration": 0.5, "velocity": 100}


def test_replace_is_one_call_and_verified():
    clip = FakeClip([[40, 1.0, 1.0, 90, 0]])
    res = add_clip_notes(0, 0, [NOTE], send=clip.send)
    assert res["success"] and res["verified"] and clip.calls == 1
    assert clip.notes == [[60, 0.0, 0.5, 100.0, 0]]
    assert "readback" not in res  # small reply when it worked


def test_append_keeps_existing_notes():
    clip = FakeClip([[40, 1.0, 1.0, 90, 0]])
    res = add_clip_notes(0, 0, [NOTE], mode="append", send=clip.send)
    assert res["verified"] and res["expected_count"] == 2


def test_mismatch_is_not_verified_and_shows_readback():
    def dropping_send(cmd, params, timeout=5.0):
        return {"success": True, "before": [], "after": []}  # Live dropped the notes

    res = add_clip_notes(0, 0, [NOTE], send=dropping_send)
    assert not res["success"] and res["readback"] == []


def test_live_error_is_a_plain_failure():
    res = add_clip_notes(0, 0, [NOTE], send=lambda *a, **k: {"success": False, "message": "No clip in slot 0"})
    assert not res["success"] and "No clip" in res["message"]
