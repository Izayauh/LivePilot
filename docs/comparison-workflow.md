# Comparison Workflow

Use `setup_comparison.py` when you want a fast, repeatable A/B between your
processed vocal track and a local reference file.

## Flow

Register a reference once:

```powershell
python scripts/register_reference.py --slug jackie_brown --path "C:\Users\isaia\Music\References\Brent Faiyaz - Jackie Brown.wav" --title "Jackie Brown" --artist "Brent Faiyaz"
```

Set up the comparison in a session:

```powershell
python scripts/setup_comparison.py --reference-key jackie_brown --my-vocal-track 2
```

Then listen, tweak the vocal chain by ear, and save the decision:

```powershell
python scripts/remember_chain.py --track 2 --style cla_modern_pop --note "matched ref brightness, less low-mid weight"
```

You can also skip the library and pass a one-off file:

```powershell
python scripts/setup_comparison.py --reference "C:\path\to\reference.wav" --my-vocal-track 2
```

## Loudness Matching

The setup command measures integrated LUFS and normalizes both sources to the
same playback target, `-10 LUFS` by default. That removes the easy trap where
the louder signal feels better even when the chain is not actually closer to
the reference. The command does not change the artistic chain settings; it only
adds gain staging needed for a fair comparison.

## Fake Doubles

`--simulate-doubles` creates two extra tracks from the user's clip, pans them
left and right, drops them by 7 dB, and reruns the `cla_modern_pop` vocal preset
on each. This is cosmetic density checking only. A single take with fake
doubles is not a real 4-track stack, so use it for ballparking commercial vocal
width and thickness, not for judging final performance or arrangement quality.

## Bridge Limitations

`setup_comparison.py` depends on bridge functions that are now surfaced
explicitly:

- `create_audio_track` is implemented through AbletonOSC, including optional
  naming when Live returns track data.
- `add_utility_device` is implemented through JarvisDeviceLoader plus reliable
  parameter setting, but device renaming is not exposed yet.
- `set_clip_path`, `get_clip_audio_path`, and `set_clip_detune` are honest
  stubs until AbletonOSC or JarvisDeviceLoader exposes file import, clip file
  path readback, and clip pitch controls.

Those gaps are raised clearly instead of silently pretending the Ableton state
changed.
