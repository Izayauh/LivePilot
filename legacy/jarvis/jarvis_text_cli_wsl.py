#!/usr/bin/env python3
"""
Jarvis-Ableton WSL Text Chat CLI
Backend: OpenClaw relay (WSL native) — no Gemini/OpenAI keys required.
"""

import json
import shutil
import subprocess
import sys


BANNER = r"""
==================================================
  JARVIS-ABLETON  |  WSL Text Chat
  Backend: OpenClaw relay (WSL native)
==================================================
Commands:
  /health  — check OpenClaw connectivity
  /quit    — exit
==================================================
"""


def _resolve_openclaw() -> str:
    """Find the openclaw binary, preferring the WSL-native PATH."""
    path = shutil.which("openclaw")
    if path:
        return path
    # Common fnm / npm global install locations
    import pathlib
    for candidate in pathlib.Path.home().glob(".local/share/fnm/**/openclaw"):
        if candidate.is_file():
            return str(candidate)
    return "openclaw"  # fallback — let subprocess raise FileNotFoundError


OPENCLAW_BIN = _resolve_openclaw()
OPENCLAW_CMD = [OPENCLAW_BIN, "agent", "--agent", "jarvis-relay", "--json", "--timeout", "30"]


def extract_reply(data):
    """Extract the best available assistant text from an OpenClaw JSON response.

    Tries common field paths in priority order.
    """
    if not isinstance(data, dict):
        return str(data)

    # Top-level fields
    for key in ("reply", "message", "output", "text", "response", "content"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    # Nested under "result"
    result = data.get("result")
    if isinstance(result, dict):
        for key in ("reply", "message", "output", "text", "response", "content"):
            val = result.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()

    # Nested under "choices" (list of dicts)
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            msg = first.get("message") or first.get("text")
            if isinstance(msg, dict):
                c = msg.get("content")
                if isinstance(c, str) and c.strip():
                    return c.strip()
            if isinstance(msg, str) and msg.strip():
                return msg.strip()

    # Fallback: pretty-print the whole payload
    return json.dumps(data, indent=2)


def call_openclaw(message: str) -> str:
    """Send a message to the OpenClaw jarvis-relay agent and return the reply."""
    cmd = OPENCLAW_CMD + ["--message", message]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        return "[ERROR] 'openclaw' command not found. Is it installed and on PATH?"
    except subprocess.TimeoutExpired:
        return "[ERROR] OpenClaw timed out after 60 seconds."

    if proc.returncode != 0:
        stderr = proc.stderr.strip() if proc.stderr else "(no stderr)"
        return f"[ERROR] OpenClaw exited with code {proc.returncode}\n{stderr}"

    raw = proc.stdout.strip()
    if not raw:
        return "[ERROR] OpenClaw returned empty output."

    try:
        data = json.loads(raw)
        return extract_reply(data)
    except json.JSONDecodeError:
        # Not JSON — return raw text
        return raw


def health_check() -> str:
    """Run a lightweight connectivity check against OpenClaw."""
    try:
        proc = subprocess.run(
            [OPENCLAW_BIN, "agent", "--agent", "jarvis-relay", "--json", "--timeout", "10",
             "--message", "ping"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except FileNotFoundError:
        return "FAIL — 'openclaw' not found on PATH"
    except subprocess.TimeoutExpired:
        return "FAIL — timed out (20 s)"

    if proc.returncode == 0:
        return "OK — OpenClaw jarvis-relay reachable"
    stderr = proc.stderr.strip() if proc.stderr else "(no stderr)"
    return f"FAIL — exit code {proc.returncode}\n{stderr}"


def main():
    print(BANNER)
    print(f"  openclaw resolved: {OPENCLAW_BIN}")
    if not shutil.which(OPENCLAW_BIN):
        print("\n  [WARN] openclaw binary not found on PATH.")
        print("  Make sure you launched this script with WSL python3, NOT ./venv/Scripts/python.exe")
        print("  Correct:  python3 jarvis_text_cli_wsl.py")
        print()

    while True:
        try:
            user_input = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not user_input:
            continue

        lower = user_input.lower()

        if lower == "/quit":
            print("Goodbye.")
            break

        if lower == "/health":
            print(f"[Health] {health_check()}")
            continue

        reply = call_openclaw(user_input)
        print(f"Jarvis> {reply}")
        print()


if __name__ == "__main__":
    main()
