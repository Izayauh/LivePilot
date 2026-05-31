#!/usr/bin/env python3
"""
Adaptive control layer for Ableton Live devices.

Normalizes friendly semantic inputs (e.g. "air", "presence", "low_cut", "mud")
to concrete parameter names for common devices, then resolves them through
ReliableParameterController's name-based API.

This module is deterministic — once started, it requires zero LLM calls.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Semantic alias tables
#
# Each device maps *friendly aliases* to the canonical semantic key understood
# by ``ReliableParameterController.SEMANTIC_PARAM_MAPPINGS``.
#
# Format:  alias_string  ->  (semantic_key, default_value | None)
#
# ``default_value`` is provided only for on/off toggles so the caller can
# auto-enable bands as a side-effect.  For continuously variable parameters
# the caller must supply the value explicitly.
# ---------------------------------------------------------------------------

EQ_EIGHT_ALIASES: Dict[str, Tuple[str, Optional[float]]] = {
    # --- Low cut / high-pass ---
    "low_cut":           ("band1_freq_hz", None),
    "lowcut":            ("band1_freq_hz", None),
    "high_pass":         ("band1_freq_hz", None),
    "highpass":          ("band1_freq_hz", None),
    "hp":                ("band1_freq_hz", None),
    "hp_freq":           ("band1_freq_hz", None),
    "low_cut_freq":      ("band1_freq_hz", None),
    "low_cut_on":        ("band1_on", None),

    # --- Mud region (band 2) ---
    "mud":               ("band2_gain_db", None),
    "mud_freq":          ("band2_freq_hz", None),
    "mud_gain":          ("band2_gain_db", None),
    "mud_q":             ("band2_q", None),
    "mud_cut":           ("band2_gain_db", None),
    "mud_type":          ("band2_type", None),
    "mud_on":            ("band2_on", None),

    # --- Presence (band 3) ---
    "presence":          ("band3_gain_db", None),
    "presence_freq":     ("band3_freq_hz", None),
    "presence_gain":     ("band3_gain_db", None),
    "presence_q":        ("band3_q", None),
    "presence_boost":    ("band3_gain_db", None),
    "presence_type":     ("band3_type", None),
    "presence_on":       ("band3_on", None),

    # --- Air / brilliance (band 4) ---
    "air":               ("band4_gain_db", None),
    "air_freq":          ("band4_freq_hz", None),
    "air_gain":          ("band4_gain_db", None),
    "air_q":             ("band4_q", None),
    "air_boost":         ("band4_gain_db", None),
    "air_type":          ("band4_type", None),
    "air_on":            ("band4_on", None),

    # --- Generic band pass-through (no alias rewrite) ---
    "band1_freq_hz":     ("band1_freq_hz", None),
    "band1_gain_db":     ("band1_gain_db", None),
    "band1_q":           ("band1_q", None),
    "band1_type":        ("band1_type", None),
    "band1_on":          ("band1_on", None),
    "band2_freq_hz":     ("band2_freq_hz", None),
    "band2_gain_db":     ("band2_gain_db", None),
    "band2_q":           ("band2_q", None),
    "band2_type":        ("band2_type", None),
    "band2_on":          ("band2_on", None),
    "band3_freq_hz":     ("band3_freq_hz", None),
    "band3_gain_db":     ("band3_gain_db", None),
    "band3_q":           ("band3_q", None),
    "band3_type":        ("band3_type", None),
    "band3_on":          ("band3_on", None),
    "band4_freq_hz":     ("band4_freq_hz", None),
    "band4_gain_db":     ("band4_gain_db", None),
    "band4_q":           ("band4_q", None),
    "band4_type":        ("band4_type", None),
    "band4_on":          ("band4_on", None),
}

COMPRESSOR_ALIASES: Dict[str, Tuple[str, Optional[float]]] = {
    "threshold":         ("threshold_db", None),
    "thresh":            ("threshold_db", None),
    "ratio":             ("ratio", None),
    "attack":            ("attack_ms", None),
    "attack_time":       ("attack_ms", None),
    "release":           ("release_ms", None),
    "release_time":      ("release_ms", None),
    "makeup":            ("output_gain_db", None),
    "makeup_gain":       ("output_gain_db", None),
    "output_gain":       ("output_gain_db", None),
    "knee":              ("knee_db", None),
    "mix":               ("dry_wet_pct", None),
    "dry_wet":           ("dry_wet_pct", None),
    # Pass-through canonical names
    "threshold_db":      ("threshold_db", None),
    "attack_ms":         ("attack_ms", None),
    "release_ms":        ("release_ms", None),
    "output_gain_db":    ("output_gain_db", None),
    "knee_db":           ("knee_db", None),
    "dry_wet_pct":       ("dry_wet_pct", None),
}

# Master registry: device name -> alias dict
DEVICE_ALIAS_REGISTRY: Dict[str, Dict[str, Tuple[str, Optional[float]]]] = {
    "EQ Eight": EQ_EIGHT_ALIASES,
    "Compressor": COMPRESSOR_ALIASES,
}


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

_NORMALISE_RE = re.compile(r"[\s\-]+")


def _normalize_key(raw: str) -> str:
    """Lowercase, collapse whitespace/hyphens to underscores, strip."""
    return _NORMALISE_RE.sub("_", raw.strip().lower())


def resolve_alias(device_name: str, friendly_name: str) -> Tuple[str, Optional[float]]:
    """Resolve a friendly alias to a canonical semantic parameter key.

    Args:
        device_name: Ableton device name (e.g. ``"EQ Eight"``).
        friendly_name: Caller-supplied alias (e.g. ``"air"``).

    Returns:
        ``(canonical_key, default_value)`` if found, or
        ``(friendly_name_normalised, None)`` as a pass-through so the caller
        can still attempt a direct name lookup downstream.
    """
    normed = _normalize_key(friendly_name)
    aliases = DEVICE_ALIAS_REGISTRY.get(device_name, {})
    if normed in aliases:
        return aliases[normed]
    # Not in alias table — return normalised form for direct lookup
    return (normed, None)


def resolve_params(device_name: str,
                   params: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve a dict of ``{friendly_name: value}`` to canonical keys.

    Duplicate keys after normalisation are last-write-wins.

    Returns:
        ``{canonical_key: value}``
    """
    resolved: Dict[str, Any] = {}
    for raw_name, value in params.items():
        canonical, _default = resolve_alias(device_name, raw_name)
        resolved[canonical] = value
    return resolved


