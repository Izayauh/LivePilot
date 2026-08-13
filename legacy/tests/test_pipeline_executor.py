"""
Tests for pipeline executor with mocked Ableton controller.

Verifies that:
- Single device load + params uses correct controller calls
- Multi-device chains execute in order
- Fallback on load failure works
- Idempotency: skips params already within tolerance
- Dry-run mode makes zero controller calls
- Guardrail blocks LLM calls during execute/verify
- Result aggregation is correct
"""

import os
import sys
import time
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.schemas import (
    ChainPipelinePlan,
    DeviceSpec,
    ParamSpec,
    PipelinePhase,
)
from pipeline.executor import ChainPipelineExecutor
from pipeline.guardrail import LLMGuardrail, LLMCallBlocked


# ============================================================================
# Mock Helpers
# ============================================================================

def make_mock_controller():
    """Create a mock AbletonController."""
    ctrl = MagicMock()
    ctrl.get_track_list.return_value = {
        "success": True,
        "tracks": [
            {"index": 0, "number": 1, "name": "Lead Vocal"},
            {"index": 1, "number": 2, "name": "Drums"},
            {"index": 2, "number": 3, "name": "Bass"},
        ],
    }
    ctrl.get_num_devices_sync.return_value = {"success": True, "count": 0}
    ctrl.set_device_enabled.return_value = {"success": True}
    ctrl.delete_device.return_value = {"success": True}
    return ctrl


def make_mock_reliable(device_name="Compressor"):
    """Create a mock ReliableParameterController."""
    reliable = MagicMock()

    # load_device_verified succeeds, returns device_index
    reliable.load_device_verified.return_value = {
        "success": True,
        "device_index": 0,
        "device_name": device_name,
        "message": "Loaded",
    }

    # wait_for_device_ready succeeds
    reliable.wait_for_device_ready.return_value = True

    # find_parameter_index returns sequential indices
    _param_counter = {"idx": 0}

    def find_param(track, device, name):
        idx = _param_counter["idx"]
        _param_counter["idx"] += 1
        return idx

    reliable.find_parameter_index.side_effect = find_param

    # get_parameter_value_sync returns a value far from target (forces set)
    reliable.get_parameter_value_sync.return_value = 0.0

    # get_device_info returns None (skip idempotency normalization)
    reliable.get_device_info.return_value = None

    # set_parameter_by_name succeeds
    reliable.set_parameter_by_name.return_value = {
        "success": True,
        "verified": True,
        "actual_value": None,
        "message": "Set OK",
    }

    return reliable


# ============================================================================
# Executor Tests
# ============================================================================

class TestExecutorSingleDevice:
    def test_single_device_no_params(self):
        """Load a device with no params - just device load."""
        ctrl = make_mock_controller()
        reliable = make_mock_reliable()

        executor = ChainPipelineExecutor(controller=ctrl, reliable=reliable)
        plan = ChainPipelinePlan(
            track_index=0,
            devices=[DeviceSpec(name="EQ Eight")],
        )

        result = executor.execute(plan)

        assert result.success
        assert result.phase_reached == PipelinePhase.REPORT
        assert result.total_devices_loaded == 1
        assert result.total_params_planned == 0
        assert result.llm_calls_used == 1
        reliable.load_device_verified.assert_called_once()

    def test_single_device_with_params(self):
        """Load Compressor + set threshold, ratio, attack."""
        ctrl = make_mock_controller()
        reliable = make_mock_reliable()

        executor = ChainPipelineExecutor(controller=ctrl, reliable=reliable)
        plan = ChainPipelinePlan(
            track_index=0,
            devices=[
                DeviceSpec(
                    name="Compressor",
                    params=[
                        ParamSpec(name="threshold_db", value=-18.0),
                        ParamSpec(name="ratio", value=4.0),
                        ParamSpec(name="attack_ms", value=10.0),
                    ],
                ),
            ],
        )

        result = executor.execute(plan)

        assert result.success
        assert result.total_devices_loaded == 1
        assert result.total_params_set == 3
        assert reliable.set_parameter_by_name.call_count == 3


