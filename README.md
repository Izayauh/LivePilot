# LivePilot

A model-agnostic MCP server that gives AI models deterministic, verifiable control of Ableton Live.

Any MCP-capable model connects and calls the tools directly — there is no model-specific glue and no vendor lock-in. LivePilot exposes 72 tools covering tracks, devices, plugins, transport, mixing, and session state.

The design constraint that shaped everything else: **an agent should never have to assume a change landed.** Every write has a corresponding read. Set a device parameter and you can read it back and confirm the value. Ask for a track's state and you get the actual state, not the state the model believed it was creating. When something fails, it fails visibly rather than silently drifting out of sync with the DAW.

That property is the point of the project. Natural-language DAW control is not hard to demo and easy to trust — the hard part is making an autonomous caller's actions auditable after the fact.

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

LivePilot speaks MCP upward to the model and OSC downward to AbletonOSC, Ableton's remote script. Tools are deterministic: same call, same effect, and a readback available to prove it.

## Requirements

- Ableton Live 11 or later
- [AbletonOSC](https://github.com/ideoforms/AbletonOSC) installed and selected as a Control Surface in Preferences → Link/Tempo/MIDI (port 11000)
- Python 3.10+
- An MCP-capable client (e.g. Claude Code, Cursor, OpenClaw)

## Quick Start

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

### 5. Running the MCP Server

Run the stdio MCP server:
```powershell
python run_mcp_server.py
```

To configure with Claude Code:
```powershell
claude mcp add --scope user live-pilot -- python <path-to-your-clone>\run_mcp_server.py
```

### 6. Ableton Bridge CLI

You can also run deterministic bridge commands directly from the command line:

```bash
python ableton_bridge.py --list              # list all 72 functions
python ableton_bridge.py diag_osc '{}'       # test OSC connectivity
python ableton_bridge.py get_track_list '{}'  # query Ableton tracks
python ableton_bridge.py get_creative_context '{}' # structured creative context
python ableton_bridge.py set_device_parameters_by_name '{"track_index":0,"device_index":0,"params":{"Volume":0.8}}'
```

### 7. Plugin Recipes

```powershell
python ableton_bridge.py list_plugin_recipes '{}'
python ableton_bridge.py save_plugin_recipe '{"name":"my-eq","track_index":0,"device_index":1}'
python ableton_bridge.py apply_plugin_recipe '{"name":"night-owl-kk-piano-foundation","track_index":0,"device_index":0}'
```

## Status and Scope

LivePilot is a working tool used in a real studio workflow, and it is honest about what it is not. It has not had an independent security review, it assumes a trusted local environment, and it has known rough edges around logging and error handling. Treat it as a capable prototype and personal studio tool rather than production software.

Known operational gotcha: a stale `run_mcp_server.py` process can bind UDP port `11001`, which AbletonOSC uses for responses. Ableton will still look healthy on `11000`/`11002` while every state query times out. Kill the process holding `11001` and retry before diagnosing anything deeper.

## Project Structure

```
LivePilot/
├── run_mcp_server.py               # FastMCP stdio entrypoint
├── mcp_server/                     # MCP protocol wrapper
├── ableton_bridge.py               # Deterministic CLI bridge (72 functions)
├── ableton_controls/               # Ableton OSC communication and controller
├── livepilot_tools/                # Deterministic tool modules (context, recipes, contracts, stem tools)
├── config/                         # OSC paths, vocal chains, settings
├── data/recipes/                   # Plugin parameter snapshots
├── scripts/                        # Utility & workflow scripts
├── tests/                          # Focused unit tests
├── docs/                           # Documentation
└── legacy/                         # Archived Jarvis voice engine and agent prototypes
```

See `docs/implementation_plan.md` for the cleanup plan and `CLAUDE.md` for agent conventions.

## Tests

```powershell
pytest tests/test_ableton_bridge.py tests/test_parameter_contracts.py tests/test_plugin_recipes.py tests/test_context_tools.py tests/test_stem_tools.py
```

## Legacy Jarvis

Voice/Gemini Jarvis (`jarvis_engine.py`, agents, research bot) lives under `legacy/` for reference only. Use MCP + bridge for new work.

## History

LivePilot began as JarvisAbleton, a Gemini-driven voice assistant for Ableton. It has since been rebuilt around MCP and the readback-verification model described above. GitHub redirects the old URL; use `https://github.com/Izayauh/LivePilot.git`.

## License

This project is provided as-is for personal use.

## Credits

- Uses [AbletonOSC](https://github.com/ideoforms/AbletonOSC) by ideoforms
- Powered by [python-osc](https://github.com/attwad/python-osc)

---

**Studio Location**: Hamilton, Ohio 🎵
