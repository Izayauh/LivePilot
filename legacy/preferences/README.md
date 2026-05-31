# Vocal Chain Preferences

This directory stores per-user vocal chain parameter overrides created by
`scripts/remember_chain.py`.

Preference JSON files are intentionally gitignored because they capture local
mix decisions. To reset a style, delete its `vocal_chain_<style>.json` file and
the next apply run will use the committed template defaults again.
