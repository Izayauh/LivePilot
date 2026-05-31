# LivePilot — MCP-first Ableton control

Deterministic Ableton Live control through AbletonOSC and a shared Python bridge. Agents (Claude Code, Cursor, OpenClaw) call the same functions via MCP or CLI—no LLM inside the control layer.

## Features

- **MCP server** — `run_mcp_server.py` exposes `list_livepilot_tools`, `call_livepilot_tool`, and creative-context helpers
- **Bridge CLI** — `ableton_bridge.py` for scripting and exec-based agents (~50+ functions)
- **Verified parameters** — `set_device_parameters_by_name` with readback via `reliable_params.py`
- **Plugin recipes** — save/apply per-device snapshots under `data/recipes/`
- **Vocal chains** — Waves templates in `config/vocal_chains.json`; `scripts/apply_vocal_preset.py`, `scripts/remember_chain.py`
- **Parameter contracts** — manifest-driven plans in `livepilot_tools/parameter_contracts.py`

## Prerequisites

1. **Ableton Live** with [AbletonOSC](https://github.com/ideoforms/AbletonOSC) on port **11000**
2. **JarvisDeviceLoader** remote script (repo: `ableton_remote_script/JarvisDeviceLoader/`) on port **11002** for device load / nested params
3. **Python 3.10+** and `pip install -r requirements.txt`

## Quick start

### MCP (Claude Code / Cursor)

```powershell
cd C:\Users\isaia\Projects\music\live-pilot
python -m py_compile run_mcp_server.py mcp_server\server.py
claude mcp add --scope user live-pilot -- python C:\Users\isaia\Projects\music\live-pilot\run_mcp_server.py
```

### Bridge CLI

```powershell
python ableton_bridge.py --list
python ableton_bridge.py diag_osc '{}'
python ableton_bridge.py get_track_list '{}'
python ableton_bridge.py set_device_parameters_by_name '{"track_index":0,"device_index":0,"params":{"Volume":0.8}}'
```

### Plugin recipes

```powershell
python ableton_bridge.py list_plugin_recipes '{}'
python ableton_bridge.py save_plugin_recipe '{"name":"my-eq","track_index":0,"device_index":1}'
python ableton_bridge.py apply_plugin_recipe '{"name":"night-owl-kk-piano-foundation","track_index":0,"device_index":0}'
```

Re-capture `data/recipes/night-owl-kk-piano-foundation.json` with `save_plugin_recipe` when Ableton is open (committed file is a schema placeholder until then).

### Vocal preset (no LLM)

```powershell
python scripts/apply_vocal_preset.py --track 0 --style cla_modern_pop
python scripts/remember_chain.py --track 0 --style cla_modern_pop
```

## Project layout

```
live-pilot/
├── run_mcp_server.py
├── mcp_server/
├── ableton_bridge.py
├── ableton_controls/
├── livepilot_tools/       # shared deterministic tools
├── config/                # osc_paths, vocal_chains, manifests, …
├── data/recipes/          # plugin param snapshots
├── scripts/               # vocal preset, OSC verify, …
├── tests/                 # focused unit tests
└── legacy/                # archived Jarvis / agent stack
```

See `docs/implementation_plan.md` for the cleanup plan and `CLAUDE.md` for agent conventions.

## Tests

```powershell
python -m unittest tests.test_ableton_bridge tests.test_parameter_contracts tests.test_plugin_recipes tests.test_context_tools -v
```

## Legacy Jarvis

Voice/Gemini Jarvis (`jarvis_engine.py`, agents, research bot) lives under `legacy/` for reference only. Use MCP + bridge for new work.
