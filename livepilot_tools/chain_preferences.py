"""Local per-style vocal chain preference persistence."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = "live-pilot/chain-preferences.v1"
_REPO_ROOT = Path(__file__).resolve().parents[1]
PREFERENCES_DIR = _REPO_ROOT / "data" / "chain_preferences"


def _preference_path(style: str) -> Path:
    safe_style = style.replace("/", "_").replace("\\", "_")
    return PREFERENCES_DIR / f"vocal_chain_{safe_style}.json"


def load_overrides(style: str) -> dict:
    """Return parameter overrides for a chain style. Empty dict if no preferences saved."""
    path = _preference_path(style)
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("overrides", {})


def save_overrides(style: str, overrides: dict, note: str | None = None) -> Path:
    """Persist parameter overrides for a chain style. Overwrites previous."""
    PREFERENCES_DIR.mkdir(parents=True, exist_ok=True)
    path = _preference_path(style)
    updated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    data = {
        "schemaVersion": SCHEMA_VERSION,
        "style": style,
        "updatedAt": updated_at.replace("+00:00", "Z"),
        "note": note,
        "overrides": overrides,
        "referenceTracks": [],
    }

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    return path


def merge_with_template(template_chain: list[dict], overrides: dict) -> list[dict]:
    """Apply overrides on top of template settings. Overrides win on conflict."""
    merged = copy.deepcopy(template_chain)
    if not overrides:
        return merged

    for index, step in enumerate(merged):
        step_overrides = overrides.get(f"device_{index}", {})
        if step_overrides:
            settings = step.setdefault("settings", {})
            settings.update(step_overrides)

    return merged
