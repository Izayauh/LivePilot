"""Save and apply per-device plugin parameter recipes (committed JSON snapshots)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

RECIPE_SCHEMA = "livepilot-plugin-recipe-v1"
_REPO_ROOT = Path(__file__).resolve().parents[1]
RECIPES_DIR = _REPO_ROOT / "data" / "recipes"


def _safe_slug(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", name.strip()).strip("-").lower()
    if not slug:
        raise ValueError("recipe name must contain at least one alphanumeric character")
    return slug


def _recipe_path(name: str) -> Path:
    return RECIPES_DIR / f"{_safe_slug(name)}.json"


def list_plugin_recipes() -> Dict[str, Any]:
    """List recipe files under data/recipes/."""
    if not RECIPES_DIR.exists():
        return {"success": True, "recipes": [], "count": 0}

    recipes: List[Dict[str, str]] = []
    for path in sorted(RECIPES_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            recipes.append(
                {
                    "name": str(data.get("name") or path.stem),
                    "file": path.name,
                    "plugin_name": str(data.get("plugin_name") or ""),
                }
            )
        except (json.JSONDecodeError, OSError):
            recipes.append({"name": path.stem, "file": path.name, "plugin_name": ""})

    return {"success": True, "recipes": recipes, "count": len(recipes)}


def load_plugin_recipe(name: str) -> Dict[str, Any]:
    path = _recipe_path(name)
    if not path.exists():
        return {"success": False, "message": f"Recipe not found: {name}"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"success": False, "message": f"Failed to read recipe: {exc}"}
    return {"success": True, "recipe": data, "path": str(path)}


def _snapshot_device_params(
    controller: Any,
    track_index: int,
    device_index: int,
) -> Dict[str, Any]:
    names_result = controller.get_device_parameters_name_sync(track_index, device_index)
    if not names_result.get("success"):
        return names_result

    names = names_result.get("names") or []
    params: Dict[str, float] = {}
    for index, param_name in enumerate(names):
        if not isinstance(param_name, str) or not param_name.strip():
            continue
        value_result = controller.get_device_parameter_value_sync(
            track_index, device_index, index
        )
        if not value_result.get("success"):
            continue
        value = value_result.get("value")
        if isinstance(value, (int, float)):
            params[param_name] = float(value)

    device_name = ""
    device_class = ""
    name_result = controller.get_device_name(track_index, device_index)
    if isinstance(name_result, dict) and name_result.get("success"):
        device_name = str(name_result.get("name") or name_result.get("device_name") or "")
    class_result = controller.get_device_class_name(track_index, device_index)
    if isinstance(class_result, dict) and class_result.get("success"):
        device_class = str(
            class_result.get("class_name")
            or class_result.get("device_class_name")
            or ""
        )

    return {
        "success": True,
        "plugin_name": device_name,
        "device_class": device_class,
        "params": params,
        "param_count": len(params),
    }


def save_plugin_recipe(
    name: str,
    track_index: int,
    device_index: int,
    *,
    controller: Any,
    note: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Snapshot current device parameters to data/recipes/<name>.json."""
    snapshot = _snapshot_device_params(controller, track_index, device_index)
    if not snapshot.get("success"):
        return snapshot

    RECIPES_DIR.mkdir(parents=True, exist_ok=True)
    path = _recipe_path(name)
    payload: Dict[str, Any] = {
        "schema": RECIPE_SCHEMA,
        "name": _safe_slug(name),
        "plugin_name": snapshot.get("plugin_name", ""),
        "device_class": snapshot.get("device_class", ""),
        "params": snapshot.get("params", {}),
    }
    if note:
        payload["notes"] = note
    if extra:
        payload.update(dict(extra))

    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {
        "success": True,
        "message": f"Saved recipe '{name}'",
        "path": str(path),
        "param_count": snapshot.get("param_count", 0),
        "plugin_name": payload.get("plugin_name"),
    }


def apply_plugin_recipe(
    name: str,
    track_index: int,
    device_index: int,
    *,
    reliable: Any,
    controller: Any | None = None,
) -> Dict[str, Any]:
    """Apply a saved recipe via ReliableParameterController.set_parameters_by_name."""
    loaded = load_plugin_recipe(name)
    if not loaded.get("success"):
        return loaded

    recipe = loaded.get("recipe") or {}
    params = recipe.get("params") or {}
    if not isinstance(params, dict) or not params:
        return {"success": False, "message": f"Recipe '{name}' has no params"}

    result = reliable.set_parameters_by_name(track_index, device_index, params)
    if isinstance(result, dict):
        result.setdefault("recipe", recipe.get("name") or name)
    return result
