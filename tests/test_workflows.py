"""Workflow tests against a fake Live that formats values the way Live does."""

import math

import pytest

from livepilot_tools import telemetry, workflows


def vol_str(raw):
    return "-inf dB" if raw <= 0 else f"{(raw - 0.85) * 40:.1f} dB"


def freq_str(raw):
    hz = 20 * 1000 ** raw
    return f"{hz:.0f} Hz" if hz < 1000 else f"{hz / 1000:.2f} kHz"


def pan_str(raw):
    n = round(abs(raw) * 50)
    return "C" if n == 0 else f"{n}{'L' if raw < 0 else 'R'}"


class Param:
    """Stands in for a Live DeviceParameter: str_for_value formats, quantized values round."""

    def __init__(self, name, value, lo, hi, fmt, quantized=False, items=None):
        self.name, self.min, self.max, self.fmt = name, lo, hi, fmt
        self.is_quantized, self.items = quantized, items
        self.value = value

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, raw):
        self._value = round(raw) if self.is_quantized else raw

    @property
    def value_items(self):
        return self.items or []

    def str_for_value(self, raw):
        return self.fmt(raw)

    def describe(self, i):
        d = {"index": i, "name": self.name, "value": self.value, "min": self.min, "max": self.max,
             "is_quantized": self.is_quantized, "value_string": self.fmt(self.value)}
        if self.items:
            d["value_items"] = self.items
        return d


def eq():
    return {"name": "EQ Eight", "class_name": "Eq8", "params": [
        Param("Device On", 1.0, 0.0, 1.0, lambda r: "On" if r else "Off", True, ["Off", "On"]),
        Param("1 Frequency A", 0.3, 0.0, 1.0, freq_str),
        Param("1 Gain A", 0.5, 0.0, 1.0, lambda r: f"{(r - 0.5) * 30:.1f} dB"),
        Param("1 Filter Type A", 3.0, 0.0, 7.0, str, True,
              ["Low Cut 48", "Low Cut 12", "Low Shelf", "Bell", "Notch", "High Shelf", "High Cut 12", "High Cut 48"]),
    ]}


