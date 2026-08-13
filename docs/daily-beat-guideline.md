# Daily 9 AM Beat Guideline

This file is the default brief for the daily beat automation. Update it when Isaiah gives a more specific direction.

## Mission

Every morning at 9:00 AM, create one original beat or instrumental starter inside Ableton using the vocal-ready template as the working environment.

## Style Defaults

- Modern rap/R&B/pop-adjacent.
- Vocal-forward: leave space for a lead vocal before a vocal exists.
- Tempo range: 72-92 BPM or 136-156 BPM double-time.
- Mood: emotionally useful, not generic. Prefer late-night, intimate, cinematic, warm, or tense over bright stock-loop energy.
- Drums should hit, but not swallow the vocal center.
- Bass should be clear and mono-compatible.
- Chords should support the artist, not fill every bar with midrange motion.

## Required Structure

- 8-16 bar core loop.
- Distinct drum, bass, chord/pad, hook/lead, FX/transition, and vocal-placeholder lanes.
- Use the existing buses:
  - Drum sources to `DRUM BUS`
  - Bass to `BASS BUS`
  - Music to `MUSIC BUS - Vocal Pocket`
  - Vocal placeholders to `VOCAL BUS`
- Keep the lead vocal pocket clear around 1-4 kHz.
- Use filtered reverb/delay sends rather than washing the dry center.

## Output Expectations

At the end of the run:

- Leave the Ableton set organized and playable.
- Run `python scripts\create_daily_vocal_ready_beat.py` or an improved successor so every run creates real beat artifacts under `daily_beats/`.
- Name clips clearly.
- Update the changelog or write a short daily beat report with tempo, key/mode, mood, tracks touched, and what space was left for vocals.
- Do not ask Isaiah for routine choices unless the set is missing, Ableton is unreachable, or a destructive overwrite would be required.