# ---------------------------------------------------------------------------
# Deterministic execution helpers
# ---------------------------------------------------------------------------

def set_device_params_adaptive(reliable_params,
                               track_index: int,
                               device_index: int,
                               device_name: str,
                               params: Dict[str, Any],
                               delay_between: float = 0.05) -> Dict[str, Any]:
    """Set device parameters using friendly aliases — deterministic, no LLM.

    Pipeline:
      1. Resolve friendly aliases to canonical semantic keys.
      2. Delegate to ``reliable_params.set_parameters_by_name()``.

    Args:
        reliable_params: ``ReliableParameterController`` instance.
        track_index: 0-based track index.
        device_index: 0-based device index.
        device_name: Ableton device name for alias lookup.
        params: ``{friendly_or_canonical_name: value}``.
        delay_between: Seconds between individual parameter writes.

    Returns:
        Result dict from ``set_parameters_by_name`` with an extra
        ``resolved_params`` key showing the alias→canonical mapping.
    """
    resolved = resolve_params(device_name, params)
    result = reliable_params.set_parameters_by_name(
        track_index, device_index, resolved,
        delay_between=delay_between,
    )
    result["resolved_params"] = resolved
    return result


def build_adaptive_profile_steps(profile_name: str,
                                 device_map: Dict[int, str]) -> Optional[List[Dict[str, Any]]]:
    """Return a list of adaptive (name-based) parameter steps for a vocal profile.

    Each step is ``{"device_index": int, "device_name": str, "params": {name: value}}``.

    Args:
        profile_name: ``"airy_melodic"`` or ``"punchy_rap"``.
        device_map: ``{device_index: device_name}`` from the actual track state.
            Expected to contain at least ``{0: "EQ Eight", 1: "Compressor"}``
            (and optionally ``{7: "EQ Eight"}`` for a second EQ).

    Returns:
        List of step dicts, or ``None`` if ``profile_name`` is unknown.
    """
    eq_name = "EQ Eight"
    comp_name = "Compressor"

    # Common EQ low-cut + mud setup (device_index 0)
    common_eq0: Dict[str, Any] = {
        "band1_on": 1,
        "band1_type": 1,         # 12dB low-cut
        "band1_freq_hz": 100,    # ~100 Hz (adaptive layer resolves via name)
        "band2_on": 1,
        "band2_freq_hz": 300,    # ~300 Hz mud region
    }

    if profile_name == "airy_melodic":
        eq0_specific: Dict[str, Any] = {
            "band2_type": 4,     # Notch
            "band2_gain_db": -2.2,
            "band2_q": 2.8,
            "band3_on": 1,
            "band3_type": 3,     # Bell
            "band3_freq_hz": 2000,
            "band3_gain_db": 1.2,
            "band3_q": 1.2,
        }
        # Second EQ (device_index 7) — air shelf
        eq7_params: Dict[str, Any] = {
            "band4_on": 1,       # band 4 mapped to the 8th band slot semantically
            "band4_type": 5,     # High shelf
            "band4_freq_hz": 8000,
            "band4_gain_db": 1.8,
            "band4_q": 0.8,
        }
        comp_params: Dict[str, Any] = {}

    elif profile_name == "punchy_rap":
        eq0_specific = {
            "band2_type": 3,     # Bell
            "band2_gain_db": -3.0,
            "band2_q": 1.4,
            "band3_on": 1,
            "band3_type": 3,     # Bell
            "band3_freq_hz": 2500,
            "band3_gain_db": 2.2,
            "band3_q": 1.1,
        }
        eq7_params = {
            "band4_on": 1,
            "band4_type": 5,     # High shelf
            "band4_freq_hz": 7000,
            "band4_gain_db": 1.0,
            "band4_q": 1.0,
        }
        comp_params = {
            "ratio": 3.0,       # Firmer ratio
            "attack_ms": 5,     # Faster attack
            "release_ms": 80,   # Faster release
        }
    else:
        return None

    steps: List[Dict[str, Any]] = []

    # Step 1: Primary EQ (device 0)
    if 0 in device_map and device_map[0] == eq_name:
        merged_eq0 = {**common_eq0, **eq0_specific}
        steps.append({
            "device_index": 0,
            "device_name": eq_name,
            "params": merged_eq0,
        })

    # Step 2: Compressor (device 1) — only if profile has comp params
    if comp_params and 1 in device_map and device_map[1] == comp_name:
        steps.append({
            "device_index": 1,
            "device_name": comp_name,
            "params": comp_params,
        })

    # Step 3: Secondary EQ (device 7)
    if eq7_params and 7 in device_map and device_map[7] == eq_name:
        steps.append({
            "device_index": 7,
            "device_name": eq_name,
            "params": eq7_params,
        })

    return steps
