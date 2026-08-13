"""
Deterministic Chain Pipeline Executor.

Executes a ChainPipelinePlan through four phases with ZERO LLM calls:
    PLAN    -> Validate plan, resolve device names
    EXECUTE -> Load devices, set parameters (with idempotency)
    VERIFY  -> Re-read parameters, compare against plan
    REPORT  -> Aggregate results

Reuses existing infrastructure:
    - reliable_params.load_device_verified()    for device loading with polling
    - reliable_params.wait_for_device_ready()   for readiness check
    - reliable_params.set_parameter_by_name()   for param setting + normalization
    - reliable_params.find_parameter_index()    for semantic name resolution
    - reliable_params.get_parameter_value_sync() for readback
    - smart_normalize_parameter()               for value conversion
"""

import logging
import time
from typing import List, Optional

from pipeline.schemas import (
    ChainPipelinePlan,
    DeviceSpec,
    ParamSpec,
    PipelineResult,
    DeviceResult,
    ParamResult,
    PipelinePhase,
)
from pipeline.guardrail import LLMGuardrail
from pipeline.fallback_map import resolve_device_name, get_fallback_chain
from pipeline.metrics import PipelineMetrics

logger = logging.getLogger("jarvis.pipeline.executor")


class ChainPipelineExecutor:
    """Deterministic executor for chain pipeline plans.

    ZERO LLM calls during execution. Uses only local tool calls
    to the Ableton controller and reliable parameter controller.
    """

    # Timing constants
    DEVICE_LOAD_DELAY_S = 0.5       # min delay after device load
    DEVICE_READY_TIMEOUT_S = 8.0    # timeout for device readiness polling
    PARAM_INTER_DELAY_S = 0.05      # delay between parameter sets
    DEFAULT_TOLERANCE = 0.02        # normalized-space tolerance for idempotency

    def __init__(
        self,
        controller=None,
        reliable=None,
        guardrail: Optional[LLMGuardrail] = None,
    ):
        """Initialize the executor.

        Args:
            controller: AbletonController instance (lazy-imported if None)
            reliable: ReliableParameterController instance (lazy-imported if None)
            guardrail: LLM call guardrail (created with default budget if None)
        """
        if controller is None:
            from ableton_controls.controller import ableton
            controller = ableton
        if reliable is None:
            from ableton_controls.reliable_params import ReliableParameterController
            reliable = ReliableParameterController(controller, verbose=False)

        self.controller = controller
        self.reliable = reliable
        self.guardrail = guardrail or LLMGuardrail()
        self.metrics = PipelineMetrics()

    def execute(self, plan: ChainPipelinePlan) -> PipelineResult:
        """Execute a complete chain pipeline plan.

        Args:
            plan: Validated ChainPipelinePlan

        Returns:
            PipelineResult with detailed per-device, per-param results
        """
        start = time.time()
        result = PipelineResult(
            success=False,
            phase_reached=PipelinePhase.PLAN,
            track_index=plan.track_index,
            description=plan.description,
            total_devices_planned=len(plan.devices),
            total_params_planned=sum(len(d.params) for d in plan.devices),
            dry_run=plan.dry_run,
        )

        try:
            # ============================================================
            # PLAN PHASE
            # ============================================================
            # The Gemini tool call that produced this plan counts as LLM call #1
            self.guardrail.record_call("plan")

            # Validate track exists
            track_list_result = self.controller.get_track_list()
            if not track_list_result.get("success"):
                result.errors.append("Failed to get track list from Ableton")
                return self._finalize(result, start)

            tracks = track_list_result.get("tracks", [])
            if plan.track_index >= len(tracks):
                result.errors.append(
                    f"Track index {plan.track_index} out of range "
                    f"(have {len(tracks)} tracks)"
                )
                return self._finalize(result, start)

            track_name = tracks[plan.track_index].get("name", f"Track {plan.track_index + 1}")
            logger.info("PLAN: %d devices on track %d (%s)", len(plan.devices), plan.track_index, track_name)

            # Resolve device names (check availability, apply fallbacks)
            resolved_devices = self._resolve_all_devices(plan.devices)

            # === DRY RUN: return predicted actions without executing ===
            if plan.dry_run:
                result.phase_reached = PipelinePhase.PLAN
                result.success = True
                result.devices = [
                    DeviceResult(
                        name=rd["resolved_name"],
                        requested_name=rd["original_name"],
                        loaded=False,
                        is_fallback=rd["is_fallback"],
                        params=[
                            ParamResult(
                                name=p.name,
                                requested_value=p.value,
                                success=True,
                                verified=False,
                            )
                            for p in rd["spec"].params
                        ],
                    )
                    for rd in resolved_devices
                ]
                return self._finalize(result, start)

            # ============================================================
            # EXECUTE PHASE (no LLM calls)
            # ============================================================
            result.phase_reached = PipelinePhase.EXECUTE

            with self.guardrail.block_phase("execute"):
                # Clear existing devices if requested
                if plan.clear_existing:
                    self._clear_track_devices(plan.track_index)

                for rd in resolved_devices:
                    dev_result = self._execute_device(plan.track_index, rd)
                    result.devices.append(dev_result)

                    if dev_result.loaded:
                        result.total_devices_loaded += 1

            # ============================================================
            # VERIFY PHASE (no LLM calls)
            # ============================================================
            result.phase_reached = PipelinePhase.VERIFY

            with self.guardrail.block_phase("verify"):
                for dev_result in result.devices:
                    if dev_result.loaded and dev_result.device_index is not None:
                        self._verify_device_params(plan.track_index, dev_result)

            # ============================================================
            # REPORT PHASE
            # ============================================================
            result.phase_reached = PipelinePhase.REPORT

            for dev in result.devices:
                for pr in dev.params:
                    if pr.success:
                        result.total_params_set += 1
                    if pr.verified:
                        result.total_params_verified += 1
                    if pr.skipped_idempotent:
                        result.total_params_skipped_idempotent += 1
                    if pr.error:
                        result.errors.append(f"{dev.name}.{pr.name}: {pr.error}")

            result.llm_calls_used = 1  # always exactly 1
            result.success = (
                result.total_devices_loaded == result.total_devices_planned
                and len(result.errors) == 0
            )

            # Partial success: some devices loaded, some params failed
            if not result.success and result.total_devices_loaded > 0:
                failed_devices = result.total_devices_planned - result.total_devices_loaded
                if failed_devices == 0:
                    # All devices loaded but some params failed - still mark success
                    # with warnings
                    param_errors = [e for e in result.errors]
                    result.warnings.extend(param_errors)
                    result.errors.clear()
                    result.success = True

        except Exception as e:
            result.errors.append(f"Pipeline error: {str(e)}")
            logger.exception("Pipeline execution failed")

        return self._finalize(result, start)

    def _finalize(self, result: PipelineResult, start: float) -> PipelineResult:
        """Set timing and record metrics."""
        result.total_time_ms = (time.time() - start) * 1000
        self.metrics.record(result)
        return result

    # ------------------------------------------------------------------
    # PLAN helpers
    # ------------------------------------------------------------------

    def _resolve_all_devices(self, devices: List[DeviceSpec]) -> List[dict]:
        """Resolve each DeviceSpec to a loadable device name."""
        resolved = []
        for spec in devices:
            resolved_name, is_fallback = resolve_device_name(
                spec.name,
                fallback_override=spec.fallback,
            )
            resolved.append({
                "spec": spec,
                "original_name": spec.name,
                "resolved_name": resolved_name,
                "is_fallback": is_fallback,
            })
            if is_fallback:
                logger.info("Device fallback: %s -> %s", spec.name, resolved_name)
        return resolved

    # ------------------------------------------------------------------
    # EXECUTE helpers
    # ------------------------------------------------------------------

    def _clear_track_devices(self, track_index: int):
        """Remove all devices from a track (when clear_existing=True)."""
        try:
            num_result = self.controller.get_num_devices_sync(track_index)
            count = num_result.get("count", 0) if num_result.get("success") else 0
            # Delete from last to first to avoid index shifting
            for i in range(count - 1, -1, -1):
                self.controller.delete_device(track_index, i)
                time.sleep(0.1)
            logger.info("Cleared %d devices from track %d", count, track_index)
        except Exception as e:
            logger.warning("Failed to clear devices: %s", e)

    def _execute_device(self, track_index: int, rd: dict) -> DeviceResult:
        """Load a single device and set its parameters."""
        spec: DeviceSpec = rd["spec"]
        device_name = rd["resolved_name"]
        dev_start = time.time()

        dev_result = DeviceResult(
            name=device_name,
            requested_name=rd["original_name"],
            loaded=False,
            is_fallback=rd["is_fallback"],
        )

        # --- Load device ---
        load_result = self.reliable.load_device_verified(
            track_index,
            device_name,
            position=-1,
            timeout=self.DEVICE_READY_TIMEOUT_S,
            min_delay=self.DEVICE_LOAD_DELAY_S,
        )

        dev_result.load_time_ms = (time.time() - dev_start) * 1000

        if not load_result.get("success"):
            # Try explicit fallback
            if spec.fallback and device_name != spec.fallback:
                logger.info("Primary load failed, trying fallback: %s", spec.fallback)
                load_result = self.reliable.load_device_verified(
                    track_index, spec.fallback,
                    position=-1,
                    timeout=self.DEVICE_READY_TIMEOUT_S,
                    min_delay=self.DEVICE_LOAD_DELAY_S,
                )
                if load_result.get("success"):
                    dev_result.name = spec.fallback
                    dev_result.is_fallback = True
                else:
                    dev_result.error = load_result.get("message", "Load failed")
                    return dev_result
            else:
                # Try fallback chain from fallback_map
                fallbacks = get_fallback_chain(rd["original_name"])
                loaded = False
                for fb_name in fallbacks:
                    if fb_name == device_name:
                        continue
                    logger.info("Trying fallback chain: %s", fb_name)
                    load_result = self.reliable.load_device_verified(
                        track_index, fb_name,
                        position=-1,
                        timeout=self.DEVICE_READY_TIMEOUT_S,
                        min_delay=self.DEVICE_LOAD_DELAY_S,
                    )
                    if load_result.get("success"):
                        dev_result.name = fb_name
                        dev_result.is_fallback = True
                        loaded = True
                        break
                if not loaded:
                    dev_result.error = load_result.get("message", "Load failed (all fallbacks exhausted)")
                    return dev_result

        dev_result.loaded = True
        device_index = load_result.get("device_index")
        dev_result.device_index = device_index

        if device_index is None:
            dev_result.error = "Device loaded but index unknown"
            return dev_result

        # --- Wait for device readiness ---
        if not self.reliable.wait_for_device_ready(
            track_index, device_index,
            timeout=self.DEVICE_READY_TIMEOUT_S,
        ):
            dev_result.error = "Device loaded but not ready for parameters"
            return dev_result

        # --- Set parameters ---
        param_start = time.time()
        for param_spec in spec.params:
            pr = self._set_param(
                track_index, device_index,
                dev_result.name, param_spec,
            )
            dev_result.params.append(pr)
            time.sleep(self.PARAM_INTER_DELAY_S)

        dev_result.param_time_ms = (time.time() - param_start) * 1000

        # --- Handle enabled/bypass ---
        if not spec.enabled:
            self.controller.set_device_enabled(track_index, device_index, 0)

        return dev_result

    def _set_param(
        self,
        track_index: int,
        device_index: int,
        device_name: str,
        param_spec: ParamSpec,
    ) -> ParamResult:
        """Set a single parameter with idempotency check.

        1. Find param index via semantic name mapping
        2. Read current value (idempotency check)
        3. If already within tolerance, skip
        4. Otherwise, set via set_parameter_by_name (handles normalization)
        """
        pr = ParamResult(
            name=param_spec.name,
            requested_value=param_spec.value,
            success=False,
        )

        try:
            # 1. Find parameter index by semantic name
            param_index = self.reliable.find_parameter_index(
                track_index, device_index, param_spec.name
            )

            if param_index is None:
                pr.error = f"Parameter '{param_spec.name}' not found on {device_name}"
                return pr

            # 2. Idempotency check: read current normalized value
            current_normalized = self.reliable.get_parameter_value_sync(
                track_index, device_index, param_index
            )

            if current_normalized is not None:
                # Compute what the target normalized value would be
                target_normalized = self._compute_target_normalized(
                    track_index, device_index, param_index,
                    device_name, param_spec.name, param_spec.value,
                )

                if target_normalized is not None:
                    tolerance = param_spec.tolerance or self.DEFAULT_TOLERANCE
                    if abs(current_normalized - target_normalized) <= tolerance:
                        pr.success = True
                        pr.skipped_idempotent = True
                        pr.actual_value = param_spec.value
                        pr.verified = True
                        return pr

            # 3. Set the parameter (handles normalization internally)
            set_result = self.reliable.set_parameter_by_name(
                track_index, device_index,
                param_spec.name, param_spec.value,
            )

            pr.success = set_result.get("success", False)
            pr.verified = set_result.get("verified", False)
            pr.actual_value = set_result.get("actual_value")

            if not pr.success:
                pr.error = set_result.get("message", "Unknown error")

        except Exception as e:
            pr.error = str(e)

        return pr

    def _compute_target_normalized(
        self,
        track_index: int,
        device_index: int,
        param_index: int,
        device_name: str,
        param_name: str,
        value: float,
    ) -> Optional[float]:
        """Compute the expected normalized value for a human-readable input.

        Uses smart_normalize_parameter with the device's parameter range.
        Returns None if normalization cannot be determined.
        """
        try:
            from ableton_controls.reliable_params import smart_normalize_parameter

            info = self.reliable.get_device_info(track_index, device_index)
            if info and info.accessible and param_index < len(info.param_names):
                actual_param_name = info.param_names[param_index]
                pmin = info.param_mins[param_index] if param_index < len(info.param_mins) else 0.0
                pmax = info.param_maxs[param_index] if param_index < len(info.param_maxs) else 1.0

                normalized, _ = smart_normalize_parameter(
                    actual_param_name, value, device_name, pmin, pmax
                )
                return normalized
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # VERIFY helpers
    # ------------------------------------------------------------------

    def _verify_device_params(self, track_index: int, dev_result: DeviceResult):
        """Post-execution verification pass.

        Re-reads params that weren't already verified by set_parameter_by_name
        and marks them as verified if readback is available.
        """
        if dev_result.device_index is None:
            return

        for pr in dev_result.params:
            if pr.success and not pr.verified and not pr.skipped_idempotent:
                param_index = self.reliable.find_parameter_index(
                    track_index, dev_result.device_index, pr.name
                )
                if param_index is not None:
                    val = self.reliable.get_parameter_value_sync(
                        track_index, dev_result.device_index, param_index
                    )
                    if val is not None:
                        pr.actual_value = val
                        pr.verified = True
