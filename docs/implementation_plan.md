# LivePilot Project Cleanup & Plugin Parameter Foundation (v2)

Clean up the LivePilot repo for an **MCP-first** workflow: archive the Jarvis/LLM stack, keep deterministic Ableton control + vocal-chain tooling, and codify plugin parameter presets as a first-class feature.

> **Review status (2026-05-31):** v1 of this plan was too aggressive on deletions. v2 incorporates a repo audit: several “legacy” paths are still used by active scripts and Waves vocal workflows.

---

## Goals

1. **Single control plane:** `mcp_server/` → `ableton_bridge._build_dispatch()` → `ableton_controls/` / `livepilot_tools/`
2. **No accidental breakage** of `apply_vocal_preset.py`, `remember_chain.py`, parameter contracts, or Kontakt tooling
3. **Plugin recipes** for one-device param snapshots (e.g. night-owl Kontakt piano), unified with—not parallel to—existing chain data
4. **Two PRs:** hygiene/archive first, recipes second

---

## User Review Required

> [!IMPORTANT]
> Phase 1 still removes a large amount of code (~150–200 files), but only **after** an import graph and explicit decisions below. Work on branch `cleanup/mcp-first` (or similar); nothing is lost from git history.

> [!WARNING]
> **Do not delete** `knowledge/`, `plugins/`, `preferences/`, or `analysis/` until migrations in Phase 1b complete. Scripts and tests depend on them today.

---

## Decisions (answer before Phase 1 deletes)

| # | Question | Recommended default | If “no” |
|---|----------|---------------------|---------|
| 1 | Still run `python jarvis_engine.py` (voice/text Jarvis)? | **No** — MCP + Claude/Cursor only | Keep Jarvis files; update README only |
| 2 | Still use `jarvis_desktop_openclaw.py` as a desktop front door? | **No** — uses bridge internally but separate from MCP | Keep or archive under `legacy/` |
| 3 | Keep Waves vocal chain scripts (`apply_vocal_preset`, `remember_chain`)? | **Yes** — deterministic, bridge-backed | Drop after migrating chains to `config/` |
| 4 | `research_bot.py` + `research/` + `agents/` + `pipeline/`? | **Archive** with Jarvis — only imported by Jarvis stack | Keep if you still run research vocal chains via Jarvis |

**External references to update when Jarvis is removed:**

- `live-pilot/README.md` — still documents `jarvis_engine.py` as main entry
- `Life_Os/data/projects.json` — `"start_cmd": "python jarvis_engine.py"` (stale if MCP-only)

---

## Architecture rules (from LivePilot skill)

```text
agent request
  → mcp_server/server.py          # thin MCP wrapper (stdio-safe, no print)
  → livepilot_tools/*.py          # NEW reusable logic goes here first
  → ableton_bridge._build_dispatch  # one-line lambdas only when needed
  → ableton_controls/             # OSC + ReliableParameterController
  → Ableton Live
```

- No LLM calls in tools, scanners, or executors
- Curated presets are **committed JSON** under `config/` or `data/`
- Prefer extending existing patterns over a third preset system (see Phase 3)

---

## Execution overview

| Phase | PR | What |
|-------|-----|------|
| **0** | — | Import graph + branch + baseline tests |
| **1a** | PR-A | Safe deletes (junk files, scratch, stale logs) |
| **1b** | PR-A | Migrate data/modules still in use |
| **1c** | PR-A | Archive Jarvis stack → `legacy/` (optional) or delete |
| **1d** | PR-A | Trim tests/docs; update README + Life_Os refs |
| **2** | PR-A | Target tree matches reality (docs only if no code move left) |
| **3** | PR-B | `plugin_recipes` + night-owl JSON + bridge dispatch + tests |

---

## Phase 0: Preflight (no deletions yet)

```powershell
cd C:\Users\isaia\Projects\music\live-pilot
git checkout -b cleanup/mcp-first

# What still imports Jarvis / agents / research (exclude jarvis_* and tests)?
rg -l "jarvis_engine|jarvis_tools|research_bot|agent_system|creative_workflow" --glob "*.py"

# What imports knowledge / plugins / preferences (MCP-adjacent scripts)?
rg -l "knowledge/|plugins\.|preferences\." --glob "*.py"

# Baseline
python -m unittest tests.test_ableton_bridge tests.test_parameter_contracts tests.test_context_tools -v
python -m py_compile ableton_bridge.py mcp_server/server.py livepilot_tools/parameter_contracts.py
```

