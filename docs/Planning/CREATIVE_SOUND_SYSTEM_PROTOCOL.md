# Creative Sound System Protocol

This protocol is the operating contract for the larger creative sound system we are building around LivePilot/Jarvis. It turns vague intent into a reviewable creative direction before anything is generated, loaded into Ableton, or learned as taste memory.

## 0. Core rule

Jarvis must not jump from a vague creative request straight to generation.

```text
Bad path:
Prompt → AI guesses → Ableton changes → user rejects it
```

```text
Required path:
Intent → Questions → Brief → Taste → Direction → Plan → Taste gate → Generation/Execution → Critique → Feedback memory
```

The currently implemented `taste-workflow-v1` is the first enforceable part of this protocol: it builds a deterministic `creative_brief`, detects missing taste/target decisions, creates clarification questions, annotates planner steps with `taste_alignment`, and requires confirmation when decisions are missing.

## 1. End-to-end lifecycle

| Step | Layer | Purpose | Required output |
| --- | --- | --- | --- |
| 1 | User intent | Capture what the user is trying to make or fix. | Raw request text. |
| 2 | Questionnaire system | Ask only the missing questions needed for safe direction. | Answers for target, feel, references, avoids, preserve rules, and failure conditions. |
| 3 | Brief compiler | Turn messy desire into a structured creative brief. | `creative_brief` with compiled direction and constraints. |
| 4 | Taste system | Merge long-term, project, session, and rejection memory. | Taste profile with prefer/avoid/reference/correction fields. |
| 5 | Creative director layer | Decide the production direction before creating anything. | Reference fingerprint, sound roles, drum brief, mix placement, and risk notes. |
| 6 | Generation | Create a plan, prompt, kit, groove, chain, rack, MIDI, or Ableton move. | Reviewable candidates or executable plan. |
| 7 | Critique + revision | Score the output before the user commits to it. | Taste score, reference score, risks, and revision recommendations. |
| 8 | User feedback | Capture what worked, what failed, and what was close. | Structured feedback event. |
| 9 | Memory update | Convert feedback into reusable rules. | Updated taste rules and correction memory. |

## 2. Questionnaire protocol

The questionnaire exists to avoid forcing the user to write perfect prompts.

### Fast mode

Use when the user wants speed.

Ask at most three questions:

1. **Target** — What are we making or changing?
2. **Taste anchor** — What should it feel like, or what reference should it borrow from?
3. **Avoid/failure rule** — What would make this bad?

### Deep mode

Use when the user is starting a new beat, sound palette, drum direction, or bigger arrangement.

Ask for:

- what we are making;
- target track, section, or output type;
- emotional scene;
- reference tracks/artists;
- what to borrow from each reference;
- what not to copy;
- drum direction;
- sound palette;
- vocal space requirements;
- avoid rules;
- preserve rules;
- what would make the result fail.

### Silent mode

Use only when the user explicitly asks Jarvis to proceed using memory.

Rules:

- Use existing taste memory and project intent.
- Mark assumptions in the brief.
- Do not execute destructive or large Ableton changes without review.
- Prefer generating options over committing one result.

## 3. Creative brief schema

Every creative workflow should normalize to a brief with these fields:

```json
{
  "schema_version": "taste-workflow-v1",
  "request": "raw user request",
  "mode": "fast|deep|silent|auto",
  "target": {
    "type": "track|bus|section|full_mix|new_beat|drum_kit|plugin_chain|prompt|midi|arrangement",
    "name": "optional human label",
    "ableton_track_index": null
  },
  "compiled_direction": {
    "one_sentence": "dark vocal-centered R&B beat with sparse drums and warm low end",
    "scene": "outside_the_club",
    "emotion": ["dark", "intimate", "restrained"],
    "energy": 4,
    "density": 3,
    "brightness": 2,
    "vocal_space": "leave room for male vocal"
  },
  "references": [
    {
      "name": "Drake - Jungle",
      "borrow": ["vocal space", "dark warmth", "restraint"],
      "do_not_copy": ["melody", "exact drums", "exact chords"]
    }
  ],
  "taste_profile": {
    "prefer": [],
    "avoid": [],
    "references": [],
    "sound_traits": [],
    "correction_map": {}
  },
  "failure_conditions": [],
  "missing_decisions": [],
  "clarification_questions": [],
  "guardrails": [],
  "acceptance_checklist": []
}
```

