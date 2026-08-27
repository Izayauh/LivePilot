"""Tests for mcp_server.instance_guard.

The sweep is tested against mocked psutil so the suite never terminates
real processes on the machine running it.
"""

import os
import socket
import time
import unittest
from unittest.mock import MagicMock, patch

from mcp_server.instance_guard import (
    _matches_target_script,
    check_reply_port,
    sweep_stale_instances,
)


class TestMatchesTargetScript(unittest.TestCase):
    def test_windows_absolute_path(self):
        self.assertTrue(_matches_target_script(
            ["python", r"C:\Users\isaia\Projects\music\live-pilot\run_mcp_server.py"]
        ))

    def test_forward_slash_path(self):
        self.assertTrue(_matches_target_script(
            ["python", "C:/Users/isaia/Projects/music/live-pilot/run_mcp_server.py"]
        ))

    def test_bare_name(self):
        self.assertTrue(_matches_target_script(["python", "run_mcp_server.py"]))

    def test_other_mcp_server_not_matched(self):
        self.assertFalse(_matches_target_script(
            ["python", r"C:\Users\isaia\Projects\ai-agents\isaiah-context-mcp\run_context_mcp_server.py"]
        ))

    def test_module_invocation_not_matched(self):
        self.assertFalse(_matches_target_script(["python", "-m", "mcp_server"]))

    def test_empty_cmdline(self):
        self.assertFalse(_matches_target_script(None))
        self.assertFalse(_matches_target_script([]))


def _fake_proc(pid, name, cmdline, age_seconds, username="HOST\\isaia"):
    proc = MagicMock()
    proc.info = {
        "pid": pid,
        "name": name,
        "cmdline": cmdline,
        "create_time": time.time() - age_seconds,
        "username": username,
    }
    return proc


class TestSweepStaleInstances(unittest.TestCase):
    def _run_sweep(self, procs, grace_seconds=60.0):
        me = MagicMock()
        me.pid = os.getpid()
        me.username.return_value = "HOST\\isaia"
        with patch("psutil.Process", return_value=me), \
                patch("psutil.process_iter", return_value=procs):
            return sweep_stale_instances(grace_seconds=grace_seconds)

    def test_stale_instance_terminated(self):
        stale = _fake_proc(111, "python.exe", ["python", "run_mcp_server.py"], age_seconds=3600)
        killed = self._run_sweep([stale])
        stale.terminate.assert_called_once()
        self.assertEqual([entry["pid"] for entry in killed], [111])

    def test_young_instance_spared(self):
        young = _fake_proc(222, "python.exe", ["python", "run_mcp_server.py"], age_seconds=5)
        killed = self._run_sweep([young])
        young.terminate.assert_not_called()
        self.assertEqual(killed, [])

    def test_self_and_unrelated_processes_ignored(self):
        myself = _fake_proc(os.getpid(), "python.exe", ["python", "run_mcp_server.py"], age_seconds=3600)
        other_script = _fake_proc(333, "python.exe", ["python", "run_context_mcp_server.py"], age_seconds=3600)
        non_python = _fake_proc(444, "claude.exe", ["claude", "run_mcp_server.py"], age_seconds=3600)
        killed = self._run_sweep([myself, other_script, non_python])
        for proc in (myself, other_script, non_python):
            proc.terminate.assert_not_called()
        self.assertEqual(killed, [])

    def test_other_user_instance_spared(self):
        foreign = _fake_proc(
            555, "python.exe", ["python", "run_mcp_server.py"],
            age_seconds=3600, username="HOST\\someoneelse",
        )
        killed = self._run_sweep([foreign])
        foreign.terminate.assert_not_called()
        self.assertEqual(killed, [])


class TestCheckReplyPort(unittest.TestCase):
    TEST_PORT = 19881  # throwaway port so tests never touch the real 11001

    def test_free_port_reported_free(self):
        status = check_reply_port(port=self.TEST_PORT)
        self.assertTrue(status["free"])

    def test_held_port_reported_held(self):
        holder = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                holder.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            holder.bind(("127.0.0.1", self.TEST_PORT))
            status = check_reply_port(port=self.TEST_PORT)
            self.assertFalse(status["free"])
        finally:
            holder.close()


if __name__ == "__main__":
    unittest.main()
