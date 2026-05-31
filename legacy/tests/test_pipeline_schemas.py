"""
Tests for pipeline Pydantic schemas.

Verifies that:
- Valid plans are accepted (minimal, full, with fallbacks, dry-run)
- Invalid plans are rejected (empty devices, negative track_index, etc.)
- Result models serialize correctly
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import ValidationError
from pipeline.schemas import (
    ParamSpec,
    DeviceSpec,
    ChainPipelinePlan,
    ParamResult,
    DeviceResult,
    PipelineResult,
    PipelinePhase,
)


# ============================================================================
# ParamSpec Tests
# ============================================================================

class TestParamSpec:
    def test_valid_param(self):
        p = ParamSpec(name="threshold_db", value=-18.0)
        assert p.name == "threshold_db"
        assert p.value == -18.0
        assert p.tolerance is None

    def test_param_with_tolerance(self):
        p = ParamSpec(name="ratio", value=4.0, tolerance=0.05)
        assert p.tolerance == 0.05

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            ParamSpec(name="", value=1.0)

    def test_whitespace_name_rejected(self):
        with pytest.raises(ValidationError):
            ParamSpec(name="   ", value=1.0)

    def test_name_stripped(self):
        p = ParamSpec(name="  ratio  ", value=4.0)
        assert p.name == "ratio"

    def test_negative_value_allowed(self):
        p = ParamSpec(name="threshold_db", value=-30.0)
        assert p.value == -30.0

    def test_zero_value_allowed(self):
        p = ParamSpec(name="band1_gain_db", value=0.0)
        assert p.value == 0.0


# ============================================================================
# DeviceSpec Tests
# ============================================================================

class TestDeviceSpec:
    def test_minimal_device(self):
        d = DeviceSpec(name="EQ Eight")
        assert d.name == "EQ Eight"
        assert d.params == []
        assert d.enabled is True
        assert d.fallback is None
        assert d.purpose is None

    def test_device_with_params(self):
        d = DeviceSpec(
            name="Compressor",
            purpose="dynamics",
            params=[
                ParamSpec(name="threshold_db", value=-18.0),
                ParamSpec(name="ratio", value=4.0),
            ],
        )
        assert len(d.params) == 2
        assert d.purpose == "dynamics"

    def test_device_with_fallback(self):
        d = DeviceSpec(name="FabFilter Pro-Q 3", fallback="EQ Eight")
        assert d.fallback == "EQ Eight"

    def test_device_bypassed(self):
        d = DeviceSpec(name="Reverb", enabled=False)
        assert d.enabled is False

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            DeviceSpec(name="")


# ============================================================================
# ChainPipelinePlan Tests
# ============================================================================

class TestChainPipelinePlan:
    def test_minimal_plan(self):
        plan = ChainPipelinePlan(
            track_index=0,
            devices=[DeviceSpec(name="EQ Eight")],
        )
        assert plan.track_index == 0
        assert len(plan.devices) == 1
        assert plan.clear_existing is False
        assert plan.dry_run is False

    def test_full_plan(self):
        plan = ChainPipelinePlan(
            track_index=2,
            devices=[
                DeviceSpec(
                    name="EQ Eight",
                    purpose="high_pass",
                    params=[
                        ParamSpec(name="band1_freq_hz", value=100.0),
                        ParamSpec(name="band1_type", value=6.0),
                    ],
                ),
                DeviceSpec(
                    name="Compressor",
                    purpose="dynamics",
                    params=[
                        ParamSpec(name="threshold_db", value=-18.0),
                        ParamSpec(name="ratio", value=3.0),
                        ParamSpec(name="attack_ms", value=10.0),
                        ParamSpec(name="release_ms", value=100.0),
                    ],
                ),
                DeviceSpec(
                    name="Saturator",
                    purpose="warmth",
                    params=[
                        ParamSpec(name="drive_db", value=6.0),
                        ParamSpec(name="dry_wet_pct", value=80.0),
                    ],
                ),
                DeviceSpec(
                    name="Reverb",
                    purpose="space",
                    params=[
                        ParamSpec(name="decay_time_ms", value=1500.0),
                        ParamSpec(name="dry_wet_pct", value=20.0),
                    ],
                ),
                DeviceSpec(
                    name="Delay",
                    purpose="depth",
                    params=[
                        ParamSpec(name="dry_wet_pct", value=15.0),
                        ParamSpec(name="feedback_pct", value=30.0),
                    ],
                ),
            ],
            description="Kanye Donda-era vocal chain",
            clear_existing=True,
        )
        assert plan.track_index == 2
        assert len(plan.devices) == 5
        assert plan.description == "Kanye Donda-era vocal chain"
        assert plan.clear_existing is True
        total_params = sum(len(d.params) for d in plan.devices)
        assert total_params == 12

    def test_dry_run_flag(self):
        plan = ChainPipelinePlan(
            track_index=0,
            devices=[DeviceSpec(name="Compressor")],
            dry_run=True,
        )
        assert plan.dry_run is True

    def test_negative_track_index_rejected(self):
        with pytest.raises(ValidationError):
            ChainPipelinePlan(
                track_index=-1,
                devices=[DeviceSpec(name="EQ Eight")],
            )

    def test_empty_devices_rejected(self):
        with pytest.raises(ValidationError):
            ChainPipelinePlan(track_index=0, devices=[])

    def test_too_many_devices_rejected(self):
        devices = [DeviceSpec(name=f"Device_{i}") for i in range(17)]
        with pytest.raises(ValidationError):
            ChainPipelinePlan(track_index=0, devices=devices)

    def test_max_devices_accepted(self):
        devices = [DeviceSpec(name=f"Utility") for _ in range(16)]
        plan = ChainPipelinePlan(track_index=0, devices=devices)
        assert len(plan.devices) == 16

    def test_from_dict(self):
        """Test constructing plan from raw dict (simulating Gemini args)."""
        raw = {
            "track_index": 1,
            "devices": [
                {
                    "name": "EQ Eight",
                    "purpose": "high_pass",
                    "params": [
                        {"name": "band1_freq_hz", "value": 80.0},
                    ],
                },
                {
                    "name": "Compressor",
                    "params": [
                        {"name": "threshold_db", "value": -20.0},
                        {"name": "ratio", "value": 3.0},
                    ],
                },
            ],
            "description": "Basic vocal chain",
        }
        plan = ChainPipelinePlan(**raw)
        assert plan.track_index == 1
        assert len(plan.devices) == 2
        assert plan.devices[0].params[0].name == "band1_freq_hz"
        assert plan.devices[1].params[1].value == 3.0


# ============================================================================
# Result Model Tests
# ============================================================================

class TestResultModels:
    def test_param_result_serialize(self):
        pr = ParamResult(
            name="threshold_db",
            requested_value=-18.0,
            actual_value=-17.8,
            success=True,
            verified=True,
        )
        d = pr.model_dump()
        assert d["name"] == "threshold_db"
        assert d["success"] is True
        assert d["verified"] is True

    def test_device_result_serialize(self):
        dr = DeviceResult(
            name="Compressor",
            requested_name="Compressor",
            device_index=2,
            loaded=True,
            params=[
                ParamResult(
                    name="ratio",
                    requested_value=4.0,
                    actual_value=4.0,
                    success=True,
                    verified=True,
                ),
            ],
            load_time_ms=520.0,
        )
        d = dr.model_dump()
        assert d["loaded"] is True
        assert len(d["params"]) == 1

    def test_pipeline_result_serialize(self):
        result = PipelineResult(
            success=True,
            phase_reached=PipelinePhase.REPORT,
            track_index=0,
            total_devices_planned=3,
            total_devices_loaded=3,
            total_params_planned=8,
            total_params_set=8,
            total_params_verified=8,
            llm_calls_used=1,
            total_time_ms=4200.0,
        )
        d = result.model_dump()
        assert d["success"] is True
        assert d["phase_reached"] == "report"
        assert d["llm_calls_used"] == 1

    def test_pipeline_result_with_errors(self):
        result = PipelineResult(
            success=False,
            phase_reached=PipelinePhase.EXECUTE,
            track_index=0,
            errors=["Compressor.threshold_db: Parameter not found"],
        )
        assert len(result.errors) == 1
        assert not result.success


# ============================================================================
# Run
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
