"""
Pipeline module for deterministic chain execution.

Eliminates "chatty agent" behavior by collapsing 30+ LLM round-trips
into a single Gemini tool call with deterministic local execution.

Architecture:
    User -> Gemini -> build_chain_pipeline({track, devices, params})
                      ^-- single function_call, entire plan in arguments
                      |
                      v
                 ChainPipelineExecutor (deterministic, no LLM)
                 PLAN -> EXECUTE -> VERIFY -> REPORT
"""

from pipeline.schemas import (
    ChainPipelinePlan,
    DeviceSpec,
    ParamSpec,
    PipelineResult,
    DeviceResult,
    ParamResult,
    PipelinePhase,
)
from pipeline.executor import ChainPipelineExecutor
from pipeline.guardrail import LLMGuardrail

__all__ = [
    "ChainPipelinePlan",
    "DeviceSpec",
    "ParamSpec",
    "PipelineResult",
    "DeviceResult",
    "ParamResult",
    "PipelinePhase",
    "ChainPipelineExecutor",
    "LLMGuardrail",
]
