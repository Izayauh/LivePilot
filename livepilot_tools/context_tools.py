"""Creative context snapshots for LivePilot agents.

This module intentionally composes existing state holders instead of owning new
session state. The goal is a compact, structured JSON-ready snapshot that agents
can request before planning Ableton changes.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from context.session_manager import session_manager as default_session_manager
from librarian.session_context import get_librarian_session_context

_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT_INTENT_PATH = _REPO_ROOT / "data" / "project_intent.json"
PROJECT_INTENT_FIELDS = (
    "genre",
    "references",
    "mood",
    "arrangement_goal",
    "prefer",
    "avoid",
    "notes",
)
ARRANGEMENT_PLAN_SCHEMA_VERSION = "arrangement-plan-v1"
ARRANGEMENT_MOVE_TYPES = (
    "midi_clip",
    "automation",
    "device_change",
    "scene_or_arrangement_marker",
    "arrangement_edit",
)

ARRANGEMENT_PLAN_SCHEMA = {
    "schema_version": ARRANGEMENT_PLAN_SCHEMA_VERSION,
    "required_fields": [
        "schema_version",
        "goal",
        "target_section",
        "context_summary",
        "assumptions",
        "constraints",
        "moves",
        "warnings",
        "requires_human_review",
    ],
    "move_types": list(ARRANGEMENT_MOVE_TYPES),
    "move_required_fields": [
        "type",
        "description",
        "target",
        "parameters",
        "reason",
        "status",
    ],
}


def set_project_intent(
    intent: Dict[str, Any],
    storage_path: Any = None,
) -> Dict[str, Any]:
    """Persist project intent as deterministic local JSON."""
    if not isinstance(intent, dict):
        return {"success": False, "message": "intent must be a dict"}

    normalized = _empty_project_intent()
    normalized.update({field: _json_safe(intent.get(field, normalized[field])) for field in PROJECT_INTENT_FIELDS})
    for key, value in intent.items():
        if key not in normalized and key != "updated_at":
            normalized[key] = _json_safe(value)
    normalized["updated_at"] = datetime.now().isoformat()

    try:
        json.dumps(normalized)
    except TypeError as exc:
        return {"success": False, "message": f"intent must be JSON-serializable: {exc}"}

    path = _project_intent_path(storage_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "success": True,
        "project_intent": normalized,
        "path": str(path),
    }


def get_project_intent(storage_path: Any = None) -> Dict[str, Any]:
    """Load the persisted project intent, if one has been set."""
    path = _project_intent_path(storage_path)
    if not path.exists():
        return {
            "success": True,
            "project_intent": _empty_project_intent(),
            "path": str(path),
            "exists": False,
        }

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "success": False,
            "project_intent": _empty_project_intent(),
            "path": str(path),
            "message": f"Failed to load project intent: {exc}",
        }

    if not isinstance(data, dict):
        return {
            "success": False,
            "project_intent": _empty_project_intent(),
            "path": str(path),
            "message": "Stored project intent must be a JSON object",
        }

    return {
        "success": True,
        "project_intent": data,
        "path": str(path),
        "exists": True,
    }


def get_creative_context(
    controller: Any = None,
    reliable: Any = None,
    session_manager: Any = None,
    librarian_context: Any = None,
    project_intent_path: Any = None,
    recent_action_count: int = 10,
) -> Dict[str, Any]:
    """Return a JSON-serializable snapshot of the current creative session.

    Args:
        controller: Optional Ableton controller. Tests and wrappers may inject a
            fake; when omitted, controller-only fields are reported as missing.
        reliable: Reserved for parity with other shared LivePilot tools.
        session_manager: Optional SessionManager-like object.
        librarian_context: Optional LibrarianSessionContext-like object.
        project_intent_path: Optional override for tests or alternate local state.
        recent_action_count: Number of recent actions to include.
    """
    _ = reliable
    manager = session_manager or default_session_manager
    librarian = librarian_context or get_librarian_session_context()
    missing_fields: List[str] = []
    limitations: List[str] = []

    live_snapshot = _read_controller_snapshot(controller, missing_fields, limitations)
    session_state = getattr(manager, "state", None)

    transport = _build_transport(session_state, live_snapshot)
    loop = _build_loop(session_state)
    tracks = _build_tracks_summary(session_state, live_snapshot, missing_fields)
    selected = _build_selected_context(session_state, tracks, missing_fields)
    selected_clip = _build_selected_clip_context(selected, controller, reliable, missing_fields, limitations)
    librarian_active = _build_librarian_context(librarian, missing_fields)
    project_intent = get_project_intent(project_intent_path)
    if not project_intent.get("exists"):
        missing_fields.append("project_intent")
    recent_actions = _recent_actions(manager, recent_action_count)

    context = {
        "transport": transport,
        "loop": loop,
        "tracks": tracks,
        "selected": selected,
        "selected_clip": selected_clip,
        "active_librarian": librarian_active,
        "project_intent": project_intent.get("project_intent", _empty_project_intent()),
        "recent_actions": recent_actions,
        "project": {
            "name": getattr(manager, "project_name", None),
            "genre": getattr(manager, "detected_genre", None),
            "stage": getattr(manager, "mixing_stage", None),
            "last_updated": _iso_or_none(getattr(manager, "last_updated", None)),
            "num_scenes": _coalesce(
                live_snapshot.get("num_scenes"),
                getattr(session_state, "num_scenes", None),
            ),
        },
        "known_limitations": {
            "limitations": limitations,
            "missing_fields": sorted(set(missing_fields)),
        },
        "generated_at": datetime.now().isoformat(),
    }

    return _json_safe(context)


def analyze_clip_context(
    track_index: int,
    clip_index: int,
    controller: Any = None,
    reliable: Any = None,
) -> Dict[str, Any]:
    """Return MIDI-note summary stats for one Session clip where available.

    This is intentionally metadata/MIDI-only. It does not listen to audio or infer
    key, chord, emotion, or energy. When the current controller cannot expose a
    field, the field is left ``None`` and listed in ``missing_fields``.
    """
    _ = reliable
    try:
        track_index = int(track_index)
        clip_index = int(clip_index)
    except (TypeError, ValueError):
        return {
            "success": False,
            "message": "track_index and clip_index must be integers",
            "track_index": track_index,
            "clip_index": clip_index,
            "limitations": ["Invalid clip address; no Ableton query attempted."],
            "missing_fields": ["track_index", "clip_index"],
        }

    summary: Dict[str, Any] = {
        "success": True,
        "track_index": track_index,
        "clip_index": clip_index,
        "clip_name": None,
        "clip_length_beats": None,
        "note_count": None,
        "pitch_min": None,
        "pitch_max": None,
        "pitch_range": None,
        "velocity_min": None,
        "velocity_max": None,
        "average_velocity": None,
        "note_start_min": None,
        "note_end_max": None,
        "density_notes_per_beat": None,
        "limitations": [],
        "missing_fields": [],
    }
    missing_fields: List[str] = summary["missing_fields"]
    limitations: List[str] = summary["limitations"]

    if track_index < 0 or clip_index < 0:
        summary["success"] = False
        summary["message"] = "track_index and clip_index must be zero-based non-negative integers"
        limitations.append("Invalid clip address; no Ableton query attempted.")
        missing_fields.extend(_clip_context_value_fields())
        return _json_safe(summary)

    if controller is None:
        limitations.append("No Ableton controller supplied; MIDI clip fields are unavailable.")
        missing_fields.extend(_clip_context_value_fields())
        return _json_safe(summary)

    clip_payload = _read_clip_metadata(controller, track_index, clip_index, limitations)
    _merge_clip_metadata(summary, clip_payload)

    notes_result = _read_clip_notes(controller, track_index, clip_index, limitations)
    note_count_hint = _int_or_none(_coalesce(notes_result.get("note_count"), notes_result.get("count")))
    raw_notes = notes_result.get("notes")

    if raw_notes is None:
        if note_count_hint is not None:
            summary["note_count"] = note_count_hint
            missing_fields.extend(
                [
                    "pitch_min",
                    "pitch_max",
                    "pitch_range",
                    "velocity_min",
                    "velocity_max",
                    "average_velocity",
                    "note_start_min",
                    "note_end_max",
                ]
            )
        else:
            missing_fields.extend(
                [
                    "note_count",
                    "pitch_min",
                    "pitch_max",
                    "pitch_range",
                    "velocity_min",
                    "velocity_max",
                    "average_velocity",
                    "note_start_min",
                    "note_end_max",
                ]
            )
    else:
        normalized_notes = [_normalize_note(note) for note in raw_notes]
        summary["note_count"] = len(normalized_notes)
        _merge_note_stats(summary, normalized_notes, missing_fields, limitations)

    if summary["clip_name"] is None:
        missing_fields.append("clip_name")
    if summary["clip_length_beats"] is None:
        missing_fields.append("clip_length_beats")

    note_count = summary.get("note_count")
    clip_length = summary.get("clip_length_beats")
    if isinstance(note_count, int) and isinstance(clip_length, (int, float)) and clip_length > 0:
        summary["density_notes_per_beat"] = note_count / float(clip_length)
    else:
        missing_fields.append("density_notes_per_beat")

    summary["missing_fields"] = sorted(set(missing_fields))
    summary["limitations"] = sorted(set(limitations))
    return _json_safe(summary)


def plan_arrangement_move(
    goal: str,
    target_section: Optional[str] = None,
    controller: Any = None,
    reliable: Any = None,
    session_manager: Any = None,
    librarian_context: Any = None,
    project_intent_path: Any = None,
) -> Dict[str, Any]:
    """Build a reviewable arrangement plan without executing Ableton changes."""
    if not isinstance(goal, str) or not goal.strip():
        plan = _empty_arrangement_plan(goal=goal, target_section=target_section)
        plan["warnings"].append("Goal must be a non-empty string.")
        plan["requires_human_review"] = True
        return _finalize_arrangement_plan(plan)

    context = get_creative_context(
        controller=controller,
        reliable=reliable,
        session_manager=session_manager,
        librarian_context=librarian_context,
        project_intent_path=project_intent_path,
    )
    context_summary = _arrangement_context_summary(context)
    plan = {
        "schema_version": ARRANGEMENT_PLAN_SCHEMA_VERSION,
        "goal": goal.strip(),
        "target_section": target_section,
        "context_summary": context_summary,
        "assumptions": _arrangement_assumptions(context, target_section),
        "constraints": _arrangement_constraints(),
        "moves": _arrangement_moves(goal.strip(), target_section, context_summary),
        "warnings": _arrangement_warnings(goal.strip(), context),
        "requires_human_review": _goal_requires_human_review(goal) or _context_requires_human_review(context),
    }
    return _finalize_arrangement_plan(plan)


def validate_arrangement_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the local arrangement plan schema shape."""
    errors: List[str] = []
    if not isinstance(plan, dict):
        return {"success": False, "valid": False, "errors": ["plan must be a dict"]}

    for field in ARRANGEMENT_PLAN_SCHEMA["required_fields"]:
        if field not in plan:
            errors.append(f"missing required field: {field}")

    if plan.get("schema_version") != ARRANGEMENT_PLAN_SCHEMA_VERSION:
        errors.append(f"schema_version must be {ARRANGEMENT_PLAN_SCHEMA_VERSION}")

    if not isinstance(plan.get("goal"), str) or not plan.get("goal", "").strip():
        errors.append("goal must be a non-empty string")

    if plan.get("target_section") is not None and not isinstance(plan.get("target_section"), str):
        errors.append("target_section must be a string or null")

    for field in ("context_summary",):
        if field in plan and not isinstance(plan.get(field), dict):
            errors.append(f"{field} must be a dict")

    for field in ("assumptions", "constraints", "warnings"):
        if field in plan and not isinstance(plan.get(field), list):
            errors.append(f"{field} must be a list")

    if "requires_human_review" in plan and not isinstance(plan.get("requires_human_review"), bool):
        errors.append("requires_human_review must be a bool")

    moves = plan.get("moves")
    if not isinstance(moves, list):
        errors.append("moves must be a list")
    else:
        for index, move in enumerate(moves):
            if not isinstance(move, dict):
                errors.append(f"moves[{index}] must be a dict")
                continue
            for field in ARRANGEMENT_PLAN_SCHEMA["move_required_fields"]:
                if field not in move:
                    errors.append(f"moves[{index}] missing required field: {field}")
            if move.get("type") not in ARRANGEMENT_MOVE_TYPES:
                errors.append(f"moves[{index}].type must be one of {list(ARRANGEMENT_MOVE_TYPES)}")
            if "parameters" in move and not isinstance(move.get("parameters"), dict):
                errors.append(f"moves[{index}].parameters must be a dict")

    return {"success": not errors, "valid": not errors, "errors": errors, "schema": ARRANGEMENT_PLAN_SCHEMA}


