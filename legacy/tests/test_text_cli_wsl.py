#!/usr/bin/env python3
"""
Smoke tests for jarvis_text_cli_wsl.py
Run:  python tests/test_text_cli_wsl.py
"""

import importlib.util
import json
import os
import sys
import unittest

# Import the CLI module from the repo root
CLI_PATH = os.path.join(os.path.dirname(__file__), "..", "jarvis_text_cli_wsl.py")
spec = importlib.util.spec_from_file_location("jarvis_text_cli_wsl", CLI_PATH)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class TestExtractReply(unittest.TestCase):
    """Unit tests for the JSON reply extraction logic."""

    def test_top_level_reply(self):
        self.assertEqual(cli.extract_reply({"reply": "hello"}), "hello")

    def test_top_level_message(self):
        self.assertEqual(cli.extract_reply({"message": "hi there"}), "hi there")

    def test_top_level_output(self):
        self.assertEqual(cli.extract_reply({"output": "done"}), "done")

    def test_top_level_text(self):
        self.assertEqual(cli.extract_reply({"text": "yo"}), "yo")

    def test_nested_result_reply(self):
        data = {"result": {"reply": "nested hello"}}
        self.assertEqual(cli.extract_reply(data), "nested hello")

    def test_nested_result_message(self):
        data = {"result": {"message": "nested msg"}}
        self.assertEqual(cli.extract_reply(data), "nested msg")

    def test_choices_message_content(self):
        data = {"choices": [{"message": {"content": "choice text"}}]}
        self.assertEqual(cli.extract_reply(data), "choice text")

    def test_choices_text_string(self):
        data = {"choices": [{"text": "plain choice"}]}
        self.assertEqual(cli.extract_reply(data), "plain choice")

    def test_fallback_to_json_dump(self):
        data = {"unknown_field": 42}
        result = cli.extract_reply(data)
        self.assertIn("unknown_field", result)

    def test_non_dict_input(self):
        self.assertEqual(cli.extract_reply("just a string"), "just a string")

    def test_empty_strings_skipped(self):
        data = {"reply": "  ", "message": "actual"}
        self.assertEqual(cli.extract_reply(data), "actual")

    def test_priority_order(self):
        data = {"reply": "first", "message": "second", "output": "third"}
        self.assertEqual(cli.extract_reply(data), "first")


class TestNoGoogleImport(unittest.TestCase):
    """Verify the module does not import google.genai."""

    def test_no_google_genai(self):
        self.assertNotIn("google.genai", sys.modules)
        self.assertNotIn("google.generativeai", sys.modules)

    def test_source_has_no_genai(self):
        with open(CLI_PATH) as f:
            source = f.read()
        self.assertNotIn("google.genai", source)
        self.assertNotIn("google.generativeai", source)
        self.assertNotIn("genai", source)


class TestSyntax(unittest.TestCase):
    """Verify the module compiles cleanly."""

    def test_compile(self):
        with open(CLI_PATH) as f:
            source = f.read()
        compile(source, CLI_PATH, "exec")


if __name__ == "__main__":
    unittest.main()
