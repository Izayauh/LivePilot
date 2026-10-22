"""live_app: title parsing, dialog rules, and button finding on a captured Live dialog."""

from pathlib import Path

from PIL import Image

from livepilot_tools import live_app

FIXTURE = Path(__file__).parent / "fixtures" / "live_save_dialog.png"


def test_title_reads_unsaved_star():
    assert live_app._title_info("4.48 Metanoia*  [User Library] - Ableton Live 11 Standard") == {
        "set": "4.48 Metanoia", "unsaved": True}
    assert live_app._title_info("4.48 Metanoia  [User Library] - Ableton Live 11 Standard")["unsaved"] is False


def test_rule_matches_all_phrases(tmp_path, monkeypatch):
    rules = tmp_path / "rules.json"
    monkeypatch.setattr(live_app, "RULES_PATH", rules)
    live_app.add_rule("save", ["save changes to", "before closing"], "Yes", "keep work")
    assert live_app._rule_for('Save changes to "X" before closing?')["press"] == "Yes"
    assert live_app._rule_for('Save changes to "X"?') is None


def test_finds_live_dialog_buttons():
    buttons = live_app._find_buttons(Image.open(FIXTURE).convert("RGB"))
    assert [b["label"] for b in buttons] == ["Yes", "No", "Cancel"]
    assert buttons[0]["x"] < buttons[1]["x"] < buttons[2]["x"]


def _fake_live(monkeypatch, title, save_as=()):
    posted = []
    monkeypatch.setattr(live_app, "_process", lambda: type("P", (), {"pid": 1})())
    monkeypatch.setattr(live_app, "_main_window", lambda pid: 99)
    monkeypatch.setattr(live_app, "_save_as_dialogs", lambda pid: list(save_as))
    monkeypatch.setattr(live_app.win32gui, "GetWindowText", lambda h: title)
    monkeypatch.setattr(live_app.win32gui, "PostMessage", lambda *a: posted.append(a))
    return posted


def test_untitled_save_without_path_opens_no_dialog(monkeypatch):
    posted = _fake_live(monkeypatch, "Untitled*  [User Library] - Ableton Live 11 Standard")
    result = live_app.save()
    assert result["success"] is False and "path" in result["error"]
    assert posted == []


def test_no_second_save_as_while_one_is_open(monkeypatch):
    posted = _fake_live(monkeypatch, "Song*  [User Library] - Ableton Live 11 Standard", save_as=[5])
    assert live_app.save()["success"] is False
    assert posted == []


def test_save_as_refuses_to_overwrite(monkeypatch, tmp_path):
    (tmp_path / "Song.als").write_text("x")
    posted = _fake_live(monkeypatch, "Untitled*  [User Library] - Ableton Live 11 Standard")
    assert "overwrite" in live_app.save(path=str(tmp_path / "Song.als"))["error"]
    assert posted == []


def test_ocr_inside_running_loop():
    """The MCP server calls live() on its event loop thread; reading a dialog must still work there."""
    import asyncio

    async def from_the_loop():
        return live_app._ocr(Image.open(FIXTURE).convert("RGB"))

    lines = asyncio.run(from_the_loop())
    assert isinstance(lines, list) and lines


def test_live_dialogs_inside_running_loop(monkeypatch):
    """live('dialogs') as the MCP server runs it: on an event loop thread, reading a real Live pop-up."""
    import asyncio

    monkeypatch.setattr(live_app, "_process", lambda: type("P", (), {"pid": 1})())
    monkeypatch.setattr(live_app, "_main_window", lambda pid: 99)
    monkeypatch.setattr(live_app, "_dialog_windows", lambda pid, main: [5])
    monkeypatch.setattr(live_app.win32gui, "GetClassName", lambda h: "Ableton Live Window Class")
    monkeypatch.setattr(live_app, "_capture", lambda h: Image.open(FIXTURE).convert("RGB"))
    monkeypatch.setattr(live_app, "_rules", lambda: [])

    async def from_the_loop():
        return live_app.run("dialogs")

    result = asyncio.run(from_the_loop())
    assert result["open"][0]["buttons"] == ["Yes", "No", "Cancel"]
    assert "Yes, No, Cancel" in result["summary"]


