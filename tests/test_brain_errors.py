"""Claude errors reach the window as the fix in plain words, and the bundled CLI runs quiet.
No TCP and no Claude: the session and the client are faked."""

from __future__ import annotations

import asyncio

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

from livepilot_tools import workflows
from studio import brain, config


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(brain, "_handler_names", lambda: [])
    monkeypatch.setattr(workflows, "session", lambda: {"success": False, "message": "not open"})


class FakeClient:
    def __init__(self, *messages):
        self.messages = messages

    async def query(self, prompt):
        pass

    async def receive_response(self):
        for m in self.messages:
            yield m


def said(text, *, error=None):
    return AssistantMessage(content=[TextBlock(text=text)], model="m", error=error)


def result(text=None, is_error=True):
    return ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=is_error, num_turns=1,
                         session_id="s", result=text)


def turn(*messages):
    out = []
    b = brain.Brain(emit=out.append)
    b.client = FakeClient(*messages)
    t = asyncio.run(b.ask("turn the bass up"))
    return [e["text"] for e in out if e["type"] == "say"], t


def test_not_logged_in():
    says, t = turn(said("Not logged in · Please run /login"), result("Not logged in · Please run /login"))
    assert len(says) == 1 and "install.ps1 -Login" in says[0]
    assert t["reply"] == "" and "Not logged in" in t["error"]


def test_auth_error_code_without_known_text():
    says, _ = turn(said("Something about credentials", error="authentication_failed"))
    assert says == [brain.plain_error("", "authentication_failed")] and "install.ps1 -Login" in says[0]


def test_model_not_on_the_plan():
    says, _ = turn(result("There's an issue with the selected model (claude-x). It may not exist or you may not "
                          "have access to it. Run --model to pick a different model."))
    assert len(says) == 1 and "config.json to one your plan includes" in says[0]


def test_usage_limit():
    for line in ("Claude AI usage limit reached|1760000000", "5-hour limit reached ∙ resets 3pm",
                 "You've hit your limit · resets 9pm"):
        says, _ = turn(said(line), result(line))
        assert says == ["Your Claude plan's usage limit is reached; it resets on its own, see claude.ai for when."]


def test_unknown_error_still_says_something():
    says, _ = turn(result("API Error: 500 Internal server error"))
    assert says == ["Claude could not answer that one: API Error: 500 Internal server error"]


def test_a_normal_reply_passes_untouched():
    says, t = turn(said("Bass 0 dB -> +2 dB. The limiter is set to -1 dB."), result("done", is_error=False))
    assert says == ["Bass 0 dB -> +2 dB. The limiter is set to -1 dB."] and "error" not in t


def test_the_cli_runs_without_telemetry(monkeypatch):
    seen = {}

    class Client:
        def __init__(self, options):
            seen["options"] = options

        async def connect(self):
            pass

    monkeypatch.setattr(brain, "ClaudeSDKClient", Client)
    monkeypatch.setattr(config, "load", lambda: dict(config.DEFAULTS))
    b = brain.Brain(emit=lambda e: None)
    asyncio.run(b.start())
    env = seen["options"].env
    assert env["DISABLE_TELEMETRY"] == "1" and env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1"
    assert b.client is not None


def test_a_failed_connect_leaves_no_client(monkeypatch):
    class Client:
        def __init__(self, options):
            pass

        async def connect(self):
            raise RuntimeError("cli missing")

    monkeypatch.setattr(brain, "ClaudeSDKClient", Client)
    monkeypatch.setattr(config, "load", lambda: dict(config.DEFAULTS))
    b = brain.Brain(emit=lambda e: None)
    with pytest.raises(RuntimeError):
        asyncio.run(b.start())
    assert b.client is None


def test_prompt_and_tools_use_they():
    import re
    text = brain.SYSTEM + " ".join(t.description for t in brain.Brain(emit=lambda e: None)._tools())
    assert not re.search(r"\b(he|his|him)\b", text, re.I)
