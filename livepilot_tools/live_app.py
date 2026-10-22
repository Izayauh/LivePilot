"""Ableton Live as an application: status, save, open, close, restart, and its dialogs.

The Live Object Model cannot save a set, quit Live, or answer Live's own pop-ups, so
this module drives the Windows side, still without the mouse or keyboard focus:

- Save and Quit are posted as WM_COMMAND ids looked up by name in Live's native
  File menu, so they work while Live sits in the background.
- The main window title is the readback: a ``*`` after the set name means unsaved.
- A dialog is a visible, untitled window owned by Live's main window. Live draws
  dialogs itself, so their text is read with Windows OCR, and buttons are pressed
  by posting key or click messages to that window only.

Known dialogs are answered from ``data/live_dialog_rules.json``. Anything else is
returned to the calling agent as text plus buttons; it decides and calls
``press``, and can add a rule so the next agent never has to ask.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import ctypes
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import psutil
import win32api
import win32con
import win32gui
import win32process
import win32ui

REPO_ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = REPO_ROOT / "data" / "live_dialog_rules.json"
STATE_PATH = REPO_ROOT / "data" / "live_app_state.json"
LOG_PATH = REPO_ROOT / "data" / "telemetry" / "live_app.jsonl"
EXE_PREFIX = "Ableton Live "  # any edition or version: "Ableton Live 11 Standard.exe", "Ableton Live 12 Suite.exe"
_user32 = ctypes.windll.user32
# Live is DPI-aware; without this, window rects come back scaled and captures and clicks miss.
ctypes.windll.shcore.SetProcessDpiAwareness(2)


# -- finding Live ------------------------------------------------------------

def _process() -> psutil.Process | None:
    for proc in psutil.process_iter(["name", "exe"]):
        if (proc.info["name"] or "").startswith(EXE_PREFIX):
            return proc
    return None


def _windows(pid: int) -> list[int]:
    found: list[int] = []

    def visit(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and win32process.GetWindowThreadProcessId(hwnd)[1] == pid:
            found.append(hwnd)

    win32gui.EnumWindows(visit, None)
    return found


def _main_window(pid: int) -> int | None:
    for hwnd in _windows(pid):
        if win32gui.GetClassName(hwnd) == "Ableton Live Window Class" and " - Ableton Live" in win32gui.GetWindowText(hwnd):
            return hwnd
    return None


def _dialog_windows(pid: int, main: int | None) -> list[int]:
    """Pop-ups in Live's process: native message boxes (plugins raise these, e.g. UAD) and Live's
    own untitled dialogs. Plugin editor windows carry a title and are left alone."""
    return [h for h in _windows(pid) if h != main and win32gui.GetClassName(h) != "#32768" and (  # not menus
        win32gui.GetClassName(h) == "#32770"
        or (not win32gui.GetWindowText(h) and win32gui.GetWindowRect(h)[2] - win32gui.GetWindowRect(h)[0] > 150))]


def _native_controls(hwnd: int) -> tuple[list[str], dict[str, int]]:
    texts: list[str] = []
    buttons: dict[str, int] = {}

    def visit(child, _):
        if not win32gui.IsWindowVisible(child):
            return
        label = win32gui.GetWindowText(child).strip()
        if win32gui.GetClassName(child) == "Button" and label:
            buttons[label.replace("&", "")] = child
        elif label:
            texts.append(" ".join(label.split()))

    win32gui.EnumChildWindows(hwnd, visit, None)
    return texts, buttons


def _title_info(title: str) -> dict[str, Any]:
    name = title.split("  [")[0].split(" - Ableton Live")[0]
    return {"set": name.rstrip("*").strip(), "unsaved": name.rstrip().endswith("*")}


def _bridge_up() -> bool:
    # A real round trip: the port listens before Live's tick loop runs, and a modal
    # dialog stalls the loop with the port still open.
    from livepilot_tools import remote_script
    return bool(remote_script.send_command("ping", timeout=2).get("pong"))


def _menu_id(main: int, label: str) -> int:
    """WM_COMMAND id of a File-menu item, matched by its text before the shortcut."""
    file_menu = win32gui.GetSubMenu(win32gui.GetMenu(main), 0)
    for i in range(win32gui.GetMenuItemCount(file_menu)):
        buf = ctypes.create_unicode_buffer(256)
        _user32.GetMenuStringW(file_menu, i, buf, 256, 0x400)
        if buf.value.split("\t")[0] == label:
            return _user32.GetMenuItemID(file_menu, i)
    raise RuntimeError(f"File menu has no item '{label}'")


def _state() -> dict[str, Any]:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _remember(**fields: Any) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({**_state(), **fields}, indent=2), encoding="utf-8")


def _log(action: str, result: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "action": action, **result}) + "\n")


# -- reading and answering dialogs -------------------------------------------

def _capture(hwnd: int):
    from PIL import Image

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width, height = right - left, bottom - top
    hdc = win32gui.GetWindowDC(hwnd)
    src = win32ui.CreateDCFromHandle(hdc)
    mem = src.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(src, width, height)
    mem.SelectObject(bmp)
    _user32.PrintWindow(hwnd, mem.GetSafeHdc(), 2)
    image = Image.frombuffer("RGB", (width, height), bmp.GetBitmapBits(True), "raw", "BGRX", 0, 1)
    mem.DeleteDC(); src.DeleteDC(); win32gui.ReleaseDC(hwnd, hdc); win32gui.DeleteObject(bmp.GetHandle())
    return image


def _ocr(image, scale: int = 2) -> list[dict[str, Any]]:
    """Text lines of an image, each with its words' centres in image coordinates."""
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter

    big = image.resize((image.width * scale, image.height * scale)).convert("RGBA")
    writer = DataWriter()
    writer.write_bytes(big.tobytes())
    bitmap = SoftwareBitmap.create_copy_from_buffer(writer.detach_buffer(), BitmapPixelFormat.RGBA8, big.width, big.height)

    async def recognize():
        return await OcrEngine.try_create_from_user_profile_languages().recognize_async(bitmap)

    try:  # the MCP server calls in on its event loop thread, where asyncio.run() refuses
        asyncio.get_running_loop()
    except RuntimeError:
        result = asyncio.run(recognize())
    else:
        with concurrent.futures.ThreadPoolExecutor(1) as ex:
            result = ex.submit(asyncio.run, recognize()).result()
    lines = []
    for line in result.lines:
        words = [{"text": w.text,
                  "x": round((w.bounding_rect.x + w.bounding_rect.width / 2) / scale),
                  "y": round((w.bounding_rect.y + w.bounding_rect.height / 2) / scale)} for w in line.words]
        lines.append({"text": line.text, "words": words})
    return lines


