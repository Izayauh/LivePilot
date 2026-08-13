"""
Structured logging and metrics for pipeline executions.

Tracks:
- llm_calls_count per execution
- tool_calls_count (device loads + param sets)
- execution_time_ms
- steps_succeeded / steps_failed
- idempotent skips
"""

import logging
import time
from typing import List

from pipeline.schemas import PipelineResult

logger = logging.getLogger("jarvis.pipeline.metrics")


class PipelineMetrics:
    """Records and reports pipeline execution metrics."""

    def __init__(self, max_history: int = 100):
        self._history: List[dict] = []
        self._max_history = max_history

    def record(self, result: PipelineResult):
        """Record a pipeline execution result with structured logging."""
        entry = {
            "timestamp": time.time(),
            "success": result.success,
            "phase_reached": result.phase_reached.value,
            "track_index": result.track_index,
            "devices_planned": result.total_devices_planned,
            "devices_loaded": result.total_devices_loaded,
            "params_planned": result.total_params_planned,
            "params_set": result.total_params_set,
            "params_verified": result.total_params_verified,
            "params_skipped": result.total_params_skipped_idempotent,
            "llm_calls": result.llm_calls_used,
            "time_ms": result.total_time_ms,
            "dry_run": result.dry_run,
            "error_count": len(result.errors),
        }

        self._history.append(entry)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # Structured log output
        if result.success:
            logger.info(
                "PIPELINE_OK track=%d devices=%d/%d params=%d/%d "
                "verified=%d skipped=%d llm=%d time=%.0fms",
                result.track_index,
                result.total_devices_loaded, result.total_devices_planned,
                result.total_params_set, result.total_params_planned,
                result.total_params_verified,
                result.total_params_skipped_idempotent,
                result.llm_calls_used,
                result.total_time_ms,
            )
        else:
            logger.warning(
                "PIPELINE_FAIL track=%d phase=%s devices=%d/%d "
                "errors=%s time=%.0fms",
                result.track_index,
                result.phase_reached.value,
                result.total_devices_loaded, result.total_devices_planned,
                result.errors[:3],
                result.total_time_ms,
            )

    def get_stats(self) -> dict:
        """Return aggregate stats across all recorded executions."""
        if not self._history:
            return {"total_runs": 0}

        successes = sum(1 for h in self._history if h["success"])
        total = len(self._history)
        return {
            "total_runs": total,
            "success_rate": successes / total,
            "avg_time_ms": sum(h["time_ms"] for h in self._history) / total,
            "total_llm_calls": sum(h["llm_calls"] for h in self._history),
            "total_params_set": sum(h["params_set"] for h in self._history),
            "total_params_skipped": sum(h["params_skipped"] for h in self._history),
        }

    @property
    def history(self) -> List[dict]:
        return list(self._history)
