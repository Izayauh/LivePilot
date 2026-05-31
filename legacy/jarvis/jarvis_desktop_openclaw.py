#!/usr/bin/env python3
"""
Jarvis-Ableton Desktop Chat — OpenClaw relay backend (no Gemini/OpenAI).

Launch from Windows PowerShell:
    .\\venv\\Scripts\\python.exe jarvis_desktop_openclaw.py

Launch from WSL:
    cd /mnt/c/Users/isaia/Documents/JarvisAbleton
    ./venv/Scripts/python.exe jarvis_desktop_openclaw.py
"""

import asyncio
import json
import logging
import os
import platform
import queue
import random
import re
import shlex
import subprocess
import threading
import time
import tkinter as tk
from tkinter import scrolledtext, ttk

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WSL_EXE = r"C:\Windows\System32\wsl.exe"

# Absolute paths inside WSL — avoids PATH / fnm-shell issues.
_NODE = (
    "/home/isaiah/.local/share/fnm/node-versions"
    "/v22.22.0/installation/bin/node"
)
_OPENCLAW_MJS = (
    "/home/isaiah/.local/share/fnm/node-versions"
    "/v22.22.0/installation/lib/node_modules/openclaw/openclaw.mjs"
)

AGENT_ID = os.getenv("JARVIS_TEXT_OPENCLAW_AGENT", "main").strip()
TIMEOUT_SEC = 30
WIN_PY = r"C:\Users\isaia\Documents\JarvisAbleton\venv\Scripts\python.exe"
WIN_BRIDGE = r"C:\Users\isaia\Documents\JarvisAbleton\ableton_bridge.py"

# Retry / resilience settings (configurable via env)
OPENCLAW_MAX_RETRIES = max(1, int(os.getenv("OPENCLAW_MAX_RETRIES", "3")))
OPENCLAW_RETRY_BASE_DELAY = float(os.getenv("OPENCLAW_RETRY_BASE_DELAY", "2.0"))
OPENCLAW_COOLDOWN_SEC = int(os.getenv("OPENCLAW_COOLDOWN_SEC", "60"))

# ---------------------------------------------------------------------------
# Circuit breaker — prevents hammering the LLM during cooldown
# ---------------------------------------------------------------------------

_RATE_LIMIT_PATTERNS = (
    "rate_limit", "cooldown", "failovererror",
    "all models failed", "429", "quota", "resource_exhausted",
)


def _is_rate_limit_error(text: str) -> bool:
    """Return True if *text* looks like a provider rate-limit / cooldown error."""
    lower = text.lower()
    return any(p in lower for p in _RATE_LIMIT_PATTERNS)


class _CircuitBreaker:
    """Simple time-based circuit breaker for the OpenClaw relay."""

    def __init__(self, cooldown_sec: int = OPENCLAW_COOLDOWN_SEC):
        self.cooldown_sec = cooldown_sec
        self._open_until: float = 0.0

    def is_open(self) -> bool:
        return time.time() < self._open_until

    def remaining(self) -> int:
        return max(0, int(self._open_until - time.time()))

    def trip(self) -> None:
        self._open_until = time.time() + self.cooldown_sec
        log.warning("Circuit breaker OPEN — cooling down for %ds", self.cooldown_sec)

    def reset(self) -> None:
        if self._open_until:
            log.info("Circuit breaker reset (provider recovered)")
        self._open_until = 0.0


_breaker = _CircuitBreaker()


# ---------------------------------------------------------------------------
# JSON reply extraction (robust, multi-format)
# ---------------------------------------------------------------------------

