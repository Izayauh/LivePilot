# LivePilot

A model-agnostic MCP server that gives AI models deterministic, verifiable control of Ableton Live.

Any MCP-capable model connects and calls the tools directly — there is no model-specific
glue and no vendor lock-in. LivePilot exposes 72 tools covering tracks, devices, plugins,
transport, mixing, and session state.

The design constraint that shaped everything else: **an agent should never have to assume a
change landed.** Every write has a corresponding read. Set a device parameter and you can
read it back and confirm the value. Ask for a track's state and you get the actual state,
not the state the model believed it was creating. When something fails, it fails visibly
rather than silently drifting out of sync with the DAW.

That property is the point of the project. Natural-language DAW control is not hard to
demo and easy to trust — the hard part is making an autonomous caller's actions auditable
after the fact.

## What it does

- **Tracks** — create MIDI, audio, and return tracks; rename, color, duplicate, delete; query and set volume, pan, sends, mute, solo, and arm state
- **Devices and plugins** — discover available plugins, add devices to tracks, enable and disable them, read every parameter on a device, and set parameters individually, by name, or in batches
- **Transport and session** — play, stop, continue, set position, loop start and length, tempo, metronome, fire clips and scenes, start and stop recording
- **State and diagnostics** — enumerate tracks and devices, look up tracks by name, list armed tracks, and run an OSC connectivity check before committing to any write

## How it works

```
MCP client (any model)  ->  LivePilot MCP server  ->  OSC  ->  AbletonOSC  ->  Ableton Live
                                     |
                              readback path
                        (confirm the value that actually landed)
```

LivePilot speaks MCP upward to the model and OSC downward to AbletonOSC, Ableton's remote
script. Tools are deterministic: same call, same effect, and a readback available to prove it.

## Requirements

