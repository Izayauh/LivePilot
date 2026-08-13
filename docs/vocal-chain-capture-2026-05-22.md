# Vocal Chain Capture - 2026-05-22

## Source Session

Song built around the YouTube beat track:

- `1-[FREE] J Cole x JID x Dreamville Type Beat "Spy"` at track 1, volume `0.85`, routed to `Master`.
- Duplicate beat/print track at track 20 is routed to `Master`.

The vocal sound that felt strongest is centered around a simple visible topology:

1. Most vocal audio tracks use an Audio Effect Rack/preset named `Pro Vocal Processing SM7B` or `Lead vocal preset`.
2. Core vocal tracks route into track 4, named `4-Group`.
3. `4-Group` has a `Glue Compressor` and routes to `Master`.
4. Backing vocal tracks add per-track width with panning and a visible `Longest Ping Pong` delay plus `EQ Eight`.
5. Track 19 is a parallel/space-style vocal track with Waves reverbs, routed into `4-Group`.

AbletonOSC can read the visible device/rack names and exposed macro values. It does not expose the nested devices inside `Pro Vocal Processing SM7B` or `Lead vocal preset` from this capture, so those rack internals still need a manual rack-unfold pass or a saved rack preset inspection.

## Observed Routing

| Track | Name | Devices | Volume | Pan | Output |
| --- | --- | --- | ---: | ---: | --- |
| 3 | `3-Audio` | `Pro Vocal Processing SM7B` | `0.73` | `0.00` | `Master` |
| 4 | `4-Group` | `Glue Compressor` | `0.902` | `0.00` | `Master` |
| 5 | `5-Audio` | `Pro Vocal Processing SM7B` | `0.85` | `0.00` | `4-Group` |
| 6 | `6-Audio` | `Pro Vocal Processing SM7B` | `0.85` | `0.00` | `4-Group` |
| 7 | `7-Audio` | `Pro Vocal Processing SM7B` | `0.85` | `0.00` | `4-Group` |
| 8 | `8-Audio` | `Pro Vocal Processing SM7B` | `0.85` | `1.00` | `4-Group` |
| 9 | `9-Audio` | `Pro Vocal Processing SM7B` | `0.85` | `-1.00` | `4-Group` |
| 10 | `Highlights` | `Pro Vocal Processing SM7B` | `0.85` | `0.00` | `4-Group` |
| 11 | `Highlights` | `Pro Vocal Processing SM7B` | `0.85` | `0.00` | `4-Group` |
| 12 | `Highlights` | `Pro Vocal Processing SM7B` | `0.85` | `0.00` | `4-Group` |
| 13 | `Highlights` | `Pro Vocal Processing SM7B` | `0.85` | `0.00` | `4-Group` |
| 14 | `14-Audio` | `Lead vocal preset` | `0.85` | `0.00` | `4-Group` |
| 15 | `Backing Vocals` | `Lead vocal preset`, `Longest Ping Pong`, `EQ Eight` | `0.76` | `1.00` | `4-Group` |
| 16 | `Backing Vocals` | `Lead vocal preset`, `Longest Ping Pong`, `EQ Eight` | `0.76` | `0.61` | `4-Group` |
| 17 | `Backing Vocals` | `Lead vocal preset`, `Longest Ping Pong`, `EQ Eight` | `0.76` | `-0.565` | `4-Group` |
| 18 | `Backing Vocals` | `Lead vocal preset`, `Longest Ping Pong`, `EQ Eight` | `0.76` | `-1.00` | `4-Group` |
| 19 | `19-Audio` | `MannyM Reverb Mono/Stereo`, `H-Reverb long Stereo` | `0.845` | `0.00` | `4-Group` |

Send usage is mostly zero. One `Highlights` track had send 0 at about `0.575`; the rest of the inspected vocal tracks had sends 0 and 1 at `0.0`. This mix is therefore mostly track/bus/parallel-track based, not return-send based.

## Readable Device Settings

### Vocal Group: `Glue Compressor`

Track 4, device 0:

- `Threshold`: `-23.8095`
- `Range`: `70.0`
- `Makeup`: `1.5873`
- `Attack`: `2.0`
- `Ratio`: `1.0`
- `Release`: `2.0`
- `Dry/Wet`: `1.0`
- `Peak Clip In`: `0.0`

Functionally, this is bus glue and level density after the individual vocal racks. It is part of why the stacks feel like one vocal object rather than isolated tracks.

### Lead/SM7B Vocal Racks

`Pro Vocal Processing SM7B` and `Lead vocal preset` expose 16 generic macros plus `Chain Selector`, but all readable macro values are `0.0` with `Device On` at `1.0`.

This means the preset/rack itself is doing the heavy work internally, but AbletonOSC is only seeing the top-level rack shell. The default template should preserve this rack as the main insert until its internal chain is unfolded and documented.

### Backing Vocal Delay: `Longest Ping Pong`

Track 15, device 1:

- `Device On`: `1.0`
- `Delay Mode`: `1.0`
- `Link`: `1.0`
- `Ping Pong`: `0.0`
- `L Sync`: `0.0`
- `R Sync`: `1.0`
- `L Time`: `0.4127`
- `R Time`: `0.5954`
- `L 16th`: `5.0`
- `R 16th`: `3.0`
- `Feedback`: `0.9048`
- `Filter On`: `1.0`
- `Filter Freq`: `0.8889`
- `Filter Width`: `0.4474`
- `Mod Freq`: `0.6388`
- `Dry/Wet`: `0.5238`

