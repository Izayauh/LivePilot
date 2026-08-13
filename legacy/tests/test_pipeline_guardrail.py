"""
Tests for pipeline LLM guardrail.

Verifies that:
- Budget enforcement works (max_calls=1 blocks 2nd call)
- Phase blocking works (execute/verify phases block LLM calls)
- Reset clears state
- Thread safety
"""

import os
import sys
import threading
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.guardrail import LLMGuardrail, LLMBudgetExceeded, LLMCallBlocked


class TestLLMGuardrail:
    def test_first_call_succeeds(self):
        g = LLMGuardrail(max_calls=1)
        count = g.record_call("plan")
        assert count == 1

    def test_second_call_raises_budget_exceeded(self):
        g = LLMGuardrail(max_calls=1)
        g.record_call("plan")
        with pytest.raises(LLMBudgetExceeded):
            g.record_call("plan")

    def test_retry_budget_allows_two(self):
        g = LLMGuardrail(max_calls=LLMGuardrail.MAX_CALLS_RETRY)
        g.record_call("plan")
        count = g.record_call("retry")
        assert count == 2

    def test_retry_budget_blocks_third(self):
        g = LLMGuardrail(max_calls=2)
        g.record_call("plan")
        g.record_call("retry")
        with pytest.raises(LLMBudgetExceeded):
            g.record_call("plan")

    def test_block_phase_raises_on_assert(self):
        g = LLMGuardrail(max_calls=1)
        with g.block_phase("execute"):
            with pytest.raises(LLMCallBlocked):
                g.assert_no_llm()

    def test_block_phase_unblocks_after_exit(self):
        g = LLMGuardrail(max_calls=1)
        with g.block_phase("execute"):
            pass
        # Should not raise after context manager exits
        g.assert_no_llm()

    def test_multiple_blocked_phases(self):
        g = LLMGuardrail(max_calls=1)
        with g.block_phase("execute"):
            with pytest.raises(LLMCallBlocked):
                g.assert_no_llm()
        with g.block_phase("verify"):
            with pytest.raises(LLMCallBlocked):
                g.assert_no_llm()
        # Outside both blocks
        g.assert_no_llm()

    def test_calls_remaining(self):
        g = LLMGuardrail(max_calls=2)
        assert g.calls_remaining == 2
        g.record_call("plan")
        assert g.calls_remaining == 1
        g.record_call("retry")
        assert g.calls_remaining == 0

    def test_call_count(self):
        g = LLMGuardrail(max_calls=5)
        assert g.call_count == 0
        g.record_call("a")
        g.record_call("b")
        assert g.call_count == 2

    def test_reset_clears_state(self):
        g = LLMGuardrail(max_calls=1)
        g.record_call("plan")
        assert g.calls_remaining == 0

        g.reset()
        assert g.calls_remaining == 1
        assert g.call_count == 0
        # Should work again after reset
        g.record_call("plan")
        assert g.call_count == 1

    def test_reset_with_new_budget(self):
        g = LLMGuardrail(max_calls=1)
        g.record_call("plan")
        g.reset(max_calls=3)
        assert g.calls_remaining == 3

    def test_thread_safety(self):
        """Multiple threads recording calls should not corrupt state."""
        g = LLMGuardrail(max_calls=100)
        errors = []

        def record_calls(n):
            try:
                for _ in range(n):
                    g.record_call("test")
            except LLMBudgetExceeded:
                errors.append("budget_exceeded")

        threads = [threading.Thread(target=record_calls, args=(10,)) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert g.call_count == 100
        assert len(errors) == 0

    def test_thread_safety_over_budget(self):
        """Concurrent calls over budget should raise, not corrupt."""
        g = LLMGuardrail(max_calls=5)
        exceeded_count = 0
        lock = threading.Lock()

        def record_calls():
            nonlocal exceeded_count
            try:
                g.record_call("test")
            except LLMBudgetExceeded:
                with lock:
                    exceeded_count += 1

        threads = [threading.Thread(target=record_calls) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert g.call_count == 5
        assert exceeded_count == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
