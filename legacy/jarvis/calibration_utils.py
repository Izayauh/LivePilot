"""
Auto-calibration helpers for mapping human units <-> normalized OSC values.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple


CALIBRATION_DB_PATH = os.path.join(os.path.dirname(__file__), "config", "calibration.json")

_VALUE_UNIT_RE = re.compile(
    r"^\s*([+\-]?(?:inf|(?:\d+(?:\.\d+)?)))\s*([a-zA-Z%]+)?\s*$",
    re.IGNORECASE,
)
_RATIO_RE = re.compile(r"^\s*([+\-]?\d+(?:\.\d+)?)\s*:\s*1\s*$")


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_unit(value: float, unit: Optional[str]) -> Tuple[float, Optional[str]]:
    if not unit:
        return value, None

    unit_norm = unit.strip().lower()
    if unit_norm == "khz":
        return value * 1000.0, "Hz"
    if unit_norm == "hz":
        return value, "Hz"
    if unit_norm in ("s", "sec", "secs", "second", "seconds"):
        return value * 1000.0, "ms"
    if unit_norm == "ms":
        return value, "ms"
    if unit_norm == "db":
        return value, "dB"
    if unit_norm == "%":
        return value, "%"
    return value, unit


def parse_display_value(raw: Any) -> Dict[str, Any]:
    """
    Parse Ableton display text (e.g. "19.9 kHz", "-12 dB") into base units.
    """
    text = str(raw).strip()
    if not text:
        return {
            "raw": text,
            "value": None,
            "unit": None,
            "base_value": None,
            "base_unit": None,
            "is_finite": False,
        }

    ratio_match = _RATIO_RE.match(text)
    if ratio_match:
        value = float(ratio_match.group(1))
        return {
            "raw": text,
            "value": value,
            "unit": ":1",
            "base_value": value,
            "base_unit": "ratio",
            "is_finite": True,
        }

    match = _VALUE_UNIT_RE.match(text)
    if not match:
        number = _safe_float(text)
        if number is None:
            return {
                "raw": text,
                "value": None,
                "unit": None,
                "base_value": None,
                "base_unit": None,
                "is_finite": False,
            }
        base_value, base_unit = _normalize_unit(number, None)
        return {
            "raw": text,
            "value": number,
            "unit": None,
            "base_value": base_value,
            "base_unit": base_unit,
            "is_finite": math.isfinite(base_value),
        }

    value_str = match.group(1)
    unit = match.group(2)
    if value_str.lower() in ("inf", "+inf", "-inf"):
        return {
            "raw": text,
            "value": float(value_str),
            "unit": unit,
            "base_value": None,
            "base_unit": None,
            "is_finite": False,
        }

    value = float(value_str)
    base_value, base_unit = _normalize_unit(value, unit)
    return {
        "raw": text,
        "value": value,
        "unit": unit,
        "base_value": base_value,
        "base_unit": base_unit,
        "is_finite": math.isfinite(base_value),
    }


def coerce_target_to_base_value(value: Any, expected_unit: Optional[str] = None) -> Optional[float]:
    """
    Convert a user target (number or string like "500Hz") to a numeric base-unit value.
    """
    if isinstance(value, (int, float)):
        numeric = float(value)
        if expected_unit:
            numeric, _ = _normalize_unit(numeric, expected_unit)
        return numeric

    parsed = parse_display_value(value)
    if parsed["base_value"] is None:
        return None
    return float(parsed["base_value"])


def _mae(observed: Sequence[float], predicted: Sequence[float], denom: float) -> float:
    if not observed:
        return float("inf")
    return sum(abs(o - p) for o, p in zip(observed, predicted)) / len(observed) / max(denom, 1e-9)


def detect_curve_model(points: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Detect whether value(n) is best modeled as linear or logarithmic.
    """
    usable = [
        p for p in points
        if p.get("base_value") is not None and math.isfinite(float(p["base_value"]))
    ]
    usable = sorted(usable, key=lambda p: float(p["normalized"]))

    if len(usable) < 3:
        return {
            "curve_model": "LINEAR",
            "linear_mae": None,
            "log_mae": None,
            "sample_count": len(usable),
        }

    x_vals = [float(p["normalized"]) for p in usable]
    y_vals = [float(p["base_value"]) for p in usable]
    y_min = y_vals[0]
    y_max = y_vals[-1]
    span = abs(y_max - y_min)

    linear_pred = [y_min + ((y_max - y_min) * x) for x in x_vals]
    linear_mae = _mae(y_vals, linear_pred, span if span > 0 else 1.0)

    log_mae = float("inf")
    can_log = y_min > 0 and y_max > 0 and y_max != y_min
    if can_log:
        ratio = y_max / y_min
        log_pred = [y_min * (ratio ** x) for x in x_vals]
        log_mae = _mae(y_vals, log_pred, span)

    # Require a clear improvement before classifying as logarithmic.
    if can_log and log_mae < (linear_mae * 0.8):
        curve_model = "LOGARITHMIC"
    else:
        curve_model = "LINEAR"

    return {
        "curve_model": curve_model,
        "linear_mae": linear_mae,
        "log_mae": log_mae if can_log else None,
        "sample_count": len(usable),
    }


