#!/usr/bin/env python3
"""
Smoke tests for jarvis_desktop_openclaw.py

Run:
    python tests/test_desktop_openclaw.py          (Windows venv)
    python3 tests/test_desktop_openclaw.py         (WSL)
"""

import importlib.util
import asyncio
import json
import os
import sys
import types
import unittest

_MOD_PATH = os.path.join(os.path.dirname(__file__), "..", "jarvis_desktop_openclaw.py")

# Provide a tkinter stub so the module can be imported on headless / WSL
# systems where tkinter is not installed.
if "tkinter" not in sys.modules:
    _tk_stub = types.ModuleType("tkinter")
    _tk_stub.Tk = type("Tk", (), {})
    _tk_stub.BOTH = _tk_stub.WORD = _tk_stub.DISABLED = _tk_stub.NORMAL = ""
    _tk_stub.END = _tk_stub.LEFT = _tk_stub.X = ""
    _tk_stub.StringVar = type("StringVar", (), {"__init__": lambda *a, **k: None})
    _scrolled = types.ModuleType("tkinter.scrolledtext")
    _scrolled.ScrolledText = type("ScrolledText", (), {})
    _ttk = types.ModuleType("tkinter.ttk")
    _ttk.Frame = _ttk.Entry = _ttk.Button = _ttk.Label = type("W", (), {})
    sys.modules["tkinter"] = _tk_stub
    sys.modules["tkinter.scrolledtext"] = _scrolled
    sys.modules["tkinter.ttk"] = _ttk

