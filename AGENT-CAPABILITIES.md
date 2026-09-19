# Live Pilot — what you can do, indexed by intent

**Read this before touching Ableton. It is the answer to "can I do X?".**

Written 2026-08-27 after a session took a screenshot and started clicking around
the Ableton UI to find out whether a track was armed. `get_track_arm(track_index)`
and `get_armed_tracks()` both exist. That is the failure this file prevents.

---

## THE THREE RULES

**1. Never look when you can ask.** If you want to know the state of anything in
Ableton, there is almost certainly a function that returns it. Screenshots are for
things genuinely not exposed over OSC, and that list is short. A screenshot costs
seconds, is ambiguous, and cannot be diffed. A function call returns a value.

**2. Never click. Ever.** Do not drive the Ableton UI with mouse coordinates.
Clicking is slower, silently order-dependent, unverifiable, and breaks the moment
a window moves. If a function exists, call it. If no function exists, say so and
propose adding one — do not fall back to the mouse.

**3. Enumerate the surface at the start of every session.** One call:

```
mcp__live-pilot__list_livepilot_tools     # names + full arg schemas
mcp__plugin_jarvis-ableton_ableton__...   # the same bridge, per-tool MCP surface
```

or `describe_functions` for the schema dump. **This is self-maintaining — new
Live Pilot features appear automatically, so this file can never be the reason
you miss one.** Do this before planning, not after getting stuck.

---

## Intent index

**"Is it armed / muted / soloed? What's the state?"**
`get_track_arm` · `get_armed_tracks` · `get_track_mute` · `get_track_solo` ·
`get_track_status` (combined mute/solo/arm in one call) · `get_mixer_snapshot` (atomic composite mixer snapshot of song transport & all tracks in one call) · `get_track_volume` ·
`get_track_pan` · `get_track_send`

**"What is the session doing right now?"** — this replaces a screenshot
`get_song_status` → is_playing, record_mode, tempo, current time, arrangement
length in beats AND seconds, loop state, time signature. One call, whole transport.
`get_track_list` · `find_track_by_name` (fuzzy) · `get_cue_points` (arrangement
locators) · `get_arrangement_clips` (start/end + audio file paths per track)

**"What's on this track?"**
`get_track_devices` · `get_num_devices` · `get_device_tree` (recursive) ·
`get_all_device_trees` (every track at once) · `get_device_name` ·
`get_device_class_name`

**"What does this device's parameters look like, and can I change them?"**
`get_device_parameters` (names) · `get_device_parameter_value` ·
`get_device_parameter_value_string` (display string, e.g. "-6.0 dB") ·
`get_device_params_by_path` (nested devices, racks)
Set: `set_device_parameter` · `set_device_parameter_by_name` ·
**`set_device_parameters_by_name`** (many at once, `{name: value}`) ·
`set_device_enabled` (bypass) · `delete_device`

**"Put a plugin on / recall a chain"**
`find_plugin` · `get_available_plugins` · `add_plugin_to_track` ·
`add_utility_device` (append Utility + set gain in one)
Recipes: `list_plugin_recipes` · `save_plugin_recipe` · `apply_plugin_recipe`
— snapshot a dialled-in device and recall it later. Use these instead of
re-dialling by hand.

**"Change a level / pan / send"** — all take `verify: true` to read back
`set_track_volume` (0.0-1.0) · `set_track_pan` (-1.0-1.0) · `set_track_send`
· `mute_track` · `solo_track` · `arm_track`

**"Transport / recording"**
`play` · `stop` · `continue_playback` · `set_position` (beats) · `set_tempo` (read back via `get_song_status` tempo field) ·
`toggle_metronome` · `set_loop` / `set_loop_start` / `set_loop_length` ·
`start_recording` · `stop_recording` · `set_record_mode` (arrangement) ·
`set_session_record` · **`back_to_arranger`** (the orange Back to Arrangement
button) · `fire_clip` · `fire_scene` · `stop_clip`

**"Track management"**
`create_audio_track` · `create_midi_track` · `create_return_track` ·
`duplicate_track` · `delete_track` · `delete_return_track` · `set_track_name` ·
`set_track_color`

**"Routing and monitoring"** — needed for clean self-capture
`get_track_routing` (options + current + monitoring state) ·
**`set_track_input_routing`** (default `Resampling`, for bit-clean self-capture) ·
`set_track_output_routing` · `set_track_monitoring` (0=In, 1=Auto, 2=Off)

**"Audio files into clips"**
`set_clip_path` (drop a local file into a Session slot) · `get_clip_audio_path` ·
`set_clip_detune` (cents)

**"Create clips and write/read MIDI notes"** (Added 2026-09-12)
`create_clip` (instantiate clip in slot with beat length) · `delete_clip` ·
`add_clip_notes` (batch write notes: pitch, start, duration, velocity, mute) ·
`get_clip_notes` (read back all note events from clip) ·
`remove_clip_notes` (strip notes within specified pitch/time window)

**"What's in this MIDI clip?"**
`get_clip_notes` (deterministic note events) · `analyze_clip_context` · `analyze_rhythm_context`

**"Plan / context"**
`get_creative_context` · `get_project_intent` · `set_project_intent` ·
`plan_arrangement_move` (produces a reviewable plan, executes nothing)

**"Is the bridge even alive?"**
`diag_osc` — run this first if anything times out.
`scripts/check_port_11001.py` — verify exclusive response port ownership before long sessions.

**Batch-safe variants** (`j_` prefix, separate jarvis port)
`j_play` · `j_stop` · `j_set_position` · `j_arm` · `j_create_audio_track` ·
`j_delete_track` · `j_track_names`

---

## Verification

Setters accept `verify: true`, which reads the value back from Ableton and
confirms it took. **Use it on anything that matters.** This is the property that
makes an automated mix loop possible at all — the loop can know its change landed
rather than assuming.

---

## Known gaps (say these out loud instead of clicking)

- **MIDI note writing is now VERIFIED & LIVE** via `add_clip_notes`, `create_clip`, `get_clip_notes` (retired 2026-09-12 gap).
- **Mixer screenshot equivalent resolved** via `get_mixer_snapshot` (atomic composite of transport + all track faders, pans, mutes, solos, and arms; retired 2026-09-14 gap).

If a genuine gap blocks the work: **propose the function**, and add it to the
Live Pilot bridge. Do not route around it with the mouse. Isaiah's standing
instruction, 2026-08-27: *"it's way faster for you to do it programmatically
because you can just look at it and check it and write it in code."*

---

## Maintenance

Do **not** hand-maintain the function list above as the source of truth — it will
rot. It is a fast intent index. The authority is `list_livepilot_tools` /
`describe_functions`, which reflect the live bridge. When a new Live Pilot feature
ships, it appears there automatically; add it here only to keep the intent index
useful. Surface count at time of writing: **94 functions**.

**"Fast transport / mixer command in plain words"** (added 2026-09-18)
`jev_command(command, execute=False)` → TypeSafe Jev turns "mute the vocals and
set the tempo to 128" into typed bridge calls in ~0.5 s with a confidence per
clause. `execute=True` runs the ready steps with `verify: true`. Clauses below
the confidence gate come back as `escalate` and never run; do those the normal
way. Mixer and transport only, never creative or device-parameter work. Key in
`.env` as `TYPESAFE_API_KEY`. Code: `livepilot_tools/jev_dispatch.py`.