Record results in PR description. **Do not proceed to mass delete until `knowledge/` / `plugins/` migrations are done or explicitly waived.**

---

## Phase 1a: Safe deletes (low risk)

### Root junk / logs
- `auth_status.txt`, `branch.txt`, `create_repo_output.txt`, `remote.txt`, `status.txt`, `test_output.txt`, `wsl_diag.txt`, `nul`
- `calibration_log.txt`

### Scratch / untracked data dirs
- `scratch/` (local experiments only)
- `daily_beats/` if not tracked and not needed

### One-off capture (if unused)
- `capture_ableton.py`, `capture_monitor3.py`

### Superseded modules (verify `rg` first)
- `device_parameter_cache.py` — superseded by `ParameterCache` in `reliable_params.py`
- `calibrate_param.py`, `calibration_utils.py` — superseded by `reliable_params.py`

---

## Phase 1b: Migrate before delete

### 1. Vocal chain data (`knowledge/` → `config/`)

**Keep the data; move the file:**

| From | To |
|------|-----|
| `knowledge/plugin_chains.json` | `config/vocal_chains.json` |

**Update imports in:**
- `scripts/apply_vocal_preset.py`
- `scripts/remember_chain.py`
- `tests/test_waves_chains.py`, `tests/chain_test_utils.py`, and any test loading `knowledge/plugin_chains.json`

**Then** delete Python modules in `knowledge/` that are **only** used by Jarvis (`plugin_chain_kb.py`, `artifact_chain_store.py`, etc.) after confirming zero imports from surviving code.

### 2. Chain resolver (`plugins/` → `livepilot_tools/`)

| From | To |
|------|-----|
| `plugins/chain_resolver.py` | `livepilot_tools/chain_resolver.py` |

Update `scripts/apply_vocal_preset.py`, `scripts/remember_chain.py`, `tests/test_chain_resolver.py`.

**Do not delete** `plugins/chain_builder.py` until Jarvis archive is complete—it is Jarvis-heavy but entangled; move whole `plugins/` to `legacy/plugins/` with Jarvis if needed.

### 3. Chain preferences (`preferences/` → `data/`)

| From | To |
|------|-----|
| `preferences/chain_preferences.py` | `livepilot_tools/chain_preferences.py` (or merge into `plugin_recipes.py` in PR-B) |

Update `scripts/remember_chain.py`.

### 4. Spectral / analysis (optional keep)

`analysis/` is used by `scripts/spectral_compare.py`, bounce scripts—not MCP, but **deterministic**. Either:
- **Keep** `analysis/` + `scripts/spectral_compare.py`, or
- **Archive** together if you do not use spectral compare anymore

Do **not** list `analysis/` as “unused by MCP” alone—that is not sufficient for deletion.

---

## Phase 1c: Archive Jarvis stack (after Phase 0 sign-off)

**Recommended:** `git mv` into `legacy/` for one release, then delete in a follow-up commit.

### Files → `legacy/jarvis/`

- `jarvis_engine.py`, `jarvis_tools.py`, `jarvis_desktop_openclaw.py`
- `jarvis_enhanced.py`, `jarvis_text_cli_wsl.py`, `jarvis_text_ui.py`, `jarvis_artist_os_adapter.py`
- `research_bot.py`, `agent_system.py`, `creative_workflow.py`, `adaptive_layer.py`, `generate_song_data.py`

### Directories → `legacy/`

- `agents/`
- `pipeline/`
- `research/` (LLM research coordinators—not the same as `research_bot.py` only)
- `context/` (Jarvis session manager)
- `discovery/` (if only Jarvis imports it)
- `templates/`, `macros/` (repo `macros/` dir—not `config/macros.json`)
- Remaining `plugins/` after resolver migration
- Remaining `knowledge/` Python after `plugin_chains.json` migration

### Scripts tied to Jarvis → `legacy/scripts/` or delete

- `scripts/phase_a_smoke.py`, `scripts/run_jarvis_e2e.ps1`, `scripts/test_librarian_full_chain.py`, `scripts/e2e_orchestrator.py`, `scripts/preview_taste_workflow.py`, `scripts/probe_research.py`, etc.

---

## Phase 1d: Tests & docs trim

### Tests to **keep** (MCP / OSC / params / vocal / contracts)

