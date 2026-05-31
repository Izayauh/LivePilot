"""
Deterministic creative workflow and taste-profile helpers for Jarvis.

This module turns vague music-production requests into a stable creative brief
that every agent can pass forward.  It intentionally avoids LLM calls so the
same request + learned taste data produces the same workflow contract every
run.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Optional


SCHEMA_VERSION = "taste-workflow-v1"

# Words that are usually too vague to execute without a taste anchor.
VAGUE_CREATIVE_TERMS = {
    "better",
    "good",
    "cool",
    "vibe",
    "vibey",
    "polish",
    "professional",
    "hard",
    "fire",
    "nice",
}

# Creative traits we can detect and carry through the plan as taste anchors.
TASTE_TRAITS = {
    "airy",
    "analog",
    "bright",
    "clean",
    "dark",
    "dry",
    "glossy",
    "gritty",
    "intimate",
    "lush",
    "minimal",
    "punchy",
    "raw",
    "soft",
    "spacey",
    "tight",
    "warm",
    "wide",
}


WORKFLOW_STAGES: List[Dict[str, Any]] = [
    {
        "stage": "intake",
        "goal": "Capture the user's request, target track/section, and references before touching Ableton.",
        "exit_criteria": ["target is explicit", "desired outcome is stated"],
    },
    {
        "stage": "taste_profile",
        "goal": "Load learned preferences, corrections, avoid rules, and project intent into a taste profile.",
        "exit_criteria": ["prefer/avoid/reference anchors are available or missing decisions are surfaced"],
    },
    {
        "stage": "research_and_inventory",
        "goal": "Use local librarian/research and verified plugin inventory before proposing devices.",
        "exit_criteria": ["chain sources are known", "unavailable plugins have safe substitutes"],
    },
    {
        "stage": "plan",
        "goal": "Create a small ordered plan with one musical purpose per step.",
        "exit_criteria": ["each step has a reason", "commands are reviewable", "rollback is known where possible"],
    },
    {
        "stage": "taste_gate",
        "goal": "Check every step against the user's taste before execution.",
        "exit_criteria": ["no avoid rule is violated", "missing decisions are confirmed"],
    },
    {
        "stage": "execute_and_verify",
        "goal": "Execute confirmed commands one at a time and verify Ableton state after changes.",
        "exit_criteria": ["device/action loaded", "parameters were applied", "failure is reported clearly"],
    },
    {
        "stage": "feedback_loop",
        "goal": "Ask for accept/reject/adjust feedback and persist corrections back into the taste evaluator.",
        "exit_criteria": ["feedback is recorded", "future plans can adapt"],
    },
]


def _coerce_list(value: Any) -> List[Any]:
    """Return value as a flattened list without treating strings as iterables."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)
    return [value]


def _dedupe(items: Iterable[Any]) -> List[Any]:
    """Preserve order while removing duplicate scalar/dict values."""
    seen = set()
    result = []
    for item in items:
        marker = repr(item)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result


def _extract_learning_preferences(learning_system: Any = None) -> Dict[str, Any]:
    """
    Convert the learning system's UserPreference objects to plain values.

    The function accepts an optional object so tests and callers can inject a
    lightweight fake instead of importing the global learning system.
    """
    preferences = getattr(learning_system, "user_preferences", {}) if learning_system else {}
    extracted: Dict[str, Any] = {}

    for key, pref in preferences.items():
        confidence = getattr(pref, "confidence", 1.0)
        if confidence < 0.5:
            continue
        extracted[str(key)] = getattr(pref, "value", pref)

    return extracted


def _extract_corrections(learning_system: Any = None) -> Dict[str, str]:
    if learning_system and hasattr(learning_system, "get_common_corrections"):
        try:
            corrections = learning_system.get_common_corrections()
            if isinstance(corrections, dict):
                return {str(k): str(v) for k, v in corrections.items()}
        except Exception:
            return {}
    return {}