class FakeLive:
    def __init__(self):
        self.tracks = {
            0: {"name": "Rap", "solo": False, "devices": [eq()]},
            1: {"name": "Sing BG", "solo": True, "devices": []},
            2: {"name": "Instrumental Group", "solo": False, "devices": []},
            -1: {"name": "A-Reverb", "solo": False, "devices": []},
        }
        self.mixers = {k: [Param("Track Volume", 0.85, 0.0, 1.0, vol_str),
                           Param("Track Panning", 0.0, -1.0, 1.0, pan_str),
                           Param("A-Reverb", 0.0, 0.0, 1.0, vol_str)] for k in self.tracks}
        self.position, self.playing, self.writes = 0.0, False, 0
        self.up, self.has_lp = True, True

    def params(self, t, d):
        return self.mixers[t] if d == -1 else self.tracks[t]["devices"][d]["params"]

    def send(self, cmd, params=None, timeout=5.0, persistent=False):
        p = params or {}
        if not self.up:
            return {"success": False, "message": "LivePilot remote script unreachable on 127.0.0.1:9878: "
                                                 "[WinError 10061] No connection could be made"}
        if cmd.startswith("lp_") and not self.has_lp:
            return {"success": False, "code": "NOT_FOUND", "message": f"Unknown command type: {cmd}"}
        if cmd == "get_session_info":
            return {"success": True, "tempo": 145.0, "is_playing": self.playing, "current_song_time": self.position,
                    "signature_numerator": 4, "loop": False,
                    "tracks": [{"index": k, "name": v["name"], "solo": v["solo"]} for k, v in self.tracks.items() if k >= 0],
                    "return_tracks": [{"index": -k - 1, "name": v["name"], "solo": v["solo"]}
                                      for k, v in self.tracks.items() if k < 0]}
        t = p.get("track_index")
        if "track" in p:  # lp_chain / lp_chain_add resolve names inside Live with the shared core
            names = [(k, v["name"]) for k, v in self.tracks.items()]
            try:
                t, _ = workflows.core.resolve_track(p["track"], [x for x in names if x[0] >= 0],
                                                    sorted((x for x in names if x[0] < 0), reverse=True))
            except ValueError as e:
                return {"success": False, "code": "INVALID_PARAM", "message": str(e)}
        if cmd == "lp_chain_add":
            devices = self.tracks[t]["devices"]
            if p["name"] == "Nonsense":
                n = len(devices)
                return {"success": False, "code": "STATE_ERROR",
                        "message": f"Device not found: Nonsense (chain went from {n} to {n} devices)"}
            self.loader("track" if t >= 0 else "return", t if t >= 0 else -t - 1, p["name"], p["position"])
            index = len(devices) - 1 if p["position"] < 0 else p["position"]
            return {"success": True, "track_index": t, "track_name": self.tracks[t]["name"], "device_index": index,
                    "devices": self.chain(t)}
        if cmd == "lp_chain":
            return {"success": True, "track_index": t, "track_name": self.tracks[t]["name"], "devices": self.chain(t)}
        if cmd == "lp_params":
            return {"success": True, "parameters": [x.describe(i) for i, x in enumerate(self.params(t, p["device_index"]))]}
        if cmd == "lp_dial":
            try:
                res = workflows.core.dial(FakeSong(self), fake_get_track, p["track"], p["param"],
                                          to=p.get("to"), by=p.get("by"), device=p.get("device"))
            except ValueError as e:  # Live's router turns these into INVALID_PARAM replies
                return {"success": False, "code": "INVALID_PARAM", "message": str(e)}
            self.writes += "after_raw" in res
            return {"success": True, **res}
        if cmd == "lp_set":
            prm = self.params(t, p["device_index"])[p["parameter_index"]]
            prm.value = p["value"]
            self.writes += 1
            return {"success": True, "name": prm.name, "value": prm.value, "value_string": prm.fmt(prm.value)}
        if cmd == "delete_device":
            self.tracks[t]["devices"].pop(p["device_index"])
            return {"success": True}
        if cmd == "set_track_solo":
            self.tracks[t]["solo"] = bool(p["solo"])
            return {"success": True}
        if cmd == "jump_to_time":
            self.position = p["beat_time"]
            return {"success": True}
        if cmd in ("continue_playback", "stop_playback"):
            self.playing = cmd == "continue_playback"
            return {"success": True}
        if cmd == "get_cue_points":
            return {"success": True, "cue_points": [{"index": 0, "name": "Hook", "time": 128.0}]}
        raise AssertionError(f"unexpected command {cmd}")

    def chain(self, t):
        return [{"index": i, "name": d["name"], "class_name": d["class_name"], "is_active": True}
                for i, d in enumerate(self.tracks[t]["devices"])]

    def loader(self, kind, idx, name, pos):
        devices = self.tracks[idx if kind == "track" else -idx - 1]["devices"]
        dev = eq() if name.lower().startswith("eq") else {"name": name, "class_name": name, "params": [
            Param("Device On", 1.0, 0.0, 1.0, str), Param("Threshold", 0.5, 0.0, 1.0, lambda r: f"{r * -60:.1f} dB")]}
        devices.insert(len(devices) if pos < 0 else pos, dev)
        return {"success": True}


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _live_track(fake, key):
    data = fake.tracks[key]
    vol, pan, *sends = fake.mixers[key]
    devices = [_Obj(name=d["name"], class_name=d["class_name"], parameters=d["params"]) for d in data["devices"]]
    return _Obj(name=data["name"], devices=devices, mixer_device=_Obj(volume=vol, panning=pan, sends=sends))


class FakeSong:
    def __init__(self, fake):
        self.fake = fake
        self.tracks = [_live_track(fake, k) for k in sorted(k for k in fake.tracks if k >= 0)]
        self.return_tracks = [_live_track(fake, k) for k in sorted((k for k in fake.tracks if k < 0), reverse=True)]


def fake_get_track(song, rs_index):
    return song.return_tracks[-rs_index - 1] if rs_index < 0 else song.tracks[rs_index]


@pytest.fixture
def live(monkeypatch, tmp_path):
    fake = FakeLive()
    monkeypatch.setattr(workflows, "send", fake.send)
    monkeypatch.setattr(workflows, "JOURNAL_PATH", tmp_path / "journal.jsonl")
    monkeypatch.setattr(workflows, "_audition_saved", None)
    return fake


def test_dial_fader_in_db_lands_exactly(live):
    res = workflows.dial("rap", "volume", to="-6 dB")
    assert res["success"] and res["after"] == "-6.0 dB" and res["before"] == "0.0 dB"
    assert "Rap > Mixer > Track Volume" in res["summary"]


def test_dial_device_by_fuzzy_names_and_khz(live):
    res = workflows.dial("Rap", "1 freq", to="2.5 kHz", device="eq")
    assert res["success"], res
    assert res["after"] == "2.50 kHz"


