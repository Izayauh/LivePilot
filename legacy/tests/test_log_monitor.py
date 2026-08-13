"""Tests for discovery.log_monitor.LogMonitor"""
import os
import tempfile
import textwrap

import pytest

from discovery.log_monitor import LogMonitor, _detect_ableton_log


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_log(tmp_path):
    """Create a temporary log file with sample content."""
    log_file = tmp_path / "Log.txt"
    log_file.write_text(textwrap.dedent("""\
        2026-02-14T02:30:00 Info: Ableton Live started
        2026-02-14T02:30:01 Info: Loading project
        2026-02-14T02:30:02 Info: AbletonOSC initialized
        2026-02-14T02:30:05 [JarvisDeviceLoader] Received OSC: /jarvis/device/load [0, 'EQ Eight', -1]
        2026-02-14T02:30:06 [JarvisDeviceLoader]   FOUND in known category: EQ Eight
        2026-02-14T02:30:06 [JarvisDeviceLoader] Devices on track before load: 0
        2026-02-14T02:30:07 Internal Error: From 5 to Audio queue timeout.
        2026-02-14T02:30:08 Internal Error: From 5 to Audio queue timeout.
        2026-02-14T02:30:09 Internal Error: From 5 to Audio queue timeout.
        2026-02-14T02:30:10 Exception: Windows Exception
        2026-02-14T02:30:11 Info: Recovering...
        2026-02-14T02:35:00 Info: Normal operation resumed
        2026-02-14T02:35:01 Info: Track 1 muted
        2026-02-14T02:35:02 Info: No error encountered
        2026-02-14T02:35:03 Info: Operation complete
    """), encoding="utf-8")
    return str(log_file)


@pytest.fixture
def monitor(fake_log):
    return LogMonitor(log_path=fake_log)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLogMonitorInit:
    def test_explicit_path(self, fake_log):
        m = LogMonitor(log_path=fake_log)
        assert m.get_log_path() == fake_log

    def test_missing_path_raises_on_auto_detect(self):
        """When no log_path is given and auto-detect fails, raise FileNotFoundError."""
        import discovery.log_monitor as lm
        original = lm._detect_ableton_log
        lm._detect_ableton_log = lambda: None
        try:
            with pytest.raises(FileNotFoundError):
                LogMonitor()
        finally:
            lm._detect_ableton_log = original

    def test_exists(self, monitor, fake_log):
        assert monitor.exists() is True

    def test_not_exists(self, tmp_path):
        m = LogMonitor(log_path=str(tmp_path / "gone.txt"))
        assert m.exists() is False


class TestGetRecentLogs:
    def test_returns_last_n_lines(self, monitor):
        lines = monitor.get_recent_logs(3)
        assert len(lines) == 3
        assert "Operation complete" in lines[-1]

    def test_returns_all_if_fewer(self, monitor):
        lines = monitor.get_recent_logs(1000)
        assert len(lines) == 15  # all lines in fake log

    def test_empty_for_missing_file(self, tmp_path):
        m = LogMonitor(log_path=str(tmp_path / "nope.txt"))
        assert m.get_recent_logs(10) == []


class TestCheckForErrors:
    def test_finds_crash_keywords(self, monitor):
        errors = monitor.check_for_errors(window_lines=100)
        keywords_found = {kw for _, kw, _ in errors}
        # "Internal Error: ... Audio queue timeout" matches "error" keyword
        assert "error" in keywords_found
        assert "exception" in keywords_found
        # At least 4 error lines: 3 timeouts + 1 exception
        assert len(errors) >= 4

    def test_skips_no_error_lines(self, monitor):
        errors = monitor.check_for_errors(window_lines=100)
        # "No error encountered" line should be skipped
        error_lines = [line for _, _, line in errors]
        assert not any("No error" in l for l in error_lines)

    def test_returns_empty_for_clean_log(self, tmp_path):
        log = tmp_path / "clean.txt"
        log.write_text("Info: All good\nInfo: Still good\n", encoding="utf-8")
        m = LogMonitor(log_path=str(log))
        assert m.check_for_errors() == []


class TestGetCrashReports:
    def test_detects_crash_sequence(self, monitor):
        crashes = monitor.get_crash_reports(window_lines=100)
        assert len(crashes) == 1

        crash = crashes[0]
        assert len(crash["timeout_lines"]) == 3
        assert "Windows Exception" in crash["exception_line"]
        assert len(crash["context_before"]) > 0

    def test_no_crashes_in_clean_log(self, tmp_path):
        log = tmp_path / "clean.txt"
        log.write_text("Info: Normal\nInfo: Fine\n", encoding="utf-8")
        m = LogMonitor(log_path=str(log))
        assert m.get_crash_reports() == []


class TestSearch:
    def test_search_pattern(self, monitor):
        results = monitor.search(r"JarvisDeviceLoader.*FOUND")
        assert len(results) == 1
        assert "FOUND in known category" in results[0]

    def test_search_no_match(self, monitor):
        results = monitor.search(r"NONEXISTENT_PATTERN_XYZ")
        assert results == []


class TestAutoDetect:
    def test_detect_returns_string_or_none(self):
        result = _detect_ableton_log()
        # On a machine with Ableton installed, this returns a path
        # On CI, it returns None
        assert result is None or os.path.isfile(result)
