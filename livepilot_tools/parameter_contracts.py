"""Deterministic plugin-parameter contracts for LivePilot.

This layer turns a musical request such as "SSL EV2, low-mid cut, -2.5 dB"
into an explicit method plan, safe value, LOM name candidates, and verification
contract. It does not claim success unless the lower parameter controller gives
us a verified readback.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = _REPO_ROOT / "config" / "plugin_parameter_manifests.json"
CONTRACT_SCHEMA_VERSION = "livepilot-parameter-contract-v1"
EXECUTABLE_METHODS = {"ableton_lom"}


class ParameterContractError(ValueError):
    """Raised when a plugin-parameter manifest is malformed."""


def _token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _json_clone(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _as_float(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"[-+]?\d+(?:\.\d+)?", value.replace(",", ""))
        if match:
            return float(match.group(0))
    return None


def _list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _safe_json(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, Mapping):
            return {str(key): _safe_json(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [_safe_json(item) for item in value]
        return repr(value)


class ManifestStore:
    """Loads and resolves plugin parameter manifests."""

    def __init__(
        self,
        manifest_path: Any = None,
        manifest_data: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.manifest_path = Path(manifest_path) if manifest_path else DEFAULT_MANIFEST_PATH
        self.data = _json_clone(manifest_data) if manifest_data is not None else self._load()
        self.plugins = self.data.get("plugins", {})
        if not isinstance(self.plugins, dict):
            raise ParameterContractError("manifest plugins must be a JSON object")
        self._plugin_index = self._build_plugin_index()

    def _load(self) -> Dict[str, Any]:
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ParameterContractError(f"manifest not found: {self.manifest_path}") from exc
        except json.JSONDecodeError as exc:
            raise ParameterContractError(f"manifest is not valid JSON: {exc}") from exc

    def _build_plugin_index(self) -> Dict[str, str]:
        index: Dict[str, str] = {}
        for plugin_id, plugin in self.plugins.items():
            if not isinstance(plugin, dict):
                continue
            names = [plugin_id, plugin.get("canonical_name")]
            names.extend(_list(plugin.get("aliases")))
            for name in names:
                key = _token(name)
                if key:
                    index[key] = plugin_id
        return index

    def resolve_plugin(self, plugin_name: Any) -> Optional[Dict[str, Any]]:
        plugin_id = self._plugin_index.get(_token(plugin_name))
        if plugin_id is None:
            return None

        plugin = _json_clone(self.plugins[plugin_id])
        plugin["plugin_id"] = plugin_id
        return plugin

    def resolve_parameter(self, plugin_name: Any, parameter_name: Any) -> Optional[Dict[str, Any]]:
        plugin = self.resolve_plugin(plugin_name)
        if plugin is None:
            return None

        parameters = plugin.get("parameters", {})
        if not isinstance(parameters, dict):
            raise ParameterContractError(
                f"{plugin.get('canonical_name', plugin_name)} parameters must be a JSON object"
            )

        aliases: Dict[str, str] = {}
        for parameter_key, parameter in parameters.items():
            if not isinstance(parameter, dict):
                continue
            names = [parameter_key, parameter.get("display_name")]
            names.extend(_list(parameter.get("aliases")))
            names.extend(_list(parameter.get("lom_name_candidates")))
            for name in names:
                key = _token(name)
                if key:
                    aliases[key] = parameter_key

        parameter_key = aliases.get(_token(parameter_name))
        if parameter_key is None:
            return None

        parameter = _json_clone(parameters[parameter_key])
        parameter["parameter_key"] = parameter_key
        parameter["plugin"] = {
            "plugin_id": plugin["plugin_id"],
            "canonical_name": plugin.get("canonical_name"),
            "preferred_control": plugin.get("preferred_control"),
            "fallbacks": _list(plugin.get("fallbacks")),
        }
        return parameter

    def available_plugins(self) -> List[str]:
        return [
            plugin.get("canonical_name", plugin_id)
            for plugin_id, plugin in sorted(self.plugins.items())
            if isinstance(plugin, dict)
        ]

    def available_parameters(self, plugin_name: Any) -> List[str]:
        plugin = self.resolve_plugin(plugin_name)
        if plugin is None:
            return []
        parameters = plugin.get("parameters", {})
        return [
            parameter.get("display_name", key)
            for key, parameter in sorted(parameters.items())
            if isinstance(parameter, dict)
        ]


def _method_plan(parameter: Mapping[str, Any]) -> List[str]:
    plugin = parameter.get("plugin", {})
    methods: List[str] = []
    for method in [
        parameter.get("preferred_control"),
        plugin.get("preferred_control") if isinstance(plugin, dict) else None,
        *_list(parameter.get("fallbacks")),
        *(_list(plugin.get("fallbacks")) if isinstance(plugin, dict) else []),
    ]:
        if method and method not in methods:
            methods.append(str(method))
    return methods


def _prepare_value(
    parameter: Mapping[str, Any],
    requested_value: Any,
    clamp_unsafe: bool = True,
) -> Tuple[bool, Dict[str, Any]]:
    value_map = parameter.get("value_map")
    if isinstance(value_map, dict):
        normalized_map = {_token(key): item for key, item in value_map.items()}
        map_key = _token(requested_value)
        if map_key in normalized_map:
            return True, {
                "requested_value": requested_value,
                "effective_value": normalized_map[map_key],
                "value_status": "mapped",
            }
        numeric_value = _as_float(requested_value)
        if numeric_value is not None and numeric_value in value_map.values():
            return True, {
                "requested_value": requested_value,
                "effective_value": numeric_value,
                "value_status": "mapped",
            }
        return False, {
            "requested_value": requested_value,
            "status": "unsafe",
            "message": f"Value must be one of: {', '.join(value_map)}",
        }

    numeric_value = _as_float(requested_value)
    if numeric_value is None:
        return False, {
            "requested_value": requested_value,
            "status": "unsafe",
            "message": "Parameter value must be numeric",
        }

    safe_range = parameter.get("safe_range")
    if not isinstance(safe_range, dict):
        return True, {
            "requested_value": requested_value,
            "effective_value": numeric_value,
            "value_status": "accepted",
        }

    min_value = _as_float(safe_range.get("min"))
    max_value = _as_float(safe_range.get("max"))
    if min_value is None or max_value is None:
        raise ParameterContractError("safe_range requires numeric min and max")
    if min_value > max_value:
        raise ParameterContractError("safe_range min must be <= max")

    if min_value <= numeric_value <= max_value:
        return True, {
            "requested_value": requested_value,
            "effective_value": numeric_value,
            "value_status": "accepted",
        }

    if not clamp_unsafe or safe_range.get("on_violation") == "reject":
        return False, {
            "requested_value": requested_value,
            "effective_value": numeric_value,
            "status": "unsafe",
            "safe_range": safe_range,
            "message": (
                f"{numeric_value:g} is outside safe range "
                f"{min_value:g}-{max_value:g} {parameter.get('target_unit', '')}".strip()
            ),
        }

    clamped = max(min_value, min(max_value, numeric_value))
    return True, {
        "requested_value": requested_value,
        "effective_value": clamped,
        "value_status": "clamped",
        "clamped_from": numeric_value,
    }


def build_parameter_attempt(
    plugin_name: Any,
    parameter_name: Any,
    value: Any,
    manifest_path: Any = None,
    manifest_data: Optional[Mapping[str, Any]] = None,
    clamp_unsafe: bool = True,
) -> Dict[str, Any]:
    """Build a deterministic plan for one parameter set.

    The returned object is safe to serialize and can be logged even when no DAW
    executor is available.
    """

    store = ManifestStore(manifest_path=manifest_path, manifest_data=manifest_data)
    plugin = store.resolve_plugin(plugin_name)
    if plugin is None:
        return {
            "success": False,
            "verified": False,
            "status": "unsupported_plugin",
            "plugin": str(plugin_name),
            "available_plugins": store.available_plugins(),
            "message": f"No parameter manifest for plugin '{plugin_name}'",
        }

    parameter = store.resolve_parameter(plugin_name, parameter_name)
    if parameter is None:
        return {
            "success": False,
            "verified": False,
            "status": "unsupported_parameter",
            "plugin": plugin.get("canonical_name", plugin_name),
            "parameter": str(parameter_name),
            "available_parameters": store.available_parameters(plugin_name),
            "message": (
                f"No parameter contract for '{parameter_name}' on "
                f"{plugin.get('canonical_name', plugin_name)}"
            ),
        }

    value_ok, value_info = _prepare_value(parameter, value, clamp_unsafe=clamp_unsafe)
    if not value_ok:
        return {
            "success": False,
            "verified": False,
            "status": value_info.get("status", "unsafe"),
            "plugin": plugin.get("canonical_name", plugin_name),
            "parameter": parameter.get("display_name", parameter_name),
            "parameter_key": parameter.get("parameter_key"),
            **value_info,
        }

    verify = parameter.get("verify") if isinstance(parameter.get("verify"), dict) else {}
    method_plan = _method_plan(parameter)
    return {
        "success": True,
        "verified": False,
        "status": "planned",
        "contract_schema": CONTRACT_SCHEMA_VERSION,
        "plugin": plugin.get("canonical_name", plugin_name),
        "plugin_id": plugin.get("plugin_id"),
        "parameter": parameter.get("display_name", parameter_name),
        "parameter_key": parameter.get("parameter_key"),
        "target_unit": parameter.get("target_unit"),
        "requested_value": value_info.get("requested_value"),
        "effective_value": value_info.get("effective_value"),
        "value_status": value_info.get("value_status", "accepted"),
        "clamped_from": value_info.get("clamped_from"),
        "safe_range": parameter.get("safe_range"),
        "method_plan": method_plan,
        "lom_name_candidates": _list(parameter.get("lom_name_candidates")),
        "verify": verify,
        "fallbacks": [method for method in method_plan if method not in EXECUTABLE_METHODS],
        "musical_role": parameter.get("musical_role"),
    }


def execute_parameter_contract(
    reliable: Any,
    track_index: int,
    device_index: int,
    plugin_name: Any,
    parameter_name: Any,
    value: Any,
    manifest_path: Any = None,
    manifest_data: Optional[Mapping[str, Any]] = None,
    clamp_unsafe: bool = True,
    allow_unverified: bool = False,
    max_retries: int = 3,
    verify_delay: Optional[float] = None,
) -> Dict[str, Any]:
    """Execute one parameter contract through the reliable parameter controller.

    This is intentionally conservative: success means verified readback unless
    the caller explicitly opts into ``allow_unverified``.
    """

    plan = build_parameter_attempt(
        plugin_name=plugin_name,
        parameter_name=parameter_name,
        value=value,
        manifest_path=manifest_path,
        manifest_data=manifest_data,
        clamp_unsafe=clamp_unsafe,
    )
    if not plan.get("success"):
        return plan

    if reliable is None or not hasattr(reliable, "set_parameter_by_name"):
        plan.update(
            {
                "success": False,
                "verified": False,
                "status": "executor_missing",
                "message": "No reliable parameter controller supplied",
                "attempts": [],
            }
        )
        return plan

    attempts: List[Dict[str, Any]] = []
    tolerance = None
    verify = plan.get("verify")
    if isinstance(verify, dict):
        tolerance = verify.get("tolerance")

    for method in plan["method_plan"]:
        if method != "ableton_lom":
            attempts.append(
                {
                    "method": method,
                    "status": "not_implemented",
                    "message": "Fallback is declared in the manifest but has no executor yet.",
                }
            )
            continue

        for candidate in plan["lom_name_candidates"]:
            result = _call_set_parameter_by_name(
                reliable=reliable,
                track_index=track_index,
                device_index=device_index,
                parameter_name=candidate,
                value=plan["effective_value"],
                max_retries=max_retries,
                verify_delay=verify_delay,
                tolerance=tolerance,
            )
            attempt = {
                "method": "ableton_lom",
                "candidate": candidate,
                "result": _safe_json(result),
            }
            attempts.append(attempt)

            if not bool(result.get("success")):
                continue

            verified = bool(result.get("verified"))
            plan.update(
                {
                    "success": verified or allow_unverified,
                    "verified": verified,
                    "status": "verified" if verified else "attempted_unverified",
                    "track_index": track_index,
                    "device_index": device_index,
                    "used_method": "ableton_lom",
                    "used_parameter_name": candidate,
                    "controller_result": _safe_json(result),
                    "attempts": attempts,
                    "message": (
                        "Parameter verified by LOM readback"
                        if verified
                        else "Parameter write reported success, but readback was not verified"
                    ),
                }
            )
            return plan

    plan.update(
        {
            "success": False,
            "verified": False,
            "status": "attempted_unverified",
            "track_index": track_index,
            "device_index": device_index,
            "attempts": attempts,
            "message": "No declared control method produced a verified parameter readback",
        }
    )
    return plan


def execute_parameter_contracts(
    reliable: Any,
    track_index: int,
    device_index: int,
    plugin_name: Any,
    settings: Mapping[str, Any],
    **kwargs: Any,
) -> Dict[str, Any]:
    """Execute multiple parameter contracts and keep per-parameter proof."""

    if not isinstance(settings, Mapping):
        return {
            "success": False,
            "verified": False,
            "status": "invalid_settings",
            "message": "settings must be a mapping of parameter names to values",
        }

    results = []
    for parameter_name, value in settings.items():
        results.append(
            execute_parameter_contract(
                reliable=reliable,
                track_index=track_index,
                device_index=device_index,
                plugin_name=plugin_name,
                parameter_name=parameter_name,
                value=value,
                **kwargs,
            )
        )

    verified_count = sum(1 for result in results if result.get("verified"))
    return {
        "success": verified_count == len(results),
        "verified": verified_count == len(results),
        "status": "verified" if verified_count == len(results) else "partial_or_unverified",
        "plugin": str(plugin_name),
        "total": len(results),
        "verified_count": verified_count,
        "results": results,
    }


def _call_set_parameter_by_name(
    reliable: Any,
    track_index: int,
    device_index: int,
    parameter_name: str,
    value: float,
    max_retries: int,
    verify_delay: Optional[float],
    tolerance: Optional[float],
) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {"max_retries": max_retries}
    if verify_delay is not None:
        kwargs["verify_delay"] = verify_delay
    if tolerance is not None:
        kwargs["tolerance"] = tolerance

    try:
        result = reliable.set_parameter_by_name(
            track_index,
            device_index,
            parameter_name,
            value,
            **kwargs,
        )
    except TypeError:
        result = reliable.set_parameter_by_name(
            track_index,
            device_index,
            parameter_name,
            value,
        )
    except Exception as exc:
        return {
            "success": False,
            "verified": False,
            "message": f"{type(exc).__name__}: {exc}",
        }

    if isinstance(result, dict):
        return result
    return {
        "success": bool(result),
        "verified": bool(result),
        "message": "Controller returned a non-dict result",
        "raw_result": repr(result),
    }


__all__ = [
    "CONTRACT_SCHEMA_VERSION",
    "DEFAULT_MANIFEST_PATH",
    "ManifestStore",
    "ParameterContractError",
    "build_parameter_attempt",
    "execute_parameter_contract",
    "execute_parameter_contracts",
]