def _find_buttons(image) -> list[dict[str, Any]]:
    """Live's buttons are lighter pills on the dialog's grey panel. Find the row that crosses the
    most of them, take each pill's extent, and OCR it on its own (OCR skips text inside outlines)."""
    from PIL import ImageOps

    gray = ImageOps.grayscale(image)
    width, height = gray.size
    px = gray.load()
    lower = [px[x, y] for y in range(height // 2, height) for x in range(0, width, 3)]
    panel = max(set(lower), key=lower.count)  # the dialog's grey, the commonest shade
    best: list[tuple[int, int]] = []
    best_y = 0
    for y in range(height // 2, height):
        row = [px[x, y] for x in range(width)]
        spans, start = [], None
        for x, value in enumerate(row + [panel]):
            inside = abs(value - panel) > 8 and value > 20  # fill, outline or label; not panel, not frame
            if inside and start is None:
                start = x
            elif not inside and start is not None:
                if spans and start - spans[-1][1] <= 4:  # anti-aliased letter edges dip to panel grey
                    spans[-1] = (spans[-1][0], x)
                else:
                    spans.append((start, x))
                start = None
        runs = [s for s in spans if s[1] - s[0] >= 70]  # words of body text are narrower than a pill
        if len(runs) <= 6 and (len(runs), sum(b - a for a, b in runs)) > (len(best), sum(b - a for a, b in best)):
            best, best_y = runs, y
    buttons = []
    for x0, x1 in best:
        cx = (x0 + x1) // 2
        top = bottom = best_y
        while top > 0 and abs(px[x0 + 6, top - 1] - panel) > 8:
            top -= 1
        while bottom < height - 1 and abs(px[x0 + 6, bottom + 1] - panel) > 8:
            bottom += 1
        crop = image.crop((x0, max(0, top - 2), x1, min(height, bottom + 3)))
        label = " ".join(l["text"] for l in _ocr(crop, scale=3)).strip()
        if label:
            buttons.append({"label": label, "x": cx, "y": (top + bottom) // 2})
    return buttons


def _read_dialog(hwnd: int) -> dict[str, Any]:
    if win32gui.GetClassName(hwnd) == "#32770":  # native: exact text and real buttons, no OCR
        texts, buttons = _native_controls(hwnd)
        return {"hwnd": hwnd, "title": win32gui.GetWindowText(hwnd), "text": " ".join(texts),
                "buttons": list(buttons), "_buttons": [{"label": k, "hwnd": v} for k, v in buttons.items()]}
    image = _capture(hwnd)
    buttons = _find_buttons(image)
    labels = {b["label"] for b in buttons}
    text = " ".join(l["text"] for l in _ocr(image) if l["text"] not in labels and len(l["text"]) > 1)
    return {"hwnd": hwnd, "text": text, "buttons": [b["label"] for b in buttons], "_buttons": buttons}


def _post_key(hwnd: int, vk: int) -> None:
    # Live reads the scan code from lParam, not just the virtual key.
    scan = win32api.MapVirtualKey(vk, 0) << 16
    win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, vk, scan | 0x00000001)
    win32gui.PostMessage(hwnd, win32con.WM_KEYUP, vk, scan | 0xC0000001)


def _post_click(hwnd: int, x: int, y: int) -> None:
    # OCR coordinates are window-relative; mouse messages want client coordinates.
    left, top = win32gui.GetWindowRect(hwnd)[:2]
    cx, cy = win32gui.ScreenToClient(hwnd, (left + x, top + y))
    lparam = win32api.MAKELONG(cx, cy)
    win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lparam)
    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam)


def _gone(hwnd: int, wait: float = 3.0) -> bool:
    end = time.time() + wait
    while time.time() < end:
        if not (win32gui.IsWindow(hwnd) and win32gui.IsWindowVisible(hwnd)):
            return True
        time.sleep(0.2)
    return False


def _press(dialog: dict[str, Any], button: str) -> dict[str, Any]:
    """Answer a dialog: 'enter' or 'escape' as keys, anything else as a button label to click."""
    hwnd = dialog["hwnd"]
    key = {"enter": win32con.VK_RETURN, "escape": win32con.VK_ESCAPE}.get(button.lower())
    note = None
    if key:
        _post_key(hwnd, key)
    else:
        target = button.lower()
        match = next((b for b in dialog["_buttons"] if b["label"].lower() == target), None) \
            or next((b for b in dialog["_buttons"] if target in b["label"].lower()), None)
        labels = {b.lower() for b in dialog["buttons"]}
        # OCR misses Live's highlighted default button (2026-10-22: only "No" read on the crash-recovery
        # pop-up). On a plain question Enter presses that default, so Yes or OK may go by Enter.
        # No and Cancel never: those must be seen to be pressed. Native dialogs list real buttons: no guess.
        by_default = (match is None and target in ("yes", "ok") and not any("hwnd" in b for b in dialog["_buttons"])
                      and (dialog["text"].rstrip().endswith("?") or bool(labels) and labels <= {"yes", "no", "ok", "cancel"}))
        if by_default:
            _post_key(hwnd, win32con.VK_RETURN)
            note = f"pressed the default button ({button}) with Enter; OCR had not read that button"
        elif match is None:
            return {"success": False, "error": f"No button '{button}' on the dialog", "buttons": dialog["buttons"]}
        elif "hwnd" in match:
            win32gui.PostMessage(match["hwnd"], win32con.BM_CLICK, 0, 0)
        else:
            _post_click(hwnd, match["x"], match["y"])
    closed = _gone(hwnd)
    return {"success": closed, "pressed": button, "dialog_closed": closed, **({"message": note} if note else {})}


def _rules() -> list[dict[str, Any]]:
    try:
        return json.loads(RULES_PATH.read_text(encoding="utf-8"))["rules"]
    except (OSError, ValueError, KeyError):
        return []


def _rule_for(text: str) -> dict[str, Any] | None:
    lowered = text.lower()
    return next((r for r in _rules() if all(k.lower() in lowered for k in r["match"])), None)


def handle_dialogs(auto: bool = True) -> dict[str, Any]:
    """Read every open Live dialog; answer the ones a rule covers. Unknown ones come back for the agent."""
    proc = _process()
    if not proc:
        return {"handled": [], "open": []}
    handled, still_open = [], []
    for hwnd in _dialog_windows(proc.pid, _main_window(proc.pid)):
        dialog = _read_dialog(hwnd)
        if not dialog["buttons"]:
            continue  # splash or progress window: nothing to answer
        rule = _rule_for(dialog["text"]) if auto else None
        if rule:
            outcome = _press(dialog, rule["press"])
            handled.append({"rule": rule["name"], "text": dialog["text"][:200], **outcome})
            _log("dialog", handled[-1])
        else:
            still_open.append({k: v for k, v in dialog.items() if not k.startswith("_")})
    return {"handled": handled, "open": still_open}


# -- the actions ---------------------------------------------------------------

def status() -> dict[str, Any]:
    proc = _process()
    if not proc:
        return {"running": False, "bridge": False, "last_set": _state().get("set_path")}
    main = _main_window(proc.pid)
    info = _title_info(win32gui.GetWindowText(main)) if main else {"set": None, "unsaved": None}
    dialogs = _dialog_windows(proc.pid, main)
    return {"running": True, "pid": proc.pid, **info, "dialogs_open": len(dialogs), "bridge": _bridge_up()}


def dialog_check() -> dict[str, Any] | None:
    """Cheap guard for other tools: None when no dialog is up, else the dialog read and any auto-answer."""
    proc = _process()
    if not proc or not _dialog_windows(proc.pid, _main_window(proc.pid)):
        return None
    return handle_dialogs()


SAVE_AS_TITLE = "Save Live Set As:"


def _save_as_dialogs(pid: int) -> list[int]:
    return [h for h in _windows(pid)
            if win32gui.GetClassName(h) == "#32770" and win32gui.GetWindowText(h) == SAVE_AS_TITLE]


def _filename_box(dialog: int) -> int | None:
    """The File name edit of a Windows Save or Open dialog: the first visible Edit inside a ComboBox,
    skipping the address bar (control 41477). Save puts it on a FloatNotifySink panel, Open under
    control 1148; File type combos have no Edit."""
    found: list[int] = []

    def visit(child, _):
        if (not found and win32gui.GetClassName(child) == "Edit" and win32gui.IsWindowVisible(child)
                and win32gui.GetClassName(win32gui.GetParent(child)) == "ComboBox"
                and win32gui.GetDlgCtrlID(child) != 41477):
            found.append(child)

    win32gui.EnumChildWindows(dialog, visit, None)
    return found[0] if found else None


def _fill_save_as(dialog: int, path: Path) -> dict[str, Any] | None:
    """Type `path` into the Save As dialog and press Save. None on success, else the error.

    Verified 2026-10-20: the dialog ignores WM_SETTEXT (it saved under its default 'Untitled'),
    and a posted BM_CLICK or Enter does nothing useful. Typed WM_CHARs plus WM_COMMAND IDOK work."""
    box = _filename_box(dialog)
    if not box:
        return {"success": False, "error": "Save As dialog has no File name box"}
    _user32.SendMessageW(box, 0x00B1, 0, -1)  # EM_SETSEL: select the default name
    _user32.SendMessageW(box, win32con.WM_CHAR, win32con.VK_BACK, 0)
    for ch in str(path):
        _user32.SendMessageW(box, win32con.WM_CHAR, ord(ch), 0)
    buf = ctypes.create_unicode_buffer(1024)  # WM_GETTEXT: GetWindowText never reads another process's edit
    _user32.SendMessageW(box, win32con.WM_GETTEXT, 1024, buf)
    if buf.value != str(path):
        return {"success": False, "error": "File name box did not take the path", "box": buf.value}
    ok = win32gui.GetDlgItem(dialog, win32con.IDOK)
    win32gui.PostMessage(dialog, win32con.WM_COMMAND, (win32con.BN_CLICKED << 16) | win32con.IDOK, ok)
    return None


def _cancel_confirm_save_as(pid: int) -> bool:
    """Answer any 'X already exists, replace it?' prompt with Cancel, so nothing is overwritten."""
    found = False
    for h in _windows(pid):
        if win32gui.GetClassName(h) == "#32770" and win32gui.GetWindowText(h) == "Confirm Save As":
            win32gui.PostMessage(h, win32con.WM_COMMAND, win32con.IDCANCEL, 0)
            found = True
    return found


def save(only_if_unsaved: bool = True, path: str | None = None) -> dict[str, Any]:
    """File > Save. With `path`, File > Save Live Set As to that .als (the only way to save an
    Untitled set). Without one, an Untitled set is refused instead of opening a Save As dialog
    nobody will fill: the end-of-turn autosave stacked 27 of them on 2026-10-20.
    Outside a Live Project folder Live writes `<folder>/<Name> Project/<Name>.als`; the reply's
    `path` is where the file actually landed."""
    proc = _process()
    main = _main_window(proc.pid) if proc else None
    if not main:
        return {"success": False, "error": "Live is not running"}
    before = _title_info(win32gui.GetWindowText(main))
    open_save_as = _save_as_dialogs(proc.pid)
    if path:
        target = Path(path).with_suffix(".als")
        landed = [target, target.parent / f"{target.stem} Project" / target.name]
        if not target.parent.is_dir():
            return {"success": False, "error": f"Folder does not exist: {target.parent}"}
        if any(p.exists() for p in landed):
            return {"success": False, "error": f"Refusing to overwrite {target.stem}.als; pick a new name"}
        if len(open_save_as) > 1:
            return {"success": False, "error": f"{len(open_save_as)} Save As dialogs are open; clear them first"}
        if not open_save_as:  # reuse one already open rather than stacking another
            win32gui.PostMessage(main, win32con.WM_COMMAND, _menu_id(main, "Save Live Set As..."), 0)
            end = time.time() + 10
            while not open_save_as and time.time() < end:
                time.sleep(0.3)
                open_save_as = _save_as_dialogs(proc.pid)
            if not open_save_as:
                return {"success": False, "error": "Save As dialog did not open in 10 s"}
        failed = _fill_save_as(open_save_as[0], target)
        if failed:
            return failed
    elif open_save_as:
        return {"success": False, "error": "A Save As dialog is already open; call save(path=...) to fill it",
                "set": before["set"], "dialogs_open": len(open_save_as)}
    elif before["set"] == "Untitled":
        return {"success": False, "error": "Set is Untitled; call save(path=...) with a .als path", "set": "Untitled"}
    elif only_if_unsaved and not before["unsaved"]:
        return {"success": True, "saved": False, "set": before["set"], "message": "Already saved",
                "summary": f"{before['set']} was already saved"}
    else:
        win32gui.PostMessage(main, win32con.WM_COMMAND, _menu_id(main, "Save Live Set"), 0)
    end = time.time() + 20
    while time.time() < end:
        time.sleep(0.5)
        now = _title_info(win32gui.GetWindowText(main))
        written = next((str(p) for p in landed if p.exists()), None) if path else None
        if not now["unsaved"] and (not path or (written and now["set"] == target.stem)):
            result = {"success": True, "saved": True, "set": now["set"], **({"path": written} if path else {}),
                      "summary": f"Saved {now['set']}"}
            _log("save", result)
            return result
        if path and _cancel_confirm_save_as(proc.pid):
            return {"success": False, "error": "Live asked to replace an existing file; cancelled, nothing overwritten"}
        try:
            dialogs = handle_dialogs()
        except win32ui.error:  # a dialog closed while it was being captured
            continue
        blocking = [d for d in dialogs["open"] if d.get("title") != SAVE_AS_TITLE]  # ours, still closing
        if blocking:
            return {"success": False, "error": "A dialog blocked the save", **dialogs}
    return {"success": False, "error": "Set not saved after 20 s", "set": before["set"],
            "save_as_open": len(_save_as_dialogs(proc.pid))}


def close(save_first: bool = True, force: bool = False) -> dict[str, Any]:
    proc = _process()
    if not proc:
        return {"success": True, "message": "Live is not running", "summary": "Live was not running"}
    main = _main_window(proc.pid)
    if save_first and main:
        saved = save()
        if not saved["success"]:
            return {"success": False, "error": "Save failed, Live left open", "save": saved}
    cmdline = proc.cmdline()
    if len(cmdline) > 1 and main and _title_info(win32gui.GetWindowText(main))["set"] in cmdline[-1]:
        _remember(set_path=cmdline[-1])
    if main:
        win32gui.PostMessage(main, win32con.WM_COMMAND, _menu_id(main, "Quit"), 0)
    end, handled = time.time() + 45, []
    while time.time() < end:
        if not proc.is_running():
            result = {"success": True, "closed": True, "dialogs_handled": handled, "summary": "Live closed"}
            _log("close", result)
            return result
        dialogs = handle_dialogs()
        handled += dialogs["handled"]
        if dialogs["open"]:
            return {"success": False, "error": "A dialog is holding Live open", **dialogs}
        time.sleep(0.5)
    if force:
        proc.kill()
        return {"success": True, "closed": True, "killed": True, "summary": "Live hung, so it was killed"}
    return {"success": False, "error": "Live did not quit in 45 s; call close(force=True) to kill it"}


def open_set(path: str | None = None, wait: float = 900, heal: bool = True) -> dict[str, Any]:
    """Launch Live (or wait for a launching one) until the bridge answers. `wait` covers the ~10 min
    plugin rescan after a reboot. If the set has loaded but the bridge never answers (seen
    2026-10-15 after a slow startup), Live is restarted once. With `path` while Live is running,
    Live is switched to that set (see _switch)."""
    if path and not Path(path).exists():
        return {"success": False, "error": f"No set at {path}"}
    proc = _process()
    if proc and path:
        return _switch(proc, path)
    if not proc:  # not running: launch it, with the set if there is one, then wait for it to be ready
        path = path or _state().get("set_path")
        from studio import config  # here: live_app also runs without Studio

        exes = config.live_exes()  # newest Live first
        if not exes:
            return {"success": False, "error": f"No Ableton Live 11 or newer found under {config.PROGRAMDATA / 'Ableton'}"}
        subprocess.Popen([str(exes[0])] + ([path] if path else []), creationflags=subprocess.DETACHED_PROCESS)
        if path:
            _remember(set_path=path)
    end, handled, loaded_at, steady = time.time() + wait, [], None, 0
    while time.time() < end:
        time.sleep(1)
        dialogs = handle_dialogs()
        handled += dialogs["handled"]
        if dialogs["open"]:
            return {"success": False, "error": "Live is waiting on a dialog no rule covers", **dialogs, "dialogs_handled": handled}
        proc = _process()
        main = _main_window(proc.pid) if proc else None
        # Plugins raise pop-ups (UAD) seconds after the bridge first answers, freezing it again,
        # so ready means several answers in a row with no pop-up in between.
        steady = steady + 1 if main and not dialogs["handled"] and _bridge_up() else 0
        if steady >= 5:
            result = {"success": True, "opened": path, "dialogs_handled": handled, **status()}
            result["summary"] = f"Live is up on {result.get('set')}"
            _log("open", result)
            return result
        if main and not _dialog_windows(proc.pid, main):  # set loaded, splash gone
            loaded_at = loaded_at or time.time()
            if time.time() - loaded_at > 120:
                _log("open", {"success": False, "bridge_deaf": True})
                if not heal:
                    break
                closed = close(force=True)
                if not closed["success"]:
                    return {"success": False, "error": "Bridge deaf and Live would not quit", "close": closed}
                healed = open_set(path, wait=max(60.0, end - time.time()), heal=False)
                return {**healed, "healed": "restarted once: the set loaded but the bridge never answered"}
    return {"success": False, "error": f"Live Pilot bridge not up after {wait:.0f} s", "dialogs_handled": handled}


def _switch(proc: psutil.Process, path: str) -> dict[str, Any]:
    """Switch a running Live to `path`: launching the exe with a set hands it to the running
    instance, whose 'Save changes?' pop-up the rules answer. If the title never shows the new set,
    restart Live on it once. Never reports success unless that set is the one open."""
    stem = Path(path).stem
    main = _main_window(proc.pid)
    if main and _title_info(win32gui.GetWindowText(main))["set"] == stem:
        return {"success": True, "opened": path, "switched": False, "summary": f"Already on {stem}"}
    subprocess.Popen([proc.exe(), path], creationflags=subprocess.DETACHED_PROCESS)
    handled, steady = [], 0
    for _ in range(90):
        time.sleep(1)
        dialogs = handle_dialogs()
        handled += dialogs["handled"]
        if dialogs["open"]:
            return {"success": False, "error": f"Live would not switch to {stem}: a pop-up no rule covers is waiting",
                    **dialogs, "dialogs_handled": handled}
        main = _main_window(proc.pid)
        on_it = bool(main) and _title_info(win32gui.GetWindowText(main))["set"] == stem
        steady = steady + 1 if on_it and _bridge_up() else 0
        if steady >= 3:
            _remember(set_path=path)
            result = {"success": True, "opened": path, "switched": True, "dialogs_handled": handled, **status(),
                      "summary": f"Switched to {stem}"}
            _log("open", result)
            return result
    restarted = restart(path)
    if restarted.get("success") and restarted.get("set") == stem:
        return {**restarted, "switched": True, "switched_by": "restart", "summary": f"Switched to {stem} by restarting Live"}
    reason = restarted.get("error") or f"Live came back on {restarted.get('set')}"
    return {"success": False, "error": f"Live would not switch to {stem}: {reason}", "restart": restarted}


def restart(path: str | None = None) -> dict[str, Any]:
    closed = close()
    if not closed["success"]:
        return closed
    return open_set(path)


def press(button: str) -> dict[str, Any]:
    """Answer the open dialog with a button label, 'enter', or 'escape'."""
    proc = _process()
    hwnds = _dialog_windows(proc.pid, _main_window(proc.pid)) if proc else []
    if not hwnds:
        return {"success": False, "error": "No Live dialog is open"}
    if win32gui.GetWindowText(hwnds[0]) == SAVE_AS_TITLE and button.lower() in ("save", "enter"):
        # Pressing Save with an empty name closes the dialog and writes nothing (2026-10-20).
        return {"success": False, "error": "This is Save As; call save(path=...) to fill in the name"}
    dialog = _read_dialog(hwnds[0])
    result = {"text": dialog["text"][:200], **_press(dialog, button)}
    _log("press", result)
    return result


def add_rule(name: str, match: list[str], press_: str, why: str) -> dict[str, Any]:
    """Teach the controller a dialog answer so later agents skip the question."""
    rules = [r for r in _rules() if r["name"] != name]
    rules.append({"name": name, "match": match, "press": press_, "why": why})
    RULES_PATH.write_text(json.dumps({"rules": rules}, indent=2), encoding="utf-8")
    return {"success": True, "rules": len(rules)}


def run(action: str, **kw: Any) -> dict[str, Any]:
    actions = {
        "status": status, "save": save, "close": close, "open": open_set, "restart": restart,
        "dialogs": handle_dialogs, "press": press,
        "add_rule": lambda name, match, press, why: add_rule(name, match, press, why),
    }
    if action not in actions:
        return {"success": False, "error": f"Unknown action '{action}'", "actions": sorted(actions)}
    result = actions[action](**kw)
    result.setdefault("summary", result.get("error") or result.get("message") or _summary(action, result))
    return result


def _summary(action: str, result: dict[str, Any]) -> str:
    """A plain line for results that carry no error or message (Studio shows it in its log)."""
    if action == "status":
        if not result["running"]:
            return "Live is not running"
        return f"On {result['set']}, {'unsaved' if result['unsaved'] else 'saved'}, {result['dialogs_open']} pop-ups open"
    if action == "dialogs":
        waiting = "; ".join(f"{d['text'][:80]} [{', '.join(d['buttons'])}]" for d in result["open"])
        if not result["handled"] and not waiting:
            return "No Live pop-ups" if _process() else "Live is not running, so no pop-ups"
        return f"Answered {len(result['handled'])} pop-ups" + (f"; waiting: {waiting}" if waiting else "")
    return f"{action} done" if result.get("success", True) else f"{action} failed"


if __name__ == "__main__":
    import sys
    print(json.dumps(run(sys.argv[1] if len(sys.argv) > 1 else "status"), default=str))