def _empty_arrangement_plan(goal: Any, target_section: Optional[str]) -> Dict[str, Any]:
    return {
        "schema_version": ARRANGEMENT_PLAN_SCHEMA_VERSION,
        "goal": goal if isinstance(goal, str) else "",
        "target_section": target_section,
        "context_summary": {},
        "assumptions": [],
        "constraints": _arrangement_constraints(),
        "moves": [],
        "warnings": [],
        "requires_human_review": True,
    }


def _finalize_arrangement_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    validation = validate_arrangement_plan(plan)
    plan["validation"] = {
        "valid": validation["valid"],
        "errors": validation["errors"],
    }
    plan["schema"] = ARRANGEMENT_PLAN_SCHEMA
    plan["success"] = validation["valid"]
    return _json_safe(plan)


def _arrangement_context_summary(context: Dict[str, Any]) -> Dict[str, Any]:
    transport = context.get("transport") or {}
    tracks = context.get("tracks") or {}
    selected = context.get("selected") or {}
    selected_clip = context.get("selected_clip") or {}
    project_intent = context.get("project_intent") or {}
    active_librarian = context.get("active_librarian") or {}
    project = context.get("project") or {}

    return {
        "tempo": transport.get("tempo"),
        "playing": transport.get("playing"),
        "track_count": tracks.get("count"),
        "selected_track_index": selected.get("track_index"),
        "selected_track_name": (selected.get("track") or {}).get("name") if isinstance(selected.get("track"), dict) else None,
        "selected_scene_index": selected.get("scene_index"),
        "selected_clip": {
            "track_index": selected_clip.get("track_index"),
            "clip_index": selected_clip.get("clip_index"),
            "clip_name": selected_clip.get("clip_name"),
            "clip_length_beats": selected_clip.get("clip_length_beats"),
            "note_count": selected_clip.get("note_count"),
            "pitch_range": selected_clip.get("pitch_range"),
            "missing_fields": selected_clip.get("missing_fields", []),
        },
        "project": {
            "name": project.get("name"),
            "genre": project.get("genre"),
            "stage": project.get("stage"),
            "num_scenes": project.get("num_scenes"),
        },
        "project_intent": {
            "genre": project_intent.get("genre"),
            "mood": project_intent.get("mood"),
            "arrangement_goal": project_intent.get("arrangement_goal"),
            "prefer": project_intent.get("prefer", []),
            "avoid": project_intent.get("avoid", []),
        },
        "active_section": active_librarian.get("section"),
    }