def _extract_project_intent(orchestrator: Any = None) -> Dict[str, Any]:
    """Read optional project intent/preferences from the orchestrator context."""
    context = getattr(orchestrator, "context", None)
    if not context:
        return {}

    user_preferences = getattr(context, "user_preferences", {}) or {}
    project_intent = user_preferences.get("project_intent", {})
    if isinstance(project_intent, dict):
        return project_intent
    return {}


def _preference_bucket(name: str) -> str:
    lowered = name.lower()
    if any(token in lowered for token in ("avoid", "dislike", "never", "too_much")):
        return "avoid"
    if any(token in lowered for token in ("reference", "artist", "song")):
        return "references"
    if any(token in lowered for token in ("prefer", "like", "favorite", "want")):
        return "prefer"
    if any(token in lowered for token in ("plugin", "device", "chain")):
        return "device_preferences"
    return "notes"


def _detect_traits(text: str) -> List[str]:
    lowered = f" {text.lower()} "
    return sorted(trait for trait in TASTE_TRAITS if f" {trait} " in lowered)


def _detect_intensity(text: str, preferences: Mapping[str, Any]) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("subtle", "light", "gentle", "natural")):
        return "subtle"
    if any(word in lowered for word in ("aggressive", "heavy", "extreme", "distorted")):
        return "bold"

    pref_value = preferences.get("intensity") or preferences.get("global:intensity")
    if isinstance(pref_value, str) and pref_value.lower() in {"subtle", "moderate", "bold"}:
        return pref_value.lower()
    return "moderate"


def build_taste_profile(
    request: str,
    analysis: Optional[Mapping[str, Any]] = None,
    research: Optional[Mapping[str, Any]] = None,
    learned_preferences: Optional[Mapping[str, Any]] = None,
    project_intent: Optional[Mapping[str, Any]] = None,
    learning_system: Any = None,
) -> Dict[str, Any]:
    """Build a normalized taste profile from request, project, and learned data."""
    analysis = analysis or {}
    research = research or {}
    learned = dict(learned_preferences or {})
    learned.update(_extract_learning_preferences(learning_system))
    project_intent = project_intent or {}

    prefer: List[Any] = []
    avoid: List[Any] = []
    references: List[Any] = []
    device_preferences: List[Any] = []
    notes: List[str] = []

    prefer.extend(_coerce_list(project_intent.get("prefer")))
    avoid.extend(_coerce_list(project_intent.get("avoid")))
    references.extend(_coerce_list(project_intent.get("references")))
    if project_intent.get("mood"):
        prefer.append(f"mood:{project_intent['mood']}")
    if project_intent.get("genre"):
        prefer.append(f"genre:{project_intent['genre']}")

    for name, value in learned.items():
        bucket = _preference_bucket(str(name))
        if bucket == "avoid":
            avoid.extend(_coerce_list(value))
        elif bucket == "prefer":
            prefer.extend(_coerce_list(value))
        elif bucket == "references":
            references.extend(_coerce_list(value))
        elif bucket == "device_preferences":
            device_preferences.extend(_coerce_list(value))
        else:
            notes.append(f"{name}: {value}")

    references.extend(_coerce_list(analysis.get("references")))
    references.extend(_coerce_list(research.get("references")))

    request_traits = _detect_traits(request)
    profile = {
        "schema_version": SCHEMA_VERSION,
        "intensity": _detect_intensity(request, learned),
        "sound_traits": request_traits,
        "prefer": _dedupe(prefer + request_traits),
        "avoid": _dedupe(avoid),
        "references": _dedupe(references),
        "device_preferences": _dedupe(device_preferences),
        "correction_map": _extract_corrections(learning_system),
        "notes": _dedupe(notes),
    }
    return profile


def find_missing_decisions(request: str, taste_profile: Mapping[str, Any]) -> List[str]:
    """Return decisions that should be clarified before executing a vague creative request."""
    lowered = request.lower()
    missing: List[str] = []

    has_taste_anchor = any(
        taste_profile.get(field)
        for field in ("prefer", "avoid", "references", "sound_traits", "device_preferences")
    )
    if any(term in lowered for term in VAGUE_CREATIVE_TERMS) and not has_taste_anchor:
        missing.append(
            "taste_anchor: give a reference, preferred texture, or avoid rule before executing a vague creative request"
        )

    if "track" not in lowered and not any(
        token in lowered for token in ("vocal", "drum", "bass", "master", "guitar", "keys", "piano", "synth")
    ):
        missing.append("target: choose the track, bus, section, or full mix target")

    return missing


