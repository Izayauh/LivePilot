# Vocal Prep Edge-Case Recovery Playbook

This playbook defines the failure-recovery layer for LivePilot's post-instrumental vocal-prep system. The purpose is to make failures predictable, recoverable, logged, and safe.

The core rule:

```text
Every LivePilot action must have a resolver.
```

A resolver declares the goal, required conditions, detection method, automatic recovery path, user prompt if needed, telemetry, and next state.

## Execution model

```text
PLAN -> PREFLIGHT -> EXECUTE ONE SMALL STEP -> VERIFY -> RECOVER OR CONTINUE -> REPORT
```

The LLM should produce intent and plans. The executor should perform deterministic operations. The executor must not keep asking the LLM how to set every knob during execution.

## Resolver result schema

```json
{
  "success": true,
  "stage": "PLUGIN_PLAN_RESOLVE",
  "action_taken": "loaded_fallback_plugin",
  "fallback_used": "EQ Eight",
  "needs_user": false,
  "user_prompt": null,
  "telemetry": {
    "requested": "F6 Stereo",
    "aliases_tried": ["F6", "F6 Mono"],
    "error": null,
    "duration_ms": 0
  },
  "next_state": "VERIFY_DEVICE_LOAD"
}
```

## State machine

```text
IDLE
  -> PARSE_USER_INTENT
  -> PREFLIGHT_CHECK
  -> SAFETY_SNAPSHOT
  -> SESSION_INSPECT
  -> AUDIO_SOURCE_DECISION
  -> OPTIONAL_STEM_SPLIT
  -> IMPORT_AND_CLASSIFY
  -> PLUGIN_PLAN_RESOLVE
  -> VOCAL_PROBE
  -> MASKER_DETECT
  -> APPLY_CHAIN_STAGE_1
  -> VERIFY_STAGE_1
  -> APPLY_RETURNS
  -> VERIFY_RETURNS
  -> MAP_MACROS
  -> FINAL_A_B_REPORT
  -> DONE
```

Each state has three exits:

```text
success -> next state
recoverable failure -> resolver
unrecoverable failure -> user prompt + safe stop
```

## Severity levels

| Severity | Meaning | Behavior |
|---|---|---|
| critical | could damage session, overwrite work, crash Ableton, or make destructive changes | stop and require user confirmation |
| high | automation cannot complete intended result | run fallback or ask user |
| medium | result quality may suffer but setup can continue | fallback and report warning |
| low | cosmetic/logging issue | continue and log |

## Failure-mode matrix

