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
Intent → Questions → Brief → Taste + Identity → Song Direction → Plan → Taste/Song Gate → Generation/Execution → Critique → Feedback memory
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
| 6 | Song motion layer | Protect against the loop trap by planning focus, sections, motion, hook, moment, and finishability. | Song hierarchy, arrangement plan, section contrast, vocal lane, and finishability score. |
| 7 | Generation | Create a plan, prompt, kit, groove, chain, rack, MIDI, or Ableton move. | Reviewable candidates or executable plan. |
| 8 | Critique + revision | Score the output before the user commits to it. | Taste score, reference score, song-motion score, finishability score, risks, and revision recommendations. |
| 9 | User feedback | Capture what worked, what failed, what was close, and whether the idea became a song. | Structured feedback event with loop/song outcome labels. |
| 10 | Memory update | Convert feedback into reusable rules. | Updated taste, identity, arrangement, and correction memory. |

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
  "song_hierarchy": {
    "main_character": "vocal",
    "supporting_elements": ["bass", "dark keys", "distant drums"],
    "must_not_compete": ["busy hats", "lead synth", "bright piano runs"]
  },
  "song_motion": {
    "arrangement_arc": ["intro", "verse", "pre", "chorus", "post_hook", "verse_2", "bridge", "final_chorus", "outro"],
    "energy_curve": [2, 4, 5, 7, 6, 4, 3, 8, 2],
    "moment_candidate": "silence before hook, then vocal lift",
    "finishability_target": 7
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

### 5.5 Originality Guard

References guide decisions; they must not become costumes.

Output:

```json
{
  "borrow": ["spacious vocal lane", "dark low-end patience"],
  "avoid_copying": ["exact melody", "exact drum pocket", "exact chord movement"],
  "ours": ["different melodic identity", "different drum pocket", "personal lyrical/emotional angle"]
}
```

Rules:

- Always separate what to borrow from what not to copy.
- Penalize karaoke/reference-costume outputs.
- Require one explicit "what makes this ours" decision before generation.

## 6. Song motion protocol

A dope loop is not a dope song. Jarvis must judge whether an idea has motion, hierarchy, and finishability before calling it successful.

### 6.1 Song Director

The Song Director owns the question: "What makes this worth finishing?"

Required output:

```json
{
  "song_focus": "vocal",
  "emotional_job": "dark confession with restraint",
  "supporting_roles": {
    "bass": "emotional floor",
    "chords": "atmosphere",
    "drums": "pulse",
    "textures": "world-building"
  },
  "must_not_compete": ["busy hats", "lead synth", "bright piano runs"],
  "finishability_goal": "easy to write to; feels slightly unfinished without the vocal"
}
```

Rules:

- Every song needs a main character.
- If the brief is vocal-centered, vocal is the default main character.
- Supporting elements must have jobs; anything without a job should be muted or rejected.

### 6.2 Arrangement Director

The Arrangement Director protects against the loop trap.

It must answer:

- What changes every 4, 8, and 16 bars?
- Where does the vocal enter?
- Where does tension build?
- Where does energy drop?
- What gets muted?
- What gets introduced?
- What returns?
- Where is the moment?

Required output:

```json
{
  "sections": [
    {"name": "intro", "bars": 4, "energy": 2, "events": ["texture", "low-end hint"]},
    {"name": "verse", "bars": 16, "energy": 4, "events": ["vocal enters", "drums tucked"]},
    {"name": "pre", "bars": 4, "energy": 5, "events": ["bass thins", "tension texture"]},
    {"name": "chorus", "bars": 8, "energy": 7, "events": ["vocal lift", "background widens"]}
  ],
  "mute_unmute_map": ["drop hats before hook", "bass returns on chorus"],
  "transition_plan": ["breath gap", "one-bar drum dropout"],
  "moment_candidate": "silence before hook into vocal lift"
}
```

### 6.3 Melody Director

The Melody Director prevents good production with forgettable songwriting.

It controls:

- range;
- repetition;
- motif;
- call-and-response;
- tension notes;
- landing notes;
- phrase length;
- breath space;
- emotional contour.

It must ask:

- What phrase should people remember?
- Where does the melody lift?
- Where does it fall?
- Where does it repeat?
- Where does it break the pattern?

Related judges:

- `HookStrengthJudge`;
- `PhraseMemoryJudge`;
- `VocalRangeChecker`.

### 6.4 Emotional Alignment Judge

The Emotional Alignment Judge scores whether these agree or intentionally contrast:

- lyric emotion;
- chord emotion;
- drum energy;
- bass behavior;
- vocal performance;
- arrangement arc.

Mixed signals are allowed only when the brief marks the contrast as intentional.

### 6.5 Section Contrast Judge

The Section Contrast Judge ensures a chorus/hook feels like an arrival.

Required output:

```json
{
  "verse_energy": 4,
  "chorus_energy": 7,
  "contrast_method": [
    "higher vocal melody",
    "bass becomes more sustained",
    "background texture widens",
    "drum pattern stays restrained but kick becomes steadier"
  ]
}
```

If verse and chorus feel the same, flag the song as flat.

### 6.6 Vocal Lane Checker

If a song is vocal-centered, the instrumental should feel slightly unfinished without the vocal. That is space, not failure.

The Vocal Lane Checker must flag:

- too much midrange activity;
- chords that are too rhythmically busy;
- hats masking consonants;
- lead synth stealing topline attention;
- bass fighting vocal low-mids;
- reverb cloud too dense.

### 6.7 Transition Designer

Transitions must create motion without corny transition spam.

Allowed moves:

- pickup notes;
- reverse tails;
- drum dropouts;
- breath gaps;
- bass stops;
- vocal adlibs;
- filter opens;
- one-bar fills;
- silence before chorus.

Taste default: subtle, dark, minimal, emotionally timed. Avoid EDM risers every 8 bars unless explicitly requested.

### 6.8 Moment Designer and Moment Judge

A song needs at least one replayable moment.

Possible moments:

- first vocal entrance;
- bass drop;
- chorus lift;
- unexpected chord;
- silence before hook;
- new harmony stack;
- weird texture;
- drum dropout;
- one lyric line;
- melody leap.

The Moment Judge must answer: "What is the part someone would replay?" If it cannot answer, the result is functional but not memorable.

### 6.9 Mix Aesthetic Guard

Mix decisions must protect the vibe.

For the default dark vocal-centered lane:

- controlled highs;
- warm low end;
- clear vocal center;
- mono-safe bass;
- restrained drums;
- dark space, not shiny space;
- tucked reverb, not washed-out reverb.

Flag:

- too bright;
- too clean;
- too muddy;
- too wide;
- too dry;
- too loud;
- too compressed;
- vocal buried;
- kick too aggressive;
- clap too cheap/forward.

### 6.10 Restraint Judge

The system must not optimize for impressive when the song needs usable.

Penalize:

- too many parts;
- too many fills;
- too many chord changes;
- too many ear-candy events;
- too many drum variations;
- too much harmonic flexing.

Rule: if the part does not improve the song's main emotional job, mute it.

### 6.11 Opening Judge

The first 10 seconds must establish the world and give a reason to keep listening.

It asks:

- Does the first sound feel intentional?
- Does the intro overstay?
- Is the vocal entrance placed well?
- Is there a reason to keep listening?

Default lane: one texture, one chord/motif, one low-end hint, then vocal sooner than expected.

### 6.12 Artist Identity Profile

Taste is what the user likes. Identity is what feels like the user.

Store:

- recurring themes;
- vocal persona;
- lyrical boundaries;
- production identity;
- emotional territory;
- things that feel fake coming from the artist.

Identity rule: reject "good" music that does not feel like the artist would make it.

### 6.13 Finishability Judge

Some loops are cool but hard to finish. Score that explicitly.

```json
{
  "vibe": 8,
  "song_potential": 6,
  "vocal_space": 8,
  "hook_potential": 5,
  "arrangement_potential": 7,
  "finishability": 6
}
```

Warn when a high-vibe loop is low-finishability, for example: "This loop is cool, but it may be hard to write over because the chord rhythm is already too busy."

## 7. Auto-label and library protocol

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

## 8. Generation protocol

Generation must be reviewable before commitment.

Allowed generation outputs:

- beat idea;
- drum kit options;
- groove pattern;
- sound palette;
- plugin chain;
- Ableton session plan;
- MIDI idea;
- prompt/rack/arrangement suggestion;
- section plan;
- melody/hook plan;
- transition map;
- finishability assessment.

Required generation metadata:

- why this fits the brief;
- what taste anchors it uses;
- what avoid rules it respects;
- what risks remain;
- how to revise it;
- whether execution requires confirmation;
- whether this is a dope loop only or a finishable song seed.

## 9. Critique and revision protocol

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
| song_motion | Does the idea change over time instead of staying an 8-bar loop? |
| focal_hierarchy | Is there a clear main character and supporting cast? |
| hook_strength | Is there a phrase, motif, or moment worth remembering? |
| section_contrast | Does the chorus/hook lift or arrive? |
| originality | Does it borrow from references without becoming karaoke? |
| restraint | Did the system leave out parts that do not serve the song? |
| opening_strength | Do the first 10 seconds establish the world? |
| finishability | Is this idea likely to become a full song, not just a cool loop? |

If any critical score fails, revise before presenting it as a final recommendation.

## 10. Feedback memory protocol

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
- Track song-outcome labels such as `easy_to_write_to`, `hard_to_write_to`, `good_loop_bad_song`, `vocal_lane_clear`, `chorus_failed`, `strong_hook_seed`, and `finished_song_candidate`.

## 11. Safety and execution rules

Jarvis must obey these before Ableton execution:

1. Verify track list before track-specific operations.
2. Verify plugin inventory before third-party devices.
3. Surface missing target/taste decisions as questions.
4. Present a plan before creative multi-step changes.
5. Execute one operation at a time.
6. Verify the result after each operation.
7. Prefer reversible actions.
8. Ask for feedback and record corrections.

## 12. MVP protocol: dark vocal-centered R&B drums

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

## 13. Updated song-aware pipeline

```text
Idea / prompt
   ↓
Questionnaire
   ↓
Creative brief
   ↓
Taste system
   ↓
Artist identity check
   ↓
Reference decoder
   ↓
Song Director
   ↓
Drum Director
   ↓
Sound Selector
   ↓
Melody / hook planner
   ↓
Arrangement planner
   ↓
Generate loop / section
   ↓
Vocal lane check
   ↓
Section contrast check
   ↓
Moment check
   ↓
Mix aesthetic check
   ↓
Finishability score
   ↓
Revision
   ↓
User feedback
   ↓
Taste + identity memory update
```

The brutal bottleneck is not making sounds. It is deciding what should be left out, what should repeat, what should change, what should stay emotionally central, and what makes an idea worth finishing.

The song gate must ask:

- Can I write to it?
- Can I remember it?
- Does it have a moment?
- Does the chorus lift?
- Does the vocal have space?
- Does this feel like the artist?
- Is this worth finishing?

## 14. Build order

Do not build every layer at once.

Recommended implementation order:

1. Rich creative brief compiler.
2. Questionnaire modes.
3. Song Director and artist identity profile.
4. Arrangement Director / loop-trap guard.
5. Drum Director MVP.
6. Asset scanner and database.
7. Kit recommendation from actual assets.
8. Vocal lane, section contrast, moment, restraint, originality, and finishability judges.
9. Feedback-to-rule memory updates with finished-song labels.
10. Critique/revision scorer.
11. Ableton integration for approved choices.

## 15. Current implementation status

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
| Song Director | Planned. |
| Artist Identity Profile | Planned. |
| Arrangement Director / loop-trap guard | Planned. |
| Melody Director / Hook judges | Planned. |
| Vocal Lane Checker | Planned. |
| Section Contrast Judge | Planned. |
| Moment Designer/Judge | Planned. |
| Originality Guard | Planned. |
| Mix Aesthetic Guard | Planned. |
| Restraint Judge | Planned. |
| Finishability Judge | Planned. |
| Drum Director | Planned. |
| Kit Builder | Planned. |
| Critique/revision scorer | Planned. |
| Feedback-to-rule updater | Planned. |
