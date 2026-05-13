# Post-Instrumental Vocal Prep Textbook

This document is the operating textbook for LivePilot's post-instrumental vocal-prep workflow. It is meant to be used by the planning layer, plugin-intelligence layer, and deterministic executor. It should not be treated as a pile of fixed presets. The goal is to teach LivePilot how to inspect a session, prepare the instrumental, carve a vocal pocket, load a safe vocal chain, and expose useful macros while preserving the user's ability to steer and undo every move.

## Core principle

LivePilot should not guess harder. It should inspect the session, resolve available plugins, apply the smallest useful move, verify the result, and stop when it lacks enough evidence.

The full runtime shape is:

```text
INTENT -> PREFLIGHT -> SESSION INSPECT -> AUDIO SOURCE DECISION -> PLUGIN PLAN -> EXECUTE -> VERIFY -> REPORT
```

For a command such as:

```text
Set me up for a Lana Del Rey / The Neighbourhood type vocal on this beat.
```

LivePilot should translate the vibe into a practical target:

- dark cinematic indie/R&B/pop
- intimate lead vocal
- vocal forward but not dry
- smoky/wide atmosphere
- controlled low end
- restrained brightness
- reverbs and delays filtered so the vocal stays intelligible
- beat supports the voice instead of fighting it

## Non-destructive rules

Every operation must preserve the source audio and the Ableton undo path.

Required behavior:

1. Save or request a safety checkpoint before automated changes.
2. Duplicate or group source tracks instead of overwriting them.
3. Use live devices and racks instead of destructive renders.
4. Do not flatten, freeze, consolidate, crop, or overwrite source files unless the user explicitly approves.
5. Log every device created, parameter changed, track created, route changed, and fallback used.
6. Verify each device and parameter by reading the Ableton state back after setting it.

## Runtime workflow

### 1. Inspect the session

LivePilot should inspect:

- track count
- track names
- audio vs MIDI tracks
- selected track
- arrangement/clip state where available
- existing vocal tracks
- existing beat/stem tracks
- existing returns
- current tempo
- master peak/headroom if available
- whether AbletonOSC and the device loader are responsive

If session state is incomplete, LivePilot should continue only with the safe subset and report missing fields.

### 2. Decide whether the instrumental is stereo or stemmed

Decision tree:

```text
IF multiple stems are present:
    classify and organize stems
ELSE IF one stereo instrumental is present:
    default to a stereo-safe prep first
    offer stem separation only if the user wants deeper pocket carving
ELSE IF no instrumental is present:
    create an empty vocal-prep template and ask for the beat source
```

Stem separation is useful, but it is not mandatory. Split stems can create watery, phasey, or chirpy artifacts. LivePilot should not split a stereo beat automatically unless the user has opted into that behavior.

### 3. Track organization

Recommended layout:

```text
00_REFERENCE
10_DRUMS
20_BASS
30_MUSIC
40_ATMOS_FX
50_LEAD_VOCAL
60_DOUBLES
70_HARMONIES
80_ADLIBS
90_RETURNS
99_MIX_BUS_NOTES
```

Naming rules:

- Generated tracks should include a clear prefix such as `LP_` or numbered group names.
- Track identity should be re-read after every create/delete operation. Do not trust stale indexes.
- Ambiguous tracks should be parked in `30_MUSIC_UNKNOWN` or `40_ATMOS_FX_UNKNOWN` rather than aggressively processed.

### 4. Rough balance rules

Rough balance should be conservative. LivePilot should not pretend it can final-mix the record without listening context.

Guidelines:

- Keep master from clipping.
- Lower the instrumental or harmonic buses before boosting the vocal.
- Prefer gain compensation after every chain stage.
- Do not hard-code a universal drum or bass level.
- Report all level moves in dB.

Safe first moves:

- Pull stereo beat or MUSIC group down if master headroom is low.
- Keep low-end sources mostly unchanged until the vocal exists.
- Avoid widening low-frequency material.
- Do not compress the full beat unless explicitly requested.

## Stem EQ starting points

These are starting ranges, not universal targets. LivePilot should use them as constraints and then rely on the actual session, spectral probe, and user feedback.