def test_dial_warns_when_eq_band_frequency_does_nothing(live):
    """A shelf/bell band at 0 dB ignores its Frequency: say so instead of a clean readback."""
    workflows.dial("Rap", "1 Filter Type A", to="Low Shelf", device="EQ Eight")
    res = workflows.dial("Rap", "1 Frequency A", to="30 Hz", device="EQ Eight")
    assert res["success"] and "band 1 is Low Shelf at 0 dB, this does nothing" in res["warning"]
    assert "WARNING" in res["summary"]
    workflows.dial("Rap", "1 Filter Type A", to="Low Cut 48", device="EQ Eight")
    assert "warning" not in workflows.dial("Rap", "1 Frequency A", to="30 Hz", device="EQ Eight")
    workflows.dial("Rap", "1 Filter Type A", to="Bell", device="EQ Eight")
    workflows.dial("Rap", "1 Gain A", to="-3 dB", device="EQ Eight")
    assert "warning" not in workflows.dial("Rap", "1 Frequency A", to="350 Hz", device="EQ Eight")


def test_dial_relative_and_read(live):
    workflows.dial("Rap", "volume", to="-6 dB")
    res = workflows.dial("Rap", "volume", by="+2 dB")
    assert res["after"] == "-4.0 dB"
    assert workflows.dial("Rap", "volume")["summary"].endswith("is -4.0 dB")


def test_dial_enum_and_pan_and_send(live):
    assert workflows.dial("Rap", "filter type", to="Notch", device="EQ Eight")["after"] == "4"
    assert workflows.dial("Rap", "pan", to="30L")["after"] == "30L"
    assert workflows.dial("Rap", "send A", to="-12 dB")["after"] == "-12.0 dB"


def test_digit_strings_are_positions(live):
    live.tracks[2]["name"] = "1-808 Drifter"
    assert workflows.resolve_track("808")[1] == "1-808 Drifter"
    assert workflows.resolve_track("1")[1] == "Rap"  # 1st track as Live numbers it, even past a "1-..." name
    assert workflows.resolve_track("3")[1] == "1-808 Drifter"
    assert workflows.resolve_track("0")[1] == "Rap"  # no name contains 0: falls back to the index
    assert workflows.resolve_track(1)[1] == "Sing BG"  # a real number is always an index


def test_dial_errors_are_plain(live):

    assert "goes from -inf dB to 6.0 dB" in workflows.dial("Rap", "volume", to="+20 dB")["message"]
    assert "several parameters" in workflows.dial("Rap", "1", to="-3 dB", device="eq")["message"]
    assert "Which device" in workflows.dial("Rap", "threshold", to="-20 dB")["message"]
    assert "Closest:" in workflows.dial("Bass", "volume", to="-3 dB")["message"]


def test_undo_restores_exact_value(live):
    workflows.dial("Rap", "volume", to="-6 dB")
    workflows.dial("Rap", "pan", to="20R")
    res = workflows.undo(2)
    assert res["success"] and res["undone"] == 2
    assert live.mixers[0][0].value == 0.85 and live.mixers[0][1].value == 0.0
    assert workflows.undo()["summary"] == "Nothing to undo."


def test_chain_add_remove_and_undo(live):
    res = workflows.chain("Rap", add="Compressor")
    assert res["chain"] == ["EQ Eight", "Compressor"] and "slot 1" in res["summary"]
    workflows.dial("Rap", "threshold", to="-30.0 dB", device="Compressor")
    removed = workflows.chain("Rap", remove="compressor")
    assert removed["chain"] == ["EQ Eight"]
    workflows.undo()  # re-adds the compressor with its -30 dB threshold
    comp = live.tracks[0]["devices"][1]
    assert comp["name"] == "Compressor" and comp["params"][1].fmt(comp["params"][1].value) == "-30.0 dB"


def test_chain_add_at_position_is_one_call_and_undoes(live):
    res = workflows.chain("Rap", add="Compressor", position=0)
    assert res["success"] and res["chain"] == ["Compressor", "EQ Eight"], res
    assert workflows.undo()["success"] and [d["name"] for d in live.tracks[0]["devices"]] == ["EQ Eight"]


def test_failed_load_that_added_nothing_is_an_error(live):
    res = workflows.chain("Rap", add="Nonsense")
    assert not res["success"] and "not found" in res["message"]


def test_undo_never_deletes_a_moved_device(live):
    workflows.chain("Rap", add="Compressor")
    live.tracks[0]["devices"].reverse()  # the user rearranged the chain by hand
    res = workflows.undo()
    assert not res["success"] and "not deleting" in res["message"]
    assert len(live.tracks[0]["devices"]) == 2