def extract_reply(data):
    """Return the best human-readable text from an OpenClaw JSON response."""
    if not isinstance(data, dict):
        return str(data)

    for key in ("reply", "message", "output", "text", "response", "content"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    result = data.get("result")
    if isinstance(result, dict):
        # OpenClaw format: result.payloads[].text
        payloads = result.get("payloads")
        if isinstance(payloads, list):
            texts = []
            for p in payloads:
                if isinstance(p, dict):
                    t = p.get("text")
                    if isinstance(t, str) and t.strip():
                        texts.append(t.strip())
            if texts:
                return "\n\n".join(texts)

        for key in ("reply", "message", "output", "text", "response", "content"):
            val = result.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()

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

    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# OpenClaw subprocess helpers
# ---------------------------------------------------------------------------

def _build_wsl_command(message: str, timeout: int = TIMEOUT_SEC,
                       agent: str | None = None) -> list[str]:
    """Build a command list that calls openclaw via wsl.exe with absolute paths."""
    ag = agent or AGENT_ID
    inner = (
        f"{_NODE} {_OPENCLAW_MJS}"
        f" agent --agent {shlex.quote(ag)}"
        f" --json --timeout {timeout}"
        f" --message {shlex.quote(message)}"
    )
    return [WSL_EXE, "-e", "bash", "-c", inner]


def _build_native_command(message: str, timeout: int = TIMEOUT_SEC,
                          agent: str | None = None) -> list[str]:
    """Build a command list for direct invocation (when running inside WSL)."""
    ag = agent or AGENT_ID
    return [
        _NODE, _OPENCLAW_MJS,
        "agent", "--agent", ag,
        "--json", "--timeout", str(timeout),
        "--message", message,
    ]


def _is_windows() -> bool:
    return platform.system() == "Windows" or "microsoft" in platform.release().lower()


def _pick_candidates(message: str, timeout: int = TIMEOUT_SEC,
                     agent: str | None = None) -> list[list[str]]:
    """Return an ordered list of command candidates to try."""
    candidates = []

    # On Windows desktop, ONLY use the wsl.exe relay path.
    # The native candidate uses Linux absolute paths (/home/...) and will fail.
    if _is_windows():
        if os.path.isfile(WSL_EXE):
            candidates.append(_build_wsl_command(message, timeout, agent))
            # Fallback: wsl -- <node> <openclaw> ... (no bash wrapper)
            ag = agent or AGENT_ID
            candidates.append([
                WSL_EXE, "--",
                _NODE, _OPENCLAW_MJS,
                "agent", "--agent", ag,
                "--json", "--timeout", str(timeout),
                "--message", message,
            ])
        return candidates

    # On WSL/Linux, prefer direct native invocation.
    candidates.append(_build_native_command(message, timeout, agent))
    if os.path.isfile(WSL_EXE):
        candidates.append(_build_wsl_command(message, timeout, agent))
    return candidates


def _call_openclaw_once(message: str, timeout: int = TIMEOUT_SEC,
                       agent: str | None = None) -> tuple[str | None, str]:
    """Single attempt to call OpenClaw.  Returns (reply, error_text).

    On success reply is a non-empty string and error_text is "".
    On failure reply is None and error_text describes the problem.
    """
    candidates = _pick_candidates(message, timeout, agent)
    last_err = ""

    for cmd in candidates:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout + 15,
            )
        except FileNotFoundError:
            last_err = f"Command not found: {cmd[0]}"
            continue
        except subprocess.TimeoutExpired:
            last_err = f"Timed out ({timeout + 15}s)"
            continue

        if proc.returncode != 0:
            last_err = (proc.stderr or proc.stdout or "").strip()
            if not last_err:
                last_err = f"Exit code {proc.returncode}"
            continue

        raw = (proc.stdout or "").strip()
        if not raw:
            return "(empty response from relay)", ""

        try:
            return extract_reply(json.loads(raw)), ""
        except json.JSONDecodeError:
            return raw, ""

    return None, last_err


def call_openclaw(message: str, timeout: int = TIMEOUT_SEC,
                  agent: str | None = None) -> str:
    """Send a message to the OpenClaw agent with retry + circuit breaker.

    Retries with exponential backoff + jitter on rate-limit errors.
    A circuit breaker prevents hammering the provider during cooldown.
    """
    # --- circuit breaker check ---
    if _breaker.is_open():
        secs = _breaker.remaining()
        return (
            f"[COOLDOWN] The AI provider is rate-limited. "
            f"Please wait ~{secs}s before trying again."
        )

    max_retries = OPENCLAW_MAX_RETRIES
    base_delay = OPENCLAW_RETRY_BASE_DELAY

    for attempt in range(max_retries):
        reply, err = _call_openclaw_once(message, timeout, agent)

        # --- success ---
        if reply is not None:
            _breaker.reset()
            return reply

        # --- rate-limit error → maybe retry ---
        if _is_rate_limit_error(err):
            _breaker.trip()
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                log.warning(
                    "Rate limit detected (attempt %d/%d). "
                    "Retrying in %.1fs …  error: %s",
                    attempt + 1, max_retries, delay, err[:200],
                )
                time.sleep(delay)
                continue
            # last attempt exhausted
            return (
                f"[RATE LIMITED] The AI provider is still cooling down after "
                f"{max_retries} attempts. Please wait ~{_breaker.remaining()}s "
                f"and try again.\n{err}"
            )

        # --- non-rate-limit error → fail immediately ---
        return f"[ERROR] All relay attempts failed.\n{err}"

    return f"[ERROR] All relay attempts failed."