| Stem | Low cut | Mud / low-mid | Presence conflict | Harshness | Width guidance | Avoid |
|---|---:|---:|---:|---:|---|---|
| Kick | 20-30 Hz | 180-300 Hz | 2.5-4 kHz click | 6-10 kHz | mono | cutting 50-100 Hz body too hard |
| Snare / clap | 100-180 Hz | 250-500 Hz | 2-5 kHz | 5-8 kHz | mild width only | removing all 180-250 Hz body |
| Hats / perc | 250-500 Hz | 500-900 Hz | 5-8 kHz | 8-10 kHz | pan/width OK | over-brightening sizzle |
| 808 / sub | 20-30 Hz | 120-250 Hz | 700 Hz-1.5 kHz harmonics | 3-5 kHz | mono below 120-150 Hz | cutting the fundamental |
| Bass guitar / synth bass | 35-50 Hz | 180-350 Hz | 700 Hz-1.8 kHz | 3-5 kHz | mono lows | fighting kick with static cuts only |
| Piano / keys | 100-200 Hz | 250-500 Hz | 2-4 kHz | 4-6 kHz | wide if not masking vocal | scooping emotional chord body |
| Guitar | 80-150 Hz | 200-450 Hz | 1.5-4 kHz | 4-7 kHz | often L/R | making it thin/waspy |
| Pads | 120-250 Hz | 250-600 Hz | 1.5-4 kHz | 5-8 kHz | wide, low mids controlled | leaving 300 Hz wash everywhere |
| Strings | 100-200 Hz | 250-500 Hz | 2-5 kHz | 6-8 kHz | wide | harsh bow scrape |
| Vocal chops | 150-250 Hz | 250-600 Hz | 2-5 kHz | 5-8 kHz | mid-wide | competing with lead vocal intelligibility |
| FX / risers | 150-300 Hz | 300-700 Hz | 2-5 kHz | 6-10 kHz | wide | low-mid buildup before drops |
| Stereo beat | 20-35 Hz only if needed | 250-450 Hz | 2-4 kHz | 4-8 kHz | cautious M/S | any static cut over roughly 2 dB without review |

## Vocal pocket carving

The vocal pocket should be created by reducing masking, not by destroying the beat.

### Vocal zones

For a male lead vocal, LivePilot should treat these as probe ranges:

- rumble: 20-60 Hz
- body/chest: 90-220 Hz
- mud/proximity: 200-400 Hz
- box/nasal: 400 Hz-1.2 kHz
- intelligibility/presence: 2-5 kHz
- sibilance/harshness: 5-8 kHz
- air: 10-16 kHz+

### Carving priority

1. Fix the vocal source first: rumble, mud, harshness, sibilance.
2. Lower or clean the masking bus second.
3. Use dynamic EQ/ducking before static EQ when possible.
4. Avoid carving drums and sub-bass for vocal presence unless the conflict is proven.
5. If the beat loses emotion, undo/reduce the carve.

### Decision tree

```text
IF vocal is buried by piano, pad, guitar, or synth:
    identify the loudest masking bus
    apply dynamic carve in 2-4 kHz range at low depth
    verify vocal intelligibility improves

IF vocal is muddy:
    first apply vocal-side dynamic mud control around 200-400 Hz
    then apply instrumental-side low-mid ducking only if needed

IF vocal is harsh:
    do not brighten the vocal or cut the beat first
    de-ess/control vocal 5-8 kHz
    then add air only if sibilance is controlled

IF vocal sounds on top but not inside the beat:
    reduce dry dominance slightly
    add short room or filtered slap
    consider parallel saturation

IF beat sounds hollow after carving:
    reduce carve depth
    switch from static to dynamic carve
    bypass carve during vocal gaps
```

## Plugin strategy

LivePilot must resolve plugins from inventory before building a chain. The repo currently has a Waves-first inventory in `config/owned_plugins.json` plus Ableton stock fallbacks. Extended plugin inventory from CSV should be imported into the plugin intelligence database before runtime decisions depend on it.

### Preferred plugin roles

| Role | Preferred candidates | Stock fallback |
|---|---|---|
| tuning | Tune Real-Time | none / skip |
| subtractive EQ | F6, Renaissance EQ, Manny Marroquin EQ, FabFilter Pro-Q if imported | EQ Eight |
| fast compression | CLA-76 | Compressor |
| smooth leveling | CLA-2A, RCompressor, Renaissance Vox | Compressor / Glue Compressor |
| de-essing | Sibilance, DeEsser, Manny Marroquin Triple D | Multiband Dynamics / EQ Eight workaround |
| vocal automation | Vocal Rider | clip gain / Utility automation |
| saturation/excitement | Aphex Vintage Exciter, Scheps Parallel Particles, CLA Vocals color | Saturator |
| slap/filter delay | H-Delay | Delay / Echo if available |
| plate/hall reverb | H-Reverb, RVerb, Manny Marroquin Reverb, CLA EPIC | Reverb |
| stereo width | Ozone Imager 2 if imported, Utility | Utility |

## Vocal chain recipes

### A. Tracking-safe dark intimate chain

Use this when the user is recording live and latency matters.

