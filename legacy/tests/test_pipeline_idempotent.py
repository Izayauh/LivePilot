"""
Tests for pipeline idempotent re-execution.

Verifies that:
- Running the same plan twice skips all params on second run
- Minimal/no writes on idempotent re-run
- total_params_skipped_idempotent matches total_params_planned
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.schemas import (
    ChainPipelinePlan,
    DeviceSpec,
    ParamSpec,
    PipelinePhase,
)
from pipeline.executor import ChainPipelineExecutor
from pipeline.guardrail import LLMGuardrail


def make_mock_controller():
    ctrl = MagicMock()
    ctrl.get_track_list.return_value = {
        "success": True,
        "tracks": [{"index": 0, "number": 1, "name": "Vocal"}],
    }
    ctrl.get_num_devices_sync.return_value = {"success": True, "count": 0}
    ctrl.set_device_enabled.return_value = {"success": True}
    return ctrl


def make_idempotent_reliable():
    """Create reliable mock where all params already match target."""
    reliable = MagicMock()

    reliable.load_device_verified.return_value = {
        "success": True,
        "device_index": 0,
        "device_name": "Compressor",
        "message": "Loaded",
    }
    reliable.wait_for_device_ready.return_value = True

    # Find parameter index always succeeds
    reliable.find_parameter_index.return_value = 0

    # Current value = target (will trigger idempotency skip)
    reliable.get_parameter_value_sync.return_value = 0.5

    return reliable


class TestIdempotentExecution:
    def test_all_params_skipped_on_idempotent_rerun(self):
        """All params already at target -> all skipped."""
        ctrl = make_mock_controller()
        reliable = make_idempotent_reliable()

        plan = ChainPipelinePlan(
            track_index=0,
            devices=[
                DeviceSpec(
                    name="Compressor",
                    params=[
                        ParamSpec(name="threshold_db", value=-14.0),
                        ParamSpec(name="ratio", value=2.0),
                        ParamSpec(name="attack_ms", value=20.0),
                    ],
                ),
            ],
        )

        # Mock _compute_target_normalized to return 0.5 (matching current)
        with patch.object(
            ChainPipelineExecutor,
            "_compute_target_normalized",
            return_value=0.5,
        ):
            executor = ChainPipelineExecutor(controller=ctrl, reliable=reliable)
            result = executor.execute(plan)

        assert result.success
        assert result.total_params_planned == 3
        assert result.total_params_skipped_idempotent == 3
        # set_parameter_by_name should NOT have been called
        reliable.set_parameter_by_name.assert_not_called()

    def test_partial_idempotent(self):
        """Some params match, some don't."""
        ctrl = make_mock_controller()
        reliable = make_idempotent_reliable()

        # set_parameter_by_name for non-idempotent params
        reliable.set_parameter_by_name.return_value = {
            "success": True, "verified": True, "actual_value": None,
        }

        plan = ChainPipelinePlan(
            track_index=0,
            devices=[
                DeviceSpec(
                    name="Compressor",
                    params=[
                        ParamSpec(name="threshold_db", value=-14.0),
                        ParamSpec(name="ratio", value=2.0),
                        ParamSpec(name="attack_ms", value=20.0),
                    ],
                ),
            ],
        )

        call_idx = {"n": 0}

        def compute_target(self_unused, *args, **kwargs):
            call_idx["n"] += 1
            if call_idx["n"] == 2:
                return 0.9  # different from current 0.5 -> will set
            return 0.5  # same as current -> will skip

        with patch.object(
            ChainPipelineExecutor,
            "_compute_target_normalized",
            compute_target,
        ):
            executor = ChainPipelineExecutor(controller=ctrl, reliable=reliable)
            result = executor.execute(plan)

        assert result.success
        assert result.total_params_skipped_idempotent == 2
        assert reliable.set_parameter_by_name.call_count == 1

    def test_idempotent_when_normalize_unavailable(self):
        """If normalization fails, param is set (not skipped)."""
        ctrl = make_mock_controller()
        reliable = make_idempotent_reliable()
        reliable.set_parameter_by_name.return_value = {
            "success": True, "verified": True, "actual_value": None,
        }

        plan = ChainPipelinePlan(
            track_index=0,
            devices=[
                DeviceSpec(
                    name="Compressor",
                    params=[ParamSpec(name="threshold_db", value=-14.0)],
                ),
            ],
        )

        # _compute_target_normalized returns None (can't normalize)
        with patch.object(
            ChainPipelineExecutor,
            "_compute_target_normalized",
            return_value=None,
        ):
            executor = ChainPipelineExecutor(controller=ctrl, reliable=reliable)
            result = executor.execute(plan)

        assert result.success
        assert result.total_params_skipped_idempotent == 0
        reliable.set_parameter_by_name.assert_called_once()

    def test_idempotent_fast(self):
        """Idempotent re-run should be fast (no load delays)."""
        ctrl = make_mock_controller()
        reliable = make_idempotent_reliable()

        plan = ChainPipelinePlan(
            track_index=0,
            devices=[
                DeviceSpec(
                    name="EQ Eight",
                    params=[
                        ParamSpec(name="band1_freq_hz", value=100.0),
                        ParamSpec(name="band1_gain_db", value=-3.0),
                        ParamSpec(name="band1_q", value=0.7),
                    ],
                ),
            ],
        )

        with patch.object(
            ChainPipelineExecutor,
            "_compute_target_normalized",
            return_value=0.5,
        ):
            executor = ChainPipelineExecutor(controller=ctrl, reliable=reliable)
            result = executor.execute(plan)

        assert result.success
        assert result.total_params_skipped_idempotent == 3
        # Execution time should be very fast (no actual OSC writes)
        # Just checking the pipeline completes without error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
