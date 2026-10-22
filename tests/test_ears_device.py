"""The mic setting is used, and a missing, unplugged or silenced mic is said out loud instead of crashing."""

import queue
import types

import numpy as np
import pytest

from studio import config, ears


class PortAudioError(Exception):
    pass


class Stream:
    def __init__(self, **kw):
        self.kw = kw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_sd(monkeypatch, devices, default_index):
    opened = []

    def query_devices(device=None, kind=None):
        if kind != "input":
            return devices
        index = default_index if device is None else device
        if index is None:
            raise PortAudioError("Error querying device -1")
        return {**devices[index], "default_samplerate": float(ears.RATE)}

    def input_stream(**kw):
        opened.append(kw)
        return Stream(**kw)

    monkeypatch.setattr(ears, "sd", types.SimpleNamespace(
        query_devices=query_devices, InputStream=input_stream, PortAudioError=PortAudioError))
    return opened


@pytest.fixture
def listener(monkeypatch):
    """An Ears without the speech models: VAD always hears nothing, states are recorded with the message."""
    monkeypatch.setattr(ears, "DEAD_S", 0.05)
    monkeypatch.setattr(config, "mic", lambda: "")
    e = ears.Ears.__new__(ears.Ears)
    e.muted = e.talking = e.silent_input = False
    e.device_name = e.error = ""
    e.states = []
    e.on_state = lambda s: e.states.append((s, e.error))
    e.on_text = lambda *a: None
    e._frames, e._jobs = queue.Queue(), queue.Queue()
    e._vad = types.SimpleNamespace(run=lambda names, feed: (np.zeros((1, 1)), feed["state"]))
    return e


MICS = [{"name": "Speakers", "max_input_channels": 0}, {"name": "Analogue 1/2 (Audient iD14)", "max_input_channels": 2}]


def test_no_microphone_is_an_error_not_a_crash(listener, monkeypatch):
    _fake_sd(monkeypatch, MICS[:1], None)
    listener._listen()  # returns instead of raising into the crash box
    assert listener.states == [("error", ears.NO_MIC)]
    assert "Plug one in" in listener.error and "reopen" in listener.error


def test_mic_setting_picks_the_device(listener, monkeypatch):
    opened = _fake_sd(monkeypatch, MICS, None)
    monkeypatch.setattr(config, "mic", lambda: "audient")
    listener._listen()
    assert opened[0]["device"] == 1 and listener.device_name == "Analogue 1/2 (Audient iD14)"


def test_unplugged_mic_says_so(listener, monkeypatch):
    _fake_sd(monkeypatch, MICS, 1)
    listener._frames.put(np.full(ears.HOP, 0.01, dtype=np.float32))
    listener._listen()  # one frame, then nothing: the device went away
    assert [s for s, _ in listener.states] == ["listening", "error"]
    assert "Audient" in listener.error and "plugged in" in listener.error


def test_silent_input_points_at_windows_privacy_once_then_clears(listener, monkeypatch):
    _fake_sd(monkeypatch, MICS, 1)
    zeros = int(ears.SILENT_S * ears.RATE / ears.HOP)
    for _ in range(zeros * 2):  # twice as long as the limit: still only one warning
        listener._frames.put(np.zeros(ears.HOP, dtype=np.float32))
    listener._frames.put(np.full(ears.HOP, 0.01, dtype=np.float32))
    seen = []
    listener.on_state = lambda s: seen.append((s, listener.silent_input, listener.error))
    listener._listen()
    assert [s for s, *_ in seen] == ["listening", "error", "listening", "error"]
    assert seen[1][1] is True and "Privacy & security > Microphone" in seen[1][2]
    assert seen[2][1:] == (False, "")  # real sound came back
    assert "plugged in" in seen[3][2]  # then the frames stopped (end of this test's audio)


class FlakyASR:
    """Raises on the given call numbers (1-based), otherwise hears "play from bar four"."""

    def __init__(self, fail_on):
        self.fail_on, self.calls = set(fail_on), 0

    def recognize(self, audio, sample_rate):
        self.calls += 1
        if self.calls in self.fail_on:
            raise RuntimeError("onnxruntime: bad allocation")
        return "play from bar four"


class Stop(Exception):
    pass


def _run_transcriber(listener, asr, jobs):
    """Queue the jobs, then a sentinel that makes the next get() stop the loop, and run _transcribe inline."""
    listener._asr = asr
    for _ in range(jobs):
        listener._jobs.put((np.zeros(ears.RATE, dtype=np.float32), 1.0))
    real_get = listener._jobs.get

    def get():
        if listener._jobs.empty():
            raise Stop
        return real_get()

    listener._jobs.get = get
    heard = []
    listener.on_text = lambda text, timing: heard.append(text)
    try:
        listener._transcribe()
        return heard, False
    except Stop:
        return heard, True  # the thread was still waiting for the next utterance


def test_a_failed_transcription_is_said_and_the_next_utterance_is_still_heard(listener):
    heard, alive = _run_transcriber(listener, FlakyASR({1}), jobs=2)
    assert alive and heard == ["play from bar four"]
    assert [s for s, _ in listener.states] == ["error", "listening"]
    assert "could not make out" in listener.states[0][1] and "bad allocation" in listener.states[0][1]
    assert listener.error == ""


def test_speech_recognition_that_keeps_failing_is_said_and_stops(listener):
    heard, alive = _run_transcriber(listener, FlakyASR({1, 2, 3}), jobs=4)
    assert not alive and heard == []
    assert [s for s, _ in listener.states] == ["error", "listening"] * 2 + ["error"]
    assert "Close and reopen" in listener.error
