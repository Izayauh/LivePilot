# Jarvis Ableton - Voice-Controlled Music Production

A voice-controlled AI assistant for Ableton Live 11, powered by Google Gemini 2.5. Control your DAW hands-free using natural language commands.

## Features

- 🎤 **Voice Control**: Control Ableton Live using natural language through Gemini's real-time audio streaming
- 🎹 **Comprehensive Controls**: Playback, transport, track controls, scenes, clips, and more
- 🤖 **AI-Powered**: Uses Google Gemini 2.5 Flash with function calling
- 🔊 **Voice Feedback**: Jarvis responds with voice confirmations
- 📡 **OSC Bridge**: Communicates with Ableton via OSC protocol
- 💬 **Desktop Text Chat UI**: Local non-browser chat window for text-only control

## Prerequisites

1. **Ableton Live 11** (or compatible version)
2. **AbletonOSC Plugin** - Install from [AbletonOSC GitHub](https://github.com/ideoforms/AbletonOSC)
3. **Python 3.8+**
4. **Google Gemini API Key** - Get from [Google AI Studio](https://aistudio.google.com/app/apikey)
5. **Audio Input Device** (microphone)

## Installation

### 1. Clone or Download this Repository

```bash
cd JarvisAbleton
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

### 4. Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Windows PowerShell alternative:
```powershell
Copy-Item .env.example .env
```

Edit `.env` and add your Google Gemini API key:

```
GOOGLE_API_KEY=your_actual_api_key_here
```

### 5. Setup AbletonOSC

1. Download and install [AbletonOSC](https://github.com/ideoforms/AbletonOSC)
2. Place the AbletonOSC MIDI Remote Script in Ableton's MIDI Remote Scripts folder:
   - **Windows**: `C:\ProgramData\Ableton\Live 11\Resources\MIDI Remote Scripts\`
   - **macOS**: `/Applications/Ableton Live 11.app/Contents/App-Resources/MIDI Remote Scripts/`
3. Open Ableton Live preferences → Link/Tempo/MIDI → Control Surface
4. Select "AbletonOSC" from the dropdown
5. Verify the OSC server is running on port **11000** (default)

## Usage

### Start Jarvis

1. **Launch Ableton Live** with AbletonOSC enabled
2. **Activate your virtual environment**
3. **Run Jarvis**:

```bash
python jarvis_engine.py
```

You should see:

```
--- Testing Ableton OSC Connection ---
✓ OSC Bridge connected successfully
--- Jarvis Online (Hamilton Studio) ---
Available functions: 22
>>> Jarvis is listening (Hamilton Studio)...
```

### Start Desktop Text Chat UI (No Mic)

If you want local text-only conversation (no browser UI):

```bash
python jarvis_text_ui.py
```

This opens a desktop chat window that uses the same function-calling control path as text mode.

### Start Desktop Chat — OpenClaw (No API Keys)

Desktop chat window (Tkinter) that routes through OpenClaw relay — no Gemini or OpenAI keys needed.

**From Windows PowerShell:**
```powershell
cd C:\Users\isaia\Documents\JarvisAbleton
.\venv\Scripts\python.exe jarvis_desktop_openclaw.py
```

**From WSL:**
```bash
cd /mnt/c/Users/isaia/Documents/JarvisAbleton
./venv/Scripts/python.exe jarvis_desktop_openclaw.py
```

Type `/health` in the chat input to test relay connectivity.

> **Ableton Bridge**: The OpenClaw desktop app uses the `main` agent by default,
> which has access to Ableton controls via `ableton_bridge.py`. The agent calls the
> bridge CLI through its `exec` tool to run OSC commands (get tracks, mute, set tempo,
> load plugins, etc.). **Ableton Live must be running with AbletonOSC loaded** for
> these commands to work. If Ableton is not running, the bridge returns an error JSON
> and the agent relays the message gracefully.
>
> You can also use the bridge directly from the command line:
> ```bash
> ./venv/Scripts/python.exe ableton_bridge.py --list              # list all functions
> ./venv/Scripts/python.exe ableton_bridge.py get_track_list '{}'  # query Ableton
> ./venv/Scripts/python.exe ableton_bridge.py get_creative_context '{}' # structured creative context
> ```

Example `get_creative_context` output:

```json
{
  "transport": {"playing": false, "recording": false, "tempo": 92.0, "position_beats": 0.0},
  "loop": {"enabled": false, "start_beats": 0.0, "length_beats": 4.0},
  "tracks": {"count": 2, "items": [{"index": 0, "number": 1, "name": "Piano"}]},
  "selected": {"track_index": 0, "scene_index": 0},
  "active_librarian": {"song": "Trust Me", "section": "verse", "chain": []},
  "recent_actions": [],
  "project": {"name": "Trust Me Sketch", "genre": "rnb", "stage": "arrangement"},
  "known_limitations": {"limitations": [], "missing_fields": []}
}
```

### Start WSL Terminal Chat (OpenClaw, No API Keys)

Pure terminal chat (no window) — for WSL-only sessions:

```bash
cd /mnt/c/Users/isaia/Documents/JarvisAbleton
python3 jarvis_text_cli_wsl.py
```

> **Note**: Use WSL-native `python3` for the CLI version.
> The desktop app above uses Windows Python and calls `wsl.exe` to reach OpenClaw.

Built-in commands: `/health` (connectivity check), `/quit` (exit).

### Example Voice Commands

Once Jarvis is running, you can say:

**Playback Controls:**
- "Play" / "Start playback"
- "Stop" / "Stop playback"
- "Start recording"
- "Turn on the metronome" / "Turn off the metronome"

**Transport Controls:**
- "Set tempo to 120 BPM"
- "Set the loop to 4 beats"
- "Enable the loop"

**Track Controls:**
- "Mute track 1" / "Unmute track 2"
- "Solo track 3"
- "Arm track 1 for recording"
- "Set track 2 volume to 0.8"
- "Pan track 1 to the left" (use negative values)

**Scene & Clip Controls:**
- "Fire scene 1"
- "Launch the clip on track 2, slot 3"
- "Stop all clips on track 1"

### Important: Track Indexing

**Track 1 in Ableton = Index 0 in the code**

Jarvis understands this automatically:
- When you say "Track 1", Jarvis uses `track_index=0`
- When you say "Track 2", Jarvis uses `track_index=1`
- Same for scenes and clip slots

## Testing

Test the OSC connection independently:

```bash
python tests/test_ableton.py
```

This will toggle the metronome on/off. Check if the metronome icon in Ableton turns orange.

## Project Structure

```
JarvisAbleton/
├── jarvis_engine.py                # Main voice control engine
├── jarvis_tools.py                 # Gemini function declarations
├── ableton_bridge.py               # CLI bridge for OpenClaw agents (no Gemini)
├── ableton_controls/               # Ableton integration package
│   ├── controller.py               # OSC communication + process convenience methods
│   ├── process_manager.py          # Open/Close/Restart Ableton, crash dialog handling
│   └── reliable_params.py          # Retry-resilient parameter setting
├── agents/                         # Multi-agent AI pipeline
├── knowledge/                      # Plugin chain KB, device KB
├── research/                       # Web + YouTube research
├── discovery/                      # VST discovery, device intelligence
├── context/                        # Session management, persistence
├── config/                         # OSC paths, settings
├── tests/                          # Test suite with crash recovery
│   ├── ableton_process_manager.py  # Backward-compat stub (re-exports from ableton_controls)
│   ├── crash_resilient_wrapper.py  # Crash detection + auto-recovery
│   └── run_incremental_test.py     # Incremental chain tests
├── docs/                           # Documentation
├── requirements.txt                # Python dependencies
├── .env                            # Environment variables (not in git)
├── .env.example                    # Environment template
├── docs/architecture_visualization.html # Interactive architecture diagram
└── README.md                       # This file
```

## Architecture

```
┌─────────────────┐
│  Your Voice     │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│   Gemini 2.5 Flash      │ ◄── Real-time audio streaming
│   (Function Calling)    │     + Tool definitions (62 functions)
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│   jarvis_engine.py      │ ◄── Receives function calls
│   + 6 AI Agents         │     Routes to agents/controllers
└────────┬────────────────┘
         │
         ▼
┌──────────────────────────────────────────┐
│  ableton_controls/                       │
│  ├── controller.py  (OSC, port 11000)    │ ◄── OSC Client + process lifecycle
│  └── process_manager.py                  │ ◄── Open/Close/Restart/Crash Recovery
└────────┬─────────────────────────────────┘
         │
         ▼
┌─────────────────────────┐
│   AbletonOSC Bridge     │
│   + JarvisDeviceLoader  │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│   Ableton Live 11       │
└─────────────────────────┘
```

## Non-Chatty Execution Architecture

The chain builder now uses a deterministic pipeline instead of iterative "chatty" loops.

- Entry point: `build_chain_pipeline` (single Gemini tool call per chain)
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

Jarvis can programmatically manage the Ableton process:

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

### "No module named 'pyaudio'"

On Windows, PyAudio might need manual installation:
```bash
pip install pipwin
pipwin install pyaudio
```

On macOS with Homebrew:
```bash
brew install portaudio
pip install pyaudio
```

### Audio Input Issues

- Check your microphone is working and selected as the default input device
- Ensure your system allows Python to access the microphone
- Test with: `python -m pyaudio` to see available devices

### Gemini API Errors

- Verify your API key is correct in `.env`
- Check you have API quota remaining
- Ensure you're using the correct API version (v1alpha)

## Contributing

Feel free to open issues or submit pull requests for:
- Additional Ableton controls
- Improved error handling
- Better voice command recognition
- Documentation improvements

## License

This project is provided as-is for personal use.

## Credits

- Built with [Google Gemini](https://deepmind.google/technologies/gemini/)
- Uses [AbletonOSC](https://github.com/ideoforms/AbletonOSC) by ideoforms
- Powered by [python-osc](https://github.com/attwad/python-osc)

---

**Studio Location**: Hamilton, Ohio 🎵