def _fake_running_live(monkeypatch, titles, restarted=None):
    """Live running on Old Song; each GetWindowText call after the Popen reads the next title."""
    launched, state = [], {"titles": iter(titles), "now": "Old Song  [Songs] - Ableton Live 11 Standard"}
    monkeypatch.setattr(live_app, "_process", lambda: type("P", (), {"pid": 1, "exe": lambda self: "live.exe"})())
    monkeypatch.setattr(live_app, "_main_window", lambda pid: 99)
    monkeypatch.setattr(live_app, "_dialog_windows", lambda pid, main: [])
    monkeypatch.setattr(live_app, "_bridge_up", lambda: True)
    monkeypatch.setattr(live_app, "handle_dialogs", lambda: {"handled": [], "open": []})
    monkeypatch.setattr(live_app, "_remember", lambda **kw: None)
    monkeypatch.setattr(live_app, "_log", lambda *a: None)
    monkeypatch.setattr(live_app.time, "sleep", lambda s: None)
    monkeypatch.setattr(live_app, "restart", lambda path=None: restarted)

    def title(h):
        if launched:
            state["now"] = next(state["titles"], state["now"])
        return state["now"]

    monkeypatch.setattr(live_app.win32gui, "GetWindowText", title)
    monkeypatch.setattr(live_app.subprocess, "Popen", lambda *a, **kw: launched.append(a))
    return launched


def test_open_with_path_switches(monkeypatch, tmp_path):
    target = tmp_path / "New Song.als"
    target.write_text("x")
    launched = _fake_running_live(monkeypatch, ["Old Song  [Songs] - Ableton Live 11 Standard"] * 3
                                  + ["New Song  [Songs] - Ableton Live 11 Standard"])
    result = live_app.run("open", path=str(target))
    assert result["success"] is True and result["switched"] is True and result["opened"] == str(target)
    assert result["set"] == "New Song" and result["summary"] == "Switched to New Song"
    assert launched == [(["live.exe", str(target)],)]


def test_open_that_never_switches_says_so(monkeypatch, tmp_path):
    target = tmp_path / "New Song.als"
    target.write_text("x")
    _fake_running_live(monkeypatch, [], restarted={"success": False, "error": "Save failed, Live left open"})
    result = live_app.run("open", path=str(target))
    assert result["success"] is False and "switch" in result["error"] and "New Song" in result["summary"]


def test_open_already_on_that_set(monkeypatch, tmp_path):
    target = tmp_path / "Old Song.als"
    target.write_text("x")
    launched = _fake_running_live(monkeypatch, [])
    result = live_app.run("open", path=str(target))
    assert result["success"] is True and result["summary"] == "Already on Old Song" and launched == []


def test_open_missing_path(monkeypatch, tmp_path):
    launched = []
    monkeypatch.setattr(live_app.subprocess, "Popen", lambda *a, **kw: launched.append(a))
    result = live_app.run("open", path=str(tmp_path / "Nope.als"))
    assert result["success"] is False and result["error"].startswith("No set at") and launched == []


def test_open_launches_the_newest_live(monkeypatch):
    from studio import config

    newest, older = Path("C:/PD/Ableton/Live 12 Suite/Program/Ableton Live 12 Suite.exe"), \
        Path("C:/PD/Ableton/Live 11 Standard/Program/Ableton Live 11 Standard.exe")
    launched = []
    monkeypatch.setattr(live_app, "_process", lambda: None)
    monkeypatch.setattr(live_app, "_state", lambda: {})
    monkeypatch.setattr(config, "live_exes", lambda: [newest, older])
    monkeypatch.setattr(live_app.subprocess, "Popen", lambda args, **k: launched.append(args))
    live_app.open_set(wait=0)
    assert launched == [[str(newest)]]