def _interpolate_normalized(points: Sequence[Dict[str, Any]], base_value: float) -> Optional[float]:
    usable = [
        p for p in points
        if p.get("base_value") is not None and math.isfinite(float(p["base_value"]))
    ]
    if len(usable) < 2:
        return None
    usable = sorted(usable, key=lambda p: float(p["base_value"]))
    x0 = float(usable[0]["base_value"])
    x1 = float(usable[-1]["base_value"])
    if base_value <= x0:
        return float(usable[0]["normalized"])
    if base_value >= x1:
        return float(usable[-1]["normalized"])
    for left, right in zip(usable, usable[1:]):
        lv = float(left["base_value"])
        rv = float(right["base_value"])
        if lv <= base_value <= rv and rv != lv:
            t = (base_value - lv) / (rv - lv)
            return float(left["normalized"]) + t * (
                float(right["normalized"]) - float(left["normalized"])
            )
    return None


def value_to_normalized_from_curve(target_base_value: float, curve: Dict[str, Any]) -> Optional[float]:
    """
    Convert a base-unit target value into normalized 0..1 using a calibrated curve.
    """
    range_info = curve.get("range", {})
    min_value = _safe_float(range_info.get("min"))
    max_value = _safe_float(range_info.get("max"))
    model = str(curve.get("curve_model", "LINEAR")).upper()

    if min_value is None or max_value is None or max_value == min_value:
        interpolated = _interpolate_normalized(curve.get("points", []), target_base_value)
        return _clamp01(interpolated) if interpolated is not None else None

    if model == "LOGARITHMIC" and min_value > 0 and max_value > 0 and target_base_value > 0:
        ratio = max_value / min_value
        if ratio <= 0 or ratio == 1.0:
            return _clamp01((target_base_value - min_value) / (max_value - min_value))
        return _clamp01(math.log(target_base_value / min_value) / math.log(ratio))

    return _clamp01((target_base_value - min_value) / (max_value - min_value))


