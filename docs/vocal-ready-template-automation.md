# Vocal-Ready Template Automation

This is the standing target for recurring Codex improvement runs.

## Mission

Keep improving the `vocal_ready_beat` Ableton template so LivePilot can quickly create beats and instrumentals with an intentional vocal pocket.

Each run should make one concrete improvement to one of these areas:

- Track layout and naming
- Bus or placeholder routing
- Stock-device fallback reliability
- Vocal-pocket EQ and gain-staging defaults
- Return effects for vocal space
- Parameter profiles for every loaded device category
- Template metadata that helps future agents use the session
- Tests or verification around template behavior

## Current Runnable Pass

Run this from the LivePilot repo:

```powershell
python scripts\improve_vocal_ready_template.py
```

If Ableton is reachable but you want to avoid loading any new devices (routing/parameters-only pass):

```powershell
python scripts\improve_vocal_ready_template.py --max-device-loads 0
```

Use this for planning without touching Ableton:

```powershell
python scripts\improve_vocal_ready_template.py --dry-run
```

The script is idempotent. It creates missing named tracks, applies conservative color/volume defaults, removes blocked Pro-Q devices if they slipped in, loads starter devices with stock-oriented fallbacks, routes source tracks into bus tracks through AbletonOSC, ensures enough return slots exist for planned sends, sets send levels, applies device-parameter profiles, and writes:

- `templates/vocal_ready_template_state.json`
- `docs/vocal-ready-template-changelog.md`

Parameter profiles are applied with conservative per-run caps (devices, writes, and a time budget) so the
automation can't stall a recurring improvement loop. Re-running continues applying profiles.

## Improvement Loop

On every recurring Codex run:

1. Inspect `templates/template_manager.py`, this document, the changelog, and the state JSON.
2. Inspect Ableton reachability with `python ableton_bridge.py get_track_list "{}"`.
3. Pick exactly one high-value improvement.
4. Prefer deterministic reusable code over one-off session edits.
5. Treat FabFilter Pro-Q / Pro-Q 3 / Pro-Q 4 as blocked for this template because the license is not usable on Isaiah's system. Prefer `EQ Eight`; if a second EQ option is needed, try `reaeq-standalone`, `Q10 Paragraphic EQ Stereo`, or `F6-RTA Stereo` only after verifying they load.
6. Do not request `Wavetable` or `Operator` through the current plugin resolver for this template; on this system they resolve fuzzily to unrelated devices. Use `Drift` for stock synth placeholders until resolver exact-match behavior is improved.
7. Run focused tests or compile checks.
8. Run `python scripts\improve_vocal_ready_template.py` if Ableton is reachable.
9. Update the changelog with what changed and the next best improvement.

## Vocal Pocket Defaults

- Keep kick and sub ownership clear below 120 Hz.
- Keep chords, pads, reverbs, and delays from building up around 200-500 Hz.
- Leave room for lead-vocal intelligibility around 1-4 kHz.
- Control hats, leads, and ambience around 5-10 kHz so the vocal air band is not crowded.
- Filter every reverb and delay return.
- Keep the `VOCAL - Lead Placeholder` track available as the future sidechain/key source.

## Routing Defaults

- Drum source tracks route to `DRUM BUS`.
- `BASS - Sub 808` routes to `BASS BUS`.
- Music source tracks route to `MUSIC BUS - Vocal Pocket`.
- Vocal placeholder tracks route to `VOCAL BUS`.
- Main buses route to `Master`.
- `FX - Transitions Texture` routes to `MUSIC BUS - Vocal Pocket` so risers, impacts, and ear-candy transitions stay under the instrumental vocal-pocket carve instead of bypassing it.
- The script sets conservative sends for snare, music, and vocal placeholder tracks so ambience exists without washing out the lead-vocal center. Send slot 0 is reserved for `SEND - Short Plate`; send slot 1 is reserved for `SEND - Slap Delay`.
- `MUSIC - Chords` gets a very low default send to `SEND - Long Hall`, giving chord beds filtered depth while keeping the dry harmonic body routed through `MUSIC BUS - Vocal Pocket`.
- The drum bus also gets a low default send to `SEND - Parallel Drum Comp` so drum density can be blended without pushing dry drum levels into the vocal pocket. Because the current bridge cannot read or name return tracks directly, the script uses send-slot probing to create enough return slots before writing this send.
- `FX - Transitions Texture` gets a low default send to `SEND - Throw Delay` so risers, impacts, and ear-candy throws have filtered space without crowding the lead vocal center.
- `SEND - Long Hall` has its own longer reverb parameter profile, so chord-bed ambience keeps a filtered tail without falling back to the generic short-reverb decay.
- `SEND - Throw Delay` has its own delay parameter profile, so transition throws start with controlled synced feedback and a modest wet level instead of generic device defaults.
- `SEND - Throw Delay` delay verification now reads display strings for timing, sync, feedback, and wet controls when the bridge exposes that return track, so future live runs can prove musical delay values instead of only raw numbers.

## Parameter Defaults

- Every loaded device receives at least `Device On = 1.0` when exposed.
- `EQ Eight` instances receive track-specific pocket curves.
- Compressors, glue compression, saturators, gates, multiband dynamics, chorus, reverb, delay, and Utility devices receive role-aware starting values.
- These are starting points, not fake mastering claims. Future runs should refine them with readback, rendered audio, and listening checks where available.