```text
1. Tune Real-Time, if requested and key is known
2. EQ Eight / F6: high-pass and mild mud control
3. CLA-76 or Compressor: light peak control
4. Sibilance / DeEsser: light de-essing
5. H-Delay send: very low slap, optional
6. Short room return: low send, optional
```

Rules:

- Avoid heavy linear-phase EQ or CPU-heavy reverbs on the input path.
- Keep reverb and delay mostly on returns.
- If key is unknown, skip tuning or ask the user.

### B. Dark cinematic vocal chain

```text
1. Cleanup EQ: HPF and proximity control
2. Gentle tuning if needed
3. Fast compressor: CLA-76 for peaks
4. Smooth compressor: CLA-2A / RCompressor / RVox
5. Sibilance or DeEsser
6. Subtle saturation/exciter if needed
7. Additive top-end only after de-essing
8. Sends: short room, dark plate/hall, filtered slap, throw delay
```

Purpose:

- vocal forward
- warm body
- smoky atmosphere
- controlled brightness

### C. The Neighbourhood / smoky indie chain

```text
1. EQ cleanup
2. CLA-76 or Compressor with firmer control
3. Sibilance / DeEsser
4. Saturator or Aphex-style harmonic edge, low mix
5. Short slap delay return
6. Dark plate return
7. Optional filtered distortion/telephone parallel for adlibs only
```

Rules:

- Do not distort the lead so much that consonants blur.
- Put aggressive grit on a parallel chain or adlib bus first.

### D. Waves-first chain

```text
1. Tune Real-Time, if key/scale confirmed
2. Renaissance EQ or F6
3. CLA-76
4. Sibilance or DeEsser
5. CLA-2A or Renaissance Vox
6. Aphex Vintage Exciter, low mix if air is needed
7. H-Delay send
8. H-Reverb/RVerb/CLA EPIC send
```

Fallback if a Waves device fails to load:

```text
EQ Eight -> Compressor -> Glue Compressor -> Saturator -> Ableton Reverb/Delay sends
```

## Return tracks

Recommended returns:

| Return | Purpose | Device candidates | Filtering | Starting behavior |
|---|---|---|---|---|
| LP Short Room | puts dry vocal in a physical space | Reverb, TrueVerb, RVerb | HPF 200-300 Hz, LPF 8-10 kHz | quiet static send |
| LP Dark Plate/Hall | cinematic wash | H-Reverb, RVerb, CLA EPIC, Reverb | HPF 300-400 Hz, LPF 6-8 kHz | chorus/phrase automation |
| LP Slap | vintage width/depth | H-Delay, Delay | HPF 250-500 Hz, LPF 3-6 kHz | low feedback, short time |
| LP Filtered Delay | rhythmic movement | H-Delay, Delay | telephone/filter band | automate at phrase ends |
| LP Throw | special phrase repeats | H-Delay, Delay | filtered | default muted until written |

Rules:

- Returns should be 100% wet.
- Filter returns before or after the effect to prevent mud and sibilant splash.
- Long reverb should be ducked or manually kept low during dense phrases.

## Human-facing macros

Map macros to constrained, musical ranges only.

| Macro | Controls | Guardrail |
|---|---|---|
| Vocal Forward | vocal chain input/threshold + output compensation | never create volume spikes |
| Dark/Bright | high shelf or exciter mix | do not affect below 2 kHz |
| Intimacy | 150-300 Hz body/mud balance | do not move HPF too high |
| Smoke | saturation/exciter blend | keep distortion mostly parallel/low mix |
| Slap | slap return send | never alter dry vocal |
| Long Verb | plate/hall return send | cap max send level |
| Delay Throw | throw send automation helper | do not change feedback globally without review |
| Pocket Carve | dynamic EQ depth on music bus | avoid static EQ cuts by default |
| Low-End Clean | vocal HPF and rumble cleanup | never thin body without A/B |
| Width | return/aux width | never widen lead vocal lows |

## Machine-readable template examples

### Track layout

```json
{
  "template_type": "track_layout",
  "groups": [
    {"name": "10_DRUMS", "role": "drums", "required": false},
    {"name": "20_BASS", "role": "bass", "required": false},
    {"name": "30_MUSIC", "role": "harmony_music", "required": false},
    {"name": "40_ATMOS_FX", "role": "atmos_fx", "required": false},
    {"name": "50_LEAD_VOCAL", "role": "lead_vocal", "required": true},
    {"name": "90_RETURNS", "role": "returns", "required": true}
  ],
  "safety": {
    "requery_track_indexes_after_each_create": true,
    "do_not_delete_existing_tracks": true
  }
}
```

### Vocal chain

