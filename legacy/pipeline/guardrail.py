"""
LLM Call Guardrail for the non-chatty pipeline.

Enforces MAX_LLM_CALLS_PER_USER_INTENT = 1 (2 on explicit retry).
Blocks LLM calls during EXECUTE and VERIFY phases.

Usage:
    guardrail = LLMGuardrail(max_calls=1)

    # The Gemini tool call that produced the plan counts as call #1
    guardrail.record_call("plan")

    # EXECUTE phase - any external LLM call raises LLMCallBlocked
    with guardrail.block_phase("execute"):
        # ... deterministic execution (no LLM calls) ...
        pass

    # VERIFY phase - also blocked
    with guardrail.block_phase("verify"):
        # ... readback checks (no LLM calls) ...
        pass
"""

import threading
from contextlib import contextmanager


_GLOBAL_PHASE = threading.local()


def get_blocked_phase() -> str:
    """Return the currently blocked phase for this thread, if any."""
    return getattr(_GLOBAL_PHASE, "phase", "")


def assert_llm_allowed():
    """Global guard used by any LLM caller in the process.

    Raises:
        LLMCallBlocked: when the current thread is in a blocked phase.
    """
    phase = get_blocked_phase()
    if phase in {"execute", "verify"}:
        raise LLMCallBlocked(
            f"llm_blocked_execute: LLM calls are blocked during '{phase}' phase"
        )


class LLMBudgetExceeded(Exception):
    """Raised when LLM call count exceeds the budget for a single intent."""
    pass


class LLMCallBlocked(Exception):
    """Raised when an LLM call is attempted during a blocked phase."""
    pass


class LLMGuardrail:
    """Thread-safe LLM call counter and phase blocker.

    Ensures deterministic execution phases make zero LLM calls.
    """

    MAX_CALLS_DEFAULT = 1
    MAX_CALLS_RETRY = 2

    def __init__(self, max_calls: int = MAX_CALLS_DEFAULT):
        self._lock = threading.Lock()
        self._call_count = 0
        self._max_calls = max_calls
        self._blocked_phases: set = set()
        self._current_phase: str = "idle"

    def record_call(self, phase: str) -> int:
        """Record an LLM call. Raises LLMBudgetExceeded if over budget."""
        with self._lock:
            if self._call_count >= self._max_calls:
                raise LLMBudgetExceeded(
                    f"LLM call #{self._call_count + 1} exceeds budget of "
                    f"{self._max_calls} for this intent"
                )
            self._call_count += 1
            return self._call_count

    def assert_no_llm(self):
        """Assert that no LLM call should happen in the current phase."""
        with self._lock:
            if self._current_phase in self._blocked_phases:
                raise LLMCallBlocked(
                    f"LLM calls are blocked during '{self._current_phase}' phase"
                )
        assert_llm_allowed()

    @contextmanager
    def block_phase(self, phase: str):
        """Context manager that blocks LLM calls for the given phase."""
        prev_global_phase = get_blocked_phase()
        with self._lock:
            self._blocked_phases.add(phase)
            prev_phase = self._current_phase
            self._current_phase = phase
        _GLOBAL_PHASE.phase = phase
        try:
            yield
        finally:
            with self._lock:
                self._blocked_phases.discard(phase)
                self._current_phase = prev_phase
            _GLOBAL_PHASE.phase = prev_global_phase

    @property
    def call_count(self) -> int:
        with self._lock:
            return self._call_count

    @property
    def calls_remaining(self) -> int:
        with self._lock:
            return max(0, self._max_calls - self._call_count)

    def reset(self, max_calls: int = None):
        """Reset for the next user intent."""
        with self._lock:
            self._call_count = 0
            if max_calls is not None:
                self._max_calls = max_calls
            self._blocked_phases.clear()
            self._current_phase = "idle"
        _GLOBAL_PHASE.phase = ""
