"""
Ableton Live Log Monitor

Reads and monitors Ableton Live's log file for errors, crashes, and events.
Auto-detects the log path on Windows/macOS.

Usage:
    from discovery.log_monitor import LogMonitor

    monitor = LogMonitor()
    recent = monitor.get_recent_logs(50)
    errors = monitor.check_for_errors(window_lines=200)
    print(monitor.get_log_path())
"""
from __future__ import annotations

import glob
import os
import re
from collections import deque
from pathlib import Path
from typing import List, Optional, Tuple


# Error keywords to scan for (case-insensitive)
_ERROR_KEYWORDS = [
    "error",
    "crash",
    "exception",
    "fatal",
    "audio queue timeout",
    "windows exception",
    "failed",
    "assert",
    "segfault",
    "access violation",
]

# Patterns to SKIP (noisy but harmless log lines)
_SKIP_PATTERNS = [
    re.compile(r"RemoteScriptError", re.IGNORECASE),
    re.compile(r"error_description", re.IGNORECASE),
    re.compile(r"no error", re.IGNORECASE),
]


def _version_sort_key(path: str):
    """Extract a numeric sort key from an Ableton version path.

    E.g. 'Live 11.3.43' -> (11, 3, 43) so that 11.3.43 > 11.3.4.
    Plain string sorting gets this wrong on Windows because backslash > digit.
    """
    m = re.search(r"Live\s+([\d.]+)", path)
    if m:
        parts = []
        for p in m.group(1).split("."):
            try:
                parts.append(int(p))
            except ValueError:
                parts.append(0)
        return tuple(parts)
    return (0,)


def _detect_ableton_log() -> Optional[str]:
    """Auto-detect the Ableton Live log file path (picks the highest version)."""
    if os.name == "nt":
        # Windows: %APPDATA%/Ableton/Live <version>/Preferences/Log.txt
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            pattern = os.path.join(appdata, "Ableton", "Live *", "Preferences", "Log.txt")
            matches = sorted(glob.glob(pattern), key=_version_sort_key, reverse=True)
            if matches:
                return matches[0]  # Highest version
    else:
        # macOS: ~/Library/Preferences/Ableton/Live <version>/Log.txt
        home = os.path.expanduser("~")
        pattern = os.path.join(home, "Library", "Preferences", "Ableton", "Live *", "Log.txt")
        matches = sorted(glob.glob(pattern), key=_version_sort_key, reverse=True)
        if matches:
            return matches[0]
    return None


class LogMonitor:
    """Reads and monitors Ableton Live's log file."""

    def __init__(self, log_path: Optional[str] = None):
        if log_path:
            self._log_path = log_path
        else:
            detected = _detect_ableton_log()
            if not detected:
                raise FileNotFoundError(
                    "Could not auto-detect Ableton log file. "
                    "Pass log_path= explicitly."
                )
            self._log_path = detected

    def get_log_path(self) -> str:
        """Return the resolved path to the Ableton log file."""
        return self._log_path

    def exists(self) -> bool:
        """Check if the log file currently exists."""
        return os.path.isfile(self._log_path)

    def get_recent_logs(self, num_lines: int = 50) -> List[str]:
        """Read the last N lines of the log file.

        Uses an efficient tail approach — reads from the end of the file
        rather than loading the entire multi-MB log into memory.
        """
        if not self.exists():
            return []

        lines: deque = deque(maxlen=num_lines)
        try:
            with open(self._log_path, "r", encoding="utf-8", errors="replace") as f:
                # Seek to end and work backwards for efficiency
                f.seek(0, 2)
                file_size = f.tell()

                # Read last chunk (estimate ~200 bytes per line)
                chunk_size = min(file_size, num_lines * 200)
                f.seek(max(0, file_size - chunk_size))

                # Read and split into lines
                text = f.read()
                all_lines = text.splitlines()

                # Return last num_lines
                return all_lines[-num_lines:]
        except (OSError, IOError):
            return []

    def check_for_errors(
        self, window_lines: int = 100
    ) -> List[Tuple[int, str, str]]:
        """Scan recent logs for error keywords.

        Returns list of (line_offset_from_end, keyword_matched, line_text).
        line_offset_from_end counts backwards: 0 = last line.
        """
        recent = self.get_recent_logs(window_lines)
        if not recent:
            return []

        results = []
        total = len(recent)

        for i, line in enumerate(recent):
            line_lower = line.lower()

            # Skip known harmless patterns
            if any(pat.search(line) for pat in _SKIP_PATTERNS):
                continue

            for keyword in _ERROR_KEYWORDS:
                if keyword in line_lower:
                    offset_from_end = total - 1 - i
                    results.append((offset_from_end, keyword, line.strip()))
                    break  # One match per line is enough

        return results

    def get_crash_reports(self, window_lines: int = 500) -> List[dict]:
        """Extract structured crash reports from recent logs.

        Looks for the 'Audio queue timeout' → 'Windows Exception' pattern
        that indicates an Ableton crash.
        """
        recent = self.get_recent_logs(window_lines)
        if not recent:
            return []

        crashes = []
        i = 0
        while i < len(recent):
            line = recent[i]
            if "Audio queue timeout" in line:
                # Found start of a crash sequence
                crash = {
                    "start_line": i,
                    "timeout_lines": [line.strip()],
                    "exception_line": None,
                    "context_before": [],
                    "context_after": [],
                }

                # Gather context: 5 lines before
                start = max(0, i - 5)
                crash["context_before"] = [l.strip() for l in recent[start:i]]

                # Scan forward for more timeouts and the exception
                j = i + 1
                while j < len(recent) and j < i + 30:
                    fwd = recent[j]
                    if "Audio queue timeout" in fwd:
                        crash["timeout_lines"].append(fwd.strip())
                    elif "Exception" in fwd:
                        crash["exception_line"] = fwd.strip()
                        # Grab 3 lines after the exception
                        crash["context_after"] = [
                            l.strip() for l in recent[j + 1 : j + 4]
                        ]
                        i = j  # Skip past this crash block
                        break
                    j += 1

                crashes.append(crash)
            i += 1

        return crashes

    def search(self, pattern: str, num_lines: int = 500) -> List[str]:
        """Search recent logs for a regex pattern."""
        recent = self.get_recent_logs(num_lines)
        compiled = re.compile(pattern, re.IGNORECASE)
        return [line.strip() for line in recent if compiled.search(line)]