def _arrangement_assumptions(context: Dict[str, Any], target_section: Optional[str]) -> List[str]:
    assumptions = [
        "This plan is a proposal only; no Ableton changes have been executed.",
    ]
    if target_section:
        assumptions.append(f"Target section is interpreted as '{target_section}'.")
    elif (context.get("active_librarian") or {}).get("section"):
        assumptions.append("No target_section was provided; active librarian section is used as contextual reference only.")
    else:
        assumptions.append("No target_section was provided, so moves are section-agnostic placeholders.")

    selected = context.get("selected") or {}
    if selected.get("scene_index") is not None:
        assumptions.append("Cached selected_scene is treated as the selected clip slot index until a dedicated selected-clip API exists.")

    return assumptions


def _arrangement_constraints() -> List[str]:
    return [
        "Planning only; do not execute Ableton changes.",
        "Do not add audio listening or audio-derived judgments.",
        "Do not infer key, chords, or energy.",
        "Do not call Lyria, Suno, or external generation services.",
        "Human review is required before any proposed move is executed.",
    ]


def _arrangement_moves(goal: str, target_section: Optional[str], context_summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    section_target = target_section or context_summary.get("active_section")
    selected_clip = context_summary.get("selected_clip") or {}
    moves = [
        {
            "type": "scene_or_arrangement_marker",
            "description": "Review or label the target section boundary before making arrangement edits.",
            "target": {"section": section_target},
            "parameters": {"label": section_target, "planning_only": True},
            "reason": "Arrangement moves are safer when the intended section is explicit.",
            "status": "proposed",
        },
        {
            "type": "arrangement_edit",
            "description": "Draft a section-level edit that supports the stated goal without changing project data yet.",
            "target": {"section": section_target},
            "parameters": {"goal": goal, "planning_only": True},
            "reason": "The request is about arrangement direction, so this remains a reviewable placeholder.",
            "status": "proposed",
        },
    ]

    if selected_clip.get("track_index") is not None and selected_clip.get("clip_index") is not None:
        moves.append(
            {
                "type": "midi_clip",
                "description": "Consider a MIDI clip variation for the selected clip slot after human review.",
                "target": {
                    "track_index": selected_clip.get("track_index"),
                    "clip_index": selected_clip.get("clip_index"),
                    "clip_name": selected_clip.get("clip_name"),
                },
                "parameters": {
                    "source_note_count": selected_clip.get("note_count"),
                    "source_pitch_range": selected_clip.get("pitch_range"),
                    "planning_only": True,
                },
                "reason": "Selected clip context is available as a possible MIDI planning target.",
                "status": "proposed",
            }
        )

    lower_goal = goal.lower()
    if any(word in lower_goal for word in ("automation", "lift", "build", "rise", "transition")):
        moves.append(
            {
                "type": "automation",
                "description": "Plan a non-destructive automation idea for review, without writing automation.",
                "target": {"section": section_target},
                "parameters": {"automation_lane": None, "curve": None, "planning_only": True},
                "reason": "The goal suggests movement over time, but exact automation must be reviewed in Ableton.",
                "status": "proposed",
            }
        )

    if any(word in lower_goal for word in ("device", "effect", "filter", "reverb", "delay", "texture")):
        moves.append(
            {
                "type": "device_change",
                "description": "Plan a device or parameter change candidate for review, without loading or changing devices.",
                "target": {"section": section_target, "track_index": selected_clip.get("track_index")},
                "parameters": {"device": None, "parameter": None, "value": None, "planning_only": True},
                "reason": "The goal mentions a sonic/device direction, but this planner cannot audition audio.",
                "status": "proposed",
            }
        )

    return moves


def _arrangement_warnings(goal: str, context: Dict[str, Any]) -> List[str]:
    warnings: List[str] = []
    known_limitations = context.get("known_limitations") or {}
    for field in known_limitations.get("missing_fields", []):
        warnings.append(f"Context missing field: {field}")
    for limitation in known_limitations.get("limitations", []):
        warnings.append(f"Context limitation: {limitation}")

    selected_clip = context.get("selected_clip") or {}
    selected_missing = selected_clip.get("missing_fields") or []
    if selected_missing:
        warnings.append(f"Selected clip is missing MIDI data fields: {', '.join(selected_missing)}")

    if _goal_requires_human_review(goal):
        warnings.append("Goal appears to require listening judgment; human review is required.")

    if not warnings:
        warnings.append("No execution has occurred; review the plan before applying any move.")
    return sorted(set(warnings))


def _goal_requires_human_review(goal: str) -> bool:
    listening_terms = (
        "listen",
        "sounds",
        "feel",
        "feels",
        "energy",
        "vibe",
        "groove",
        "key",
        "chord",
        "emotion",
        "better",
        "lift",
    )
    lower_goal = goal.lower()
    return any(term in lower_goal for term in listening_terms)


def _context_requires_human_review(context: Dict[str, Any]) -> bool:
    selected_clip = context.get("selected_clip") or {}
    return bool(selected_clip.get("missing_fields") or (context.get("known_limitations") or {}).get("missing_fields"))


def _project_intent_path(storage_path: Any = None) -> Path:
    return Path(storage_path) if storage_path is not None else DEFAULT_PROJECT_INTENT_PATH


def _empty_project_intent() -> Dict[str, Any]:
    return {
        "genre": None,
        "references": [],
        "mood": None,
        "arrangement_goal": None,
        "prefer": [],
        "avoid": [],
        "notes": None,
        "updated_at": None,
    }


def _read_controller_snapshot(
    controller: Any,
    missing_fields: List[str],
    limitations: List[str],
) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {}
    if controller is None:
        limitations.append("No Ableton controller supplied; using cached session state only.")
        missing_fields.extend(["live_tempo", "live_tracks", "live_num_scenes"])
        return snapshot

    tempo_result = _call_if_available(controller, "get_tempo")
    if _success(tempo_result):
        snapshot["tempo"] = _coalesce(tempo_result.get("tempo"), tempo_result.get("result"))
    else:
        missing_fields.append("live_tempo")

    track_result = _call_if_available(controller, "get_track_list")
    if _success(track_result):
        snapshot["tracks"] = track_result.get("tracks", [])
    else:
        missing_fields.append("live_tracks")

    scenes_result = _call_if_available(controller, "get_num_scenes")
    if _success(scenes_result):
        snapshot["num_scenes"] = _coalesce(
            scenes_result.get("num_scenes"),
            scenes_result.get("count"),
            scenes_result.get("result"),
        )
    else:
        missing_fields.append("live_num_scenes")

    return snapshot


def _build_transport(session_state: Any, live_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "playing": getattr(session_state, "is_playing", None),
        "recording": getattr(session_state, "is_recording", None),
        "tempo": _coalesce(live_snapshot.get("tempo"), getattr(session_state, "tempo", None)),
        "position_beats": getattr(session_state, "current_position", None),
        "time_signature": list(getattr(session_state, "time_signature", ())) or None,
        "metronome": getattr(session_state, "metronome_on", None),
    }


def _build_loop(session_state: Any) -> Dict[str, Any]:
    return {
        "enabled": getattr(session_state, "loop_enabled", None),
        "start_beats": getattr(session_state, "loop_start", None),
        "length_beats": getattr(session_state, "loop_length", None),
    }


def _build_tracks_summary(
    session_state: Any,
    live_snapshot: Dict[str, Any],
    missing_fields: List[str],
) -> Dict[str, Any]:
    session_tracks = list(getattr(session_state, "tracks", []) or [])
    live_tracks = list(live_snapshot.get("tracks") or [])

    by_index = {}
    for track in session_tracks:
        item = _track_to_dict(track)
        by_index[item.get("index")] = item

    for track in live_tracks:
        idx = track.get("index")
        merged = dict(by_index.get(idx, {}))
        merged.update({k: v for k, v in track.items() if v is not None})
        by_index[idx] = merged

    summary = [_normalize_track(track) for _, track in sorted(by_index.items(), key=lambda kv: kv[0] if kv[0] is not None else 999999)]
    if not summary:
        missing_fields.append("tracks_summary")

    return {
        "count": len(summary),
        "items": summary,
        "muted": [t["index"] for t in summary if t.get("muted")],
        "soloed": [t["index"] for t in summary if t.get("soloed")],
        "armed": [t["index"] for t in summary if t.get("armed")],
    }


def _build_selected_context(
    session_state: Any,
    tracks: Dict[str, Any],
    missing_fields: List[str],
) -> Dict[str, Any]:
    selected_track_index = getattr(session_state, "selected_track", None)
    selected_scene_index = getattr(session_state, "selected_scene", None)
    selected_track = None
    for track in tracks.get("items", []):
        if track.get("index") == selected_track_index:
            selected_track = track
            break

    if selected_track_index is None:
        missing_fields.append("selected_track")
    if selected_scene_index is None:
        missing_fields.append("selected_scene")

    return {
        "track_index": selected_track_index,
        "track": selected_track,
        "scene_index": selected_scene_index,
    }


def _build_selected_clip_context(
    selected: Dict[str, Any],
    controller: Any,
    reliable: Any,
    missing_fields: List[str],
    limitations: List[str],
) -> Dict[str, Any]:
    track_index = selected.get("track_index")
    # Treat cached selected_scene as the clip slot until a selected-clip API exists.
    clip_index = selected.get("scene_index")
    if track_index is None or clip_index is None:
        missing = []
        if track_index is None:
            missing.append("track_index")
        if clip_index is None:
            missing.append("clip_index")
        missing_fields.append("selected_clip")
        return {
            "success": False,
            "track_index": track_index,
            "clip_index": clip_index,
            "limitations": ["Selected track or clip slot is not available from current session state."],
            "missing_fields": missing,
        }

    clip_context = analyze_clip_context(
        track_index=track_index,
        clip_index=clip_index,
        controller=controller,
        reliable=reliable,
    )
    for field in clip_context.get("missing_fields", []):
        missing_fields.append(f"selected_clip.{field}")
    limitations.extend(clip_context.get("limitations", []))
    return clip_context


def _build_librarian_context(librarian: Any, missing_fields: List[str]) -> Dict[str, Any]:
    active = librarian.get_active() if librarian and hasattr(librarian, "get_active") else None
    if not active:
        missing_fields.append("active_librarian")
        return {
            "song": None,
            "section": None,
            "chain": [],
            "track_index": None,
            "song_file": None,
            "loaded_at": None,
        }

    song_data = active.get("active_song_data") or {}
    chain = active.get("active_chain_devices") or []
    return {
        "song": _coalesce(song_data.get("song"), song_data.get("title"), song_data.get("name")),
        "artist": song_data.get("artist"),
        "section": active.get("active_section"),
        "chain": _summarize_chain(chain),
        "track_index": active.get("track_index"),
        "song_file": active.get("active_song_file"),
        "loaded_at": active.get("loaded_at"),
    }


def _recent_actions(manager: Any, count: int) -> List[Dict[str, Any]]:
    if hasattr(manager, "get_recent_actions"):
        return list(manager.get_recent_actions(count))
    return []


def _normalize_track(track: Dict[str, Any]) -> Dict[str, Any]:
    idx = track.get("index")
    return {
        "index": idx,
        "number": track.get("number", track.get("display_index", idx + 1 if isinstance(idx, int) else None)),
        "name": track.get("name") or (f"Track {idx + 1}" if isinstance(idx, int) else None),
        "muted": track.get("muted"),
        "soloed": track.get("soloed"),
        "armed": track.get("armed"),
        "volume": track.get("volume"),
        "pan": track.get("pan"),
        "has_clips": track.get("has_clips"),
    }


def _summarize_chain(chain: Iterable[Any]) -> List[Dict[str, Any]]:
    summary = []
    for index, device in enumerate(chain):
        if isinstance(device, dict):
            summary.append(
                {
                    "index": index,
                    "name": _coalesce(device.get("name"), device.get("device"), device.get("plugin")),
                    "type": _coalesce(device.get("type"), device.get("category")),
                    "purpose": _coalesce(device.get("why"), device.get("purpose")),
                }
            )
        else:
            summary.append({"index": index, "name": str(device), "type": None, "purpose": None})
    return summary


def _track_to_dict(track: Any) -> Dict[str, Any]:
    if is_dataclass(track):
        return asdict(track)
    if isinstance(track, dict):
        return dict(track)
    return {
        "index": getattr(track, "index", None),
        "name": getattr(track, "name", None),
        "muted": getattr(track, "muted", None),
        "soloed": getattr(track, "soloed", None),
        "armed": getattr(track, "armed", None),
        "volume": getattr(track, "volume", None),
        "pan": getattr(track, "pan", None),
        "has_clips": getattr(track, "has_clips", None),
    }


def _call_if_available(obj: Any, method_name: str) -> Optional[Dict[str, Any]]:
    method = getattr(obj, method_name, None)
    if not callable(method):
        return None
    try:
        result = method()
    except Exception as exc:
        return {"success": False, "message": str(exc)}
    return result if isinstance(result, dict) else {"success": True, "result": result}


def _clip_context_value_fields() -> List[str]:
    return [
        "clip_name",
        "clip_length_beats",
        "note_count",
        "pitch_min",
        "pitch_max",
        "pitch_range",
        "velocity_min",
        "velocity_max",
        "average_velocity",
        "note_start_min",
        "note_end_max",
        "density_notes_per_beat",
    ]


def _read_clip_metadata(
    controller: Any,
    track_index: int,
    clip_index: int,
    limitations: List[str],
) -> Dict[str, Any]:
    method_name, result = _call_first_available(
        controller,
        ["get_clip_info", "get_clip", "get_clip_details"],
        track_index,
        clip_index,
    )
    if method_name is None:
        limitations.append("Current controller exposes no clip metadata reader.")
        return {}
    if not _success(result):
        limitations.append(
            f"{method_name} could not read clip metadata: {result.get('message') or result.get('error') or 'unknown error'}"
        )
        return {}
    payload = _mapping_payload(result, ["clip", "clip_info", "result", "data"])
    return payload


def _read_clip_notes(
    controller: Any,
    track_index: int,
    clip_index: int,
    limitations: List[str],
) -> Dict[str, Any]:
    method_name, result = _call_first_available(
        controller,
        [
            "get_clip_notes",
            "get_midi_clip_notes",
            "get_midi_notes",
            "get_notes_for_clip",
            "get_clip_note_list",
        ],
        track_index,
        clip_index,
    )
    if method_name is None:
        limitations.append("Current controller exposes no MIDI note reader for clips.")
        return {}
    if not _success(result):
        limitations.append(
            f"{method_name} could not read MIDI notes: {result.get('message') or result.get('error') or 'unknown error'}"
        )
        return {}

    payload = _mapping_payload(result, ["clip", "clip_notes", "midi_notes", "result", "data"])
    notes = _notes_payload(result)
    note_count = _coalesce(payload.get("note_count"), payload.get("count"), result.get("note_count"), result.get("count"))
    return {"notes": notes, "note_count": note_count, "count": note_count}


def _merge_clip_metadata(summary: Dict[str, Any], payload: Dict[str, Any]) -> None:
    if not payload:
        return
    summary["clip_name"] = _coalesce(
        payload.get("clip_name"),
        payload.get("name"),
        payload.get("title"),
        summary.get("clip_name"),
    )
    summary["clip_length_beats"] = _float_or_none(
        _coalesce(
            payload.get("clip_length_beats"),
            payload.get("length_beats"),
            payload.get("length"),
            payload.get("duration_beats"),
            payload.get("duration"),
            summary.get("clip_length_beats"),
        )
    )


def _merge_note_stats(
    summary: Dict[str, Any],
    notes: List[Dict[str, Any]],
    missing_fields: List[str],
    limitations: List[str],
) -> None:
    if not notes:
        limitations.append("MIDI notes were accessible, but the clip contains no notes.")
        missing_fields.extend(
            [
                "pitch_min",
                "pitch_max",
                "pitch_range",
                "velocity_min",
                "velocity_max",
                "average_velocity",
                "note_start_min",
                "note_end_max",
            ]
        )
        return

    pitches = [note["pitch"] for note in notes if note.get("pitch") is not None]
    velocities = [note["velocity"] for note in notes if note.get("velocity") is not None]
    starts = [note["start"] for note in notes if note.get("start") is not None]
    ends = [note["end"] for note in notes if note.get("end") is not None]

    if pitches:
        summary["pitch_min"] = min(pitches)
        summary["pitch_max"] = max(pitches)
        summary["pitch_range"] = summary["pitch_max"] - summary["pitch_min"]
    else:
        missing_fields.extend(["pitch_min", "pitch_max", "pitch_range"])

    if velocities:
        summary["velocity_min"] = min(velocities)
        summary["velocity_max"] = max(velocities)
        summary["average_velocity"] = sum(velocities) / len(velocities)
    else:
        missing_fields.extend(["velocity_min", "velocity_max", "average_velocity"])

    if starts:
        summary["note_start_min"] = min(starts)
    else:
        missing_fields.append("note_start_min")

    if ends:
        summary["note_end_max"] = max(ends)
    else:
        missing_fields.append("note_end_max")


def _call_first_available(obj: Any, method_names: List[str], *args: Any) -> Tuple[Optional[str], Dict[str, Any]]:
    for method_name in method_names:
        method = getattr(obj, method_name, None)
        if not callable(method):
            continue
        try:
            result = method(*args)
        except TypeError:
            try:
                result = method(track_index=args[0], clip_index=args[1])
            except Exception as exc:
                return method_name, {"success": False, "message": str(exc)}
        except Exception as exc:
            return method_name, {"success": False, "message": str(exc)}
        return method_name, result if isinstance(result, dict) else {"success": True, "result": result}
    return None, {}


def _mapping_payload(result: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
    for key in keys:
        value = result.get(key)
        if isinstance(value, dict):
            return dict(value)
    return dict(result)


def _notes_payload(result: Dict[str, Any]) -> Optional[List[Any]]:
    for value in (result, _mapping_payload(result, ["clip", "clip_notes", "midi_notes", "result", "data"])):
        if isinstance(value, dict):
            for key in ("notes", "clip_notes", "midi_notes"):
                notes = value.get(key)
                if isinstance(notes, list):
                    return notes
    direct = result.get("result")
    if isinstance(direct, list):
        return direct
    return None


def _normalize_note(note: Any) -> Dict[str, Any]:
    if isinstance(note, dict):
        pitch = _int_or_none(_coalesce(note.get("pitch"), note.get("note"), note.get("midi_note")))
        start = _float_or_none(_coalesce(note.get("start"), note.get("start_time"), note.get("time"), note.get("beat")))
        duration = _float_or_none(_coalesce(note.get("duration"), note.get("length"), note.get("length_beats")))
        end = _float_or_none(_coalesce(note.get("end"), note.get("end_time"), note.get("stop")))
        if end is None and start is not None and duration is not None:
            end = start + duration
        velocity = _float_or_none(note.get("velocity"))
        return {"pitch": pitch, "start": start, "end": end, "velocity": velocity}

    if isinstance(note, (list, tuple)):
        pitch = _int_or_none(note[0] if len(note) > 0 else None)
        start = _float_or_none(note[1] if len(note) > 1 else None)
        duration = _float_or_none(note[2] if len(note) > 2 else None)
        velocity = _float_or_none(note[3] if len(note) > 3 else None)
        end = start + duration if start is not None and duration is not None else None
        return {"pitch": pitch, "start": start, "end": end, "velocity": velocity}

    return {"pitch": None, "start": None, "end": None, "velocity": None}


def _int_or_none(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _success(result: Optional[Dict[str, Any]]) -> bool:
    return bool(isinstance(result, dict) and result.get("success"))


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _iso_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
