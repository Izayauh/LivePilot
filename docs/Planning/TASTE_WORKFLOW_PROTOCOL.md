# Taste Workflow Protocol

Jarvis now carries a deterministic `taste-workflow-v1` brief through complex creative requests so vague prompts like "make it better" do not jump straight into Ableton edits.

## Workflow order

1. **Intake** — identify the target track, section, or bus and the desired outcome.
2. **Taste profile** — load learned preferences, corrections, project intent, references, avoid rules, and requested traits.
3. **Research and inventory** — use local librarian/research and verified plugin availability before proposing devices.
4. **Plan** — create a small ordered plan with one musical purpose per step.
5. **Taste gate** — check every planned move against taste anchors and avoid rules before execution.
6. **Execute and verify** — run confirmed commands one at a time and verify the Ableton state.
7. **Feedback loop** — record accept/reject/adjust feedback so the taste evaluator improves future plans.

## What this changes

- Vague creative requests now surface missing decisions instead of silently guessing.
- Plans include `taste_alignment` metadata that explains which references, traits, or learned preferences support each step.
- The planner requires confirmation when the taste gate finds missing decisions.
- Learned corrections are included as avoid/substitution guidance for future plans.

## How to teach taste

Use direct feedback after auditioning a result:

- "I like warm intimate vocals; remember that."
- "Avoid harsh top end on my vocals."
- "When you add reverb, make it shorter and darker than that."
- "Use Drake - Jungle and PARTYNEXTDOOR - Persian Rugs as references for this project."

The workflow does not replace your taste evaluator. It gives that evaluator a fixed place in the production chain so its learned preferences affect planning before execution.

## How to verify before using Ableton

Run the local preview command with the same prompt you would give Jarvis:

```bash
python scripts/preview_taste_workflow.py "make it sound better"
```

For a more realistic prompt, include your taste anchors:

```bash
python scripts/preview_taste_workflow.py "make the lead vocal feel better" \
  --prefer "warm,intimate,subtle" \
  --avoid "harsh top end,huge reverb" \
  --reference "Drake - Jungle"
```

The preview shows:

- the fixed workflow stages Jarvis will follow;
- the taste profile it will use;
- the exact clarification questions it should ask before execution;
- preview plan steps with `taste_alignment` status.

If the preview says `needs_confirmation`, Jarvis should ask those questions and stop before changing Ableton. If it says `aligned`, Jarvis has enough taste/target context to produce a reviewable plan.