| ID | Stage | Edge case | Symptom | Detection | Recovery |
|---|---|---|---|---|---|
| LP-CONN-001 | PREFLIGHT | Ableton not running | no OSC response | ping AbletonOSC fails | prompt user to open Ableton; retry healthcheck |
| LP-CONN-002 | PREFLIGHT | AbletonOSC not selected | OSC timeout | no response on expected port | show Ableton Preferences checklist; stop safely |
| LP-CONN-003 | PREFLIGHT | MCP server down | tool route unavailable | local server healthcheck fails | restart MCP server if allowed; otherwise prompt |
| LP-CONN-004 | PREFLIGHT | Device loader unavailable | plugins cannot load | loader ping fails | continue with analysis-only plan or stop before plugin actions |
| LP-SAFE-001 | SAFETY | session unsaved | no known rollback point | project path empty or dirty-state unknown | create named checkpoint request or ask user to save copy |
| LP-SAFE-002 | SAFETY | destructive action requested | split/render/freeze/flatten/crop | action type flagged destructive | require explicit user approval |
| LP-TRACK-001 | SESSION | stale track indexes | action affects wrong track | track count/order changed after action | re-query tracks after every create/delete; use stable generated names |
| LP-TRACK-002 | SESSION | duplicate track names | ambiguous target | multiple matches | ask user or use selected track plus explicit generated prefix |
| LP-TRACK-003 | SESSION | no instrumental found | cannot prep beat | no audio tracks or no selected source | create empty template and ask for beat source |
| LP-TRACK-004 | SESSION | no vocal track exists | cannot mix vocal | no vocal track/audio/input | create lead vocal track; mark EQ provisional |
| LP-AUDIO-001 | AUDIO_SOURCE | stereo beat only | no stems for bus carving | one stereo source detected | use stereo-safe prep first; ask before stem separation |
| LP-AUDIO-002 | AUDIO_SOURCE | stem split fails | missing output files | CLI nonzero exit or missing manifest | retry lower model/resource mode; revert to stereo beat |
| LP-AUDIO-003 | AUDIO_SOURCE | stem artifacts | watery/chirpy/phasey stems | artifact score/high spectral mismatch/user rejection | reject stems and use original stereo source |
| LP-AUDIO-004 | IMPORT | warped stems | phase smear or timing drift | clip warp flag true or lengths mismatch | disable warp; reimport; align starts |
| LP-AUDIO-005 | IMPORT | mismatched sample rate/length | stems drift | stem durations differ unexpectedly | warn user; align only if difference is small; otherwise stop |
| LP-CLASS-001 | CLASSIFY | ambiguous stem names | `other.wav` unclear | low classification confidence | route to UNKNOWN group; apply only bus-safe processing |
| LP-CLASS-002 | CLASSIFY | drums/bass mislabeled | wrong EQ/route | stem features contradict filename | lower confidence; ask user if action would be aggressive |
| LP-PLUGIN-001 | PLUGIN | plugin in inventory but not in Ableton | load fails | device count unchanged after load | try aliases; then fallback; mark unavailable for run |
| LP-PLUGIN-002 | PLUGIN | license missing | plugin loads broken/silent | parameter list empty or load dialog blocks | mark blocked_license; use fallback |
| LP-PLUGIN-003 | PLUGIN | mono/stereo variant mismatch | preferred plugin fails | exact name fails but variant exists | try stereo, mono, generic aliases |
| LP-PLUGIN-004 | PLUGIN | plugin scan cache stale | plugin not found after install | inventory says present, Ableton does not | prompt user to rescan plugins in Ableton |
| LP-PARAM-001 | PARAMETERS | parameter profile missing | cannot set knobs | no profile for plugin | load scratch instance, scan params, save profile |
| LP-PARAM-002 | PARAMETERS | wrong parameter name | set command fails | no exact match | fuzzy match canonical names; require read-back verification |
| LP-PARAM-003 | PARAMETERS | parameter write ignored | value unchanged | read-back mismatch | retry once; use fallback or skip unsafe param |
| LP-PARAM-004 | PARAMETERS | raw 0-1 range unknown | wrong value scaling | unit metadata missing | do not set musical value; request/manual profile pass |
| LP-VOCAL-001 | VOCAL_PROBE | no recorded vocal | cannot know EQ target | no clips on lead vocal | create tracking chain only; ask user to record/import vocal |
| LP-VOCAL-002 | VOCAL_PROBE | vocal too quiet/noisy | probe unreliable | low SNR or peak too low | ask for better take or use conservative defaults |
| LP-VOCAL-003 | VOCAL_PROBE | clipping vocal | EQ/compression meaningless | peaks at/near 0 dBFS | warn user; suggest re-record or clip gain down before chain |
| LP-VOCAL-004 | VOCAL_EQ | system does not know EQ target | arbitrary EQ risk | no probe/confidence low | run vocal_probe before EQ; otherwise keep provisional chain |
| LP-MASK-001 | MASKER | unknown masking source | vocal buried | no bus clearly overlaps | ask user what fights vocal, or use tiny full-stereo mid carve |
| LP-MASK-002 | MASKER | carve makes beat hollow | emotional loss | A/B warning/user rejection | reduce depth, switch dynamic, rollback last carve |
| LP-SIDE-001 | SIDECHAIN | external sidechain unsupported | routing fails | sidechain route unavailable | fallback to bus ducking or static micro-carve |
| LP-SIDE-002 | SIDECHAIN | wrong sidechain source | ducking responds wrong | sidechain meter inactive or wrong trigger | re-route to LEAD VOCAL post-FX; verify activity |
| LP-RETURN-001 | RETURNS | reverb mud | vocal loses clarity | low-mid buildup after sends | filter return, reduce send, duck return |
| LP-RETURN-002 | RETURNS | delay clutter | phrases smear | high feedback/center delay | lower feedback, filter delay, automate throws only |
| LP-MACRO-001 | MACROS | macro maps unsafe parameter | knob breaks mix | target not allowlisted | block mapping; require allowlist only |
| LP-MACRO-002 | MACROS | macro range too wide | tiny turn causes big change | range exceeds safe max | clamp range and report |
| LP-CPU-001 | PERFORMANCE | CPU overload | pops/dropouts | CPU/latency check fails | switch to tracking_safe_chain; disable heavy returns |
| LP-CPU-002 | PERFORMANCE | high-latency chain while tracking | recording feels delayed | latency plugin detected | bypass heavy devices during record; use mix chain later |
| LP-GAIN-001 | GAIN | master clipping | red master | peak/headroom check fails | trim groups; do not slap limiter on master as first fix |
| LP-REPORT-001 | REPORT | user cannot tell what changed | low trust | missing changelog | output concise before/after report with fallbacks |

## Resolver modules

### 1. `connection_healthcheck`

Purpose: verify Ableton, AbletonOSC, MCP, and device loader before session edits.

Checks:

```json
{
  "ableton_open": true,
  "abletonosc_reachable": true,
  "mcp_server_alive": true,
  "device_loader_alive": true,
  "round_trip_ms": 0
}
```