```json
{
  "template_type": "vocal_chain",
  "chain_name": "dark_cinematic_waves_first",
  "requires_vocal_probe": true,
  "devices": [
    {
      "role": "tuning",
      "preferred": ["Tune Real-Time Stereo", "Tune Real-Time Mono", "Tune Real-Time"],
      "fallback": "skip_if_key_unknown",
      "human_gate": "ask_if_key_or_scale_missing"
    },
    {
      "role": "subtractive_eq",
      "preferred": ["F6 Stereo", "F6 Mono", "Renaissance EQ", "Manny Marroquin EQ Stereo"],
      "fallback": "EQ Eight",
      "parameters_from": "vocal_probe"
    },
    {
      "role": "peak_compression",
      "preferred": ["CLA-76 Stereo", "CLA-76 Mono", "CLA-76"],
      "fallback": "Compressor",
      "target": "2_to_5_db_gain_reduction_on_peaks"
    },
    {
      "role": "de_essing",
      "preferred": ["Sibilance Stereo", "Sibilance Mono", "Sibilance", "DeEsser Stereo", "DeEsser Mono", "DeEsser"],
      "fallback": "Multiband Dynamics",
      "parameters_from": "sibilance_probe"
    },
    {
      "role": "leveling",
      "preferred": ["CLA-2A Stereo", "CLA-2A Mono", "Renaissance Vox Stereo", "RVox Stereo", "RCompressor"],
      "fallback": "Glue Compressor",
      "target": "stable_level_without_flattening"
    }
  ]
}
```

### Pocket carve

```json
{
  "template_type": "pocket_carve",
  "target_buses": ["30_MUSIC", "40_ATMOS_FX"],
  "avoid_buses": ["10_DRUMS", "20_BASS"],
  "preferred_method": "sidechain_dynamic_eq",
  "fallback_methods": ["bus_dynamic_duck", "stereo_mid_static_micro_carve", "ask_user"],
  "bands": [
    {
      "name": "low_mid_masking",
      "candidate_range_hz": [200, 450],
      "max_depth_db": -3,
      "requires_masker_detection": true
    },
    {
      "name": "presence_masking",
      "candidate_range_hz": [2000, 4500],
      "max_depth_db": -3,
      "requires_masker_detection": true
    }
  ],
  "verification": [
    "vocal_intelligibility_improves",
    "beat_does_not_sound_hollow",
    "master_does_not_clip"
  ]
}
```

## Final runtime prompt for LivePilot

```text
Prepare this Ableton session for a dark cinematic indie/R&B/pop male lead vocal inspired by Lana Del Rey and The Neighbourhood.

Use the local plugin inventory and plugin profiles. Do not invent plugins. Prefer Waves-first chains when verified; fall back to Ableton stock devices when needed.

Steps:
1. Run preflight checks for AbletonOSC, device loader, session safety, plugin DB, and master headroom.
2. Inspect the session and identify whether the source is stems, a stereo instrumental, or empty template prep.
3. Create a safety checkpoint before changes.
4. Organize stems/tracks into DRUMS, BASS, MUSIC, ATMOS/FX, LEAD VOCAL, and RETURNS.
5. If only a stereo beat exists, do stereo-safe prep first and ask before stem separation.
6. Create or identify the lead vocal track.
7. If vocal audio exists, run a vocal probe before EQ decisions. If no vocal exists, create a tracking-safe chain and mark EQ as provisional.
8. Resolve plugins from inventory and load the best available chain with stock fallbacks.
9. Create filtered return tracks for short room, dark plate/hall, slap delay, and throw delay.
10. Detect masking before carving. Prefer dynamic sidechain carve on MUSIC/ATMOS buses. Avoid drums/sub unless a conflict is proven.
11. Expose safe macros: Vocal Forward, Dark/Bright, Intimacy, Smoke, Slap, Long Verb, Delay Throw, Pocket Carve, Low-End Clean, Width.
12. Verify every device and parameter by read-back.
13. Report all changes, fallbacks, warnings, and anything requiring user review.
14. Stop before destructive edits, aggressive static EQ, stem splitting, or unsupported sidechain routing.
```

## Do not overdo this

- Do not use fixed EQ numbers as if every voice or beat is the same.
- Do not split stems unless the user approves or the system has a strong reason.
- Do not brighten vocals before de-essing.
- Do not carve huge static holes in the beat.
- Do not widen low-end content.
- Do not put heavy CPU/latency chains on a live tracking path.
- Do not continue after parameter writes fail verification.
- Do not bury the user in plugin details when a simple user gate is needed.

LivePilot becomes useful when it can build a safe starting point quickly and then give the user a small number of musical controls to steer the result.