```
tests/test_ableton_bridge.py
tests/test_context_tools.py
tests/test_device_params.py
tests/test_direct_osc.py
tests/test_parameter_contracts.py
tests/test_kontakt_library.py
tests/test_osc_preflight.py
tests/test_verified_osc.py
tests/test_apply_vocal_preset_idempotency.py   # if keeping apply_vocal_preset
tests/test_remember_chain.py                   # if keeping remember_chain
tests/test_waves_chains.py                     # after vocal_chains.json migration
tests/test_chain_resolver.py                   # after chain_resolver move
```

### Tests to **archive** with Jarvis (`legacy/tests/` or delete)

- All `test_pipeline_*`, `test_*jarvis*`, `test_apply_research_chain`, `test_research_*`, `test_end_to_end_pipeline`, `test_creative_workflow`, `test_desktop_openclaw`, etc.

Run after trim:

```powershell
python -m unittest discover -s tests -p "test_ableton_bridge.py" -v
python -m unittest tests.test_parameter_contracts tests.test_context_tools -v
```

### Docs to **keep**

- `README.md` (rewrite for MCP entry—see below)
- `CLAUDE.md`
- `docs/parameter_normalization_guide.md`
- `docs/livepilot-context-and-listening-plan.md`

### Docs to **archive** (`legacy/docs/`)

- Jarvis-era planning, audits, research prompts, PDFs under `docs/Planning/`, etc.

### README rewrite (required in PR-A)

- Primary entry: `python run_mcp_server.py` / Claude MCP registration
- Document `call_livepilot_tool` + `list_livepilot_tools` (50+ bridge functions, not only 6 MCP tool names)
- Remove or move Jarvis voice instructions to `legacy/README-jarvis.md`

---

## Phase 2: Target project structure (post PR-A)

```
live-pilot/
├── README.md
├── CLAUDE.md
├── requirements.txt
├── run_mcp_server.py
│
├── mcp_server/
│   ├── __init__.py
│   ├── __main__.py
│   └── server.py                 # 6 MCP tools; bridge via call_livepilot_tool
│
├── ableton_bridge.py             # dispatch + describe_functions
│
├── ableton_controls/
│   ├── controller.py
│   ├── process_manager.py
│   └── reliable_params.py
│
├── ableton_remote_script/
│   └── JarvisDeviceLoader/
│
├── livepilot_tools/
│   ├── context_tools.py
│   ├── kontakt_library.py
│   ├── parameter_contracts.py    # KEEP — manifest-driven param plans
│   ├── chain_resolver.py         # migrated from plugins/
│   ├── chain_preferences.py    # migrated from preferences/ (or merged in PR-B)
│   └── plugin_recipes.py         # PR-B
│
├── librarian/
│   └── session_context.py
│
├── config/
│   ├── osc_paths.json
│   ├── owned_plugins.json
│   ├── plugin_aliases.json
│   ├── plugin_preferences.json
│   ├── plugin_parameter_manifests.json
│   ├── kontakt_favorites.json
│   ├── vocal_chains.json         # migrated from knowledge/plugin_chains.json
│   ├── macros.json
│   └── vst_config.json
│
├── data/
│   ├── recipes/                  # PR-B — per-device param snapshots
│   └── …                         # project intent, overrides, etc.
│
├── scripts/
│   ├── refresh_plugins.py
│   ├── apply_vocal_preset.py
│   ├── remember_chain.py
│   ├── verify_osc_reliability.py
│   ├── dump_device_params.py
│   └── export_kontakt_favorites.py
│
├── analysis/                     # OPTIONAL — keep if using spectral_compare
│
├── tests/                        # trimmed list above
│
├── docs/                         # kept docs only
├── osc_preflight.py
├── logging_config.py
│
└── legacy/                       # optional archive (Jarvis, old tests, old docs)
```

---

## Phase 3: Plugin recipes (PR-B only)

### What already works (no changes required)

- `get_track_devices` → `get_device_parameters` → `set_device_parameters_by_name`
- `smart_normalize_parameter` in `reliable_params.py`
- `livepilot_tools/parameter_contracts.py` for manifest-driven **named** param plans (Waves SSL, etc.)

### Preset systems — unify, don’t multiply

| System | Purpose | Action |
|--------|---------|--------|
| `config/vocal_chains.json` | Full multi-plugin Waves chains | Keep; used by `apply_vocal_preset` |
| `remember_chain.py` + preferences | User tweaks vs template | Keep; consider merging save format with recipes later |
| `config/plugin_parameter_manifests.json` | Contract/manifest per plugin | Keep |
| `config/macros.json` | Empty placeholder | Future macro profiles |
| **`data/recipes/*.json`** | **Single-device param snapshots** | **Add in PR-B** |

