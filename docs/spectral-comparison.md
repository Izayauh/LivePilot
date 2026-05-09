# Spectral Comparison

`scripts/spectral_compare.py` captures a loudness-matched reference and vocal
group, analyzes both captures, prints objective differences, and saves the full
numbers to JSON for trend tracking.

## Flow

1. Load or register a reference and put the reference on an Ableton track.
2. Run the comparison against your vocal group:

```powershell
python scripts/spectral_compare.py --reference-track reference --my-vocal-group "3-Group" --capture-device "Loop-back 1/2" --capture-seconds 6
```

3. Read the report and decide which suggested moves fit the record.
4. Tweak the vocal chain manually.
5. Re-run the command and compare the saved JSON reports in `logs/` to see
   whether the gap closed.

## Metrics

Frequency balance shows the normalized dB difference between your vocal stack
and the reference across broad vocal-relevant frequency bands. Positive numbers
mean your stack has more energy than the reference in that band; negative
numbers mean it has less.

Crest factor is peak level minus RMS level in dB. A higher crest factor usually
means a more dynamic or less compressed signal; a lower crest factor usually
means stronger compression, limiting, saturation, or peak control.

Spectral centroid is a single-number brightness estimate. A higher centroid
means the energy is weighted brighter on average. Spectral bandwidth estimates
how widely the energy is spread around that center.

Mid/side ratio estimates stereo focus. Values near `1.0` are mostly centered;
lower values indicate proportionally more side energy and a wider or less
focused stack.

## Suggestions

Suggestions are deterministic and not auto-applied. If your `320-630 Hz` band
is `+2.7 dB` over the reference, the script suggests cutting roughly that
amount. If your `2.5-5 kHz` band is `-3.5 dB`, it suggests a presence boost.
Use the numbers as a diagnosis, then use taste to decide whether matching the
reference is actually the right move.

## Limitations

This command does not auto-apply EQ, compression, stereo width, or limiter
changes. It does not detect phase problems, comb filtering, transient response,
or whether a move should be surgical or broad. It is a one-shot capture and
analysis pass, not a real-time meter.