class TestExecutorMultiDevice:
    def test_multi_device_ordering(self):
        """3 devices load in order."""
        ctrl = make_mock_controller()
        reliable = make_mock_reliable()

        # Track which devices are loaded in order
        load_order = []
        original_load = reliable.load_device_verified

        def track_load(track_index, device_name, **kwargs):
            load_order.append(device_name)
            return {"success": True, "device_index": len(load_order) - 1, "message": "OK"}

        reliable.load_device_verified.side_effect = track_load

        executor = ChainPipelineExecutor(controller=ctrl, reliable=reliable)
        plan = ChainPipelinePlan(
            track_index=0,
            devices=[
                DeviceSpec(name="EQ Eight"),
                DeviceSpec(name="Compressor"),
                DeviceSpec(name="Reverb"),
            ],
        )

        result = executor.execute(plan)

        assert result.success
        assert result.total_devices_loaded == 3
        assert load_order == ["EQ Eight", "Compressor", "Reverb"]


class TestExecutorFallback:
    def test_fallback_on_load_failure(self):
        """Primary load fails, explicit fallback succeeds."""
        ctrl = make_mock_controller()
        reliable = make_mock_reliable()

        call_count = {"n": 0}
        load_names = []

        def load_device(track_index, device_name, **kwargs):
            call_count["n"] += 1
            load_names.append(device_name)
            if device_name == "MyCustomPlugin":
                return {"success": False, "message": "Not found"}
            return {"success": True, "device_index": 0, "message": "OK"}

        reliable.load_device_verified.side_effect = load_device

        executor = ChainPipelineExecutor(controller=ctrl, reliable=reliable)
        plan = ChainPipelinePlan(
            track_index=0,
            devices=[
                DeviceSpec(name="MyCustomPlugin", fallback="EQ Eight"),
            ],
        )

        result = executor.execute(plan)

        assert result.success
        assert result.devices[0].is_fallback
        assert result.devices[0].name == "EQ Eight"
        # Primary tried first, then fallback
        assert call_count["n"] == 2
        assert load_names == ["MyCustomPlugin", "EQ Eight"]


class TestExecutorIdempotency:
    def test_skip_params_within_tolerance(self):
        """Param already at target value is skipped."""
        ctrl = make_mock_controller()
        reliable = make_mock_reliable()

        # Return a normalized value close to target
        reliable.get_parameter_value_sync.return_value = 0.5

        # Mock get_device_info to enable normalization
        mock_info = MagicMock()
        mock_info.accessible = True
        mock_info.param_names = ["Threshold"]
        mock_info.param_mins = [0.0]
        mock_info.param_maxs = [1.0]
        reliable.get_device_info.return_value = mock_info

        # Mock smart_normalize_parameter to return 0.5 (matching current)
        with patch("pipeline.executor.ChainPipelineExecutor._compute_target_normalized") as mock_norm:
            mock_norm.return_value = 0.5  # same as current

            executor = ChainPipelineExecutor(controller=ctrl, reliable=reliable)
            plan = ChainPipelinePlan(
                track_index=0,
                devices=[
                    DeviceSpec(
                        name="Compressor",
                        params=[ParamSpec(name="threshold_db", value=-14.0)],
                    ),
                ],
            )

            result = executor.execute(plan)

        assert result.success
        assert result.total_params_skipped_idempotent == 1
        assert result.total_params_set == 1  # counted as set (success=True)
        # set_parameter_by_name should NOT have been called
        reliable.set_parameter_by_name.assert_not_called()


class TestExecutorDryRun:
    def test_dry_run_no_controller_calls(self):
        """Dry run should not call load_device or set_parameter."""
        ctrl = make_mock_controller()
        reliable = make_mock_reliable()

        executor = ChainPipelineExecutor(controller=ctrl, reliable=reliable)
        plan = ChainPipelinePlan(
            track_index=0,
            devices=[
                DeviceSpec(
                    name="EQ Eight",
                    params=[ParamSpec(name="band1_freq_hz", value=100.0)],
                ),
                DeviceSpec(name="Compressor"),
            ],
            dry_run=True,
        )

        result = executor.execute(plan)

        assert result.success
        assert result.dry_run
        assert result.phase_reached == PipelinePhase.PLAN
        assert len(result.devices) == 2
        assert not result.devices[0].loaded
        assert not result.devices[1].loaded
        reliable.load_device_verified.assert_not_called()
        reliable.set_parameter_by_name.assert_not_called()


class TestExecutorGuardrail:
    def test_guardrail_blocks_extra_llm_during_execute(self):
        """Verify that assert_no_llm raises during execute phase."""
        g = LLMGuardrail(max_calls=1)
        g.record_call("plan")  # consume the budget

        with g.block_phase("execute"):
            with pytest.raises(LLMCallBlocked):
                g.assert_no_llm()

    def test_executor_uses_guardrail(self):
        """Verify the executor records exactly 1 LLM call."""
        ctrl = make_mock_controller()
        reliable = make_mock_reliable()
        guardrail = LLMGuardrail(max_calls=1)

        executor = ChainPipelineExecutor(
            controller=ctrl, reliable=reliable, guardrail=guardrail
        )
        plan = ChainPipelinePlan(
            track_index=0,
            devices=[DeviceSpec(name="EQ Eight")],
        )

        result = executor.execute(plan)

        assert result.success
        assert guardrail.call_count == 1
        assert result.llm_calls_used == 1


