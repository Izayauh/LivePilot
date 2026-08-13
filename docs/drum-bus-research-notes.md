# Drum/Bus Research Notes

These notes explain the current LivePilot template defaults and the mistake fixed on 2026-05-12.

## Sources Checked

- iZotope, "What is a drum bus? How to set one up in your session"
- iZotope, "How to EQ Drums"
- iZotope, "Ultimate Drum Compression Guide"
- CreativeLive, "Use Parallel Compression to Help Your Drums Cut Through the Mix"
- MusicRadar, "6 drum processing techniques to help you program state-of-the-art beats"

## Practical Defaults

- Drum bus EQ should be broad and conservative. It is not the place for a destructive high-pass that removes drum body.
- Kick low cuts should remove sub-rumble only, usually around 20-35 Hz for modern programmed drums unless the source is broken.
- Snare/clap low cuts can sit higher, often around 80-120 Hz, because the kick/808 own the sub region.
- Hats/top loops can be high-passed much higher, often 200 Hz or above, because they do not need low-end body.
- Drum bus compression should glue, not flatten: conservative ratios around 2:1 to 4:1, slower attack to keep transients, and release timed so gain reduction recovers before the next hit.
- Parallel drum compression is a separate effect for density/sustain/punch. It should not replace clean source balance.
- Saturation/soft clipping can shave transient peaks and add density, but should be light on the main drum bus.

## LivePilot Fix

The template previously used `1 Filter Type A = 0` as if it were a high-pass/low-cut. Local tests in `tests/chain_test_utils.py` identify EQ Eight filter type `4` as HP12, `5` as HP24, and `6` as HP48. Type `0` is not a safe low-cut default.

Current policy:

- Use `1 Filter Type A = 4` for HP12 low cuts.
- `DRUM BUS` HP frequency: 28 Hz.
- `BASS BUS` HP frequency: 24 Hz.
- Kick HP frequency: 28 Hz.
- Snare/clap HP frequency: 95 Hz.
- Hats/top HP frequency: 260 Hz.
- Never high-pass a full drum bus anywhere near vocal-presence ranges.