Functionally, this is not subtle send ambience. It is a printed/insert backing-vocal width and smear move. The high feedback and dry/wet make the backing vocals feel like a halo around the lead rather than a second dry performance.

### Backing Vocal EQ

Track 15, device 2:

- Band 1 on, type `1`, frequency `0.5679`, gain `0.0`, resonance `0.3802`
- Band 2 on, type `3`, frequency `0.3892`, gain `0.0`, resonance `0.3767`
- Band 3 on, type `3`, frequency `0.5984`, gain `0.0`, resonance `0.3767`
- Band 4 on, type `5`, frequency `0.8075`, gain `0.0`, resonance `0.3767`
- Bands 5-8 mostly off.

Functionally, this looks more like tonal framing than aggressive corrective EQ. The backing tracks are being positioned with pan, delay, and group compression more than heavy EQ carving.

### Parallel/Space Track: `19-Audio`

Track 19, routed into `4-Group`:

`MannyM Reverb Mono/Stereo`

- `Device On`: `1.0`
- `Input`: `0.5`
- `Reverb Amount`: `1.0`
- `Lows`: `0.7920`
- `Mids`: `0.4000`
- `Highs`: `0.6220`
- `Comp`: `0.0`
- `Phaser`: `0.0`
- `Distortion`: `0.0`
- `Dry/Wet`: `1.0`
- `Output`: `0.6167`

`H-Reverb long Stereo`

- `Device On`: `0.0`

Functionally, this is a dedicated reverb/space lane feeding the vocal group. That matters: the space is compressed/glued with the vocals instead of only floating on a master return.

## Why This Vocal Sit Works

- The lead and stacks are organized around one vocal group, so the vocal mass hits the master as a single controlled object.
- The main dry vocal processing is mostly inside a reusable rack, which keeps individual tracks consistent.
- Width is created with panned doubles and backing vocals, not by widening the lead.
- Backing vocals are quieter (`0.76`) than the main vocal tracks (`0.85`) and hard/semi-hard panned in pairs.
- Delay is inserted on backing vocals, which lets the backgrounds smear outward while the lead stays center-focused.
- The reverb lane is routed into the vocal group, so the ambience belongs to the vocal bus instead of sitting disconnected from it.
- The beat is static around `0.85`, while vocal bus level and group glue let the vocal sit forward without needing lots of return sends.

## Default Ableton Template Proposal

Create this as a reusable vocal template:

1. `VOCAL BUS`
   - Device 1: `Glue Compressor`
   - Output: `Master`
   - Starting level: around `0.90`

2. `LEAD VOCAL`
   - Device 1: `Lead vocal preset` or `Pro Vocal Processing SM7B`
   - Output: `VOCAL BUS`
   - Pan: `0`
   - Starting level: `0.85`

3. `LEAD DOUBLE`
   - Device 1: same vocal rack
   - Output: `VOCAL BUS`
   - Pan: `0`
   - Starting level: lower than lead, adjusted per song

4. `STACK L`
   - Device 1: same vocal rack
   - Device 2: `Longest Ping Pong`
   - Device 3: `EQ Eight`
   - Output: `VOCAL BUS`
   - Pan: `-0.60` to `-1.00`
   - Starting level: `0.76`

5. `STACK R`
   - Device 1: same vocal rack
   - Device 2: `Longest Ping Pong`
   - Device 3: `EQ Eight`
   - Output: `VOCAL BUS`
   - Pan: `0.60` to `1.00`
   - Starting level: `0.76`

6. `HIGHLIGHT / ADLIB`
   - Device 1: same vocal rack
   - Output: `VOCAL BUS`
   - Optional send/space amount per phrase
   - Starting level: `0.85`, then automate down if it competes with lead

7. `VOCAL SPACE PRINT`
   - Device 1: `MannyM Reverb Mono/Stereo`
   - Device 2: optional `H-Reverb long Stereo`, default off
   - Output: `VOCAL BUS`
   - Starting level: around `0.845`
   - Use for reverb commitment or printed throws, not as the only reverb strategy

## Fixed Defaults vs Per-Song Knobs

Keep fixed:

- Vocal tracks route to `VOCAL BUS`.
- Lead stays centered.
- Width comes from doubles/stacks, not the lead.
- Backing tracks start lower than lead.
- Vocal space/parallel ambience routes into the vocal bus.
- `VOCAL BUS` has light glue after all vocal elements.

Adjust per song:

- Lead vocal input gain into the vocal rack.
- Vocal bus compressor threshold if the take is quieter/louder.
- Backing vocal pan width.
- `Longest Ping Pong` dry/wet and feedback.
- Amount of `VOCAL SPACE PRINT`.
- Beat volume or instrumental pocket EQ if the vocal is fighting the sample.
- Reverb taste and throw automation.

## Next Capture Step

The missing piece is the inside of `Lead vocal preset` / `Pro Vocal Processing SM7B`.

To finish the template properly, unfold that rack in Ableton and capture or save the internal device chain. The likely final template will be:

`cleanup/tuning or gate -> corrective EQ -> compression/leveling -> de-essing -> tone/saturation -> optional final EQ -> vocal bus glue -> controlled space`

Until the rack internals are visible, the safest production move is to reuse the existing rack as the core insert and build the template around the routing, panning, backing delay, parallel space track, and group compression captured here.