- Ableton Live 11 or later
- [AbletonOSC](https://github.com/ideoforms/AbletonOSC) installed and selected as a Control Surface
  in Preferences → Link/Tempo/MIDI (port 11000)
- Python 3.8+
- An MCP-capable client (e.g. Claude Code, Cursor, OpenClaw)

## Status and scope

LivePilot is a working tool used in a real studio workflow, and it is honest about what it
is not. It has not had an independent security review, it assumes a trusted local
environment, and it has known rough edges around logging and error handling. Treat it as a
capable prototype and personal studio tool rather than production software.

Known operational gotcha: a stale `run_mcp_server.py` process can bind UDP port `11001`,
which AbletonOSC uses for responses. Ableton will still look healthy on `11000`/`11002`
while every state query times out. Kill the process holding `11001` and retry before
diagnosing anything deeper.

## History

LivePilot began as JarvisAbleton, a Gemini-driven voice assistant for Ableton. It has since
been rebuilt around MCP and the readback-verification model described above. GitHub
redirects the old URL; use `https://github.com/Izayauh/LivePilot.git`.

## Installation

### 1. Clone this Repository

```bash
git clone https://github.com/Izayauh/LivePilot.git
cd LivePilot
```

### 2. Create Virtual Environment

```bash
python -m venv venv
```

Activate it:
- **Windows PowerShell**: `.\venv\Scripts\Activate.ps1`
- **Windows CMD**: `.\venv\Scripts\activate.bat`
- **macOS/Linux**: `source venv/bin/activate`

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Setup AbletonOSC

1. Download and install [AbletonOSC](https://github.com/ideoforms/AbletonOSC)
2. Place the AbletonOSC MIDI Remote Script in Ableton's MIDI Remote Scripts folder:
   - **Windows**: `C:\ProgramData\Ableton\Live 11\Resources\MIDI Remote Scripts\`
   - **macOS**: `/Applications/Ableton Live 11.app/Contents/App-Resources/MIDI Remote Scripts/`
3. Open Ableton Live preferences → Link/Tempo/MIDI → Control Surface
4. Select "AbletonOSC" from the dropdown
5. Verify the OSC server is running on port **11000** (default)

## Quick Start

### MCP (Claude Code / Cursor)

Run the stdio MCP server:
```powershell
python run_mcp_server.py
```

To configure with Claude Code:
```powershell
claude mcp add --scope user live-pilot -- python C:\Users\isaia\Projects\music\live-pilot\run_mcp_server.py
```

### Ableton Bridge CLI

You can also run deterministic bridge commands directly from the command line:

```bash
python ableton_bridge.py --list              # list all 72 functions
python ableton_bridge.py diag_osc '{}'       # test OSC connectivity
python ableton_bridge.py get_track_list '{}'  # query Ableton tracks
python ableton_bridge.py get_creative_context '{}' # structured creative context
python ableton_bridge.py analyze_clip_context '{"track_index":0,"clip_index":0}' # MIDI clip summary
python ableton_bridge.py analyze_rhythm_context '{"track_index":2,"clip_index":0,"role":"drums"}' # MIDI-only rhythm grid alignment
python ableton_bridge.py plan_arrangement_move '{"goal":"make the hook lift without adding busy drums","target_section":"hook"}' # reviewable plan only
python ableton_bridge.py set_project_intent '{"genre":"rnb","mood":"intimate","references":["Trust Me - The Fray"],"arrangement_goal":"preserve groove while improving emotional lift","avoid":["fake listening claims"]}'
python ableton_bridge.py get_project_intent '{}'
```

Example `get_creative_context` output:

```json
{
  "transport": {"playing": false, "recording": false, "tempo": 92.0, "position_beats": 0.0},
  "loop": {"enabled": false, "start_beats": 0.0, "length_beats": 4.0},
  "tracks": {"count": 1, "items": [{"index": 0, "number": 1, "name": "Piano"}]},
  "selected": {"track_index": 0, "scene_index": 0},
  "selected_clip": {"track_index": 0, "clip_index": 0, "note_count": 12, "pitch_range": 19},
  "selected_rhythm": {"track_index": 0, "clip_index": 0, "likely_resolution": "1/16", "average_grid_error": 0.0},
  "rhythm_context": {"track_index": 0, "clip_index": 0, "likely_resolution": "1/16", "average_grid_error": 0.0},
  "active_librarian": {"song": "Trust Me", "section": "verse", "chain": []},
  "project_intent": {
    "genre": "rnb",
    "references": ["Trust Me - The Fray"],
    "mood": "intimate",
    "arrangement_goal": "preserve groove while improving emotional lift",
    "prefer": [],
    "avoid": ["fake listening claims"],
    "notes": null,
    "updated_at": "2026-05-01T00:00:00"
  },
  "recent_actions": [],
  "project": {"name": "Trust Me Sketch", "genre": "rnb", "stage": "arrangement"},
  "known_limitations": {"limitations": [], "missing_fields": []}
}
```

In this version, `selected_clip` uses the cached selected track and selected scene as the clip-slot address when no dedicated selected-clip API is exposed.
`selected_rhythm`/`rhythm_context` use the same selected clip-slot address and only inspect accessible MIDI note timing.

Example `analyze_clip_context` output when the active controller exposes clip metadata and MIDI notes:

```json
{
  "success": true,
  "track_index": 0,
  "clip_index": 0,
  "clip_name": "Verse Piano",
  "clip_length_beats": 8.0,
  "note_count": 24,
  "pitch_min": 48,
  "pitch_max": 72,
  "pitch_range": 24,
  "velocity_min": 64.0,
  "velocity_max": 112.0,
  "average_velocity": 88.5,
  "note_start_min": 0.0,
  "note_end_max": 7.75,
  "density_notes_per_beat": 3.0,
  "limitations": [],
  "missing_fields": []
}
```

Example `analyze_rhythm_context` output for a sparse half-time drum clip:

```json
{
  "success": true,
  "track_index": 2,
  "clip_index": 0,
  "role": "drums",
  "clip_length_beats": 4.0,
  "note_count": 6,
  "notes_by_beat": [{"beat": 0, "count": 2, "pitches": [36, 42]}],
  "detected_grid_positions": [{"beat": 0.0, "count": 2, "likely_drum_families": ["hat", "kick"]}],
  "off_grid_notes": [],
  "average_grid_error": 0.0,
  "max_grid_error": 0.0,
  "likely_resolution": "1/4",
  "density_by_bar": [{"bar": 1, "start_beat": 0.0, "end_beat": 4.0, "note_count": 6, "notes_per_beat": 1.5}],
  "downbeat_hits": {"count": 2, "positions": [{"beat": 0.0, "pitch": 36, "likely_drum_family": "kick"}]},
  "backbeat_hits": {"count": 2, "standard_backbeat_offsets": [1.0, 3.0], "half_time_candidate_count": 2},
  "syncopation_notes": [],
  "drum_interpretation": {
    "confidence": "pitch/name heuristic only",
    "family_counts": {"hat": 4, "kick": 1, "snare": 1}
  },
  "warnings": [
    "MIDI note starts are tightly quantized to the detected grid; timing variance appears mechanical from note data alone."
  ],
  "missing_fields": [],
  "limitations": [
    "Assumes 4/4 bar grouping for downbeat, backbeat, and density summaries.",
    "MIDI-only analysis; no audio listening, transient detection, swing extraction, or groove feel judgment."
  ]
}
```

Example `plan_arrangement_move` output:

```json
{
  "success": true,
  "schema_version": "arrangement-plan-v1",
  "goal": "make the hook lift without adding busy drums",
  "target_section": "hook",
  "context_summary": {
    "tempo": 92.0,
    "selected_track_index": 0,
    "selected_scene_index": 0,
    "selected_clip": {"track_index": 0, "clip_index": 0, "note_count": 12, "missing_fields": []}
  },
  "assumptions": ["This plan is a proposal only; no Ableton changes have been executed."],
  "constraints": ["Planning only; do not execute Ableton changes."],
  "moves": [
    {
      "type": "scene_or_arrangement_marker",
      "description": "Review or label the target section boundary before making arrangement edits.",
      "target": {"section": "hook"},
      "parameters": {"label": "hook", "planning_only": true},
      "reason": "Arrangement moves are safer when the intended section is explicit.",
      "status": "proposed"
    },
    {
      "type": "arrangement_edit",
      "description": "Draft a section-level edit that supports the stated goal without changing project data yet.",
      "target": {"section": "hook"},
      "parameters": {"goal": "make the hook lift without adding busy drums", "planning_only": true},
      "reason": "The request is about arrangement direction, so this remains a reviewable placeholder.",
      "status": "proposed"
    }
  ],
  "warnings": ["Goal appears to require listening judgment; human review is required."],
  "requires_human_review": true
}
```

`plan_arrangement_move` does not execute changes. It returns a schema-validated proposal and flags missing context or listening-dependent goals for human review.

Known v1 limitations:

- `get_creative_context` is a context snapshot, not an audio listener.
- `analyze_clip_context` only summarizes accessible MIDI clip data. If the current controller cannot expose clip metadata or notes, those fields are returned as missing.
- `analyze_rhythm_context` uses MIDI note starts only; drum family labels are pitch/name heuristics and are not certainty claims.
- `plan_arrangement_move` is planning only and never writes arrangement, MIDI, device, or automation changes.
- Some live Ableton fields may be reported as missing if the current controller does not expose them.
- Audio, key, energy, and section analysis are intentionally out of scope for the current context milestones.

### Optional Legacy Entry Points

#### Desktop Text Chat UI (No Mic)

Local desktop chat window (Tkinter):

```bash
python jarvis_text_ui.py
```

#### OpenClaw Desktop Chat / WSL CLI

Desktop chat window routing through OpenClaw relay:

```powershell
python jarvis_desktop_openclaw.py
```

Or pure terminal chat in WSL:

```bash
python3 jarvis_text_cli_wsl.py
```

#### Voice Assistant (Original Prototype)

To run the original voice assistant flow:
1. Configure `GOOGLE_API_KEY` in `.env`
2. Run `python jarvis_engine.py`

### Important: Track Indexing

**Track 1 in Ableton = Index 0 in the code**

- When addressing Track 1, tools use `track_index=0`
- When addressing Track 2, tools use `track_index=1`
- Same 0-based indexing applies to scenes and clip slots.

## Testing

Test the OSC connection independently:

```bash
python tests/test_ableton.py
```

This will toggle the metronome on/off. Check if the metronome icon in Ableton turns orange.

## Project Structure

```
LivePilot/
├── run_mcp_server.py               # FastMCP stdio entrypoint
├── mcp_server/                     # MCP protocol wrapper
├── ableton_bridge.py               # Deterministic CLI bridge (72 functions)
├── ableton_controls/               # Ableton integration package
│   ├── controller.py               # OSC communication + process lifecycle
│   ├── process_manager.py          # Open/Close/Restart Ableton, crash dialog handling
│   └── reliable_params.py          # Parameter readback and verification
├── livepilot_tools/                # Deterministic tool modules (context, recipes, contracts)
├── config/                         # OSC paths, vocal chains, settings
├── data/recipes/                   # Plugin parameter snapshots
├── scripts/                        # Utility & workflow scripts
├── tests/                          # Test suite with crash recovery
├── docs/                           # Documentation
└── legacy/                         # Archived Jarvis voice engine and agent prototypes
```

## Architecture

```
┌────────────────────────────────────────────────────────┐
│  MCP Client (Claude Code, Cursor, OpenClaw, any model) │
└───────────────────────────┬────────────────────────────┘
                            │ (stdio JSON-RPC)
                            ▼
┌────────────────────────────────────────────────────────┐
│             LivePilot MCP Server / Bridge              │
│       (run_mcp_server.py / ableton_bridge.py)          │
└───────────────────────────┬────────────────────────────┘
                            │ (OSC, port 11000 / 11002)
                            ▼
┌────────────────────────────────────────────────────────┐
│       AbletonOSC Remote Script + JarvisDeviceLoader    │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                     Ableton Live                       │
└────────────────────────────────────────────────────────┘
```

## Non-Chatty Execution Architecture

The chain builder uses a deterministic pipeline instead of iterative "chatty" loops.

- Entry point: `build_chain_pipeline` (single tool call per chain)
- Plan schema: `pipeline/schemas.py` (`ChainPipelinePlan`, `DeviceSpec`, `ParamSpec`)
- Executor: `pipeline/executor.py` (`PLAN -> EXECUTE -> VERIFY -> REPORT`)
- Guardrail: `pipeline/guardrail.py` (blocks extra LLM calls in execute/verify)
- Fallback resolver: `pipeline/fallback_map.py` (stock -> blacklist/prefs -> keyword fallback)

### Pipeline Phases

1. **PLAN**: Validate track + payload, resolve device names, and count the single planning LLM call.
2. **EXECUTE**: Load devices and set semantic parameters with idempotency checks.
3. **VERIFY**: Re-read values and mark verified/skipped outcomes.
4. **REPORT**: Return a complete `PipelineResult` with timing, per-device/per-param results, skips, and errors/warnings.

### Before vs. After LLM Call Count

| Scenario | Old "Chatty" Loop | New Non-Chatty Pipeline |
|---|---:|---:|
| 3-device vocal chain (8 params) | Usually many iterative calls (often `30+` in practice) | `1` call total |
| 5-device chain (20 params) | Scales with per-param/per-step retries | `1` call total |
| General behavior | ~`O(params + retries)` | `O(1)` (exactly `1` plan call) |

Notes:
- Old behavior was conversational and iterative (`add_plugin_to_track` + repeated `set_device_parameter` loops).
- New behavior sends the entire chain plan once, then executes locally and deterministically.

### Manual Verification Checklist (Live Ableton)

Use this checklist on your Ableton machine before deployment sign-off.

1. **Preflight setup**
   - Start Ableton Live.
   - In Ableton Preferences -> Link/Tempo/MIDI -> Control Surface:
     - Enable `AbletonOSC` (default OSC control path, port `11000`).
     - Enable `JarvisDeviceLoader` (device load path, port `11002`/`11003`).
   - Activate your venv and install dependencies.

2. **Run pipeline integration script**
   - Command: `python tests/test_pipeline_integration.py --track 0`
   - Expected preflight output:
     - `[OK] Ableton connected: ... tracks`
     - `[OK] JarvisDeviceLoader connected`
   - If preflight fails, script should skip gracefully.

3. **Validate Dry Run phase**
   - Test should print `[PASS] Dry run test passed`.
   - Confirm:
     - `phase_reached == plan`
     - no devices loaded
     - no parameter writes performed

4. **Validate End-to-End chain execution**
   - Test should print `[PASS] Basic vocal chain test passed`.
   - Confirm:
     - `Devices: 3/3`
     - planned params were set/verified
     - `LLM calls: 1`
     - `phase_reached == report`

5. **Validate idempotent re-run**
   - Test should print `[PASS] Idempotent re-run test passed`.
   - Confirm:
     - first and second run both succeed
     - second run `total_params_skipped_idempotent >=` first run
     - each run reports `LLM calls: 1`

6. **Validate fallback behavior (manual spot-check)**
   - Create a test plan that includes a missing device name plus `fallback`.
   - Confirm run succeeds with fallback device and `is_fallback=True` on affected device result.

7. **Deployment pass criteria**
   - All three integration tests pass on at least one real track.
   - No extra LLM calls beyond `1` per chain intent.
   - No unexpected errors in pipeline result or logs.

### Process Control

LivePilot can programmatically manage the Ableton process:

```python
from ableton_controls import ableton

ableton.open_ableton()                              # Launch Ableton
ableton.open_ableton(project_path="song.als")       # Launch with project
ableton.close_ableton(force=True)                    # Close (force kill if needed)
ableton.restart_ableton(reopen_project=True)         # Restart, accept recovery dialog
ableton.restart_ableton(reopen_project=False)        # Restart, decline recovery dialog
```

The crash recovery dialog can be configured to default to Yes, No, or Ask:
```python
from ableton_controls.process_manager import get_ableton_manager
manager = get_ableton_manager(recovery_action="yes")  # "yes", "no", or "ask"
```

## Troubleshooting

### "OSC Bridge not responding"

- Make sure Ableton Live is running
- Check that AbletonOSC is selected in Ableton's Control Surface preferences
- Verify AbletonOSC is configured to use port 11000
- Try running `python tests/test_ableton.py` to verify OSC connectivity
- Check if port 11001 is held by a stale Python process

### "No module named 'pyaudio'"

If using optional voice features on Windows, PyAudio might need manual installation:
```bash
pip install pipwin
pipwin install pyaudio
```

On macOS with Homebrew:
```bash
brew install portaudio
pip install pyaudio
```

### Gemini API Errors (Voice/Legacy Mode Only)

- Verify your API key is correct in `.env`
- Check you have API quota remaining
- Ensure you're using the correct API version (v1alpha)

## Contributing

Feel free to open issues or submit pull requests for:
- Additional Ableton controls
- Improved error handling
- Documentation improvements

## License

This project is provided as-is for personal use.

## Credits

- Uses [AbletonOSC](https://github.com/ideoforms/AbletonOSC) by ideoforms
- Powered by [python-osc](https://github.com/attwad/python-osc)

---

**Studio Location**: Hamilton, Ohio 🎵