The current implementation already creates the core fields: `schema_version`, `request`, `taste_profile`, fixed workflow stages, `missing_decisions`, `clarification_questions`, `guardrails`, and `acceptance_checklist`.

## 4. Taste system protocol

Taste memory is split into four scopes.

| Scope | Meaning | Examples |
| --- | --- | --- |
| Permanent taste | Stable user preferences across projects. | dark, spacious, vocal-centered, avoid generic/corny/over-polished. |
| Project taste | Taste for this project/app/session family. | LivePilot tools should be practical, visual, and useful in real sessions. |
| Session taste | Tonight's specific direction. | outside-the-club R&B, sparse drums, warm low end. |
| Rejection memory | Things the user disliked or corrected. | bright claps failed, busy hats failed, kick too clicky, reverb too huge. |

When building a plan, Jarvis must merge these scopes into a taste profile and expose them to every downstream director/judge.

## 5. Creative director layer protocol

The director layer decides what should happen before generation.

### 5.1 Reference Decoder

Input:

- user references;
- brief direction;
- taste memory.

Output:

```json
{
  "reference": "Dark vocal-centered R&B",
  "borrow": ["spacious vocal lane", "dark chord bed", "restrained drums", "warm sub weight"],
  "do_not_copy": ["melody", "drum pattern", "exact sounds"],
  "production_recipe": ["low brightness", "wide but tucked space", "slow head-nod pocket"]
}
```

Rules:

- Decode references into decisions.
- Never copy protected melody, exact arrangement, or exact sound identity.
- Use references as directional fingerprints, not templates to clone.

### 5.2 Sound Selector

Input:

- creative brief;
- sound roles needed;
- indexed asset library;
- taste profile.

Output:

- candidate sounds by role;
- fit score;
- risk notes;
- reasons.

Principle:

```text
A sound is not chosen because it is generally good.
A sound is chosen because it performs the correct job in this brief.
```

### 5.3 Drum Director

Input:

- creative brief;
- taste profile;
- references;
- drum avoid rules.

Output:

```json
{
  "scene": "outside_the_club",
  "job": "support the vocal and give the bottom a slow pulse",
  "energy": 4,
  "density": 3,
  "swing": 5,
  "brightness": 2,
  "aggression": 2,
  "kick_goal": "deep pulse, not clicky",
  "clap_goal": "distant dark snap/clap",
  "hat_goal": "minimal motion, tucked behind vocal",
  "avoid": ["hype trap", "busy hats", "bright clap", "generic Splice bounce"]
}
```

Rules:

- Choose the drum scene before choosing samples.
- Choose the groove archetype before generating the pattern.
- Choose an anchor sample before filling the kit.
- Reject kits where pieces do not live in the same world.
- Prioritize vocal space over impressive drum activity when the brief is vocal-centered.

### 5.4 Kit Cohesion Judge

The kit judge must score:

- whether samples live in the same world;
- clap cheapness risk;
- hat busyness risk;
- kick clickiness risk;
- vocal-space fit;
- genericness risk;
- emotional accuracy.

## 6. Auto-label and library protocol

The sound library brain should eventually scan and tag local assets.

### Asset database tables

Minimum tables:

- `assets` — file identity, path, type, vendor/plugin metadata, scan status.
- `tags` — creative labels with confidence, source, and evidence.
- `audio_features` — measurable traits such as brightness, low-end weight, loudness, transient density, BPM, and key.
- `feedback_log` — user reactions and extracted rules.

### Tagging sources

Use layered confidence:

1. filename tags;
2. folder tags;
3. metadata tags;
4. audio feature tags;
5. user-reviewed tags;
6. render-and-listen tags later.

User-reviewed tags override automatic guesses.

## 7. Generation protocol

Generation must be reviewable before commitment.

Allowed generation outputs:

- beat idea;
- drum kit options;
- groove pattern;
- sound palette;
- plugin chain;
- Ableton session plan;
- MIDI idea;
- prompt/rack/arrangement suggestion.

Required generation metadata:

- why this fits the brief;
- what taste anchors it uses;
- what avoid rules it respects;
- what risks remain;
- how to revise it;
- whether execution requires confirmation.

## 8. Critique and revision protocol

Before the user commits, the system should critique the result.

Minimum scores:

| Score | Meaning |
| --- | --- |
| taste_match | Does this match known user taste? |
| reference_match | Does it borrow the intended traits without copying? |
| drum_direction | Do drums follow the scene and role? |
| sample_cohesion | Do selected sounds live in one world? |
| vocal_space | Does the result leave room for vocal? |
| cheapness_risk | Does any element feel cheap/corny/generic? |
| genericness_risk | Does it feel like default AI/sample-pack output? |
| emotional_accuracy | Does it create the intended feeling? |

If any critical score fails, revise before presenting it as a final recommendation.

## 9. Feedback memory protocol

User feedback must become reusable memory.

Example:

```text
User: "This is close, but the hats are too busy and the clap sounds cheap."
```

Extract:

```json
{
  "preserve": ["overall direction is close"],
  "reject": ["busy hats", "cheap clap"],
  "new_rules": [
    "For outside_the_club drums, hats must stay tucked",
    "Avoid bright/cheap claps in dark vocal-centered R&B"
  ]
}
```

Memory update rules:

- Preserve what the user says is working.
- Reject what the user names as failing.
- Convert repeated corrections into higher-confidence rules.
- Keep context attached to every rule: global, project, session, track type, drum scene, or reference.

## 10. Safety and execution rules

Jarvis must obey these before Ableton execution:

1. Verify track list before track-specific operations.
2. Verify plugin inventory before third-party devices.
3. Surface missing target/taste decisions as questions.
4. Present a plan before creative multi-step changes.
5. Execute one operation at a time.
6. Verify the result after each operation.
7. Prefer reversible actions.
8. Ask for feedback and record corrections.

## 11. MVP protocol: dark vocal-centered R&B drums

First useful target:

```text
User says:
"Give me drums for a dark vocal-centered R&B beat.
Outside the club, not hype, leave room for vocals."
```

System must:

1. Build a creative brief.
2. Build a drum brief.
3. Choose drum scene: `outside_the_club`.
4. Search actual drum samples.
5. Build three kit options:
   - safest match;
   - darker/emptier;
   - bouncier but restrained.
6. Explain why each kit fits.
7. Warn about possible issues.
8. Let the user approve/reject.
9. Save the reaction as taste memory.

Example response shape:

```text
DRUM DIRECTION:
outside_the_club_dark_rnb

KIT A — Safest Match
Kick: Deep Dry Kick 03
Clap: Distant Snap 02
Hat: Muted Hat 06
Perc: Room Tick 05

Why:
Deep center, dark top-end, clap feels far back, hats will not crowd the vocal.

Risk:
May feel too minimal without bass movement.
```

## 12. Build order

Do not build every layer at once.

Recommended implementation order:

1. Rich creative brief compiler.
2. Questionnaire modes.
3. Drum Director MVP.
4. Asset scanner and database.
5. Kit recommendation from actual assets.
6. Feedback-to-rule memory updates.
7. Critique/revision scorer.
8. Ableton integration for approved choices.

## 13. Current implementation status

| Component | Status |
| --- | --- |
| Deterministic `creative_brief` | Implemented. |
| Taste profile merge | Implemented, basic. |
| Missing decision detection | Implemented, basic. |
| Clarification questions | Implemented, basic. |
| Planner `taste_alignment` | Implemented, basic. |
| Preview CLI | Implemented. |
| Rich compiled musical brief | Planned. |
| Questionnaire modes | Planned. |
| Reference decoder | Planned. |
| Auto-label asset database | Planned. |
| Drum Director | Planned. |
| Kit Builder | Planned. |
| Critique/revision scorer | Planned. |
| Feedback-to-rule updater | Planned. |
