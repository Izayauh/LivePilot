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

**3. Reach for the one-call workflows first.** They cover what most sessions do
(measured 2026-10-13: knob dialing, plugin chains, and auditioning were ~70% of
982 recorded calls), take names instead of indices, read every change back, and
are undoable:

| Task | Call |
|---|---|
| What is in the set | `session()` |
| Set or read a knob/fader | `dial(track, param, to="-6 dB" \| by="+2 dB", device="EQ Eight")` (omit device for volume / pan / send A) |
| Show / add / remove a device | `chain(track)` · `chain(track, add="Compressor")` · `chain(track, remove="Compressor")` |
| Save a track's chain as a rack preset with macros | `rack(als, "Piano Rig", out=r"...\User Library\Presets\Instruments\Instrument Rack\Piano Rig.adg", macros=[{name, device, param, min, max, value}])` (reads the saved .als, so save first; MIDI track = Instrument Rack, else Audio Effect Rack; `param` is Live's name or XML path, `"Device On"` maps a plugin's power; never overwrites unless `overwrite=True`). Live lists it after a rescan or restart, then `live_command("load_browser_item", {track_index, uri: browser_uri})`. No nested racks, no plugin-parameter macros yet. Code: `livepilot_tools/rack_builder.py` |
| Listen to part of the song | `audition("Rap", at=33)` · `audition(["Rap","A-Reverb"], at="Hook")` · `audition(stop=True)` restores solos |
| Take it back | `undo()` / `undo(3)` (reverts dial/chain changes with readback) |
| Render a passage to a WAV | `bounce(at=1, bars=8, name="pad loop")` (Audient loop-back; returns path, peak/RMS dBFS, `silent`). Clears Back to Arrangement first, and re-records once on a silent capture or a dropout (20 ms of digital silence cut abruptly into loud sound; a dry soloed kick decaying into silence is not one); `retried` says why, `success: false` means do not send it). Never resample into a track: Live locks its own recordings |
| Anything else Live can do (~200 handlers: clips, notes, automation, browser, scenes) | `list_commands("automation")` gives names, docstrings and param keys; `live_command(type, params)` runs one over TCP 9878 (raw: no name resolution, no undo) |
| Cost and reliability | `usage()` · cap a long task with `set_budget(max_calls=30)` |
| Save / open / quit / restart Live | `live("save")` · `live("save", path=r"...\Projects Current\2026\Name.als")` (Save As; the only way to save an Untitled set; never overwrites; outside a project folder Live writes `Name Project\Name.als`, the reply's `path` says where) · `live("open")` (last set, or `path=`) · `live("close")` · `live("restart")` · `live("status")` (`unsaved` = title star) |
| A Live pop-up is blocking | `live("dialogs")` reads it; known ones are answered by `data/live_dialog_rules.json`. Unknown: `live("press", button="Yes")`, then `live("add_rule", rule={name, match:[phrases], press, why})` so no agent asks Isaiah again |

Never ask Isaiah to press Ctrl+S, open or close Ableton, or click OK on a pop-up: `live()` does
all of it without the mouse or keyboard focus (menu commands by id, native buttons by handle,
Live-drawn dialogs read by Windows OCR). Every agent turn ends with an automatic save
(Stop hook `scripts/live_autosave.py`). An Untitled set is never auto-saved: `live("save")` with no
`path` refuses it, and refuses while a Save As dialog is open, because each turn's autosave used to stack
another dialog (27 on 2026-10-20) and pressing Save on one writes nothing. Use `live("save", path=...)`. When another tool fails, its reply carries
`live_dialog` if a pop-up was the cause. Code: `livepilot_tools/live_app.py`.

Do not hand-roll get_range / set / get_value_string loops for display values;
`dial` does that search inside Live without writing anything until the final value.

For anything else, `list_livepilot_tools()` returns just the function names
(small); `list_livepilot_tools(function="name")` returns one schema. It is
self-maintaining, so this file can never be the reason you miss a feature.

---

## Intent index

**"Is it armed / muted / soloed? What's the state?"**
`get_track_arm` · `get_armed_tracks` · `get_track_mute` · `get_track_solo` ·
`get_track_status` (combined mute/solo/arm in one call) · `get_mixer_snapshot` (atomic composite mixer snapshot of song transport & all tracks in one call) · `get_track_volume` ·
`get_track_pan` · `get_track_send`

**"How loud is it? Is anything hitting the ceiling?"**
`get_track_meters` (one track via `track_index`, or all; `include_stereo` adds
left/right) · `get_master_meters` (level/left/right). Values are Live's 0.0-1.0
meter scale, not dBFS, and are live peaks, so read them while audio is playing.
These go through the LivePilot remote script on TCP 127.0.0.1:9878, not OSC.

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

**"Work on a return track (A-Reverb, B-Delay) or the master"** (added 2026-09-26)
Pass `track_kind: "return"` (track_index 0 = A) or `track_kind: "master"` to
`get_track_devices` · `get_device_parameters` · `set_device_parameter` ·
`set_device_parameter_by_name` · `set_device_parameters_by_name` · `add_plugin_to_track`.
Default is `"track"`. Return/master reads and writes go through TCP 9878, and
**writes take the raw Live value** inside the min..max that `get_device_parameters`
returns (no Hz/dB/% guessing; out-of-range is refused, never clamped).
`get_mixer_snapshot include_returns: true` lists return names, volume, pan.
`dial("return A", "Time", to="310 ms", device="Delay")` and `dial("master", ...)` cover returns and the master in one call.
Track specs in `dial`, `chain`, `rack`, `recipe`, `audio_to_midi`: a name, or the number he says as a string (`"4"` is the 4th track, `"4-Audio"` also works); an integer is the snapshot index; a miss names the three closest tracks.

**"Put a plugin on / recall a chain"**
`find_plugin` · `get_available_plugins` · `add_plugin_to_track` (`position`: chain index, -1 = end; the result's `devices_after` shows where it landed) ·
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
Before any creative move (writing notes, picking sounds), read `get_creative_context()["taste_profile"]`:
Isaiah's music taste lines, each earned by a rated round (wiki `Music Taste Profile.md`). Taste rounds:
`scripts/taste/` (ear_one, index_splice, gen_round1 + render_round, selftest_drums), data in `data/taste/`.

**"Make drums for this loop" (never pick drums by file name)**
`python scripts/taste/drums_from_loop.py <loop.wav> [--bpm] [--send]` hears the loop (`loop_ear.py`: tempo,
key, its bass line, brightness, texture, accents, swing, owned mids, hat gap), picks his one-shots by how they
sound (`drum_index.py`, cached features in `data/taste/drum_features.json`), tunes kick and 808 to the loop,
shapes and grooves them, and renders 3 ranked 4-bar takes with the loop under them (`--send` = his phone).
After he picks: `--pick N --song 5-20,21-36 --stems-out <dir> --prefix X` writes <=16-bar stems for warped
audio tracks (this Live cannot load samples into Simpler). A loop file in a set: read its path from the .als.

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
- **Meter reading resolved** via `get_track_meters` / `get_master_meters` (retired 2026-09-26 gap).
- **Return/master device access resolved** via `track_kind` (retired 2026-09-26 gap). **`add_plugin_to_track` `position` now honoured** (2026-09-26). Both load features need the JarvisDeviceLoader control surface reloaded once; until then the load is refused with a reload message instead of landing on the wrong track.

- **Locators: `lp_marker(time, delete)` places or deletes one, but cannot name it** (2026-10-20). Live's API rejects `CuePoint.name` ("can't set attribute"), a new locator lands where the playhead was on the previous tick (so `lp_marker` returns `done: false` once; call it again), and a stopped transport snaps it to the bar. Label sections with named clips on an empty MIDI lane instead (`create_clip` + `set_clip_name` + `place_in_arrangement`).
- **No sample-into-Simpler on this Live** (2026-10-20): `replace_sample_native` needs 12.4+, and Live's browser does not index the Splice folder, so one-shots go in as rendered audio stems, not playable MIDI kits. A 40-bar unwarped file started 2 s late and was cut at bar 25 (unwarped markers are in seconds). Fixed in JarvisDeviceLoader 2026-10-20: unwarped placement sets start 0 and end to the file length, checks `end_time` against the file, and removes and refuses a mismatch. Verified live after a restart: a 40-bar unwarped file placed at bar 5 ends at bar 45.
- **`start_playback` ignores `jump_to_time`** and plays from the start marker; use `continue_playback` after a jump (meter reads were of the intro until this was found).
- **No arrangement-clip delete and no arrangement-clip note reader** (2026-10-14). `place_in_arrangement(clear_existing=1)` is the only way to clear a track's arrangement clips.
- **`place_in_arrangement` on MIDI clips** threw a warping error after already placing the clip, so agents retried into duplicates. Fixed in JarvisDeviceLoader 2026-10-14; takes effect after the next Live restart.

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

**"A bit more / less of a device control, without a number"** (added 2026-09-18)
`nudge_device_parameter(track_index, device_index, param_name, fraction)` moves a
parameter by a fraction of its raw range (0.1 = a notch, 1.0 = all the way) and
reads back raw + display string. No unit conversion, so it is safe on dB, Hz,
ms, and percent alike. `get_device_parameter_range` returns min/max/current/
display for one parameter. `jev_command` uses both for "a little drier",
"longer tail", "tighten the attack", "crank the ratio all the way".
