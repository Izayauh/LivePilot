"""JarvisDeviceLoader place_in_arrangement against a fake Live with the 2026-10-20 bug.

Unwarped audio markers are in seconds. Live left a 40-bar (66.67 s at 144 BPM) stem with an
auto start marker at 2 s and a stale end, so it started late and stopped at bar 25.
"""

import importlib
import sys
import types

import pytest

TEMPO = 144.0
FILE_SECONDS = 160 * 60.0 / TEMPO  # 40 bars of 4/4


class FakeClip:
    is_audio_clip = True

    def __init__(self, sticky=False):
        self.warping, self.looping = True, True
        self.sample_length, self.sample_rate = int(FILE_SECONDS * 48000), 48000.0
        self.file_path = r"C:\stems\long.wav"
        self.sticky = sticky  # a Live that ignores marker writes
        self._start, self._end = 2.0, 40.0
        self.loop_start, self.loop_end = 2.0, 40.0
        self.start_time = self.end_time = 0.0

    @property
    def start_marker(self):
        return self._start

    @start_marker.setter
    def start_marker(self, v):
        if not self.sticky:
            if v >= self._end:
                raise RuntimeError("start must be before end")
            self._start = v

    @property
    def end_marker(self):
        return self._end

    @end_marker.setter
    def end_marker(self, v):
        if not self.sticky:
            if v <= self._start:
                raise RuntimeError("end must be after start")
            self._end = v
        self._place()

    def _place(self):
        self.end_time = self.start_time + (self._end - self._start) * TEMPO / 60.0


class FakeTrack:
    def __init__(self, clip):
        self.clip_slots = [types.SimpleNamespace(has_clip=True, clip=clip)]
        self.arrangement_clips = []

    def delete_clip(self, c):
        self.arrangement_clips.remove(c)

    def duplicate_clip_to_arrangement(self, clip, beat):
        c = FakeClip(clip.sticky)
        c.warping, c._start, c._end = clip.warping, clip._start, clip._end
        c.start_time = beat
        c._place()
        self.arrangement_clips.append(c)


@pytest.fixture
def loader(monkeypatch):
    monkeypatch.setitem(sys.modules, "Live", types.ModuleType("Live"))
    mod = importlib.import_module("ableton_remote_script.JarvisDeviceLoader")
    return mod


def place(mod, clip, args):
    surface = object.__new__(mod.JarvisDeviceLoader)
    track = FakeTrack(clip)
    surface._ext_track = lambda i: (types.SimpleNamespace(tempo=TEMPO), track)
    out = {}

    def run(_addr, _resp, fn):
        try:
            out["result"] = fn()
        except Exception as exc:
            out["error"] = str(exc)
    surface._run_main = run
    surface._handle_place_in_arrangement(args, None)
    return out, track


def test_unwarped_long_file_is_placed_whole(loader):
    out, track = place(loader, FakeClip(), [0, 0, 16.0, 0, 1])
    res = out["result"]
    assert res["start_marker"] == 0.0
    assert res["end_time"] == pytest.approx(16.0 + 160.0)  # bar 5 to bar 45, not bar 25
    assert res["file_seconds"] == pytest.approx(FILE_SECONDS)
    assert len(track.arrangement_clips) == 1


def test_unwarped_mismatch_is_refused_and_removed(loader):
    out, track = place(loader, FakeClip(sticky=True), [0, 0, 0.0, 0, 1])
    assert "Place it warped" in out["error"]
    assert track.arrangement_clips == []


def test_warped_end_beat_still_applies(loader):
    clip = FakeClip()
    out, _track = place(loader, clip, [0, 0, 0.0, 1, 1, 64.0])
    assert clip.end_marker == 64.0 and clip.loop_end == 64.0
    assert out["result"]["file_seconds"] is None