def health_check(agent: str | None = None) -> str:
    """Quick connectivity test against the OpenClaw relay."""
    ag = agent or AGENT_ID
    candidates = _pick_candidates("ping", timeout=10, agent=ag)
    for cmd in candidates:
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=20,
            )
            if proc.returncode == 0 and (proc.stdout or "").strip():
                return f"OK — OpenClaw agent '{ag}' reachable"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return f"FAIL — could not reach OpenClaw agent '{ag}'"


# ---------------------------------------------------------------------------
# Async backend wrapper
# ---------------------------------------------------------------------------

class OpenClawBackend:
    """Async-safe wrapper so the Tkinter event loop stays responsive."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self.agent = AGENT_ID

    async def warmup(self) -> str:
        # Pre-warm: fire a lightweight health check so the WSL/Node process
        # is already loaded by the time the user sends their first query.
        status = await asyncio.to_thread(health_check, self.agent)
        log.info("OpenClaw warmup: %s", status)
        return (
            f"Jarvis text mode is ready.\n"
            f"Backend: OpenClaw relay (desktop app)\n"
            f"Agent: {self.agent}\n"
            f"Health: {status}"
        )

    def _structured_intent_error(self, *, intent: str, input_text: str,
                                 message: str, expected: str) -> str:
        payload = {
            "success": False,
            "error": {
                "code": "ABLETON_INTENT_PARSE_FAILED",
                "intent": intent,
                "message": message,
                "expected": expected,
            },
            "input": input_text,
        }
        return json.dumps(payload, indent=2)

    def _parse_track_number(self, raw: str):
        try:
            number = int(raw)
        except Exception:
            return None, "Track number must be an integer."
        if number < 1:
            return None, "Track number must be 1 or greater."
        return number - 1, None

    def _looks_like_ableton_intent(self, lower: str) -> bool:
        if not lower:
            return False
        if re.match(r"^(get|list|show|add|load|mute|unmute|solo|unsolo|arm|disarm|set)\b", lower) is None:
            return False
        return re.search(r"\b(track|tempo|bpm|plugin|device|ableton|mute|solo|arm)\b", lower) is not None

    def _parse_local_tool_intent(self, text: str):
        raw = text.strip()
        lower = raw.lower()
        if lower in {"get track list", "list tracks", "get_track_list"}:
            return {"fn": "get_track_list", "args": {}}

        if re.match(r"^(get|list|show)\s+track\s+devices\b", lower):
            m = re.match(r"^(?:get|list|show)\s+track\s+devices\s+on\s+track\s+(\d+)\s*$", lower)
            if not m:
                return {"error": self._structured_intent_error(
                    intent="get_track_devices",
                    input_text=text,
                    message="Command matched track-device intent but required track number was missing/invalid.",
                    expected="get track devices on track <N>",
                )}
            track_index, err = self._parse_track_number(m.group(1))
            if err:
                return {"error": self._structured_intent_error(
                    intent="get_track_devices",
                    input_text=text,
                    message=err,
                    expected="get track devices on track <N>",
                )}
            return {"fn": "get_track_devices", "args": {"track_index": track_index}}

        if re.match(r"^(add|load)\s+plugin\b", lower):
            m = re.match(r"^(?:add|load)\s+plugin\s+(.+?)\s+on\s+track\s+(\d+)\s*$", raw, re.IGNORECASE)
            if not m:
                return {"error": self._structured_intent_error(
                    intent="add_plugin_to_track",
                    input_text=text,
                    message="Command matched plugin-load intent but plugin name or track number was missing/invalid.",
                    expected="add plugin <name> on track <N>",
                )}
            plugin_name = m.group(1).strip()
            if not plugin_name:
                return {"error": self._structured_intent_error(
                    intent="add_plugin_to_track",
                    input_text=text,
                    message="Plugin name cannot be empty.",
                    expected="add plugin <name> on track <N>",
                )}
            track_index, err = self._parse_track_number(m.group(2))
            if err:
                return {"error": self._structured_intent_error(
                    intent="add_plugin_to_track",
                    input_text=text,
                    message=err,
                    expected="add plugin <name> on track <N>",
                )}
            return {
                "fn": "add_plugin_to_track",
                "args": {"track_index": track_index, "plugin_name": plugin_name, "position": -1},
            }

        if re.match(r"^(unmute|mute|unsolo|solo|disarm|arm)\s+track\b", lower):
            m = re.match(r"^(unmute|mute|unsolo|solo|disarm|arm)\s+track\s+(\d+)\s*$", lower)
            if not m:
                return {"error": self._structured_intent_error(
                    intent="track_state",
                    input_text=text,
                    message="Command matched track-state intent but track number was missing/invalid.",
                    expected="<mute|unmute|solo|arm> track <N>",
                )}
            action = m.group(1)
            track_index, err = self._parse_track_number(m.group(2))
            if err:
                return {"error": self._structured_intent_error(
                    intent="track_state",
                    input_text=text,
                    message=err,
                    expected="<mute|unmute|solo|arm> track <N>",
                )}

            if action in {"mute", "unmute"}:
                return {"fn": "mute_track", "args": {"track_index": track_index, "muted": 0 if action == "unmute" else 1}}
            if action in {"solo", "unsolo"}:
                return {"fn": "solo_track", "args": {"track_index": track_index, "soloed": 0 if action == "unsolo" else 1}}
            return {"fn": "arm_track", "args": {"track_index": track_index, "armed": 0 if action == "disarm" else 1}}

        if re.match(r"^set\s+tempo\b", lower):
            m = re.match(r"^set\s+tempo\s+to\s+(-?\d+(?:\.\d+)?)\s*(?:bpm)?\s*$", lower)
            if not m:
                return {"error": self._structured_intent_error(
                    intent="set_tempo",
                    input_text=text,
                    message="Command matched tempo intent but BPM value was missing/invalid.",
                    expected="set tempo to <BPM>",
                )}
            bpm = float(m.group(1))
            if bpm <= 0:
                return {"error": self._structured_intent_error(
                    intent="set_tempo",
                    input_text=text,
                    message="BPM must be greater than 0.",
                    expected="set tempo to <BPM>",
                )}
            return {"fn": "set_tempo", "args": {"bpm": bpm}}

        if (
            re.match(r"^set\s+parameters?\s+for\s+track\s+\d+\s+vocal\s+chain\b", lower)
            or re.match(r"^apply\s+airy\s+melodic\s+vocal\s+(settings|preset)\s+on\s+track\s+\d+\b", lower)
            or re.match(r"^apply\s+punchy\s+rap\s+vocal\s+(settings|preset)\s+on\s+track\s+\d+\b", lower)
            or re.match(r"^shape\s+vocal\s+track\s+\d+\s+as\s+(airy\s+melodic|punchy\s+rap)\b", lower)
        ):
            profile = "airy_melodic"
            m = re.match(r"^set\s+parameters?\s+for\s+track\s+(\d+)\s+vocal\s+chain\s*$", lower)
            if not m:
                m = re.match(r"^apply\s+airy\s+melodic\s+vocal\s+(?:settings|preset)\s+on\s+track\s+(\d+)\s*$", lower)
                profile = "airy_melodic"
            if not m:
                m = re.match(r"^apply\s+punchy\s+rap\s+vocal\s+(?:settings|preset)\s+on\s+track\s+(\d+)\s*$", lower)
                profile = "punchy_rap"
            if not m:
                m = re.match(r"^shape\s+vocal\s+track\s+(\d+)\s+as\s+(airy\s+melodic|punchy\s+rap)\s*$", lower)
                if m:
                    profile = "airy_melodic" if "airy" in m.group(2) else "punchy_rap"
            if not m:
                return {"error": self._structured_intent_error(
                    intent="apply_vocal_profile",
                    input_text=text,
                    message="Command matched vocal-profile intent but track number was missing/invalid.",
                    expected="shape vocal track <N> as airy melodic|punchy rap",
                )}
            track_index, err = self._parse_track_number(m.group(1))
            if err:
                return {"error": self._structured_intent_error(
                    intent="apply_vocal_profile",
                    input_text=text,
                    message=err,
                    expected="shape vocal track <N> as airy melodic|punchy rap",
                )}
            return {"fn": "__apply_vocal_profile", "args": {"track_index": track_index, "profile": profile}}

        if re.match(r"^set\s+device\s+parameter\b", lower) or re.match(r"^set\s+track\s+\d+\s+device\b", lower):
            m = re.match(
                r"^set\s+device\s+parameter\s+(\d+)\s+on\s+device\s+(\d+)\s+on\s+track\s+(\d+)\s+to\s+(-?\d+(?:\.\d+)?)\s*$",
                lower,
            )
            if not m:
                m = re.match(
                    r"^set\s+track\s+(\d+)\s+device\s+(\d+)\s+parameter\s+(\d+)\s+to\s+(-?\d+(?:\.\d+)?)\s*$",
                    lower,
                )
                if m:
                    track_num = m.group(1)
                    device_num = m.group(2)
                    param_num = m.group(3)
                    value_num = m.group(4)
                else:
                    return {"error": self._structured_intent_error(
                        intent="set_device_parameter",
                        input_text=text,
                        message="Command matched device-parameter intent but required explicit indices/value were missing/invalid.",
                        expected="set device parameter <P> on device <D> on track <T> to <V>",
                    )}
            else:
                param_num = m.group(1)
                device_num = m.group(2)
                track_num = m.group(3)
                value_num = m.group(4)

            track_index, err = self._parse_track_number(track_num)
            if err:
                return {"error": self._structured_intent_error(
                    intent="set_device_parameter",
                    input_text=text,
                    message=err,
                    expected="set device parameter <P> on device <D> on track <T> to <V>",
                )}

            try:
                device_index = int(device_num) - 1
                param_index = int(param_num) - 1
                value = float(value_num)
            except Exception:
                return {"error": self._structured_intent_error(
                    intent="set_device_parameter",
                    input_text=text,
                    message="Device index, parameter index, and value must be numeric.",
                    expected="set device parameter <P> on device <D> on track <T> to <V>",
                )}

            if device_index < 0 or param_index < 0:
                return {"error": self._structured_intent_error(
                    intent="set_device_parameter",
                    input_text=text,
                    message="Device index and parameter index must be 1 or greater.",
                    expected="set device parameter <P> on device <D> on track <T> to <V>",
                )}

            return {
                "fn": "set_device_parameter",
                "args": {
                    "track_index": track_index,
                    "device_index": device_index,
                    "param_index": param_index,
                    "value": value,
                },
            }

        if self._looks_like_ableton_intent(lower):
            # Fallback to relay for richer natural-language handling.
            # We only hard-fail on intents that matched a local command family
            # but had invalid/missing required fields above.
            return None

        return None

    def _run_local_bridge(self, fn: str, args: dict) -> str:
        cmd = [WIN_PY, WIN_BRIDGE, fn, json.dumps(args)]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=40)
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode != 0:
            return f"[LocalToolError] exit={proc.returncode}\nstdout: {out}\nstderr: {err}"
        return out or "{}"

    def _profile_steps(self, profile: str):
        # Filter type map (0..7): 0=LC48, 1=LC12, 2=LS, 3=Bell, 4=Notch, 5=HS, 6=HC12, 7=HC48
        common = [
            {"device_index": 0, "param_index": 4, "value": 1, "label": "EQ1 band1 on"},
            {"device_index": 0, "param_index": 5, "value": 1, "label": "EQ1 low-cut type (12dB)"},
            {"device_index": 0, "param_index": 6, "value": 0.22, "label": "EQ1 low-cut ~100Hz"},
            {"device_index": 0, "param_index": 14, "value": 1, "label": "EQ1 band2 on"},
            {"device_index": 0, "param_index": 16, "value": 0.43, "label": "EQ1 mud freq ~300Hz"},
        ]

        airy = [
            {"device_index": 0, "param_index": 15, "value": 4, "label": "EQ1 mud type notch"},
            {"device_index": 0, "param_index": 17, "value": -2.2, "label": "EQ1 mud cut"},
            {"device_index": 0, "param_index": 18, "value": 2.8, "label": "EQ1 mud Q narrow"},
            {"device_index": 0, "param_index": 24, "value": 1, "label": "EQ1 band3 on"},
            {"device_index": 0, "param_index": 25, "value": 3, "label": "EQ1 presence type bell"},
            {"device_index": 0, "param_index": 26, "value": 0.82, "label": "EQ1 presence ~2kHz"},
            {"device_index": 0, "param_index": 27, "value": 1.2, "label": "EQ1 presence +dB"},
            {"device_index": 0, "param_index": 28, "value": 1.2, "label": "EQ1 presence Q"},
            {"device_index": 7, "param_index": 74, "value": 1, "label": "EQ2 band8 on"},
            {"device_index": 7, "param_index": 75, "value": 5, "label": "EQ2 air type high shelf"},
            {"device_index": 7, "param_index": 76, "value": 0.974, "label": "EQ2 air ~8kHz"},
            {"device_index": 7, "param_index": 77, "value": 1.8, "label": "EQ2 air +dB"},
            {"device_index": 7, "param_index": 78, "value": 0.8, "label": "EQ2 air Q broad"},
        ]

        punchy = [
            {"device_index": 0, "param_index": 15, "value": 3, "label": "EQ1 mud type bell"},
            {"device_index": 0, "param_index": 17, "value": -3.0, "label": "EQ1 mud cut"},
            {"device_index": 0, "param_index": 18, "value": 1.4, "label": "EQ1 mud Q"},
            {"device_index": 0, "param_index": 24, "value": 1, "label": "EQ1 band3 on"},
            {"device_index": 0, "param_index": 25, "value": 3, "label": "EQ1 presence type bell"},
            {"device_index": 0, "param_index": 26, "value": 0.84, "label": "EQ1 presence ~2.5k"},
            {"device_index": 0, "param_index": 27, "value": 2.2, "label": "EQ1 presence boost"},
            {"device_index": 0, "param_index": 28, "value": 1.1, "label": "EQ1 presence Q"},
            {"device_index": 7, "param_index": 74, "value": 1, "label": "EQ2 band8 on"},
            {"device_index": 7, "param_index": 75, "value": 5, "label": "EQ2 top type high shelf"},
            {"device_index": 7, "param_index": 76, "value": 0.95, "label": "EQ2 top ~7kHz"},
            {"device_index": 7, "param_index": 77, "value": 1.0, "label": "EQ2 top lift"},
            {"device_index": 7, "param_index": 78, "value": 1.0, "label": "EQ2 top Q"},
            {"device_index": 1, "param_index": 2, "value": 0.52, "label": "Comp ratio firmer"},
            {"device_index": 1, "param_index": 4, "value": 0.12, "label": "Comp faster attack"},
            {"device_index": 1, "param_index": 5, "value": 0.28, "label": "Comp faster release"},
        ]

        return common + (punchy if profile == "punchy_rap" else airy)

    def _apply_vocal_profile(self, track_index: int, profile: str) -> str:
        # Try adaptive (name-based) path first, fall back to legacy param_index path
        adaptive_result = self._try_adaptive_vocal_profile(track_index, profile)
        if adaptive_result is not None:
            return adaptive_result

        # Legacy fallback: hardcoded param_index writes
        steps = self._profile_steps(profile)
        out = []
        ok = 0
        for s in steps:
            args = {
                "track_index": track_index,
                "device_index": s["device_index"],
                "param_index": s["param_index"],
                "value": s["value"],
            }
            raw = self._run_local_bridge("set_device_parameter", args)
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = {"success": False, "raw": raw}
            if parsed.get("success"):
                ok += 1
            out.append({"step": s["label"], "args": args, "result": parsed})

        return json.dumps({
            "success": ok == len(steps),
            "profile": profile,
            "applied": ok,
            "total": len(steps),
            "message": f"Applied {profile} vocal profile" if ok == len(steps) else f"Applied {profile} with some failures",
            "details": out,
        }, indent=2)

    def _try_adaptive_vocal_profile(self, track_index: int, profile: str):
        """Attempt name-based adaptive vocal profile application.

        Returns JSON string on success, or None to signal fallback to legacy path.
        """
        try:
            from adaptive_layer import build_adaptive_profile_steps
        except ImportError:
            return None

        # Query device map from the track
        raw = self._run_local_bridge("get_track_devices", {"track_index": track_index})
        try:
            dev_resp = json.loads(raw)
        except Exception:
            return None
        if not dev_resp.get("success"):
            return None

        devices = dev_resp.get("devices", [])
        device_map = {}
        for d in devices:
            idx = d.get("index")
            name = d.get("name", "")
            if idx is not None:
                device_map[idx] = name

        steps = build_adaptive_profile_steps(profile, device_map)
        if steps is None or not steps:
            return None

        out = []
        ok_total = 0
        total_params = 0
        for step in steps:
            di = step["device_index"]
            params = step["params"]
            total_params += len(params)
            # Use set_device_parameters_by_name bridge command
            raw = self._run_local_bridge("set_device_parameters_by_name", {
                "track_index": track_index,
                "device_index": di,
                "params": params,
            })
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = {"success": False, "raw": raw}
            ok_count = parsed.get("succeeded", 0)
            ok_total += ok_count
            out.append({
                "device_index": di,
                "device_name": step["device_name"],
                "params_sent": len(params),
                "params_ok": ok_count,
                "result": parsed,
            })

        return json.dumps({
            "success": ok_total == total_params,
            "profile": profile,
            "method": "adaptive_name_based",
            "applied": ok_total,
            "total": total_params,
            "message": (
                f"Applied {profile} vocal profile (adaptive)"
                if ok_total == total_params
                else f"Applied {profile} with some failures ({ok_total}/{total_params})"
            ),
            "details": out,
        }, indent=2)

    async def send_message(self, user_text: str) -> list[str]:
        async with self._lock:
            local = self._parse_local_tool_intent(user_text)
            if local:
                if local.get("error"):
                    return [local["error"]]
                fn = local["fn"]
                args = local["args"]
                if fn == "__apply_vocal_profile":
                    result = await asyncio.to_thread(self._apply_vocal_profile, args["track_index"], args["profile"])
                    return [result]
                result = await asyncio.to_thread(self._run_local_bridge, fn, args)
                return [result]

            reply = await asyncio.to_thread(
                call_openclaw, user_text, TIMEOUT_SEC, self.agent
            )
            return [reply or "Command complete."]

    async def check_health(self) -> str:
        return await asyncio.to_thread(health_check, self.agent)

    def set_agent(self, name: str):
        self.agent = name


# ---------------------------------------------------------------------------
# Tkinter desktop UI  (structure matches jarvis_text_ui.py)
# ---------------------------------------------------------------------------

class JarvisDesktopApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Jarvis Ableton - OpenClaw Desktop")
        self.root.geometry("900x620")
        self.root.minsize(700, 450)

        self.events: queue.Queue = queue.Queue()
        self.backend = OpenClawBackend()
        self.ready = False
        self.busy = False

        self._build_ui()
        self._start_worker()
        self._set_status("Connecting to Jarvis (OpenClaw relay)...")
        self.root.after(120, self._drain_events)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- UI construction --------------------------------------------------

    def _build_ui(self):
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        # Banner label (shows active agent)
        self.banner_var = tk.StringVar(
            value=f"Backend: OpenClaw relay  |  Agent: {self.backend.agent}"
        )
        banner = ttk.Label(
            frame,
            textvariable=self.banner_var,
            font=("Consolas", 10, "italic"),
        )
        banner.pack(anchor="w", pady=(0, 6))

        # Chat log
        self.chat = scrolledtext.ScrolledText(
            frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Consolas", 11),
        )
        self.chat.pack(fill=tk.BOTH, expand=True)
        self.chat.tag_configure("user", foreground="#0b5ed7")
        self.chat.tag_configure("jarvis", foreground="#1f7a1f")
        self.chat.tag_configure("system", foreground="#5a5a5a")
        self.chat.tag_configure("error", foreground="#b00020")

        # Input row
        controls = ttk.Frame(frame)
        controls.pack(fill=tk.X, pady=(10, 0))

        self.input_var = tk.StringVar()
        self.entry = ttk.Entry(controls, textvariable=self.input_var)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.entry.bind("<Return>", self._on_enter)
        self.entry.configure(state=tk.DISABLED)

        self.send_button = ttk.Button(
            controls, text="Send", command=self._send_message, state=tk.DISABLED,
        )
        self.send_button.pack(side=tk.LEFT, padx=(8, 0))

        # Status bar
        self.status_var = tk.StringVar(value="Initializing...")
        self.status = ttk.Label(frame, textvariable=self.status_var)
        self.status.pack(anchor="w", pady=(8, 0))

    # ---- Async worker thread ----------------------------------------------

    def _start_worker(self):
        self.loop = asyncio.new_event_loop()
        self.worker = threading.Thread(target=self._run_loop, daemon=True)
        self.worker.start()
        asyncio.run_coroutine_threadsafe(self._init_backend(), self.loop)

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def _init_backend(self):
        try:
            greeting = await self.backend.warmup()
            self.events.put(("ready", greeting))
        except Exception as exc:
            self.events.put(("error", f"Startup failed: {exc}"))

    # ---- User actions -----------------------------------------------------

    def _on_enter(self, _event):
        self._send_message()
        return "break"

    def _send_message(self):
        if not self.ready or self.busy:
            return
        text = self.input_var.get().strip()
        if not text:
            return

        self.input_var.set("")
        lower = text.lower()

        # /health — connectivity check
        if lower == "/health":
            self._append("You", "/health", "user")
            self._set_busy(True)
            fut = asyncio.run_coroutine_threadsafe(self._do_health(), self.loop)
            fut.add_done_callback(self._background_done)
            return

        # /agent <name> — hot-swap the OpenClaw agent
        if lower.startswith("/agent "):
            new_agent = text[7:].strip()
            if not new_agent:
                self._append("System", "Usage: /agent <name>  (e.g. /agent main)", "system")
                return
            old = self.backend.agent
            self.backend.set_agent(new_agent)
            self._update_agent_display()
            self._append("System",
                         f"Switched agent: {old} -> {new_agent}", "system")
            return

        # /agent — show current
        if lower == "/agent":
            self._append("System",
                         f"Current agent: {self.backend.agent}\n"
                         f"Change with: /agent <name>", "system")
            return

        self._append("You", text, "user")
        self._set_busy(True)
        fut = asyncio.run_coroutine_threadsafe(self._do_send(text), self.loop)
        fut.add_done_callback(self._background_done)

    async def _do_send(self, text: str):
        replies = await self.backend.send_message(text)
        for item in replies:
            self.events.put(("assistant", item))
        self.events.put(("done", None))

    async def _do_health(self):
        result = await self.backend.check_health()
        self.events.put(("assistant", f"[Health] {result}"))
        self.events.put(("done", None))

    def _background_done(self, future):
        try:
            future.result()
        except Exception as exc:
            self.events.put(("error", f"Request failed: {exc}"))
            self.events.put(("done", None))

    # ---- Event drain (main thread) ----------------------------------------

    def _drain_events(self):
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break

            if kind == "ready":
                self.ready = True
                self._set_busy(False)
                self._set_status("Ready")
                self._append("Jarvis", payload, "jarvis")
                self.entry.focus_set()
            elif kind == "assistant":
                self._append("Jarvis", payload, "jarvis")
            elif kind == "error":
                self._append("System", payload, "error")
                self._set_busy(False)
                self._set_status("Error — see chat log")
            elif kind == "done":
                self._set_busy(False)
                if self.ready:
                    self._set_status("Ready")

        self.root.after(120, self._drain_events)

    # ---- Helpers ----------------------------------------------------------

    def _update_agent_display(self):
        ag = self.backend.agent
        self.root.title(f"Jarvis Ableton - OpenClaw [{ag}]")
        self.banner_var.set(f"Backend: OpenClaw relay  |  Agent: {ag}")

    def _set_status(self, text: str):
        self.status_var.set(text)

    def _set_busy(self, busy: bool):
        self.busy = busy
        if not self.ready and not busy:
            return
        if busy:
            self.send_button.configure(state=tk.DISABLED)
            self.entry.configure(state=tk.DISABLED)
            self._set_status("Jarvis is thinking...")
        else:
            self.send_button.configure(state=tk.NORMAL if self.ready else tk.DISABLED)
            self.entry.configure(state=tk.NORMAL if self.ready else tk.DISABLED)

    def _append(self, speaker: str, message: str, tag: str):
        self.chat.configure(state=tk.NORMAL)
        self.chat.insert(tk.END, f"{speaker}: ", tag)
        self.chat.insert(tk.END, f"{message}\n\n")
        self.chat.configure(state=tk.DISABLED)
        self.chat.see(tk.END)

    def _on_close(self):
        if hasattr(self, "loop"):
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.root.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    root = tk.Tk()
    JarvisDesktopApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
