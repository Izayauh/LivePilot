"""
Pydantic schemas for the non-chatty chain pipeline.

Input models (what Gemini provides as build_chain_pipeline tool args):
    - ParamSpec: A single parameter to set on a device
    - DeviceSpec: A device to load with its parameter configuration
    - ChainPipelinePlan: Complete execution plan for a device chain

Output models (result returned to Gemini as FunctionResponse):
    - ParamResult: Result of setting a single parameter
    - DeviceResult: Result of loading and configuring a single device
    - PipelineResult: Complete result of the pipeline execution
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class PipelinePhase(str, Enum):
    """Execution phase of the pipeline."""
    PLAN = "plan"
    EXECUTE = "execute"
    VERIFY = "verify"
    REPORT = "report"


# ============================================================================
# INPUT MODELS (Gemini -> Pipeline)
# ============================================================================

class ParamSpec(BaseModel):
    """A single parameter to set on a device.

    Uses semantic parameter names from
    ReliableParameterController.SEMANTIC_PARAM_MAPPINGS
    (e.g., 'threshold_db', 'band1_freq_hz', 'ratio', 'attack_ms',
    'dry_wet_pct').

    Values are in human-readable units: Hz for frequency, dB for
    gain/threshold, ms for attack/release, ratio for compression ratio
    (e.g., 4.0 means 4:1), percentage for dry/wet (0-100).
    """
    name: str = Field(
        ...,
        description="Semantic parameter name (e.g., 'threshold_db', "
                    "'band1_freq_hz', 'ratio', 'attack_ms', 'dry_wet_pct')"
    )
    value: float = Field(
        ...,
        description="Human-readable value in real units (Hz, dB, ms, ratio, pct)"
    )
    tolerance: Optional[float] = Field(
        default=None,
        description="Optional readback tolerance in normalized space (0-1). "
                    "If None, uses the default (0.02)."
    )

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Parameter name must not be empty")
        return v.strip()


class DeviceSpec(BaseModel):
    """A single device to load with its parameter configuration."""
    name: str = Field(
        ...,
        description="Exact Ableton device name (e.g., 'EQ Eight', "
                    "'Compressor', 'Reverb', 'Saturator', 'Delay')"
    )
    purpose: Optional[str] = Field(
        default=None,
        description="Human-readable purpose (e.g., 'high_pass', 'dynamics')"
    )
    params: List[ParamSpec] = Field(
        default_factory=list,
        description="Parameters to set after loading"
    )
    enabled: bool = Field(
        default=True,
        description="Whether to enable (True) or bypass (False) the device"
    )
    fallback: Optional[str] = Field(
        default=None,
        description="Alternative device name if the primary fails to load"
    )

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Device name must not be empty")
        return v.strip()


class ChainPipelinePlan(BaseModel):
    """Complete execution plan for a device chain.

    This IS the argument schema for the build_chain_pipeline Gemini tool.
    Gemini generates the entire plan in a single function_call.
    """
    track_index: int = Field(
        ...,
        ge=0,
        description="0-based track index (Track 1 = 0, Track 2 = 1, etc.)"
    )
    devices: List[DeviceSpec] = Field(
        ...,
        min_length=1,
        max_length=16,
        description="Ordered list of devices to load (signal chain order)"
    )
    description: Optional[str] = Field(
        default=None,
        description="What this chain achieves (e.g., 'Kanye Donda vocal chain')"
    )
    clear_existing: bool = Field(
        default=False,
        description="Remove all existing devices before loading. Default False."
    )
    dry_run: bool = Field(
        default=False,
        description="Validate without executing. Returns what WOULD happen."
    )

    @model_validator(mode="after")
    def at_least_one_device(self) -> "ChainPipelinePlan":
        if not self.devices:
            raise ValueError("Plan must contain at least one device")
        return self


# ============================================================================
# OUTPUT MODELS (Pipeline -> Gemini)
# ============================================================================

class ParamResult(BaseModel):
    """Result of setting a single parameter."""
    name: str
    requested_value: float
    actual_value: Optional[float] = None
    success: bool
    verified: bool = False
    skipped_idempotent: bool = False
    error: Optional[str] = None


class DeviceResult(BaseModel):
    """Result of loading and configuring a single device."""
    name: str
    requested_name: str
    device_index: Optional[int] = None
    loaded: bool
    is_fallback: bool = False
    params: List[ParamResult] = Field(default_factory=list)
    error: Optional[str] = None
    load_time_ms: float = 0.0
    param_time_ms: float = 0.0


class PipelineResult(BaseModel):
    """Complete result of the pipeline execution."""
    success: bool
    phase_reached: PipelinePhase
    track_index: int
    description: Optional[str] = None
    devices: List[DeviceResult] = Field(default_factory=list)
    total_devices_planned: int = 0
    total_devices_loaded: int = 0
    total_params_planned: int = 0
    total_params_set: int = 0
    total_params_verified: int = 0
    total_params_skipped_idempotent: int = 0
    llm_calls_used: int = 0
    total_time_ms: float = 0.0
    dry_run: bool = False
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
