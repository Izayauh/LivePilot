# Live Pilot

**Talk to Ableton Live.** Live Pilot Studio listens on your mic while you work, and does what
you say in your set: levels, pans, sends, mutes, solos, devices, plugin settings, auditioning
a section, tempo, saving. It reads every change back from Live and shows it in a small window,
so you never have to look away from the music to trust it. Everything it does is undoable.

> **Open it:** double-click **Live Pilot** on your desktop (after `install.cmd` below).
> Talk when the light is green. Close the window to stop.

```
"Bring the vocal down two dB."          "Solo the drums and play from the hook."
"Put a compressor on the bass."         "What's on the piano track?"
"Set the tempo to 92."                  "Undo that."
```

Windows 10/11, Ableton Live 11 or 12 (any edition), a Claude account (Pro or Max), a microphone.

**What leaves your computer.** Speech is turned into text on your computer and the audio never
leaves it, but the mic hears the whole room: everything it transcribes, other people's voices
included, goes as text to Anthropic's Claude through your own account, with a short snapshot of
your set. Claude's usage reporting is switched off, and apart from the one-time speech model
download from Hugging Face nothing else is sent. Transcripts are kept on your computer in
`data\telemetry\studio_turns.jsonl` and `data\telemetry\calls.jsonl` inside the Live Pilot
folder; deleting the folder removes them.

## Install (10 minutes, once)

1. Install **Python 3.12 or 3.13** (3.14 and newer are not supported yet) from
   https://www.python.org/downloads/windows/ and tick **Add python.exe to PATH** on the first
   screen of the Python installer.
2. Download the latest `LivePilot-x.y.z.zip` from this repository's Releases page and unzip it
   somewhere permanent (for example `C:\LivePilot`). Or `git clone` this repository.
3. Double-click **`install.cmd`** in that folder. If Windows says it protected your PC, click
   **More info**, then **Run anyway**. A window opens and walks through the rest: it creates a
   private Python environment, installs the LivePilot remote script into every Ableton Live it
   finds, signs you in to Claude (type `/login` when Claude opens, then `/exit`), downloads the
   speech model (2.4 GB, once), asks what to call you, and puts **Live Pilot** on your desktop.
   It ends with a list of checks; the line about Ableton Live answering says FIX until Live is
   open, which is expected. Press a key to close the window.
4. Open Ableton Live. In **Options > Preferences > Link, Tempo & MIDI**, pick **LivePilot** as a
   Control Surface. This is a one-time step; Live remembers it.
5. Double-click **Live Pilot** on your desktop.

Running `install.cmd` again is safe: it only fixes what is missing. The options below are for a
PowerShell or Command Prompt window opened in the Live Pilot folder.

## Using it

The window has three parts: the conversation (what you said, what it did), the log on the right
(every call to Live with how long it took), and a text box at the bottom if you would rather type.
The header shows the set's tempo, bar and play state, polled every two seconds.

- The mic hears the whole room and ignores anything that is not for it (singing, a song playing,
  you talking to someone else). **Mic on/off** in the header pauses it; `--no-mic` starts typing-only.