_spec = importlib.util.spec_from_file_location("jarvis_desktop_openclaw", _MOD_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


class TestExtractReply(unittest.TestCase):
    """Verify JSON reply extraction across formats."""

    def test_top_level_reply(self):
        self.assertEqual(mod.extract_reply({"reply": "ok"}), "ok")

    def test_top_level_message(self):
        self.assertEqual(mod.extract_reply({"message": "hi"}), "hi")

    def test_top_level_output(self):
        self.assertEqual(mod.extract_reply({"output": "done"}), "done")

    def test_top_level_text(self):
        self.assertEqual(mod.extract_reply({"text": "yo"}), "yo")

    def test_nested_result_reply(self):
        self.assertEqual(mod.extract_reply({"result": {"reply": "nested"}}), "nested")

    def test_nested_result_message(self):
        self.assertEqual(mod.extract_reply({"result": {"message": "msg"}}), "msg")

    def test_result_payloads_single(self):
        data = {"result": {"payloads": [{"text": "hello from relay"}]}}
        self.assertEqual(mod.extract_reply(data), "hello from relay")

    def test_result_payloads_multiple(self):
        data = {"result": {"payloads": [{"text": "line1"}, {"text": "line2"}]}}
        self.assertEqual(mod.extract_reply(data), "line1\n\nline2")

    def test_result_payloads_skip_empty(self):
        data = {"result": {"payloads": [{"text": ""}, {"text": "real"}]}}
        self.assertEqual(mod.extract_reply(data), "real")

    def test_real_openclaw_response(self):
        """Exact structure from a real OpenClaw jarvis-relay response."""
        data = {
            "runId": "06b2bc47",
            "status": "ok",
            "result": {
                "payloads": [{"text": "Yep, I\u2019m here", "mediaUrl": None}],
                "meta": {"durationMs": 1659},
            },
        }
        self.assertEqual(mod.extract_reply(data), "Yep, I\u2019m here")

    def test_choices_message_content(self):
        data = {"choices": [{"message": {"content": "choice"}}]}
        self.assertEqual(mod.extract_reply(data), "choice")

    def test_choices_text_string(self):
        data = {"choices": [{"text": "plain"}]}
        self.assertEqual(mod.extract_reply(data), "plain")

    def test_fallback_json(self):
        data = {"unknown": 42}
        self.assertIn("unknown", mod.extract_reply(data))

    def test_non_dict(self):
        self.assertEqual(mod.extract_reply("raw string"), "raw string")

    def test_whitespace_skipped(self):
        self.assertEqual(mod.extract_reply({"reply": "  ", "message": "real"}), "real")

    def test_priority_order(self):
        self.assertEqual(
            mod.extract_reply({"reply": "a", "message": "b", "text": "c"}), "a"
        )


class TestCommandBuilders(unittest.TestCase):
    """Verify WSL and native command construction."""

    def test_wsl_command_structure(self):
        cmd = mod._build_wsl_command("hello")
        self.assertTrue(cmd[0].endswith("wsl.exe"))
        self.assertIn("-e", cmd)
        self.assertIn("bash", cmd)
        # Should use -c (non-login) not -lc (login) to avoid ~/.bashrc interactive guard
        self.assertEqual(cmd[3], "-c")
        inner = cmd[-1]
        self.assertIn("openclaw.mjs", inner)
        self.assertIn("hello", inner)
        self.assertIn("--json", inner)

    def test_native_command_structure(self):
        cmd = mod._build_native_command("test msg")
        self.assertIn("node", cmd[0])
        self.assertIn("openclaw.mjs", cmd[1])
        self.assertIn("--message", cmd)
        self.assertIn("test msg", cmd)

    def test_candidates_not_empty(self):
        cands = mod._pick_candidates("x")
        self.assertGreater(len(cands), 0)

    def test_timeout_propagated(self):
        cmd = mod._build_wsl_command("hi", timeout=99)
        self.assertIn("99", cmd[-1])


class TestNoGoogleImports(unittest.TestCase):
    """Guarantee no google.genai dependency."""

    def test_no_genai_in_source(self):
        with open(_MOD_PATH) as f:
            src = f.read()
        self.assertNotIn("google.genai", src)
        self.assertNotIn("google.generativeai", src)
        self.assertNotIn("import genai", src)
        self.assertNotIn("jarvis_engine", src)


class TestSyntax(unittest.TestCase):
    def test_compiles(self):
        with open(_MOD_PATH) as f:
            compile(f.read(), _MOD_PATH, "exec")


class TestLocalIntentRouter(unittest.TestCase):
    def setUp(self):
        self.backend = mod.OpenClawBackend()

    def test_parse_get_track_list(self):
        parsed = self.backend._parse_local_tool_intent("get track list")
        self.assertEqual(parsed["fn"], "get_track_list")
        self.assertEqual(parsed["args"], {})

    def test_parse_get_track_devices(self):
        parsed = self.backend._parse_local_tool_intent("get track devices on track 3")
        self.assertEqual(parsed["fn"], "get_track_devices")
        self.assertEqual(parsed["args"]["track_index"], 2)

    def test_parse_add_plugin(self):
        parsed = self.backend._parse_local_tool_intent("add plugin EQ Eight on track 2")
        self.assertEqual(parsed["fn"], "add_plugin_to_track")
        self.assertEqual(parsed["args"]["track_index"], 1)
        self.assertEqual(parsed["args"]["plugin_name"], "EQ Eight")

    def test_parse_track_state(self):
        parsed = self.backend._parse_local_tool_intent("solo track 4")
        self.assertEqual(parsed["fn"], "solo_track")
        self.assertEqual(parsed["args"], {"track_index": 3, "soloed": 1})

    def test_parse_set_tempo(self):
        parsed = self.backend._parse_local_tool_intent("set tempo to 123.5 bpm")
        self.assertEqual(parsed["fn"], "set_tempo")
        self.assertEqual(parsed["args"]["bpm"], 123.5)

    def test_parse_set_device_parameter(self):
        parsed = self.backend._parse_local_tool_intent(
            "set device parameter 8 on device 2 on track 1 to 0.5"
        )
        self.assertEqual(parsed["fn"], "set_device_parameter")
        self.assertEqual(
            parsed["args"],
            {"track_index": 0, "device_index": 1, "param_index": 7, "value": 0.5},
        )

    def test_parse_fail_returns_structured_error(self):
        parsed = self.backend._parse_local_tool_intent("set tempo to fast")
        self.assertIn("error", parsed)
        data = json.loads(parsed["error"])
        self.assertFalse(data["success"])
        self.assertEqual(data["error"]["code"], "ABLETON_INTENT_PARSE_FAILED")

    def test_non_ableton_is_none(self):
        self.assertIsNone(self.backend._parse_local_tool_intent("tell me a joke"))


class TestLocalFirstSendMessage(unittest.TestCase):
    def setUp(self):
        self.backend = mod.OpenClawBackend()
        self._orig_call_openclaw = mod.call_openclaw

    def tearDown(self):
        mod.call_openclaw = self._orig_call_openclaw

    def test_ableton_intent_executes_local_bridge(self):
        calls = {}

        def fake_bridge(fn, args):
            calls["fn"] = fn
            calls["args"] = args
            return '{"success": true}'

        self.backend._run_local_bridge = fake_bridge
        mod.call_openclaw = lambda *_args, **_kwargs: "relay should not be used"

        out = asyncio.run(self.backend.send_message("get track devices on track 2"))
        self.assertEqual(out, ['{"success": true}'])
        self.assertEqual(calls["fn"], "get_track_devices")
        self.assertEqual(calls["args"]["track_index"], 1)

    def test_ableton_parse_failure_does_not_relay(self):
        mod.call_openclaw = lambda *_args, **_kwargs: "relay should not be used"
        out = asyncio.run(self.backend.send_message("mute track x"))
        data = json.loads(out[0])
        self.assertFalse(data["success"])
        self.assertEqual(data["error"]["code"], "ABLETON_INTENT_PARSE_FAILED")

    def test_non_ableton_uses_relay(self):
        mod.call_openclaw = lambda *_args, **_kwargs: "relay ok"
        out = asyncio.run(self.backend.send_message("what is compression?"))
        self.assertEqual(out, ["relay ok"])


if __name__ == "__main__":
    unittest.main()
