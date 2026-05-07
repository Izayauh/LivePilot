#!/usr/bin/env python3
"""Tests for deterministic creative workflow and taste profile handling."""

import asyncio
import os
import sys
import unittest
from dataclasses import dataclass

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from agents.planner_agent import PlannerAgent
from creative_workflow import (
    SCHEMA_VERSION,
    annotate_plan_steps,
    build_clarification_questions,
    build_creative_brief,
    build_taste_profile,
    find_missing_decisions,
)


@dataclass
class FakePreference:
    value: object
    confidence: float = 1.0


class FakeLearningSystem:
    def __init__(self):
        self.user_preferences = {
            "prefer_vocal_texture": FakePreference(["intimate", "warm"]),
            "avoid_mix_moves": FakePreference(["harsh top end"]),
            "favorite_reference": FakePreference("Drake - Jungle"),
            "favorite_plugin_chain": FakePreference({"vocal": ["CLA-76", "H-Delay"]}),
            "low_confidence_preference": FakePreference("ignore me", confidence=0.2),
        }

    def get_common_corrections(self):
        return {"too much reverb": "shorter darker room"}


class FakeOrchestrator:
    pass


def run_async(coro):
    return asyncio.run(coro)


class TestTasteProfile(unittest.TestCase):
    def test_build_taste_profile_merges_learning_and_project_intent(self):
        profile = build_taste_profile(
            request="make the vocal warm and intimate but subtle",
            project_intent={
                "genre": "rnb",
                "references": ["PARTYNEXTDOOR - Persian Rugs"],
                "prefer": ["minimal drums"],
                "avoid": ["bright brittle EQ"],
            },
            learning_system=FakeLearningSystem(),
        )

        self.assertEqual(profile["schema_version"], SCHEMA_VERSION)
        self.assertEqual(profile["intensity"], "subtle")
        self.assertIn("warm", profile["sound_traits"])
        self.assertIn("intimate", profile["prefer"])
        self.assertIn("bright brittle EQ", profile["avoid"])
        self.assertIn("harsh top end", profile["avoid"])
        self.assertIn("PARTYNEXTDOOR - Persian Rugs", profile["references"])
        self.assertIn("Drake - Jungle", profile["references"])
        self.assertNotIn("ignore me", profile["notes"])
        self.assertEqual(profile["correction_map"]["too much reverb"], "shorter darker room")

    def test_missing_decisions_catches_vague_prompt_without_taste_anchor(self):
        missing = find_missing_decisions(
            "make it sound better",
            {"prefer": [], "avoid": [], "references": [], "sound_traits": [], "device_preferences": []},
        )
        self.assertTrue(any(item.startswith("taste_anchor") for item in missing))
        self.assertTrue(any(item.startswith("target") for item in missing))

    def test_creative_brief_contains_workflow_contract(self):
        brief = build_creative_brief(
            request="make the vocal warm",
            learning_system=FakeLearningSystem(),
        )
        self.assertEqual(brief["schema_version"], SCHEMA_VERSION)
        self.assertEqual(brief["workflow"][0]["stage"], "intake")
        self.assertEqual(brief["workflow"][-1]["stage"], "feedback_loop")
        self.assertIn("record user feedback/corrections after the result is reviewed", brief["guardrails"])
        self.assertEqual(brief["clarification_questions"], [])

    def test_clarification_questions_are_user_facing(self):
        questions = build_clarification_questions([
            "taste_anchor: give a reference",
            "target: choose the track",
        ])

        self.assertEqual([q["id"] for q in questions], ["taste_anchor", "target"])
        self.assertIn("What taste should I aim for", questions[0]["question"])
        self.assertIn("What exact track", questions[1]["question"])


class TestPlanAnnotation(unittest.TestCase):
    def test_annotate_plan_steps_adds_taste_gate_metadata_without_mutating(self):
        steps = [{"order": 1, "description": "Add EQ", "commands": []}]
        brief = build_creative_brief(
            request="make the vocal warm",
            learning_system=FakeLearningSystem(),
        )

        annotated = annotate_plan_steps(steps, brief)

        self.assertNotIn("taste_alignment", steps[0])
        self.assertIn("taste_alignment", annotated[0])
        self.assertIn("warm", annotated[0]["taste_alignment"]["anchors"])
        self.assertEqual(annotated[0]["taste_alignment"]["status"], "aligned")

    def test_planner_requires_confirmation_when_taste_gate_has_missing_decisions(self):
        planner = PlannerAgent(FakeOrchestrator())
        brief = build_creative_brief(request="make it sound better")
        plan = run_async(planner._create_plan(
            goal="make it sound better",
            analysis={"workflow_steps": [{"step": 1, "action": "Add EQ"}]},
            research={},
            creative_brief=brief,
        ))

        self.assertTrue(plan.requires_confirmation)
        self.assertEqual(plan.steps[0]["taste_alignment"]["status"], "needs_confirmation")


if __name__ == "__main__":
    unittest.main()
