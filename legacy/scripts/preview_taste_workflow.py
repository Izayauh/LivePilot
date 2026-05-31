#!/usr/bin/env python3
"""Preview Jarvis' taste workflow without connecting to Ableton.

This command is intentionally local/deterministic: it builds the same creative
brief that the workflow coordinator passes into planning, then prints the
questions Jarvis should ask before execution.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from creative_workflow import build_creative_brief, annotate_plan_steps
from discovery.learning_system import learning_system


def _csv(values: List[str] | None) -> List[str]:
    if not values:
        return []
    result: List[str] = []
    for value in values:
        result.extend(part.strip() for part in value.split(",") if part.strip())
    return result


def _sample_steps() -> List[Dict[str, Any]]:
    return [
        {
            "order": 1,
            "description": "Verify target and current creative context",
            "commands": [{"function": "get_track_list", "args": {}}],
        },
        {
            "order": 2,
            "description": "Propose a small reversible move that matches the taste profile",
            "commands": [],
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preview the questions and taste gate Jarvis will use for a creative prompt."
    )
    parser.add_argument("request", help="The vague or specific prompt you want to test")
    parser.add_argument("--prefer", action="append", help="Preference anchor(s), comma-separated or repeated")
    parser.add_argument("--avoid", action="append", help="Avoid rule(s), comma-separated or repeated")
    parser.add_argument("--reference", action="append", help="Reference song/artist(s), comma-separated or repeated")
    parser.add_argument("--genre", help="Optional project genre")
    parser.add_argument("--mood", help="Optional project mood")
    parser.add_argument("--json", action="store_true", help="Print full JSON instead of a readable summary")
    args = parser.parse_args()

    project_intent = {
        "prefer": _csv(args.prefer),
        "avoid": _csv(args.avoid),
        "references": _csv(args.reference),
        "genre": args.genre,
        "mood": args.mood,
    }
    project_intent = {k: v for k, v in project_intent.items() if v}

    brief = build_creative_brief(
        request=args.request,
        project_intent=project_intent,
        learning_system=learning_system,
    )
    preview_steps = annotate_plan_steps(_sample_steps(), brief)

    payload = {"creative_brief": brief, "preview_steps": preview_steps}
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print("Taste workflow preview")
    print("=" * 23)
    print(f"Request: {args.request}")
    print(f"Schema:  {brief['schema_version']}")
    print("\nWorkflow:")
    for idx, stage in enumerate(brief["workflow"], start=1):
        print(f"  {idx}. {stage['stage']}: {stage['goal']}")

    taste = brief["taste_profile"]
    print("\nTaste profile:")
    print(f"  Intensity:  {taste['intensity']}")
    print(f"  Prefer:     {taste['prefer'] or 'none yet'}")
    print(f"  Avoid:      {taste['avoid'] or 'none yet'}")
    print(f"  References: {taste['references'] or 'none yet'}")

    print("\nQuestions Jarvis should ask before execution:")
    if brief["clarification_questions"]:
        for question in brief["clarification_questions"]:
            print(f"  - {question['question']}")
            for example in question["examples"]:
                print(f"      e.g. {example}")
    else:
        print("  None. The prompt has enough taste/target context to proceed to a reviewable plan.")

    print("\nTaste-gated preview steps:")
    for step in preview_steps:
        gate = step["taste_alignment"]
        print(f"  {step['order']}. {step['description']}")
        print(f"     gate: {gate['status']} | anchors={gate['anchors'] or 'none'} | avoid={gate['avoid'] or 'none'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
