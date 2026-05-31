# Legacy archive

Jarvis-era LLM orchestration, research pipelines, and agent systems moved here during the MCP-first cleanup (`cleanup/mcp-first`).

**Active entry points (repo root):**

- `python run_mcp_server.py` — MCP stdio server for Claude/Cursor
- `python ableton_bridge.py --list` — CLI dispatch table
- `scripts/apply_vocal_preset.py`, `scripts/remember_chain.py` — deterministic vocal chains

Do not import from `legacy/` in production code. Git history retains deleted paths if you need to restore behavior.