def test_audition_solos_jumps_and_restores(live):
    res = workflows.audition("Rap", at=33)
    assert res["success"] and live.position == 128.0 and live.playing
    assert live.tracks[0]["solo"] and not live.tracks[1]["solo"]
    workflows.audition(["Rap", "A-Reverb"], at="Hook")
    assert live.tracks[-1]["solo"] and live.position == 128.0
    workflows.audition(stop=True)
    assert not live.playing and live.tracks[1]["solo"] and not live.tracks[0]["solo"] and not live.tracks[-1]["solo"]


def test_live_down_and_stale_script_hints(live):
    live.up = False
    assert "Open Ableton" in workflows.session()["message"]
    live.up, live.has_lp = True, False
    assert "restart Live" in workflows.dial("Rap", "volume", to="-6 dB")["message"]


def test_session_is_compact(live):
    res = workflows.session()
    assert res["tracks"] == ["0:Rap", "1:Sing BG [S]", "2:Instrumental Group"] and res["returns"] == ["A:A-Reverb"]
    assert telemetry.reply_tokens(res) < 120


def test_parse_display():
    assert workflows.parse_display("-inf dB") == (-math.inf, "db")
    assert workflows.parse_display("1.20 s") == (1200.0, "ms")
    assert workflows.parse_display("4.00 : 1") == (4.0, "ratio")
    assert workflows.parse_display("C") == (0.0, "pan")


def test_budget_blocks_then_resets(monkeypatch, tmp_path):
    monkeypatch.setattr(telemetry, "CALLS_PATH", tmp_path / "calls.jsonl")
    import time
    telemetry.set_budget(max_calls=2)
    for _ in range(2):
        assert telemetry.over_budget("dial") is None
        telemetry.record("dial", None, {"success": True}, time.perf_counter())
    assert telemetry.over_budget("dial")["budget_exceeded"]
    assert telemetry.over_budget("undo") is None
    rep = telemetry.report(1)
    assert rep["by_function"][0]["calls"] == 2
    telemetry.set_budget()
    assert telemetry.over_budget("dial") is None


def test_undo_refuses_in_a_different_set(live):
    workflows.dial("Rap", "volume", to="-6 dB")
    live.tracks[0]["name"] = "Lead Vox"  # a different set is open now
    res = workflows.undo()
    assert not res["success"] and "different set" in res["message"]
    assert live.mixers[0][0].value != 0.85


def test_persistent_connection_reconnects_once(monkeypatch):
    from livepilot_tools import remote_script

    class Sock:
        def __init__(self, replies):
            self.replies = list(replies)
        def settimeout(self, t):
            pass
        def sendall(self, data):
            pass
        def recv(self, n):
            return self.replies.pop(0) if self.replies else b""
        def close(self):
            pass

    socks = [Sock([b""]), Sock([b'{"ok": true, "result": {"x": 1}}\n', b'{"ok": true, "result": {"x": 2}}\n'])]
    made = []
    monkeypatch.setattr(remote_script.socket, "create_connection", lambda *a, **k: made.append(1) or socks.pop(0))
    monkeypatch.setattr(remote_script, "_conn", None)
    assert remote_script.send_command("lp_chain", {}, persistent=True)["x"] == 1  # first socket was dead
    assert remote_script.send_command("lp_chain", {}, persistent=True)["x"] == 2  # reused, no new connect
    assert len(made) == 2


def test_dropouts_flag_digital_gaps_not_rests():
    import numpy as np

    rate = 1000
    tone = 0.3 * np.ones(rate)
    gap = np.zeros(100)
    assert workflows._dropouts(np.concatenate([tone, gap, tone]), rate) == [1.0]
    rest = 0.001 * np.ones(100)  # quiet reverb tail, about -60 dBFS
    assert workflows._dropouts(np.concatenate([tone, rest, tone]), rate) == []
    assert workflows._dropouts(np.concatenate([gap, tone]), rate) == []  # silence before the downbeat is fine


def test_dropouts_ignore_a_dry_sparse_part():
    """A soloed kick decays into true digital silence between hits; that is not a dropout."""
    import numpy as np

    rate = 48000
    t = np.arange(int(0.12 * rate)) / rate
    hit = np.sin(2 * np.pi * 55 * t) * np.exp(-t / 0.012)  # decays below -90 dBFS before it ends
    hit[np.abs(hit) < 10 ** (-90 / 20)] = 0.0
    beat = np.concatenate([hit, np.zeros(int(0.30 * rate))])  # 144 BPM-ish: hit, then rest
    kick = np.tile(beat, 8)
    assert workflows._dropouts(kick, rate) == []
    # The same capture glitching mid-pad is still caught.
    pad = 0.3 * np.sin(2 * np.pi * 220 * np.arange(rate) / rate)
    glitch = np.concatenate([pad, np.zeros(int(0.03 * rate)), pad])
    assert workflows._dropouts(glitch, rate) == [1.0]
