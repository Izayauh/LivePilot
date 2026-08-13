# Vocal Template Recursive Capture Implementation Plan

## Goal

Make LivePilot able to inspect, save, and recreate the complete vocal template from the `Spy` session:

- every visible track and bus
- every top-level device
- every nested Audio Effect Rack chain
- every nested device inside those chains
- every readable device parameter, including Waves/plugin parameters
- routing, pan, volume, mute/solo/arm, sends, and return/parallel lanes

The end-user command should eventually be:

```text
make my captured vocal template
```

LivePilot should then create and label the vocal tracks, load the required racks/plugins, apply settings, route everything into the vocal bus, and verify readback.

## Current Finding

The Ableton set itself is not the blocker. The current LivePilot bridge is.

AbletonOSC currently exposes only top-level track devices through paths like:

- `/live/track/get/devices/name`
- `/live/device/get/parameters/name`
- `/live/device/get/parameter/value`

That works for normal track devices, but it treats an Audio Effect Rack such as `Lead vocal preset` or `Pro Vocal Processing SM7B` as one top-level device. It does not recurse into:

- rack chains
- nested devices inside chains
- nested racks inside nested chains
- rack return chains

The local `JarvisDeviceLoader` Remote Script already runs inside Ableton and has access to the Live API. It should become the visibility layer for recursive device inspection.

## Architecture

Add recursive inspection and template application in this order:

```text
Ableton Live
  -> JarvisDeviceLoader Remote Script on 11002
  -> ableton_controls/controller.py
  -> ableton_bridge.py
  -> livepilot_tools/vocal_template_tools.py
  -> scripts/capture_vocal_template.py
  -> scripts/apply_captured_vocal_template.py
```

Keep protocol wrappers thin. The reusable logic should live in `livepilot_tools/`.

## Phase 1: Expose Recursive Device Trees

### Remote Script Endpoints

Add these OSC endpoints to `ableton_remote_script/JarvisDeviceLoader/__init__.py`:

- `/jarvis/device/tree`
  - Args: `track_index`
  - Returns: JSON string describing all devices on that track recursively.

- `/jarvis/device/tree_all`
  - Args: none
  - Returns: paged or compressed JSON for all tracks.
  - Use cautiously because UDP packet size can be a problem.

- `/jarvis/device/params_by_path`
  - Args: `track_index`, `device_path_json`
  - Returns: full parameter names, raw values, min, max, default if available, and display string if available.

### Device Path Format

Use stable nested paths, not only flat indices:

```json
{
  "track_index": 14,
  "device_path": [
    {"kind": "track_device", "index": 0, "name": "Lead vocal preset"},
    {"kind": "chain", "index": 0, "name": "Main"},
    {"kind": "chain_device", "index": 2, "name": "CLA-76 Mono"}
  ]
}
```

For top-level devices:

```json
{
  "track_index": 3,
  "device_path": [
    {"kind": "track_device", "index": 0, "name": "Glue Compressor"}
  ]
}
```

### Recursive Traversal Rules

In the Remote Script:

1. Start with `song.tracks[track_index].devices`.
2. For each device, capture:
   - name
   - class name
   - type
   - is enabled
   - parameter list
   - `can_have_chains`
   - `can_show_chains`
3. If the device has `chains`, recurse into each chain:
   - chain name
   - chain mixer data if exposed
   - chain devices
4. If the device has `return_chains`, recurse into those too.
5. Use a max depth guard, probably `5`, to prevent accidental loops.
6. Return errors per device, not as a whole-capture failure.

### Parameter Capture Rules

For each `Live.DeviceParameter`, capture:

- index
- name
- value
- min
- max
- is_enabled if exposed
- display value if exposed as `str_for_value` or equivalent

For third-party plugins, store raw values even if display strings are unavailable. Raw values are still useful for restoring the setting.

## Phase 2: Add Python Bridge Methods

Update `ableton_controls/controller.py` with:

- `get_device_tree(track_index)`
- `get_all_device_trees(track_indices=None)`
- `get_device_params_by_path(track_index, device_path)`

Update `ableton_bridge.py` with matching functions:

- `get_device_tree`
- `get_all_device_trees`
- `get_device_params_by_path`

The bridge response should be JSON, not a huge positional OSC argument list. The remote script can send JSON as a single string argument.

## Phase 3: Capture The Current Vocal Template

Create `livepilot_tools/vocal_template_tools.py` with deterministic functions:

- `identify_vocal_template_tracks(controller)`
- `capture_track_mixer_state(controller, track_index)`
- `capture_track_device_tree(controller, track_index)`
- `capture_vocal_template(controller, template_id, track_indices=None)`
- `validate_captured_template(template)`

Create `scripts/capture_vocal_template.py`:

```powershell
python scripts/capture_vocal_template.py --template-id spy_manual_vocal_2026_05_22 --auto-detect
```

Expected output:

```text
templates/captured_vocal_templates/spy_manual_vocal_2026_05_22.json
```

