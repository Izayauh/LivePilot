# artist-os Integration Note

## Canonical contract source

The canonical cross-repo contract note lives in the `artist-os` repo:

- `C:\Users\isaia\Documents\Business\Zay_Music\docs\ableton-integration-contract.md`

This file is the short Jarvis-side companion note.

## Integration stance

`JarvisAbleton` should act as the deterministic Ableton executor for `artist-os` session outputs.

It should **not** own the upstream songwriting/session pipeline.

## Recommended boundary

- `artist-os` writes a request JSON in its timestamped session folder
- `artist-os` invokes a Windows-side Jarvis adapter CLI
- `JarvisAbleton` reads the request, performs deterministic Ableton actions, and writes a result JSON
- `artist-os` records the result in its own manifest/history files

## Recommended transport

Use a Windows-side subprocess CLI, not HTTP and not direct cross-repo imports.

Example shape:

```bat
C:\Users\isaia\Documents\JarvisAbleton\venv\Scripts\python.exe C:\Users\isaia\Documents\JarvisAbleton\jarvis_artist_os_adapter.py --request C:\Users\isaia\Documents\Business\Zay_Music\data\sessions\<session-id>\ableton_handoff.request.json --response C:\Users\isaia\Documents\Business\Zay_Music\data\sessions\<session-id>\ableton_handoff.result.json
```

## Existing Jarvis surfaces to build on

### 1. `ableton_bridge.py`

Use this for boring JSON CLI control of:
- track lookup
- track creation
- track naming
- tempo
- arm state
- device inspection
- plugin loading
- parameter setting
- OSC diagnostics

### 2. `pipeline/executor.py`

Use this when a request includes a small starter chain that needs deterministic:
- load
- parameter set
- verify
- report

## Smallest reliable v1 actions

1. ensure/create target MIDI track
2. set tempo and arm state
3. apply a tiny stock-safe starter chain
4. verify and report

## Explicit v1 non-goal

Do not promise true MIDI file import into Ableton clips/tracks until Jarvis has a dedicated deterministic import surface.

MIDI file paths can still be carried in the request as reference artifacts.

## Recommended first implementation

Add:
- `jarvis_artist_os_adapter.py`

First supported action:
- `prepare-writing-session`

That action should:
1. run OSC preflight
2. ensure/create target track
3. set tempo
4. arm the track if requested
5. apply starter chain
6. verify state
7. write result JSON