class CalibrationStore:
    def __init__(self, path: str = CALIBRATION_DB_PATH):
        self.path = path

    def load(self) -> Dict[str, Any]:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except (OSError, json.JSONDecodeError):
                pass
        return {"version": 1, "plugins": {}}

    def save(self, data: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _find_plugin_key(self, data: Dict[str, Any], plugin_name: str) -> Optional[str]:
        plugins = data.get("plugins", {})
        target = plugin_name.lower()
        for key in plugins:
            if key.lower() == target:
                return key
        return None

    def get_curve(
        self,
        plugin_name: str,
        param_name: str,
        param_index: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        data = self.load()
        plugin_key = self._find_plugin_key(data, plugin_name)
        if not plugin_key:
            return None

        plugin = data["plugins"].get(plugin_key, {})
        params = plugin.get("parameters", {})
        target = param_name.lower()
        for key, curve in params.items():
            if key.lower() == target:
                return curve

        if param_index is not None:
            for curve in params.values():
                if curve.get("param_index") == param_index:
                    return curve
        return None

    def upsert_plugin_calibration(self, plugin_name: str, plugin_data: Dict[str, Any]) -> None:
        data = self.load()
        plugins = data.setdefault("plugins", {})
        existing_key = self._find_plugin_key(data, plugin_name)
        key = existing_key or plugin_name

        existing = plugins.get(key, {})
        existing_params = existing.get("parameters", {})
        new_params = plugin_data.get("parameters", {})
        existing_params.update(new_params)

        merged = dict(existing)
        merged.update(plugin_data)
        merged["parameters"] = existing_params
        merged["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        plugins[key] = merged
        data["version"] = 1
        self.save(data)


class CalibrationSweeper:
    """
    Sweeps normalized values 0.0 -> 1.0, captures display strings, and fits curves.
    """

    def __init__(
        self,
        ableton_controller: Any,
        settle_ms: int = 50,
        query_timeout_s: float = 2.0,
    ):
        self.ableton = ableton_controller
        self.settle_s = max(0.0, settle_ms / 1000.0)
        self.query_timeout_s = query_timeout_s

    @staticmethod
    def _sweep_values() -> List[float]:
        return [round(i * 0.1, 1) for i in range(11)]

    def _read_display_value(self, track_index: int, device_index: int, param_index: int) -> str:
        value_string_result = self.ableton.get_device_parameter_value_string_sync(
            track_index, device_index, param_index, timeout=self.query_timeout_s
        )
        if value_string_result.get("success"):
            return str(value_string_result.get("value_string", ""))

        numeric_result = self.ableton.get_device_parameter_value_sync(
            track_index, device_index, param_index, timeout=self.query_timeout_s
        )
        if numeric_result.get("success"):
            return str(numeric_result.get("value"))
        return ""

    def sweep_parameter(
        self,
        track_index: int,
        device_index: int,
        param_index: int,
        param_name: str,
    ) -> Dict[str, Any]:
        initial_read = self.ableton.get_device_parameter_value_sync(
            track_index, device_index, param_index, timeout=self.query_timeout_s
        )
        initial_value = initial_read.get("value") if initial_read.get("success") else None

        points: List[Dict[str, Any]] = []
        for normalized in self._sweep_values():
            self.ableton.set_device_parameter(track_index, device_index, param_index, normalized)
            time.sleep(self.settle_s)

            display = self._read_display_value(track_index, device_index, param_index)
            parsed = parse_display_value(display)
            points.append(
                {
                    "normalized": normalized,
                    "display": display,
                    "base_value": parsed.get("base_value"),
                    "base_unit": parsed.get("base_unit"),
                }
            )

        if initial_value is not None:
            self.ableton.set_device_parameter(track_index, device_index, param_index, initial_value)

        fit = detect_curve_model(points)
        finite_points = [p for p in points if p.get("base_value") is not None]
        mid_point = next((p for p in points if abs(float(p["normalized"]) - 0.5) < 1e-9), None)
        unit = next((p.get("base_unit") for p in finite_points if p.get("base_unit")), None)

        curve = {
            "param_index": param_index,
            "param_name": param_name,
            "curve_model": fit["curve_model"],
            "unit": unit,
            "range": {
                "min": finite_points[0]["base_value"] if finite_points else None,
                "mid": mid_point["base_value"] if mid_point else None,
                "max": finite_points[-1]["base_value"] if finite_points else None,
            },
            "fit": fit,
            "points": points,
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        return curve

    def sweep_device(
        self,
        track_index: int,
        device_index: int,
        param_indices: Optional[Sequence[int]] = None,
    ) -> Dict[str, Any]:
        name_result = self.ableton.get_device_name_sync(track_index, device_index, timeout=self.query_timeout_s)
        if name_result.get("success"):
            plugin_name = name_result.get("name") or f"Track {track_index} Device {device_index}"
        else:
            plugin_name = f"Track {track_index} Device {device_index}"

        params_result = self.ableton.get_device_parameters_name_sync(track_index, device_index, timeout=self.query_timeout_s)
        param_names = params_result.get("names", []) if params_result.get("success") else []
        if not param_names:
            raise RuntimeError(f"Could not fetch parameter names for track={track_index}, device={device_index}")

        targets = list(param_indices) if param_indices is not None else list(range(len(param_names)))
        curves: Dict[str, Any] = {}
        errors: List[Dict[str, Any]] = []
        for idx in targets:
            if idx < 0 or idx >= len(param_names):
                errors.append({"param_index": idx, "error": "index out of range"})
                continue
            param_name = param_names[idx]
            try:
                curve = self.sweep_parameter(track_index, device_index, idx, param_name)
                curves[param_name] = curve
            except Exception as exc:
                errors.append({"param_index": idx, "param_name": param_name, "error": str(exc)})

        return {
            "plugin_name": plugin_name,
            "track_index": track_index,
            "device_index": device_index,
            "parameters": curves,
            "errors": errors,
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    def sweep_and_save(
        self,
        track_index: int,
        device_index: int,
        param_indices: Optional[Sequence[int]] = None,
        store_path: str = CALIBRATION_DB_PATH,
    ) -> Dict[str, Any]:
        result = self.sweep_device(track_index, device_index, param_indices=param_indices)
        store = CalibrationStore(store_path)
        store.upsert_plugin_calibration(result["plugin_name"], result)
        return result
