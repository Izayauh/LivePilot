# Waves Vocal Chains

Live Pilot includes four Waves-first vocal chain styles. The plugin names are
resolved from `config/owned_plugins.json`, so edit that file if Ableton reports
different names in the plugin browser.

## Styles

- `cla_modern_pop`: CLA-flavored modern pop/R&B vocal. Use it for bright,
  forward leads that need polish, density, and a little top-end excitement.
- `greg_wells_pop_ballad`: Wells-flavored pop ballad or midtempo chain. Use it
  when the vocal should feel smooth, musical, and spacious.
- `eddie_kramer_rock_rap`: Kramer-flavored rock/rap vocal. Use it when the take
  needs more edge, compression, and a more dramatic ambience.
- `clean_modern_neutral`: Minimal transparent fallback. Use it when the vocal
  already works and only needs cleanup, level control, and a small room.

## Workflow

Apply a style to a track:

```powershell
python scripts/apply_vocal_preset.py --style cla_modern_pop --track 0
```

Tweak the loaded devices in Ableton until the vocal sits right, then remember
the changed parameters:

```powershell
python scripts/remember_chain.py --track 0 --style cla_modern_pop --note "less compression, more reverb"
```

The next `apply_vocal_preset.py --style ...` run loads the committed template,
then applies your saved overrides on top.

## Preferences

Preferences live in `preferences/vocal_chain_<style>.json`. These files are
gitignored because they are local mix decisions. To reset a style, delete its
preference JSON file and the committed template defaults will be used again.

Waves plugins must be installed and visible in Ableton's plugin browser. If a
plugin is listed in `owned_plugins.json` but is not actually available in
Ableton, `add_plugin_to_track` will fail. Investigate the plugin list via
`get_available_plugins`.