The captured JSON should include:

- template metadata
- Ableton set track map
- track creation order
- track names and roles
- track volume/pan/mute/solo/arm
- output routing
- send levels
- top-level devices
- nested rack chains
- nested devices
- parameters for every device
- unsupported or unreadable fields
- confidence and warnings

## Phase 4: Build The Recreate/Apply Path

Create `scripts/apply_captured_vocal_template.py`:

```powershell
python scripts/apply_captured_vocal_template.py --template spy_manual_vocal_2026_05_22
```

Application order:

1. Create missing tracks:
   - `VOCAL BUS`
   - `LEAD VOCAL`
   - `LEAD DOUBLE`
   - `STACK L`
   - `STACK R`
   - `HIGHLIGHTS / ADLIBS`
   - `VOCAL SPACE PRINT`
2. Set track names, colors, volume, pan, and mute/arm defaults.
3. Load top-level devices and racks.
4. If a rack preset is loadable as a browser item, load the rack as one device.
5. If individual nested plugins are loadable, rebuild the rack structure only if Live API exposes safe rack creation and chain insertion.
6. Apply parameters by name/path.
7. Route all vocal sources to `VOCAL BUS`.
8. Apply send levels.
9. Verify:
   - track exists
   - output routing readback matches
   - device tree matches expected names
   - critical parameters match within tolerance

Important: if rack creation/chain insertion is not safe through the Live API, the first production version should load saved `.adg` racks as whole devices and apply macro/top-level parameters. That is safer than trying to reconstruct racks device-by-device.

## Phase 5: Template Command Alias

Add a friendly top-level command path:

```text
make my captured vocal template
```

Map that to:

```powershell
python scripts/apply_captured_vocal_template.py --template spy_manual_vocal_2026_05_22
```

Possible code locations:

- `templates/template_manager.py`: register metadata for the captured vocal template.
- `livepilot_tools/ableton_tools.py`: expose reusable apply function.
- `mcp_server/server.py`: one-line wrapper if this needs MCP exposure.

## Data Shape

Use a versioned JSON artifact:

```json
{
  "schema_version": "captured_vocal_template.v1",
  "template_id": "spy_manual_vocal_2026_05_22",
  "created_from": {
    "ableton_set_name": null,
    "date": "2026-05-22",
    "notes": "Manual vocal mix over Spy beat"
  },
  "tracks": [
    {
      "role": "lead",
      "name": "LEAD VOCAL",
      "source_track_index": 13,
      "type": "audio",
      "volume": 0.85,
      "pan": 0.0,
      "output": "VOCAL BUS",
      "sends": [],
      "devices": []
    }
  ],
  "warnings": []
}
```

## Tests

Add focused fake-controller/unit tests before live smoke tests:

- `tests/test_recursive_device_capture.py`
  - captures nested racks
  - captures nested rack inside nested rack
  - preserves device paths
  - tolerates unreadable parameters
  - validates schema output

- `tests/test_captured_vocal_template_apply.py`
  - creates missing template tracks
  - routes source tracks to vocal bus
  - loads saved rack device names in order
  - applies parameters by path/name
  - reports missing plugins without corrupting the set

Run:

```powershell
python -m unittest tests.test_recursive_device_capture -v
python -m unittest tests.test_captured_vocal_template_apply -v
python -m py_compile ableton_remote_script\JarvisDeviceLoader\__init__.py ableton_controls\controller.py ableton_bridge.py livepilot_tools\vocal_template_tools.py
```

Then run one live read-only smoke:

```powershell
python ableton_bridge.py get_device_tree "{\"track_index\":13}"
```

And one capture smoke:

```powershell
python scripts/capture_vocal_template.py --template-id spy_manual_vocal_2026_05_22 --track 13 --track 14 --track 15 --track 16 --track 17 --track 18 --track 3
```

## Risks And Guardrails

- UDP packet size: large captures should be paged, chunked, or written to a temp file by the Remote Script and returned as a path.
- Plugin availability: captured Waves/plugin names must be resolved through `config/owned_plugins.json` and browser search before applying.
- Parameter instability: third-party plugin parameter order can differ by mono/stereo version. Store plugin name, class name, and parameter names, not only indices.
- Rack reconstruction: creating nested racks and chains from scratch may be unsafe or unsupported. Prefer loading saved `.adg` rack presets as the first reliable implementation.
- User worktree safety: applying the template should never delete existing tracks unless explicitly requested.

## Immediate Next Step

Implement `/jarvis/device/tree` in `JarvisDeviceLoader`, then expose it through `ableton_bridge.py`.

Once `get_device_tree` can show the internals of `Lead vocal preset`, rerun the capture on:

- track 13: `14-Audio`
- tracks 14-17: `Backing Vocals`
- track 18: `19-Audio`
- track 3: `4-Group`

Then replace the provisional capture in `docs/vocal-chain-capture-2026-05-22.md` with the full nested plugin map and create the first `spy_manual_vocal_2026_05_22.json` captured template artifact.