class TestExecutorResultAggregation:
    def test_totals_match(self):
        """Verify total counts are aggregated correctly."""
        ctrl = make_mock_controller()
        reliable = make_mock_reliable()

        executor = ChainPipelineExecutor(controller=ctrl, reliable=reliable)
        plan = ChainPipelinePlan(
            track_index=0,
            devices=[
                DeviceSpec(
                    name="EQ Eight",
                    params=[
                        ParamSpec(name="band1_freq_hz", value=100.0),
                        ParamSpec(name="band1_gain_db", value=-3.0),
                    ],
                ),
                DeviceSpec(
                    name="Compressor",
                    params=[
                        ParamSpec(name="threshold_db", value=-18.0),
                    ],
                ),
            ],
        )

        result = executor.execute(plan)

        assert result.total_devices_planned == 2
        assert result.total_devices_loaded == 2
        assert result.total_params_planned == 3
        assert result.total_params_set == 3


class TestExecutorDeviceNotReady:
    def test_device_not_ready_skips_params(self):
        """If device isn't ready, params are not set."""
        ctrl = make_mock_controller()
        reliable = make_mock_reliable()
        reliable.wait_for_device_ready.return_value = False

        executor = ChainPipelineExecutor(controller=ctrl, reliable=reliable)
        plan = ChainPipelinePlan(
            track_index=0,
            devices=[
                DeviceSpec(
                    name="Compressor",
                    params=[ParamSpec(name="threshold_db", value=-18.0)],
                ),
            ],
        )

        result = executor.execute(plan)

        # Device loaded but params not set due to not ready
        assert result.total_devices_loaded == 1
        assert result.devices[0].loaded
        assert result.devices[0].error is not None
        reliable.set_parameter_by_name.assert_not_called()


class TestExecutorTrackValidation:
    def test_invalid_track_index(self):
        """Track index out of range should fail in PLAN phase."""
        ctrl = make_mock_controller()
        reliable = make_mock_reliable()

        executor = ChainPipelineExecutor(controller=ctrl, reliable=reliable)
        plan = ChainPipelinePlan(
            track_index=99,  # way out of range
            devices=[DeviceSpec(name="EQ Eight")],
        )

        result = executor.execute(plan)

        assert not result.success
        assert result.phase_reached == PipelinePhase.PLAN
        assert any("out of range" in e for e in result.errors)

    def test_ableton_not_responding(self):
        """If get_track_list fails, pipeline fails gracefully."""
        ctrl = make_mock_controller()
        ctrl.get_track_list.return_value = {"success": False}
        reliable = make_mock_reliable()

        executor = ChainPipelineExecutor(controller=ctrl, reliable=reliable)
        plan = ChainPipelinePlan(
            track_index=0,
            devices=[DeviceSpec(name="EQ Eight")],
        )

        result = executor.execute(plan)

        assert not result.success
        assert any("Failed to get track list" in e for e in result.errors)


class TestExecutorClearExisting:
    def test_clear_existing_devices(self):
        """clear_existing=True should delete devices before loading."""
        ctrl = make_mock_controller()
        ctrl.get_num_devices_sync.return_value = {"success": True, "count": 3}
        reliable = make_mock_reliable()

        executor = ChainPipelineExecutor(controller=ctrl, reliable=reliable)
        plan = ChainPipelinePlan(
            track_index=0,
            devices=[DeviceSpec(name="EQ Eight")],
            clear_existing=True,
        )

        result = executor.execute(plan)

        assert result.success
        # Should have called delete_device 3 times (for indices 2, 1, 0)
        assert ctrl.delete_device.call_count == 3


class TestExecutorBypass:
    def test_device_bypass(self):
        """enabled=False should call set_device_enabled(0)."""
        ctrl = make_mock_controller()
        reliable = make_mock_reliable()

        executor = ChainPipelineExecutor(controller=ctrl, reliable=reliable)
        plan = ChainPipelinePlan(
            track_index=0,
            devices=[DeviceSpec(name="Reverb", enabled=False)],
        )

        result = executor.execute(plan)

        assert result.success
        ctrl.set_device_enabled.assert_called_once_with(0, 0, 0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