Recovery:

- Retry once.
- If AbletonOSC fails, show setup checklist.
- If device loader fails, stop before plugin operations.
- If only context reading works, offer analysis-only mode.

### 2. `safety_checkpoint_resolver`

Purpose: protect the session before automated edits.

Required before:

- stem separation
- import/delete/move actions
- large chain builds
- route creation
- macro mapping
- any action that cannot be trivially undone

Telemetry:

```json
{
  "checkpoint_id": "2026-05-13T...",
  "project_path": null,
  "tracks_before": [],
  "devices_before": [],
  "unsafe_actions_blocked": []
}
```

### 3. `track_identity_resolver`

Purpose: prevent stale track indexes from causing wrong-track edits.

Rules:

- Re-query track list after every create/delete.
- Generated tracks receive stable names: `LP_LEAD_VOCAL`, `LP_SHORT_ROOM`, etc.
- If duplicate names exist, target by selected track plus user confirmation or generated unique suffix.

### 4. `plugin_inventory_resolver`

Purpose: avoid fake plugins and load the best available device.

Resolution ladder:

```text
1. exact profile match
2. exact inventory match
3. alias match
4. same role preferred plugin
5. stock fallback
6. skip optional device
7. user prompt
```

Example output:

```json
{
  "role": "de_esser",
  "selected": "Sibilance Stereo",
  "fallback": null,
  "confidence": 0.93,
  "aliases_tried": ["Sibilance", "DeEsser Stereo"]
}
```

### 5. `parameter_profile_resolver`

Purpose: learn how a plugin exposes its parameters.

Process:

1. Load plugin on scratch track.
2. Read all exposed parameters.
3. Normalize parameter names.
4. Infer units if possible.
5. Test a safe write.
6. Read back.
7. Save profile.
8. Mark unsafe parameters as read-only.

Profile shape:

```json
{
  "plugin": "F6 Stereo",
  "role": "dynamic_eq",
  "profile_version": 1,
  "safe_to_automate": true,
  "parameters": [
    {
      "canonical": "band_1_frequency_hz",
      "actual_name": "Band 1 Freq",
      "index": 14,
      "unit": "Hz",
      "write_verified": true
    }
  ]
}
```

### 6. `audio_source_resolver`

Purpose: decide between stereo-safe workflow and stem workflow.

```text
IF stems exist:
    classify stems
ELSE IF stereo beat exists:
    prepare stereo-safe workflow
    ask before stem separation
ELSE:
    create empty vocal template
```

Stem separation output should include a manifest:

```json
{
  "source_file": "beat.wav",
  "method": "audio-separator/demucs",
  "outputs": ["drums.wav", "bass.wav", "other.wav", "vocals.wav"],
  "duration_match": true,
  "artifact_check": "passed_or_skipped",
  "user_approved": true
}
```

### 7. `vocal_probe_resolver`

Purpose: prevent arbitrary vocal EQ.

Minimum probe:

- loudness/peak check
- rumble below 60 Hz
- body range estimate
- mud range estimate
- sibilance zone estimate
- harshness zone estimate
- air/top-end deficit estimate

Output:

```json
{
  "vocal_profile": {
    "body_hz": [100, 200],
    "mud_risk_hz": [240, 380],
    "sibilance_risk_hz": [5800, 7600],
    "air_needed": "medium",
    "confidence": 0.72
  },
  "moves": [
    {
      "type": "hpf",
      "range_hz": [65, 95],
      "reason": "remove rumble without thinning body",
      "requires_user": false
    }
  ]
}
```

If no vocal exists:

```text
Create tracking-safe chain. Do not finalize EQ. Mark as provisional.
```

### 8. `masker_resolver`

Purpose: identify what part of the beat blocks the vocal.

Process:

1. Compare vocal profile against buses.
2. Rank masking sources.
3. Pick the smallest target.
4. Apply dynamic carve.
5. Verify improvement.

If confidence is low, ask:

```text
I cannot confidently identify the masking source. Does the vocal feel blocked by piano/keys, pads, guitar/synth, or the whole beat?
```

### 9. `sidechain_resolver`

Purpose: build a working dynamic carve.

Fallback ladder:

```text
1. F6 sidechain dynamic EQ
2. FabFilter dynamic EQ profile if available
3. broad sidechain compression on MUSIC/ATMOS
4. tiny static EQ carve
5. ask user
```

Safety:

- Never carve drums or sub-bass for presence unless conflict is proven.
- Keep static cuts tiny by default.
- Verify sidechain activity if possible.

### 10. `return_resolver`

Purpose: create reverb/delay returns without washing out the vocal.

Rules:

- All returns 100% wet.
- Filter returns.
- Keep throw delay muted until automation.
- Prefer sends over inserts.
- Duck long reverb if it masks the vocal.

