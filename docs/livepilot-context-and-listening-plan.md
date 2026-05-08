# LivePilot Context And Listening Plan

## Goal

Make LivePilot capable of understanding what is happening in an Ableton session well enough to generate arrangement, MIDI, device, and automation moves that fit the song.

The target is not just "read session data." The target is an AI producer workflow:

```text
Ableton session/audio
  -> listening and analysis layer
  -> musical interpretation
  -> producer plan
  -> deterministic LivePilot execution
  -> Ableton edits
```

## Current Foundation

LivePilot already has several useful pieces:

- `livepilot_tools/` is the shared deterministic tool layer for Ableton behavior.
- `mcp_server/` exposes LivePilot tools as thin MCP wrappers.
- `ableton_controls/` contains the AbletonOSC controller surface.
- `context/session_manager.py` tracks transport, tracks, recent actions, and project metadata.
- `librarian/session_context.py` tracks an active song, section, chain, and target track.
- `knowledge/` contains device, plugin, chain, and audio knowledge stores.

This gives LivePilot hands inside Ableton. The missing piece is a reliable way to give the AI ears and a producer's brief before it acts.

## Recommended Architecture

Use a hybrid stack instead of expecting one model to do everything.

```text
Audio/DSP analyzers = stable facts
Music generation models = musical imagination/reference generation
GPT-5.5-class planner = producer reasoning and tool orchestration
LivePilot tools = deterministic Ableton execution
```

### 1. Session Scanner

Collect raw Ableton state:

- tempo, time signature, loop state, playhead
- tracks, names, armed/muted/soloed state
- devices and important parameters
- clip names, lengths, note counts, MIDI notes
- selected track, selected scene, active clip
- recent LivePilot actions

The scanner should return structured JSON and avoid model calls.

### 2. Listening Layer

Bounce the master, selected clips, or stems from Ableton, then analyze the audio.

Useful facts:

- tempo and downbeat confidence
- key and chord movement
- section boundaries
- energy curve by bar or section
- spectral density and frequency masking
- drum/groove density
- vocal presence and vocal-space conflicts
- instrument roles

This can start with Python analyzers such as librosa-style feature extraction and later add stronger audio models.

### 3. Interpretation Layer

Turn raw facts into musical meaning:

```text
The track is a slow minor-key R&B ballad at 70 BPM.
The piano owns the harmony with sparse long voicings.
The pad fills the upper-mid space, so new melodic material should avoid dense sustained notes.
The hook needs lift around bars 5-8 through width, register, and automation rather than busy percussion.
```

The interpretation layer should produce a compact `CreativeContext` object.

### 4. Producer Planner

Use a GPT-5.5-class reasoning model as the creative director.

Responsibilities:

- explain what is happening in the session
- identify missing arrangement roles
- decide what should happen next
- choose where to add MIDI, devices, automation, or scene changes
- output a structured plan that LivePilot can execute

The planner should always read `get_creative_context()` before generating or modifying material.

### 5. Deterministic Executor

LivePilot should execute explicit structured commands, not vague model prose.

Example output from the planner:

```json
{
  "moves": [
    {
      "type": "automation",
      "track": "Pad",
      "parameter": "filter_cutoff",
      "section": "hook",
      "shape": "slow_rise",
      "start_bar": 1,
      "end_bar": 8,
      "from": 0.35,
      "to": 0.72
    },
    {
      "type": "midi_clip",
      "track": "Lead",
      "section": "hook",
      "role": "restrained counter-melody",
      "length_beats": 32
    }
  ]
}
```

## Where Lyria Or Suno Fit

Lyria and Suno-style systems are better thought of as music generation or music-imagination engines.

They can help with:

- generating reference audio from a creative brief
- creating alternate melodic or arrangement directions
- producing rough audio sketches
- inspiring stem or section ideas

They should not be the core LivePilot controller. LivePilot still needs a reasoning model that can inspect context, choose tools, produce structured commands, and make reversible Ableton edits.

Best division of labor:

```text
Lyria/Suno-like model = musical imagination and reference audio
GPT-5.5-class model = producer brain and tool planner
LivePilot = hands in Ableton
```

## Proposed New LivePilot Tools

Add these in `livepilot_tools/context_tools.py`, then expose them as one-line MCP wrappers:

- `scan_session_context()`
- `set_project_intent(intent: dict)`
- `get_project_intent()`
- `analyze_clip_context(track_index: int, clip_index: int)`
- `analyze_audio_bounce(path: str)`
- `get_creative_context()`
- `record_creative_decision(decision: dict)`
- `plan_arrangement_move(goal: str, target_section: str | None = None)`

The first useful milestone is `get_creative_context()`. Even a simple version should include tempo, track list, selected clip, recent actions, active section, user intent, and any known project constraints.

## Prompt Contract

Before creating anything, the agent should follow this sequence:

1. Call `get_creative_context()`.
2. Explain what is musically happening.
3. Identify the missing role or problem to solve.
4. Produce a structured plan.
5. Execute through LivePilot tools.
6. Record the creative decision.

Recommended instruction:

```text
Before generating notes, devices, or automation, call get_creative_context.
Create only material that fits that context.
State the intended musical role before writing.
Return executable changes as structured JSON.
```

## Milestones

1. Add `get_creative_context()` using existing session, librarian, and track-list data.
2. Add persistent project intent, including genre, reference, mood, arrangement goals, and avoid/prefer constraints.
3. Add selected-clip MIDI summarization.
4. Add audio bounce analysis for key, energy, density, and section hints.
5. Add arrangement planner JSON schema.
6. Add automation execution helpers for curves over bars.
7. Add tests with fake controllers and fixture context.

## Success Criteria

LivePilot should be able to answer:

- What kind of song is this?
- What section am I in?
- What role does each track currently play?
- What is missing from the arrangement?
- What should change over the next 4, 8, or 16 bars?
- Which Ableton tool calls will make that happen safely?

When it can answer those questions before acting, the AI will stop feeling blind and start behaving more like a producer inside the session.
