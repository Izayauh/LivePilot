"""A Windows toast for a question when the Studio window isn't in front, and bringing that window forward.

The toast is shown by Windows PowerShell (WinRT is built in, nothing to install), which waits for a click
and prints "clicked". The Studio card is always there too; the toast only gets his eyes to it.
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import subprocess
import sys
from ctypes import wintypes
from xml.sax.saxutils import escape

POWERSHELL = os.path.expandvars(r"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe")
NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
AUMID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
WAIT_S = 1800  # a click from the Action Center still counts for half an hour

SHOW = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
$x = New-Object Windows.Data.Xml.Dom.XmlDocument
$x.LoadXml($env:LP_TOAST_XML)
$t = [Windows.UI.Notifications.ToastNotification]::new($x)
$t.Tag = $env:LP_TOAST_TAG; $t.Group = 'livepilot'
Register-ObjectEvent -InputObject $t -EventName Activated -SourceIdentifier act > $null
Register-ObjectEvent -InputObject $t -EventName Dismissed -SourceIdentifier dis > $null
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:LP_TOAST_APP).Show($t)
'shown'
$end = (Get-Date).AddSeconds([int]$env:LP_TOAST_WAIT)
while ((Get-Date) -lt $end) {
  $e = Wait-Event -Timeout 5
  if (-not $e) { continue }
  Remove-Event -EventIdentifier $e.EventIdentifier
  if ($e.SourceIdentifier -eq 'act') { 'clicked'; break }
  if ($e.SourceEventArgs.Reason -eq 'UserCanceled') { 'closed'; break }
}
"""
REMOVE = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.UI.Notifications.ToastNotificationManager]::History.Remove($env:LP_TOAST_TAG, 'livepilot', $env:LP_TOAST_APP)
"""


def _env(tag: str, **extra: str) -> dict:
    return {**os.environ, "LP_TOAST_TAG": tag[:16], "LP_TOAST_APP": AUMID, **extra}


async def toast(tag: str, title: str, text: str) -> asyncio.subprocess.Process:
    """Shows the toast; the returned process prints 'clicked' if he clicks it. Kill it to stop waiting."""
    xml = (f'<toast scenario="reminder"><visual><binding template="ToastGeneric"><text>{escape(title)}</text>'
           f'<text>{escape(text)}</text></binding></visual><actions><action content="Open Studio" arguments="open"/>'
           f'</actions></toast>')
    return await asyncio.create_subprocess_exec(
        POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", SHOW, env=_env(tag, LP_TOAST_XML=xml, LP_TOAST_WAIT=str(WAIT_S)),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, creationflags=NO_WINDOW)


async def remove(tag: str) -> None:
    """Takes the toast off screen and out of the Action Center (answered elsewhere)."""
    proc = await asyncio.create_subprocess_exec(POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", REMOVE, env=_env(tag),
                                                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                                                creationflags=NO_WINDOW)
    await proc.wait()


def focus_window(title: str) -> bool:
    """Brings the Studio app window (a Brave/Edge --app window titled `title`) to the front. False if none is open."""
    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if buf.value == title and cls.value == "Chrome_WidgetWin_1" and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(each, 0)
    if not found:
        return False
    hwnd = found[0]
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.keybd_event(0x12, 0, 0, 0)  # a tap of Alt lets this process take the foreground
    user32.keybd_event(0x12, 0, 2, 0)
    user32.SetForegroundWindow(hwnd)
    return True
