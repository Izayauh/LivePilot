#!/usr/bin/env python3
"""Remember user tweaks from an Ableton track as vocal chain preferences."""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from preferences.chain_preferences import load_overrides, merge_with_template, save_overrides
from plugins.chain_resolver import resolve_plugin


EPSILON = 0.01


def _execute(func_name: str, args: dict) -> dict:
    """Call an ableton_bridge function directly."""
    import ableton_bridge

    dispatch = ableton_bridge._build_dispatch(args)
    if func_name not in dispatch:
        return {"success": False, "message": f"Unknown function: {func_name}"}
    try:
        return dispatch[func_name]()
    except Exception as e:
        return {"success": False, "message": str(e)}


def load_owned_plugins() -> dict:
    with open(os.path.join(_REPO_ROOT, "config", "owned_plugins.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def load_template_chain(style: str) -> list[dict]:
    path = os.path.join(_REPO_ROOT, "knowledge", "plugin_chains.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    styles = data.get("waves_vocal_chains", {})
    if style not in styles:
        available = ", ".join(sorted(styles))
        raise ValueError(f"Unknown Waves vocal chain style '{style}'. Available: {available}")

    return styles[style].get("chain", [])


def resolve_template_plugins(template_chain: list[dict], owned: dict) -> list[dict]:
    resolved = []
    for step in template_chain:
        plugin_name, host = resolve_plugin(step.get("plugin_suggestions", []), owned)
        step_copy = dict(step)
        step_copy["plugin_name"] = plugin_name
        step_copy["host"] = host
        resolved.append(step_copy)
    return resolved


def _coerce_parameter_map(result: dict, track_index: int, device_index: int) -> dict:
    """Read current params from bridge output, supporting names-only and dict shapes."""
    if not result.get("success"):
        return {}

    for key in ("parameters", "params", "values"):
        value = result.get(key)
        if isinstance(value, dict):
            return value

    names = result.get("names", [])
    values = {}
    for param_index, name in enumerate(names):
        value_result = _execute(
            "get_device_parameter_value",
            {
                "track_index": track_index,
                "device_index": device_index,
                "param_index": param_index,
            },
        )
        if value_result.get("success") and value_result.get("value") is not None:
            values[name] = value_result["value"]
    return values


def diff_overrides(track_index: int, style: str) -> tuple[dict, list[str], list[str]]:
    template_chain = load_template_chain(style)
    owned = load_owned_plugins()
    resolved_chain = resolve_template_plugins(template_chain, owned)
    existing_overrides = load_overrides(style)
    defaults_chain = merge_with_template(resolved_chain, existing_overrides)

    devices_result = _execute("get_track_devices", {"track_index": track_index})
    track_devices = devices_result.get("devices", []) if devices_result.get("success") else []

    overrides = copy.deepcopy(existing_overrides)
    summaries = []
    warnings = []

    for index, step in enumerate(defaults_chain):
        expected_name = step.get("plugin_name", "")
        if index >= len(track_devices):
            warnings.append(f"Missing device {index}: expected {expected_name}")
            continue

        actual_name = track_devices[index]
        if expected_name and expected_name.lower() not in actual_name.lower():
            warnings.append(
                f"Device {index} mismatch: expected {expected_name}, found {actual_name}. Skipping."
            )
            continue

        loaded_defaults = step.get("settings", {})
        base_defaults = resolved_chain[index].get("settings", {})
        if not loaded_defaults:
            continue

        params_result = _execute(
            "get_device_parameters",
            {"track_index": track_index, "device_index": index},
        )
        current_params = _coerce_parameter_map(params_result, track_index, index)

        device_key = f"device_{index}"
        device_overrides = overrides.setdefault(device_key, {})
        for name, default_value in loaded_defaults.items():
            if name not in current_params:
                continue
            current_value = current_params[name]
            if not isinstance(default_value, (int, float)) or not isinstance(current_value, (int, float)):
                continue
            if abs(float(current_value) - float(default_value)) > EPSILON:
                base_value = base_defaults.get(name)
                if isinstance(base_value, (int, float)) and abs(float(current_value) - float(base_value)) <= EPSILON:
                    device_overrides.pop(name, None)
                else:
                    device_overrides[name] = current_value
                summaries.append(f"{name}: {default_value:.2f} -> {current_value:.2f}")

        if not device_overrides:
            overrides.pop(device_key, None)

    return overrides, summaries, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Remember vocal chain tweaks as preferences")
    parser.add_argument("--track", type=int, required=True, help="Track index (0-based)")
    parser.add_argument("--style", type=str, required=True, help="Waves vocal chain style")
    parser.add_argument("--note", type=str, default=None, help="Optional note about the tweak")
    args = parser.parse_args()

    overrides, summaries, warnings = diff_overrides(args.track, args.style)
    for warning in warnings:
        print(f"WARNING: {warning}")

    save_overrides(args.style, overrides, args.note)
    count = sum(len(params) for params in overrides.values())
    suffix = f" {', '.join(summaries)}" if summaries else ""
    print(f"Saved {count} parameter overrides for {args.style}.{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