def test_open_without_live_says_so(monkeypatch):
    from studio import config

    monkeypatch.setattr(live_app, "_process", lambda: None)
    monkeypatch.setattr(live_app, "_state", lambda: {})
    monkeypatch.setattr(config, "live_exes", lambda: [])
    result = live_app.open_set(wait=0)
    assert result["success"] is False and "Live 11 or newer" in result["error"]


CRASH_TEXT = ("Live unexpectedly quit while you were working on the Live Set 'X.als'. "
              "Would you like to recover your work?")


def _ocr_dialog(text, labels):
    return {"hwnd": 5, "text": text, "buttons": list(labels),
            "_buttons": [{"label": l, "x": 40 + 80 * i, "y": 100} for i, l in enumerate(labels)]}


def _fake_keys(monkeypatch):
    keys, clicks = [], []
    monkeypatch.setattr(live_app, "_post_key", lambda h, vk: keys.append((h, vk)))
    monkeypatch.setattr(live_app, "_post_click", lambda h, x, y: clicks.append((h, x, y)))
    monkeypatch.setattr(live_app.win32gui, "PostMessage", lambda *a: clicks.append(a))
    monkeypatch.setattr(live_app, "_gone", lambda h, wait=3.0: True)
    return keys, clicks


def test_crash_recovery_rule_in_the_shipped_rules():
    rule = live_app._rule_for(CRASH_TEXT)
    assert rule and rule["name"] == "recover-after-crash" and rule["press"] == "enter"


def test_crash_recovery_dialog_is_answered_with_enter(monkeypatch):
    keys, clicks = _fake_keys(monkeypatch)
    monkeypatch.setattr(live_app, "_process", lambda: type("P", (), {"pid": 1})())
    monkeypatch.setattr(live_app, "_main_window", lambda pid: 99)
    monkeypatch.setattr(live_app, "_dialog_windows", lambda pid, main: [5])
    monkeypatch.setattr(live_app, "_read_dialog", lambda h: _ocr_dialog(CRASH_TEXT, ["No"]))
    monkeypatch.setattr(live_app, "_log", lambda *a: None)
    result = live_app.handle_dialogs()
    assert result["open"] == [] and result["handled"][0]["rule"] == "recover-after-crash"
    assert result["handled"][0]["success"] is True
    assert keys == [(5, live_app.win32con.VK_RETURN)] and clicks == []


def test_press_yes_falls_back_to_enter_when_ocr_missed_it(monkeypatch):
    keys, clicks = _fake_keys(monkeypatch)
    result = live_app._press(_ocr_dialog(CRASH_TEXT, ["No"]), "Yes")
    assert result["success"] is True and keys == [(5, live_app.win32con.VK_RETURN)] and clicks == []
    assert result["message"] == "pressed the default button (Yes) with Enter; OCR had not read that button"
    # Not a question, but every button read is a plain answer: OK still goes by Enter.
    keys.clear()
    assert live_app._press(_ocr_dialog("Plug-in scan finished.", ["Cancel"]), "OK")["success"] is True
    assert keys == [(5, live_app.win32con.VK_RETURN)]


def test_press_never_guesses_no_cancel_or_unknown_dialogs(monkeypatch):
    keys, clicks = _fake_keys(monkeypatch)
    for button in ("No", "Cancel"):
        result = live_app._press(_ocr_dialog(CRASH_TEXT, ["Yes"]), button)
        assert result["success"] is False and f"No button '{button}'" in result["error"]
    # Not a question and buttons other than yes/no/ok/cancel: Enter could be anything.
    assert live_app._press(_ocr_dialog("Choose an audio device.", ["Open Preferences"]), "OK")["success"] is False
    # Native dialogs list their real buttons; a missing Yes really is missing.
    native = {"hwnd": 5, "text": CRASH_TEXT, "buttons": ["No"], "_buttons": [{"label": "No", "hwnd": 7}]}
    assert live_app._press(native, "Yes")["success"] is False
    assert keys == [] and clicks == []