- Routine moves happen right away, no confirmation. Taste questions ("does the hook need more
  energy?") get a two-sentence take, then action if you asked for it.
- **"Undo"** reverts the last change Live Pilot made, with readback. Live's own Ctrl+Z also works.
- Saved device settings (**recipes**) live in `data/recipes/`. "Put my Drake vocal chain on the
  rap track" recalls one by name.
- If something is wrong before it can start (not signed in, remote script missing, no mic), a red
  **Before we start** card lists each thing with its fix and a **Check again** button.

### Settings

`%APPDATA%\LivePilot\config.json` (created by the installer):

| key | what it does |
|---|---|
| `name`, `artist_name` | what Studio calls you |
| `model`, `effort` | the Claude model (`claude-opus-5-5` by default) and effort (`low` is fastest) |
| `mic` | part of an input device's name, to pick a specific mic |
| `remote_script_dir` | where the LivePilot remote script is, if you installed it somewhere unusual |
| `telegram_script` | optional script that sends a question to your phone; leave blank |

Logs: `%LOCALAPPDATA%\LivePilot\logs\studio.log`. `python -m studio --check` prints the setup
checks; `python -m studio --version` prints the version.

### Update

```powershell
.\install.cmd -Update      # git copies only: git pull, then install again
```

From a zip: the zip unpacks to its own `LivePilot-<version>` folder, so unzipping it over the old
folder does not update anything. Unzip the new zip to a new folder and double-click `install.cmd`
there: your settings are kept and the desktop shortcut is rewritten to point at the new folder.
Then delete the old folder.

### Uninstall

```powershell
.\install.cmd -Uninstall   # removes the remote script from Live, the desktop shortcut, your settings, the logs and the remote script backups
```

Then delete the folder. Your Claude sign-in and the speech model cache are left alone.

## When something is off

| you see | do this |
|---|---|
| Header says **Live is not answering on port 9878** | Open Live with LivePilot enabled as a Control Surface (step 4). If Live just opened, wait for the set to load. |
| **Before we start** card | Follow the fix on each line, then press **Check again**. |
| **Could not start Claude** | `.\install.cmd -Login`. Check that your plan includes the model in `config.json`. |
| Installer says **Python 3.12 or 3.13 was not found** | Install 3.12 or 3.13 (step 1). Other Python versions can stay; the installer looks for them with `py -3.12` and `py -3.13`. |
| Installer says **No Ableton Live found** | Live is installed somewhere other than `C:\ProgramData\Ableton`. Create `%APPDATA%\LivePilot\config.json` containing `{"remote_script_dir": "D:/Ableton/Live 12 Suite/Resources/MIDI Remote Scripts/LivePilot"}` (your Live's folder, forward slashes, ending in `/LivePilot`), then run `install.cmd` again. |
| Window closes right after it opens | You ran `install.ps1` directly. Double-click `install.cmd` instead; it keeps the window open so you can read what happened. |
| Window never opens | Open http://127.0.0.1:8770 in a browser. The app uses Brave, Chrome or Edge as an app window. |
| It did not hear you | The header light turns green while it listens. Check the mic Windows uses by default, or set `mic` in the settings. |
| It stopped with a message box | The full error is in `%LOCALAPPDATA%\LivePilot\logs\studio.log`. |

One instance of the remote script serves one client at a time: two programs talking to port 9878
at the same moment drop one reply. Close other Live Pilot tools while Studio is open.

## How it works

```
mic -> Silero VAD + Parakeet (on your CPU) -> one warm Claude session (Agent SDK, your account)
    -> Live Pilot tools (dial, chain, audition, transport, undo, session, recipe, audio_to_midi,
       live_command) -> LivePilot remote script inside Ableton Live (TCP 127.0.0.1:9878)
    -> readback -> the window (aiohttp, 127.0.0.1:8770)
```

- `studio/` is the app: `ears.py` (listening), `brain.py` (the Claude session and its tools),
  `server.py` (the window), `health.py` (setup checks, logs, crash messages), `config.py` (settings).
- `livepilot_tools/workflows.py` holds the one-call workflows; `livepilot_tools/live_app.py`
  drives Live itself (save, open, restart, pop-ups) without touching your mouse.
- `ableton_remote_script/` is what runs inside Live: the LivePilot remote script by Pilot Studio
  (`LivePilot_base`, BSL-1.1) plus Live Pilot's TCP server and workflow handlers (`LivePilot`). `scripts/install_remote_script.py`
  assembles them into Live's MIDI Remote Scripts folder.
- The older MCP server (`run_mcp_server.py`, `ableton_bridge.py`, AbletonOSC on UDP 11000/11001)
  lets coding agents such as Claude Code drive Live from a chat. It is not needed for Studio.
  See `AGENT-CAPABILITIES.md`.

## For developers

```powershell
venv\Scripts\python.exe -m pytest tests -q          # tests
venv\Scripts\python.exe scripts\deploy_remote_handlers.py   # hot-reload handler edits into a running Live
venv\Scripts\python.exe scripts\make_release.py     # build dist/LivePilot-<version>.zip
venv\Scripts\python.exe studio\make_icon.py         # redraw the icon
```

The version is `studio/__init__.py`. Every tool call Studio makes is logged to
`data/telemetry/calls.jsonl`; in a git checkout, `scripts/ux_analyzer.py` turns a week of them into
`data/telemetry/ux_report.md`, the list of what made sessions stop. `constraints.txt` pins the
tested package versions; its header says how to refresh it.

## License

See [LICENSE.md](LICENSE.md). Free for your own use. The remote script that runs inside Live is
based on LivePilot by Pilot Studio and is under the Business Source License 1.1.