Recipe schema (suggested):

```json
{
  "schema": "livepilot-plugin-recipe-v1",
  "name": "night-owl-kk-piano-foundation",
  "device_class": "PluginDevice",
  "plugin_name": "Kontakt",
  "params": { "Volume": 0.82, "…": "…" },
  "notes": "Night-owl piano foundation — applied 2026-05"
}
```

### Implementation (PR-B)

1. **[NEW]** `livepilot_tools/plugin_recipes.py`
   - `save_plugin_recipe(name, track_index, device_index)` — read via bridge/controller, write JSON
   - `apply_plugin_recipe(name, track_index, device_index)` — call `set_device_parameters_by_name` logic
   - `list_plugin_recipes()` — glob `data/recipes/*.json`
   - Accept `controller` / `reliable` kwargs for tests (fake injection)

2. **[NEW]** `data/recipes/night-owl-kk-piano-foundation.json` — first committed recipe

3. **[MODIFY]** `ableton_bridge.py` — thin dispatch entries + `_describe_functions()` only

4. **[OPTIONAL]** `mcp_server/server.py` — dedicated `@mcp.tool()` wrappers **or** expose only via `call_livepilot_tool` (prefer latter to avoid MCP surface sprawl)

5. **[NEW]** `tests/test_plugin_recipes.py` — fake controller; no Ableton required

### Architecture flow

```text
save_plugin_recipe / apply_plugin_recipe
  → livepilot_tools/plugin_recipes.py
  → ReliableParameterController.set_parameters_by_name (apply)
  → data/recipes/<name>.json
```

---

## Verification plan

### PR-A (after cleanup / archive)

```powershell
python -m py_compile ableton_bridge.py mcp_server/server.py livepilot_tools/*.py
python -m unittest tests.test_ableton_bridge tests.test_parameter_contracts tests.test_context_tools -v
python run_mcp_server.py   # manual: confirm stdio starts, no import errors
```

- `claude mcp get live-pilot` → Connected (if registered)
- `list_livepilot_tools` via MCP → non-empty function list
- `scripts/verify_osc_reliability.py` (only if AbletonOSC running)
- `scripts/apply_vocal_preset.py --help` and `remember_chain.py --help` still run

### PR-B (recipes)

```powershell
python -m unittest tests.test_plugin_recipes -v
```

**Manual (Ableton open):**

1. `get_track_devices` → `get_device_parameters` → `set_device_parameters_by_name` on a test device
2. `save_plugin_recipe` → change params → `apply_plugin_recipe` → verify readback
3. Apply `night-owl-kk-piano-foundation` on a fresh Kontakt instance

### MCP surface check

| Layer | Count | Notes |
|-------|-------|-------|
| Named MCP tools in `server.py` | 6 | `list_livepilot_tools`, `call_livepilot_tool`, context/intent/plan |
| Bridge functions via `call_livepilot_tool` | ~50+ | Real daily surface—spot-check device, param, transport, clip |

---

## Risk register

| Risk | Mitigation |
|------|------------|
| Delete `knowledge/` before migration | Phase 1b first; update script paths |
| Delete `plugins/chain_resolver` | Move to `livepilot_tools/` first |
| Lose Jarvis with no archive | `git mv` to `legacy/` for one release |
| Third preset format drifts | Document schema; align with `parameter_contracts` long-term |
| Life_Os stale start_cmd | Update `data/projects.json` in PR-A or separate Life_Os commit |

---

## Suggested commit messages

**PR-A:** `chore(live-pilot): archive Jarvis stack and migrate MCP-first layout`

**PR-B:** `feat(live-pilot): add plugin recipe save/apply for parameter snapshots`

---

## Changelog from v1

- Split into PR-A (hygiene/archive) and PR-B (recipes)
- Added Phase 0 import graph and baseline tests
- **Removed** blanket delete of `knowledge/`, `plugins/`, `preferences/`, `analysis/`
- Added migrations for `vocal_chains.json`, `chain_resolver`, preferences
- Expanded kept tests, scripts, and `livepilot_tools/parameter_contracts.py`
- Phase 3 aligned with LivePilot skill (logic in `livepilot_tools`, thin bridge)
- Documented preset-system unification and MCP verification nuance