def build_clarification_questions(missing_decisions: Iterable[str]) -> List[Dict[str, Any]]:
    """Convert missing decision codes into user-facing questions for the UI/agent."""
    questions: List[Dict[str, Any]] = []
    for decision in missing_decisions:
        key = str(decision).split(":", 1)[0]
        if key == "taste_anchor":
            questions.append({
                "id": "taste_anchor",
                "question": "What taste should I aim for before I touch the session?",
                "examples": [
                    "Reference: Drake - Jungle vocal space",
                    "Texture: warm, intimate, subtle",
                    "Avoid: harsh top end or huge reverb",
                ],
                "why": "Vague prompts need a reference, texture, or avoid rule so Jarvis does not guess your taste.",
            })
        elif key == "target":
            questions.append({
                "id": "target",
                "question": "What exact track, bus, section, or full-mix target should I work on?",
                "examples": [
                    "Lead Vocal track",
                    "Hook section",
                    "Drum bus",
                ],
                "why": "Jarvis must verify the target before planning Ableton changes.",
            })
        else:
            questions.append({
                "id": key,
                "question": f"Please clarify: {decision}",
                "examples": [],
                "why": "This decision is required before safe execution.",
            })
    return questions

def build_creative_brief(
    request: str,
    analysis: Optional[Mapping[str, Any]] = None,
    research: Optional[Mapping[str, Any]] = None,
    learning_system: Any = None,
    orchestrator: Any = None,
    learned_preferences: Optional[Mapping[str, Any]] = None,
    project_intent: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the workflow contract passed between agents for creative work."""
    effective_project_intent = dict(project_intent or _extract_project_intent(orchestrator))
    taste_profile = build_taste_profile(
        request=request,
        analysis=analysis,
        research=research,
        learned_preferences=learned_preferences,
        project_intent=effective_project_intent,
        learning_system=learning_system,
    )
    missing = find_missing_decisions(request, taste_profile)
    clarification_questions = build_clarification_questions(missing)

    return {
        "schema_version": SCHEMA_VERSION,
        "request": request,
        "taste_profile": taste_profile,
        "workflow": deepcopy(WORKFLOW_STAGES),
        "missing_decisions": missing,
        "clarification_questions": clarification_questions,
        "guardrails": [
            "verify track list before track-specific operations",
            "verify plugin inventory before third-party devices",
            "propose plan before executing creative multi-step changes",
            "execute one operation at a time and verify success",
            "record user feedback/corrections after the result is reviewed",
        ],
        "acceptance_checklist": [
            "Does this move match at least one prefer/reference/trait anchor?",
            "Does this move avoid every avoid/correction rule?",
            "Can the user audition and undo the change?",
            "Was the outcome recorded for the taste evaluator?",
        ],
    }


def annotate_plan_steps(steps: List[Dict[str, Any]], creative_brief: Optional[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Attach taste-gate metadata to each plan step without mutating the input list."""
    if not creative_brief:
        return steps

    taste_profile = creative_brief.get("taste_profile", {})
    anchors = _dedupe(
        _coerce_list(taste_profile.get("prefer"))
        + _coerce_list(taste_profile.get("references"))
        + _coerce_list(taste_profile.get("sound_traits"))
    )
    avoid = _coerce_list(taste_profile.get("avoid"))

    annotated: List[Dict[str, Any]] = []
    for step in steps:
        copied = deepcopy(step)
        copied["taste_alignment"] = {
            "intensity": taste_profile.get("intensity", "moderate"),
            "anchors": anchors,
            "avoid": avoid,
            "status": "needs_confirmation" if creative_brief.get("missing_decisions") else "aligned",
            "reason": "checked in deterministic taste gate before execution",
        }
        annotated.append(copied)
    return annotated