### 11. `macro_resolver`

Purpose: map only safe, musical controls.

Macro allowlist:

```json
[
  "Vocal Forward",
  "Dark/Bright",
  "Intimacy",
  "Smoke",
  "Slap",
  "Long Verb",
  "Delay Throw",
  "Pocket Carve",
  "Low-End Clean",
  "Width"
]
```

Rules:

- Clamp every macro range.
- Never map macros to destructive actions.
- Never let Width affect low-end mono safety.
- Never let Vocal Forward create uncompensated loudness jumps.

### 12. `performance_resolver`

Purpose: stop latency/dropouts.

If tracking:

- use tracking-safe chain
- avoid heavy reverbs on insert
- keep heavy mix devices bypassed until playback/mix mode

If CPU overload detected:

- bypass heavy returns
- switch to stock fallback
- disable analyzers
- report performance mode

## User-in-the-loop gates

LivePilot should ask the user only when the machine lacks key context or a step is risky.

Ask before:

- stem separation
- destructive render/freeze/flatten/crop
- tuning without key/scale
- aggressive EQ over safe range
- sidechain route cannot be verified
- replacing existing chains
- deleting/moving user tracks
- importing many generated files

Do not ask before:

- creating a clearly named lead vocal track
- creating muted returns
- loading a stock fallback after a missing optional plugin
- applying tiny provisional cleanup moves when clearly reversible

## Logging fields

Every action should log:

```json
{
  "run_id": "uuid",
  "timestamp": "iso8601",
  "user_intent": "dark cinematic vocal prep",
  "stage": "APPLY_CHAIN_STAGE_1",
  "action": "load_device",
  "target_track": "LP_LEAD_VOCAL",
  "requested_device": "Sibilance Stereo",
  "resolved_device": "Sibilance Stereo",
  "fallback_used": false,
  "parameters_before": {},
  "parameters_after": {},
  "verification": "passed",
  "warnings": [],
  "needs_user": false
}
```

## Test plan

### Unit tests

- plugin alias resolution
- fallback selection
- parameter fuzzy matching
- unsafe macro blocking
- edge-case schema validation
- state transition validation

### Integration tests with mocked Ableton

- AbletonOSC timeout
- device loader timeout
- plugin load failure
- parameter write mismatch
- track index drift
- duplicate track names
- no vocal/no beat
- stereo-only workflow
- sidechain failure fallback

### Live Ableton smoke tests

1. Open empty set.
2. Run preflight only.
3. Create lead vocal track and returns.
4. Load stock fallback chain.
5. Load Waves-first chain.
6. Verify parameter read-back.
7. Re-run idempotently.
8. Confirm no duplicate devices unless requested.
9. Confirm undo/rollback path.

## Prioritized build plan

### Phase 1: hard safety

- connection healthcheck
- safety checkpoint
- track re-query after every mutation
- device load verification
- parameter read-back verification
- action log

### Phase 2: plugin intelligence

- alias table
- plugin role resolver
- scratch-track parameter scanner
- parameter profile store
- license/load failure marking

### Phase 3: audio source handling

- stereo vs stem detector
- stem split approval gate
- stem manifest
- warp/length verification
- classification confidence score

### Phase 4: vocal intelligence

- vocal probe
- masker detector
- sidechain resolver
- provisional chain mode when no vocal exists

### Phase 5: musical verification

- A/B bypass checks
- clipping/headroom checks
- CPU/latency checks
- user rejection rollback
- failed config as negative example

## Codex implementation prompt

```text
Build LivePilot's vocal-prep failure-recovery layer as deterministic resolvers.

Do not let the LLM directly decide plugin parameters inside executor code.

Every operation must follow:
1. declare goal
2. declare required conditions
3. preflight check
4. execute smallest possible action
5. verify by read-back or session inspection
6. recover if verification fails
7. log before/after state
8. stop safely if recovery is uncertain

Implement resolvers for:
- AbletonOSC/MCP connection
- session safety snapshot
- track identity/index drift
- plugin inventory aliases
- plugin load failure
- parameter profile missing
- parameter write/read-back mismatch
- stereo-vs-stem decision
- stem separation failure/artifacts
- warp/alignment mismatch
- track classification ambiguity
- vocal EQ probe missing
- masker detection uncertainty
- sidechain routing failure
- return send over-wash
- macro unsafe mapping
- CPU/latency overload
- master clipping
- user rejection rollback

Each resolver must output:
{
  success,
  action_taken,
  fallback_used,
  needs_user,
  user_prompt,
  telemetry,
  next_state
}
```

## Bottom line

The system should not fail silently, guess randomly, or keep stacking plugins because the first answer sounded musical. It should diagnose what is missing, run the smallest useful routine, verify the result, and either continue or stop cleanly.
