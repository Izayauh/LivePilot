# Jarvis-Ableton Architecture Plan v2: The Local Librarian Pivot

> **Status**: APPROVED PLAN — Ready for implementation
> **Date**: 2026-02-15
> **Supersedes**: All prior web-research-based architecture
> **Audience**: Any AI agent or developer needing full context to contribute to this codebase

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [The Pivot: What Changed and Why](#2-the-pivot-what-changed-and-why)
3. [Current Codebase State (Pre-Pivot)](#3-current-codebase-state-pre-pivot)
4. [Confirmed Architectural Decisions](#4-confirmed-architectural-decisions)
5. [The New JSON Song Schema](#5-the-new-json-song-schema)
6. [Revised Architecture Flowchart](#6-revised-architecture-flowchart)
7. [Component Inventory: What Changes vs. What Stays](#7-component-inventory-what-changes-vs-what-stays)
8. [New Module Specifications](#8-new-module-specifications)
9. [Integration Points with Existing Code](#9-integration-points-with-existing-code)
10. [Step-by-Step Implementation Plan](#10-step-by-step-implementation-plan)
11. [File Structure Summary](#11-file-structure-summary)
12. [Key Interfaces and Data Contracts](#12-key-interfaces-and-data-contracts)
13. [Open Questions and Future Considerations](#13-open-questions-and-future-considerations)

---

## 1. Executive Summary

Jarvis-Ableton is a voice-controlled AI assistant for Ableton Live. The user speaks creative
requests (e.g., "Give me the Ultralight Beam chorus vocal chain") and Jarvis translates them
into precise plugin chains loaded onto tracks via OSC.

**The pivot**: We are removing all runtime web/API search dependencies. Instead of searching
Google, YouTube, or scraping articles during a music session, Jarvis will query a **local
JSON database** of pre-researched song analyses stored in `docs/Research/`. This database
contains not just plugin settings, but granular **reasoning** for every parameter choice
(the "Teacher" capability).

**What stays the same**: The cloud LLM (Gemini/OpenAI) remains the conversational brain.
The OSC control layer, plugin name resolution, parameter normalization, and chain-building
pipeline are all unchanged. The only thing changing is **where the chain data comes from**.

---

## 2. The Pivot: What Changed and Why

### 2.1 The Problem with Web Research at Runtime

The prior architecture used a multi-source research pipeline (`research_coordinator.py`,
`youtube_research.py`, `web_research.py`, `research_bot.py`) that:

- Made multiple LLM calls per query (intent classification, extraction, synthesis)
- Scraped YouTube transcripts and web articles in real-time
- Was slow (5-30 seconds per research query)
- Was unreliable (API rate limits, changing web content, scraping failures)
- Could hallucinate or return low-confidence results from poor sources
- Required internet connectivity during the creative session

### 2.2 The Solution: Pre-Researched Local Database

Instead of researching at runtime, we:

1. **Pre-research** songs using a standalone offline tool (`generate_song_data.py`)
2. **Store** the results as validated JSON files in `docs/Research/`
3. **Query** these files instantly at runtime with zero LLM calls for data retrieval
4. **Explain** every parameter choice using embedded `param_why` reasoning data

### 2.3 What "Offline" Means (Precisely)

- **"Offline" = No web searching during the music-making session.** No Google, no YouTube,
  no article scraping while the user is working in Ableton.
- **The LLM brain is still cloud-based.** Gemini or OpenAI is still used for voice
  interaction, intent parsing, and natural language responses. We are NOT switching to a
  local LLM (like Ollama/llama.cpp), though the architecture should permit that swap later.
- **The data source is local.** All plugin chain data comes from JSON files on disk.

---

## 3. Current Codebase State (Pre-Pivot)

### 3.1 Project Structure Overview

```
JarvisAbleton/
├── ableton_controls/          # OSC control layer for Ableton
│   ├── controller.py          # Main AbletonController (OSC client, ~1000 lines)
│   ├── reliable_params.py     # Verified parameter mappings & normalization (~1500 lines)
│   └── process_manager.py     # Process lifecycle management
├── ableton_remote_script/     # Ableton MIDI Remote Script integration
├── agents/                    # Multi-agent orchestration system
│   ├── router_agent.py        # Intent classification & routing
│   ├── audio_engineer_agent.py
│   ├── research_agent.py
│   ├── planner_agent.py
│   ├── implementation_agent.py
│   └── executor_agent.py
├── config/                    # Configuration & mapping files
│   ├── plugin_aliases.json    # Fuzzy matching for plugin names (100+ entries)
│   ├── vst_config.json        # VST discovery configuration
│   ├── plugin_preferences.json # Blacklist/whitelist/fallback
│   ├── osc_paths.json         # AbletonOSC endpoint mappings
│   └── macros.json            # Macro command storage
├── discovery/                 # Plugin & device discovery systems
│   ├── vst_discovery.py       # VST discovery service
│   ├── plugin_name_resolver.py # Tiered plugin name resolution
│   ├── device_intelligence.py # Semantic parameter understanding (~1200 lines)
│   └── learning_system.py     # Learning from user corrections
├── knowledge/                 # Knowledge base & plugin definitions
│   ├── plugin_chains.json     # Cached chain research results (15 entries, ~770 lines)
│   ├── plugin_semantic_kb.json # Parameter semantics for all devices (~1980 lines)
│   ├── plugin_chain_kb.py     # Plugin chain knowledge manager
│   ├── artifact_chain_store.py # Filesystem-backed chain artifact cache
│   ├── device_kb.py           # Device parameter knowledge
│   └── micro_settings_kb.py   # Fine-tuning settings DB
├── plugins/                   # Plugin chain building & management
│   └── chain_builder.py       # Chain building from research (~968 lines)
├── research/                  # Research orchestration & LLM analysis
│   ├── research_coordinator.py # Main research orchestrator (~1460 lines)
│   ├── research_cache.json
│   ├── youtube_research.py    # YouTube transcript research
│   ├── web_research.py        # Web article research
│   ├── single_shot_research.py
│   └── reference_analyzer.py
├── pipeline/                  # Execution pipeline definitions
│   ├── tool_definition.py     # Gemini FunctionDeclaration schema
│   ├── executor.py
│   ├── guardrail.py
│   └── schemas.py
├── macros/                    # Macro command system
│   └── macro_builder.py
├── context/                   # Session & state management
│   ├── session_manager.py
│   ├── session_persistence.py
│   └── crash_recovery.py
├── docs/Research/             # THE NEW DATA DIRECTORY (seed files exist here)
│   ├── *.prompt.txt           # 10 LLM prompt templates for song analysis
│   ├── *.docx                 # Raw research data (3 songs)
│   └── *.pdf                  # Reference documents
├── jarvis_engine.py           # MAIN: Gemini integration & orchestration (~3623 lines)
├── jarvis_tools.py            # Tool definitions for Gemini (~1159 lines)
├── research_bot.py            # Autonomous chain research & iteration (~2013 lines)
└── CLAUDE.md                  # Jarvis protocol (thinking steps, constraints)
```

### 3.2 Current Data Flow (Being Replaced)

```
User says "Kanye vocal chain"
    → Gemini calls research_vocal_chain()
    → jarvis_engine.py:execute_research_vocal_chain()
    → research_coordinator.py:perform_research()
        → Step 0: Check artifact_chain_store (knowledge/chains/*.json)
        → Step 0b: Check legacy caches (research_cache.json, plugin_chains.json)
        → Step 1: Single-shot LLM research (1 API call)
        → Step 2: OR deep research (web scraping + YouTube + multiple LLM calls)
    → Returns ChainSpec (plugin list + settings + confidence)
    → User confirms
    → execute_apply_research_chain()
    → chainspec_to_builder_format() converts to builder format
    → PluginChainBuilder.build_chain_from_research()
    → Matches plugins to available inventory
    → load_chain_on_track() via OSC
    → Parameters applied via ResearchBot normalization
```

### 3.3 Key Existing Data Structures

**ChainSpec** (from `research_coordinator.py`):
```python
@dataclass
class ChainSpec:
    query: str
    style_description: str
    devices: List[DeviceSpec]    # Ordered list of devices
    confidence: float
    sources: List[str]
    artist: Optional[str]
    song: Optional[str]
    genre: Optional[str]
    meta: Dict[str, Any]

@dataclass
class DeviceSpec:
    plugin_name: str
    category: str                # eq, compressor, reverb, etc.
    parameters: Dict[str, Any]   # param_name -> {value, unit, confidence}
    purpose: str
    reasoning: str
    confidence: float
    sources: List[str]
```

**Builder format** (what `PluginChainBuilder.build_chain_from_research()` expects):
```python
{
    "artist_or_style": "Kanye West",
    "track_type": "vocal",
    "chain": [
        {
            "type": "eq",
            "purpose": "high_pass_cleanup",
            "plugin_name": "EQ Eight",
            "name": "EQ Eight",
            "settings": {"Band 1 Frequency": 95, "Band 1 Filter Type": 5, ...}
        },
        ...
    ],
    "confidence": 0.8,
    "sources": [...],
    "from_research": True
}
```

### 3.4 Existing Seed Data in docs/Research/

10 `.prompt.txt` files exist, each containing a structured LLM prompt designed to generate
the new JSON schema. Songs covered:

| # | Song | Artist |
|---|------|--------|
| 001 | Ultralight Beam | Kanye West |
| 002 | Saint Pablo | Kanye West |
| 003 | Miami (feat. Leon Thomas) | Odeal / Leon Thomas |
| 004 | Back to Me | Kanye West / Ty Dolla $ign |
| 005 | Which One (feat. Central Cee) | Drake / Central Cee |
| 006 | Die Trying | PARTYNEXTDOOR / Drake / Yebba |
| 007 | Say What's Real | Drake |
| 008 | Treasure in the Hills | Leon Thomas |
| 009 | The Violence | Childish Gambino |
| 010 | Apocalypse | Cigarettes After Sex |

Additionally, 3 `.docx` files contain raw research data for Ultralight Beam, Die Trying,
and Apocalypse.

The prompt template format (identical across all 10 files):
```
You are an elite vocal production analyst helping build an offline vocal-chain
database for an AI DAW assistant.
Song to analyze - ({title} - {artist})
Return EXACTLY one valid JSON object (no markdown, no commentary) that follows
this schema intent:
{song schema definition}
Where each Device is:
{device schema definition}
Hard requirements:
1) Include all 4 sections: verse, chorus, background_vocals, adlibs.
2) For each section, provide an ORDERED chain (5-10 devices typical).
3) key_params must be practical and machine-usable.
4) Prefer common plugins and/or stock-equivalent naming.
5) Do NOT fabricate false precision.
6) Add global_tags for retrieval.
7) Ensure param_why covers key_params entries.
Return JSON only.
```

---

## 4. Confirmed Architectural Decisions

These decisions were explicitly confirmed by the project owner. They are final.

### 4.1 Data Source

- `docs/Research/` is the **single source of truth** for chain data.
- The old `knowledge/` folder is ignored for this pivot. No automatic migration.
- The library will be manually rebuilt using the new schema.

### 4.2 Schema Design

- **1 JSON file = 1 song** (not per-chain, not per-concept).
- **Hierarchy**: Song -> Sections (verse, chorus, background_vocals, adlibs) -> Chain -> Devices.
- **Reasoning is granular**: Every device has a `param_why` object that maps each `key_params`
  entry to a short justification string.
- **Global tags** at the top level enable "vibe" searching (e.g., "gospel", "lush", "warm").

### 4.3 Research Pipeline Disposition

- The web scrapers (`research_bot.py`, `youtube_research.py`, `web_research.py`) are being
  **converted to a standalone offline tool**, not deleted.
- The assistant does **NOT** search the web at runtime.
- New flow: User runs `generate_song_data.py` manually -> reviews output -> saves to
  `docs/Research/` -> it becomes available to Jarvis.

### 4.4 Query/Retrieval Model

- **Primary search**: Keyword match against `song.title` and `song.artist`.
- **Secondary search ("vibe")**: Scan `global_tags` of all files, rank by tag overlap.
- **Fallback**: If no exact match, find the file with highest tag overlap.
- **Section-level access**: The bot loads specific sections from a file.
  Example: "Load the chorus vocal chain from Ultralight Beam" ->
  reads `ultralight_beam.json` -> finds `sections.chorus` -> loads that chain.

### 4.5 Agent Routing

- `PLUGIN_CHAIN` intent no longer triggers `ResearchAgent`.
- It triggers a new **LibrarianAgent** (or ContextLoader) that queries local JSON files.

### 4.6 Teacher Behavior

- Explanations must be **grounded** in the `param_why` fields from the JSON.
- When the user asks "Why 4:1?", the system reads the specific `param_why.ratio` from the
  loaded JSON and presents that context.
- The LLM may rephrase for natural speech but must NOT hallucinate general theory.
- Source of truth = the JSON file's reasoning data.

### 4.7 "Offline" Scope

- "Offline" means no web searching during the session.
- The LLM brain (Gemini/OpenAI) is still cloud-based.
- Architecture should permit swapping to a local LLM in the future.

---

## 5. The New JSON Song Schema

### 5.1 Complete Schema Definition

```json
{
  "song": {
    "title": "Ultralight Beam",
    "artist": "Kanye West",
    "year": 2016,
    "genre": "gospel hip-hop"
  },
  "global_tags": ["gospel", "lush", "warm", "choir", "ethereal", "spiritual"],
  "sections": {
    "verse": {
      "intent": "Warm, intimate lead vocal sitting slightly behind the choir",
      "chain": [
        {
          "plugin": "EQ Eight",
          "stage": "cleanup",
          "key_params": {
            "high_pass_freq": 85,
            "low_mid_cut_freq": 300,
            "low_mid_cut_gain": -2.5
          },
          "param_why": {
            "high_pass_freq": "85 Hz removes rumble without thinning the chest resonance",
            "low_mid_cut_freq": "300 Hz is where vocal mud accumulates in a dense gospel mix",
            "low_mid_cut_gain": "-2.5 dB is a gentle cut that cleans without making it nasal"
          },
          "why": "Clean up low-end before compression to prevent the compressor from reacting to non-vocal energy"
        },
        {
          "plugin": "Compressor",
          "stage": "dynamics",
          "key_params": {
            "threshold": -18,
            "ratio": 4,
            "attack": 10,
            "release": 80,
            "makeup_gain": 3
          },
          "param_why": {
            "threshold": "-18 dB catches the loudest phrases without clamping quiet moments",
            "ratio": "4:1 tames peaks without pumping, keeps the vocal natural",
            "attack": "10 ms lets the initial consonant transient through for intelligibility",
            "release": "80 ms releases before the next syllable to avoid swallowing words",
            "makeup_gain": "3 dB compensates for the average gain reduction at this threshold"
          },
          "why": "Even out the vocal dynamics so it sits consistently in a mix with a large choir"
        }
      ]
    },
    "chorus": {
      "intent": "...",
      "chain": [...]
    },
    "background_vocals": {
      "intent": "...",
      "chain": [...]
    },
    "adlibs": {
      "intent": "...",
      "chain": [...]
    }
  },
  "confidence": 0.8,
  "notes": "Analysis based on production interviews and reference listening. Chance the Rapper's verse uses different processing than Kanye's hook.",
  "sources": ["production interview", "reference analysis", "community discussion"]
}
```

### 5.2 Schema Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `song.title` | string | Yes | Song title (primary search key) |
| `song.artist` | string | Yes | Artist name (primary search key) |
| `song.year` | int or null | No | Release year |
| `song.genre` | string or null | No | Genre classification |
| `global_tags` | string[] | Yes | Vibe/style tags for secondary search |
| `sections` | object | Yes | Must contain verse, chorus, background_vocals, adlibs |
| `sections.{name}.intent` | string | Yes | Creative description of the target sound for this section |
| `sections.{name}.chain` | Device[] | Yes | Ordered signal chain (5-10 devices typical) |
| `Device.plugin` | string | Yes | Plugin name (prefer Ableton stock names) |
| `Device.stage` | enum | Yes | One of: cleanup, tone, dynamics, space, creative, utility |
| `Device.key_params` | object | Yes | Machine-usable parameter names and values |
| `Device.param_why` | object | Yes | Must have a key for every key in `key_params` |
| `Device.why` | string | Yes | Overall purpose of this device in the chain context |
| `confidence` | float | Yes | 0.0-1.0 confidence in the analysis accuracy |
| `notes` | string | No | Additional context, caveats, or production notes |
| `sources` | string[] | No | Where the analysis data came from |

### 5.3 Stage Enum Values

| Stage | Signal Flow Position | Purpose |
|-------|---------------------|---------|
| `cleanup` | First | High-pass filtering, noise removal, de-essing |
| `tone` | Early-mid | EQ shaping, tonal character |
| `dynamics` | Mid | Compression, limiting, expansion |
| `space` | Late | Reverb, delay, spatial effects |
| `creative` | Variable | Saturation, distortion, pitch effects, modulation |
| `utility` | Last | Gain staging, stereo width, monitoring |

---

## 6. Revised Architecture Flowchart

### 6.1 Main Data Flow (Runtime)

```
USER VOICE / TEXT INPUT
        |
        v
+--------------------+
|  Gemini / OpenAI   |  Cloud LLM (voice interaction, intent parsing)
|  Session Engine    |
+--------+-----------+
         |  Function call from LLM
         v
+--------------------+
|   RouterAgent      |  Classifies intent into one of:
|                    |    SIMPLE_COMMAND  -> existing DAW control path (unchanged)
|                    |    LIBRARY_LOOKUP  -> LibrarianAgent (NEW)
|                    |    TEACHER_QUERY   -> LibrarianAgent + Teacher (NEW)
|                    |    COMPLEX_WORKFLOW -> existing multi-agent path
+--------+-----------+
         |
         |--- LIBRARY_LOOKUP or TEACHER_QUERY --->+
         |                                         |
         v                                         v
+--------------------+                   +---------------------+
| Existing DAW       |                   |  LibrarianAgent     |  NEW MODULE
| Control Path       |                   |                     |
| (unchanged)        |                   |  1. Parse intent    |
|                    |                   |     - artist/song   |
| mute, solo, arm,   |                   |     - section       |
| volume, pan, etc.  |                   |     - vibe tags     |
+--------------------+                   |                     |
                                         |  2. Query Index     |
                                         |     (in-memory scan |
                                         |      of all JSONs)  |
                                         |                     |
                                         |  3. Load JSON file  |
                                         |     from            |
                                         |     docs/Research/  |
                                         |                     |
                                         |  4. Extract section |
                                         |     chain           |
                                         |                     |
                                         |  5. Return result   |
                                         |     as ChainSpec +  |
                                         |     param_why data  |
                                         +----------+----------+
                                                    |
                                                    v
                                         +---------------------+
                                         | PluginChainBuilder  |  EXISTING (unchanged)
                                         |                     |
                                         | - Match plugins to  |
                                         |   available VSTs    |
                                         | - Resolve names     |
                                         | - Apply blacklist/  |
                                         |   whitelist         |
                                         | - Native fallbacks  |
                                         +----------+----------+
                                                    |
                                                    v
                                         +---------------------+
                                         | AbletonController   |  EXISTING (unchanged)
                                         | + ResearchBot       |
                                         |   param normalize   |
                                         |                     |
                                         | - Load devices OSC  |
                                         | - Set parameters    |
                                         | - Verify success    |
                                         +---------------------+
```

### 6.2 Teacher Path (Question About Loaded Chain)

```
USER: "Why did you set the ratio to 4:1?"
         |
         v
+--------------------+
|   RouterAgent      |  Detects TEACHER_QUERY intent
+--------+-----------+
         |
         v
+--------------------+
|  LibrarianAgent    |  Looks up currently-active chain in session context
|  + Teacher module  |  Finds the device with "ratio" in key_params
|                    |  Reads param_why["ratio"]
|                    |  Returns: "4:1 tames peaks without pumping, keeps the vocal natural"
+--------+-----------+
         |
         v
+--------------------+
|  Gemini / OpenAI   |  Receives grounded context from param_why
|                    |  Rephrases into natural speech:
|                    |  "I set the ratio to 4:1 because at this level, it controls
|                    |   the peaks in the vocal without causing audible pumping.
|                    |   It keeps the performance sounding natural, which is
|                    |   important for the intimate gospel feel of this track."
+--------------------+
```

### 6.3 Offline Enrichment Flow (Not Runtime)

```
USER (outside of Ableton session):
    Runs: python generate_song_data.py --song "New Song" --artist "New Artist"
         |
         v
+--------------------+
|  generate_song_    |  Standalone CLI tool
|  data.py           |
|                    |
|  - Reads prompt    |
|    template        |
|  - Optionally uses |
|    old research    |
|    modules for     |
|    raw data        |
|  - Sends to LLM   |
|  - Validates JSON  |
|    against schema  |
|  - Saves to        |
|    docs/Research/  |
+--------------------+
         |
         v
    User reviews JSON file manually
         |
         v
    File is now available to LibrarianAgent at next startup
```

---

## 7. Component Inventory: What Changes vs. What Stays

### 7.1 UNCHANGED Components

These are stable and require zero modifications:

| Component | File(s) | Role |
|-----------|---------|------|
| AbletonController | `ableton_controls/controller.py` | OSC communication with Ableton |
| Reliable Params | `ableton_controls/reliable_params.py` | Parameter normalization/calibration |
| PluginChainBuilder | `plugins/chain_builder.py` | Plugin matching, chain building, track loading |
| Plugin Name Resolver | `discovery/plugin_name_resolver.py` | Tiered fuzzy name resolution |
| VST Discovery | `discovery/vst_discovery.py` | Plugin scanning and inventory |
| Device Intelligence | `discovery/device_intelligence.py` | Semantic parameter understanding |
| Plugin Semantic KB | `knowledge/plugin_semantic_kb.json` | Parameter ranges and typical values |
| Plugin Aliases | `config/plugin_aliases.json` | Name alias mappings |
| Plugin Preferences | `config/plugin_preferences.json` | Blacklist/whitelist/fallback |
| OSC Paths | `config/osc_paths.json` | AbletonOSC endpoint reference |
| Session Manager | `context/session_manager.py` | Transport/track state tracking |
| Crash Recovery | `context/crash_recovery.py` | Disconnection handling |
| Macro System | `macros/macro_builder.py` | Reusable command sequences |
| Research Bot (params) | `research_bot.py` | Parameter application/normalization ONLY |

### 7.2 MODIFIED Components

| Component | File(s) | What Changes |
|-----------|---------|-------------|
| RouterAgent | `agents/router_agent.py` | Add `LIBRARY_LOOKUP` and `TEACHER_QUERY` intent types |
| jarvis_engine.py | `jarvis_engine.py` | `execute_research_vocal_chain` calls Librarian first |
| jarvis_tools.py | `jarvis_tools.py` | New tool declarations for library operations |

### 7.3 NEW Components

| Component | File(s) | Role |
|-----------|---------|------|
| Schema Validator | `librarian/schema.py` | Validates song JSON files against the defined schema |
| Library Index | `librarian/index.py` | In-memory index over all `docs/Research/*.json` files |
| Section Extractor | `librarian/extractor.py` | Extracts section chains, converts to builder format |
| LibrarianAgent | `librarian/librarian_agent.py` | Main query entry point for chain lookups |
| Teacher | `librarian/teacher.py` | Grounded explanations from `param_why` data |
| Session Context | `librarian/session_context.py` | Tracks currently-loaded chain for Teacher queries |
| Song Data Generator | `generate_song_data.py` | Standalone CLI tool for offline enrichment |

### 7.4 BYPASSED Components (Kept for Offline Tool Only)

These modules are NOT deleted. They remain in the codebase but are no longer called at
runtime. They are used exclusively by `generate_song_data.py` for offline data generation.

| Component | File(s) | Prior Role |
|-----------|---------|-----------|
| Research Coordinator | `research/research_coordinator.py` | Web+YouTube research orchestration |
| YouTube Research | `research/youtube_research.py` | YouTube transcript analysis |
| Web Research | `research/web_research.py` | Web article scraping |
| Single-Shot Research | `research/single_shot_research.py` | One-call LLM research |
| Research Cache | `research/research_cache.json` | Cached web research results |

### 7.5 DEPRECATED Components (Replaced by Librarian)

| Component | File(s) | Replaced By |
|-----------|---------|-------------|
| Artifact Chain Store | `knowledge/artifact_chain_store.py` | `librarian/index.py` |
| Plugin Chain KB | `knowledge/plugin_chain_kb.py` | `librarian/index.py` |
| Plugin Chains JSON | `knowledge/plugin_chains.json` | `docs/Research/*.json` |

---

## 8. New Module Specifications

### 8.1 `librarian/schema.py` — Schema Validator

**Purpose**: Validate song JSON files against the defined schema before they enter the library.

**Key functions**:
```python
def validate_song_file(path: str) -> Tuple[bool, List[str]]:
    """Validate a JSON file against the song schema.
    Returns (is_valid, list_of_error_messages)."""

def validate_song_data(data: dict) -> Tuple[bool, List[str]]:
    """Validate a parsed dict against the song schema."""
```

**Validation rules**:
- `song.title` and `song.artist` must be non-empty strings
- `global_tags` must be a non-empty list of strings
- `sections` must contain all four keys: verse, chorus, background_vocals, adlibs
- Each section must have `intent` (string) and `chain` (list of devices)
- Each device must have: `plugin` (string), `stage` (valid enum), `key_params` (dict),
  `param_why` (dict), `why` (string)
- Every key in `key_params` must have a corresponding key in `param_why`
- `confidence` must be a float between 0.0 and 1.0

**Dataclass models** (for type safety, not for serialization):
```python
@dataclass
class SongMeta:
    title: str
    artist: str
    year: Optional[int] = None
    genre: Optional[str] = None

@dataclass
class Device:
    plugin: str
    stage: str  # cleanup|tone|dynamics|space|creative|utility
    key_params: Dict[str, Any]
    param_why: Dict[str, str]
    why: str

@dataclass
class Section:
    intent: str
    chain: List[Device]

@dataclass
class SongAnalysis:
    song: SongMeta
    global_tags: List[str]
    sections: Dict[str, Section]
    confidence: float
    notes: str = ""
    sources: List[str] = field(default_factory=list)
```

### 8.2 `librarian/index.py` — Library Index

**Purpose**: On startup, scan `docs/Research/*.json`, build an in-memory index for fast
querying. Refresh when files change.

**Key class**: `LibraryIndex`

**Index entry structure** (per file):
```python
{
    "filename": "ultralight_beam.json",
    "path": "docs/Research/ultralight_beam.json",
    "title": "Ultralight Beam",
    "artist": "Kanye West",
    "year": 2016,
    "genre": "gospel hip-hop",
    "global_tags": ["gospel", "lush", "warm", "choir", "ethereal"],
    "section_keys": ["verse", "chorus", "background_vocals", "adlibs"],
    "confidence": 0.8,
    "title_normalized": "ultralight beam",
    "artist_normalized": "kanye west",
    "tags_set": {"gospel", "lush", "warm", "choir", "ethereal"}
}
```

**Query methods**:
```python
def search_by_song(self, title: str, artist: str = "") -> Optional[IndexEntry]:
    """Exact or fuzzy match on song title + artist.
    Returns the best matching entry or None."""

def search_by_tags(self, tags: List[str]) -> List[Tuple[IndexEntry, int]]:
    """Return entries ranked by number of matching global_tags.
    Returns list of (entry, overlap_count) sorted descending."""

def search_by_vibe(self, query: str) -> List[Tuple[IndexEntry, float]]:
    """Tokenize query, match against tags + artist + title.
    Returns list of (entry, score) sorted descending."""

def list_all(self) -> List[IndexEntry]:
    """Return all entries in the library."""

def reload(self) -> int:
    """Re-scan the docs/Research/ directory. Returns count of valid files loaded."""
```

### 8.3 `librarian/extractor.py` — Section Extractor

**Purpose**: Given loaded song JSON data, extract a specific section's chain and convert it
to the format that `PluginChainBuilder` already expects.

**Key functions**:
```python
def get_section_chain(song_data: dict, section_name: str) -> List[dict]:
    """Extract the device chain for a specific section.
    Returns the list of Device dicts from the JSON."""

def to_builder_format(
    devices: List[dict],
    song_meta: dict,
    section_name: str
) -> dict:
    """Convert JSON Device list to the dict format expected by
    PluginChainBuilder.build_chain_from_research().

    Input (from JSON):
        {"plugin": "EQ Eight", "stage": "cleanup",
         "key_params": {"high_pass_freq": 85}, ...}

    Output (builder format):
        {"type": "cleanup", "purpose": "...", "plugin_name": "EQ Eight",
         "name": "EQ Eight", "settings": {"high_pass_freq": 85}}
    """

def get_param_why(
    song_data: dict,
    section_name: str,
    plugin_name: str,
    param_name: str
) -> Optional[str]:
    """Look up the param_why for a specific parameter on a specific device
    in a specific section. Returns the reasoning string or None."""

def get_device_why(
    song_data: dict,
    section_name: str,
    plugin_name: str
) -> Optional[str]:
    """Look up the device-level 'why' for a plugin in a section."""
```

**Critical conversion detail**: The `key_params` from the JSON schema uses semantic names
(e.g., `high_pass_freq`, `ratio`, `attack`). The `PluginChainBuilder` passes `settings`
through to `ResearchBot.apply_parameters()`, which uses `reliable_params.py` for
normalization. The semantic names in the JSON must align with what `reliable_params.py`
recognizes, or the extractor must include a mapping layer.

### 8.4 `librarian/librarian_agent.py` — Main Query Agent

**Purpose**: Receives a parsed user request, queries the index, loads the JSON, extracts
the chain, returns a result compatible with the existing pipeline.

**Key class**: `LibrarianAgent`

**Main method**:
```python
async def lookup(
    self,
    query: str,
    section: Optional[str] = None,
    artist: Optional[str] = None,
    song_title: Optional[str] = None,
    tags: Optional[List[str]] = None
) -> dict:
    """
    Query the local library.

    Returns a dict compatible with what execute_research_vocal_chain() returns:
    {
        "success": True/False,
        "chain_spec": {...},       # ChainSpec-compatible dict
        "message": "...",
        "query": "...",
        "confidence": 0.8,
        "source": "local_library",
        "song_file": "ultralight_beam.json",
        "section": "chorus",
        "param_why_available": True,
        "style_description": "Warm, intimate lead vocal..."
    }
    """
```

**Search priority**:
1. If `song_title` and/or `artist` provided: `search_by_song()` (exact match)
2. If tags provided or query contains vibe words: `search_by_tags()` / `search_by_vibe()`
3. If no match found: return `{"success": False, "message": "Song not in library"}`

**Section resolution**:
- If user specifies a section ("chorus vocal chain"), use that section.
- If user doesn't specify, default to "verse" (most common request).
- If user says "the whole song" or "all sections", return all section chains.

### 8.5 `librarian/teacher.py` — Grounded Explanations

**Purpose**: Provide parameter-level explanations grounded in the JSON `param_why` data.

**Key functions**:
```python
def explain_setting(plugin_name: str, param_name: str) -> Optional[dict]:
    """Look up the param_why for a parameter on the currently-active chain.
    Returns:
    {
        "plugin": "Compressor",
        "param": "ratio",
        "value": 4,
        "reason": "4:1 tames peaks without pumping, keeps the vocal natural",
        "device_context": "Even out dynamics so vocal sits consistently with choir",
        "section": "verse",
        "song": "Ultralight Beam",
        "artist": "Kanye West"
    }
    """

def explain_device(plugin_name: str) -> Optional[dict]:
    """Return the device-level 'why' from the active chain."""

def explain_section_intent(section_name: str) -> Optional[dict]:
    """Return the section-level 'intent' from the active chain."""

def get_full_chain_explanation(section_name: str) -> Optional[dict]:
    """Return the complete chain with all param_why data for a section.
    Used when the user asks 'explain the whole chain'."""
```

### 8.6 `librarian/session_context.py` — Active Chain Tracking

**Purpose**: Track which song and section are currently loaded so the Teacher knows what
to reference.

**Key class**: `LibrarianSessionContext` (singleton)

**State tracked**:
```python
{
    "active_song_file": "ultralight_beam.json",
    "active_song_data": { ... },          # Full parsed JSON
    "active_section": "chorus",
    "active_chain_devices": [ ... ],      # The specific chain that was loaded
    "loaded_at": "2026-02-15T14:30:00",
    "track_index": 2                       # Which Ableton track it was loaded on
}
```

**Key methods**:
```python
def set_active(self, song_data: dict, section: str, track_index: int) -> None:
    """Set the currently-active chain context."""

def get_active(self) -> Optional[dict]:
    """Get the current context, or None if nothing loaded."""

def clear(self) -> None:
    """Clear the active context (e.g., when user starts fresh)."""
```

### 8.7 `generate_song_data.py` — Offline Enrichment Tool

**Purpose**: Standalone CLI script to generate song JSON files from prompts.

**Usage**:
```bash
# Generate from an existing prompt file
python generate_song_data.py --prompt docs/Research/001_kanye-west-ultralight-beam.prompt.txt

# Generate from song info (creates prompt automatically)
python generate_song_data.py --song "Ultralight Beam" --artist "Kanye West"

# Batch generate all prompt files
python generate_song_data.py --batch docs/Research/

# Validate an existing JSON file
python generate_song_data.py --validate docs/Research/ultralight_beam.json
```

**Workflow**:
1. Read or generate the prompt text
2. Send to LLM (Gemini or OpenAI)
3. Parse response as JSON
4. Validate against `librarian/schema.py`
5. If valid: save to `docs/Research/{slug}.json`
6. If invalid: print errors, save to `docs/Research/{slug}.draft.json` for manual review

---

## 9. Integration Points with Existing Code

### 9.1 RouterAgent Modification

**File**: `agents/router_agent.py`

**Changes**:
- Add new intent types to the classification:
  ```python
  # New keyword sets
  self.library_lookup_keywords = {
      "chain", "plugin chain", "vocal chain", "load",
      "from", "like", "style",
      # Artist names from the library index (loaded dynamically)
  }

  self.teacher_keywords = {
      "why", "explain", "what does", "tell me about",
      "reason", "because", "purpose",
  }
  ```
- New intent types: `LIBRARY_LOOKUP`, `TEACHER_QUERY`
- Logic: If query mentions a specific song/artist AND contains chain-related words ->
  `LIBRARY_LOOKUP`. If query asks "why" about a parameter/device -> `TEACHER_QUERY`.

### 9.2 jarvis_engine.py Modification

**File**: `jarvis_engine.py`

**Function**: `execute_research_vocal_chain()` (lines ~1655-1813)

**Change**: Insert Librarian lookup BEFORE the existing research pipeline:

```python
def execute_research_vocal_chain(query, ...):
    # NEW: Try local library first
    from librarian.librarian_agent import get_librarian_agent
    librarian = get_librarian_agent()
    local_result = librarian.lookup(query)

    if local_result["success"]:
        # Found in local library - return immediately (zero LLM calls for data)
        return {
            "success": True,
            "chain_spec": local_result["chain_spec"],
            "message": f"Found in library: {local_result['song_file']}",
            "source": "local_library",
            "param_why_available": True,
            ...
        }

    # NOT FOUND in library - either fail or fall through to existing research
    # Default behavior: inform user the song isn't in the library
    return {
        "success": False,
        "message": f"'{query}' is not in the local library. "
                   "Use generate_song_data.py to add it.",
        "source": "local_library_miss",
    }
```

### 9.3 jarvis_tools.py Modification

**File**: `jarvis_tools.py`

**New Gemini tool declarations**:

```python
# lookup_song_chain - query the local library for a chain
FunctionDeclaration(
    name="lookup_song_chain",
    description="Search the local song database for a vocal chain. "
                "Returns plugin chain data for a specific song and section.",
    parameters={
        "type": "object",
        "properties": {
            "song_title": {"type": "string", "description": "Song title to search for"},
            "artist": {"type": "string", "description": "Artist name"},
            "section": {
                "type": "string",
                "description": "Song section: verse, chorus, background_vocals, or adlibs",
                "enum": ["verse", "chorus", "background_vocals", "adlibs"]
            }
        },
        "required": ["song_title"]
    }
)

# explain_parameter - read param_why from the loaded chain
FunctionDeclaration(
    name="explain_parameter",
    description="Explain why a specific parameter was set to its current value. "
                "Reads from the local database reasoning data.",
    parameters={
        "type": "object",
        "properties": {
            "plugin_name": {"type": "string", "description": "Name of the plugin"},
            "param_name": {"type": "string", "description": "Parameter name to explain"}
        },
        "required": ["plugin_name", "param_name"]
    }
)

# list_library - show all available songs
FunctionDeclaration(
    name="list_library",
    description="List all songs available in the local chain database.",
    parameters={"type": "object", "properties": {}}
)

# search_library_by_vibe - tag-based search
FunctionDeclaration(
    name="search_library_by_vibe",
    description="Search the local database by mood/vibe/style tags.",
    parameters={
        "type": "object",
        "properties": {
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of vibe/style tags to search for"
            }
        },
        "required": ["tags"]
    }
)
```

### 9.4 Data Format Bridge

The critical bridge between the new JSON schema and the existing pipeline:

**JSON Device format (from song files)**:
```json
{
    "plugin": "Compressor",
    "stage": "dynamics",
    "key_params": {"threshold": -18, "ratio": 4, "attack": 10, "release": 80},
    "param_why": {"threshold": "...", "ratio": "...", ...},
    "why": "Even out dynamics..."
}
```

**Builder format (what PluginChainBuilder expects)**:
```python
{
    "type": "dynamics",           # mapped from "stage"
    "purpose": "Even out...",     # mapped from "why"
    "plugin_name": "Compressor",  # mapped from "plugin"
    "name": "Compressor",         # mapped from "plugin"
    "settings": {"threshold": -18, "ratio": 4, "attack": 10, "release": 80}
                                  # mapped from "key_params"
}
```

The `extractor.py` module handles this conversion. The mapping is straightforward:
- `plugin` -> `plugin_name` and `name`
- `stage` -> `type`
- `why` -> `purpose`
- `key_params` -> `settings`
- `param_why` is preserved separately for the Teacher module (not sent to the builder)

---

## 10. Step-by-Step Implementation Plan

### Phase 1: Schema & Seed Data (Foundation)

**Nothing else works without valid JSON files.**

| Step | Task | Output |
|------|------|--------|
| 1.1 | Create `librarian/__init__.py` | Package init |
| 1.2 | Create `librarian/schema.py` | Schema dataclasses + `validate_song_file()` |
| 1.3 | Create `generate_song_data.py` (minimal) | CLI that reads prompt, calls LLM, validates, saves |
| 1.4 | Run generator on all 10 prompt files | 10 validated `.json` files in `docs/Research/` |
| 1.5 | Manual review of generated JSONs | Ensure quality of seed data |

**Exit criteria**: At least 3 valid, reviewed JSON files in `docs/Research/`.

### Phase 2: The Librarian (Query Engine)

**Build and test in isolation before wiring into the engine.**

| Step | Task | Output |
|------|------|--------|
| 2.1 | Create `librarian/index.py` | LibraryIndex class with search methods |
| 2.2 | Create `librarian/extractor.py` | Section extraction + builder format conversion |
| 2.3 | Create `librarian/session_context.py` | Active chain tracking singleton |
| 2.4 | Create `librarian/librarian_agent.py` | Main LibrarianAgent with `lookup()` method |
| 2.5 | Write standalone test script | Verify: load index, search, extract, convert |

**Exit criteria**: Can run `python -c "from librarian.index import LibraryIndex; idx = LibraryIndex(); print(idx.search_by_song('Ultralight Beam'))"` and get a valid result.

### Phase 3: Wire Into Engine (The Swap)

**This is where the runtime behavior changes.**

| Step | Task | Output |
|------|------|--------|
| 3.1 | Modify `agents/router_agent.py` | New intent types: LIBRARY_LOOKUP, TEACHER_QUERY |
| 3.2 | Modify `jarvis_engine.py` | `execute_research_vocal_chain` calls Librarian first |
| 3.3 | Modify `jarvis_tools.py` | New tool declarations for library operations |
| 3.4 | Add `execute_` handlers in engine | Handler functions for new tools |
| 3.5 | Integration test | Voice command -> Librarian -> ChainBuilder -> Ableton |

**Exit criteria**: "Load the chorus vocal chain from Ultralight Beam" works end-to-end
without any web calls.

### Phase 4: The Teacher (Explainability)

**Can be developed in parallel with Phase 3.**

| Step | Task | Output |
|------|------|--------|
| 4.1 | Create `librarian/teacher.py` | Explanation functions grounded in param_why |
| 4.2 | Wire `explain_parameter` tool | Engine handler that calls Teacher |
| 4.3 | Wire session context updates | LibrarianAgent sets context on chain load |
| 4.4 | Test Teacher flow | "Why 4:1?" returns grounded explanation |

**Exit criteria**: "Why did you set the ratio to 4:1?" returns the `param_why` text from
the JSON, rephrased by the LLM.

### Phase 5: Polish & Offline Generator

**Lowest priority — manual JSON creation works as a stopgap.**

| Step | Task | Output |
|------|------|--------|
| 5.1 | Enhance `generate_song_data.py` | Batch mode, better error handling |
| 5.2 | Optionally integrate old research modules | Use web scraping as data source for generator |
| 5.3 | Add `list_library` and `search_library_by_vibe` handlers | Full tool suite |
| 5.4 | Update `CLAUDE.md` protocol | Reflect new Librarian-first workflow |

---

## 11. File Structure Summary

### New Files to Create

```
librarian/                        # NEW PACKAGE
├── __init__.py                   # Package init, exports
├── schema.py                     # JSON schema validation (dataclasses + validator)
├── index.py                      # In-memory index over docs/Research/*.json
├── extractor.py                  # Section chain extraction + format conversion
├── librarian_agent.py            # Main query entry point
├── teacher.py                    # Grounded explanations from param_why
└── session_context.py            # Tracks currently-active chain for Teacher

generate_song_data.py             # NEW standalone CLI tool (offline enrichment)
```

### Files to Modify

```
agents/router_agent.py            # Add LIBRARY_LOOKUP, TEACHER_QUERY intents
jarvis_engine.py                  # execute_research_vocal_chain calls Librarian first
jarvis_tools.py                   # New tool declarations
```

### Data Files (Generated)

```
docs/Research/
├── ultralight_beam.json          # Generated from prompt 001
├── saint_pablo.json              # Generated from prompt 002
├── miami_leon_thomas.json        # Generated from prompt 003
├── back_to_me.json               # Generated from prompt 004
├── which_one_drake.json          # Generated from prompt 005
├── die_trying.json               # Generated from prompt 006
├── say_whats_real.json           # Generated from prompt 007
├── treasure_in_the_hills.json    # Generated from prompt 008
├── the_violence.json             # Generated from prompt 009
├── apocalypse.json               # Generated from prompt 010
├── *.prompt.txt                  # Existing prompts (kept as source)
├── *.docx                        # Existing raw research (kept as reference)
└── *.pdf                         # Existing reference docs (kept)
```

---

## 12. Key Interfaces and Data Contracts

### 12.1 LibrarianAgent.lookup() Return Contract

This is the primary interface between the Librarian and the engine. The return format must
be compatible with what `execute_research_vocal_chain()` already returns so downstream code
(chain building, parameter application) works unchanged.

```python
# On success:
{
    "success": True,
    "chain_spec": {
        "query": "Ultralight Beam chorus",
        "style_description": "Warm, intimate lead vocal sitting behind the choir",
        "devices": [
            {
                "plugin_name": "EQ Eight",
                "category": "cleanup",
                "parameters": {"high_pass_freq": 85, "low_mid_cut_freq": 300, ...},
                "purpose": "Clean up low-end before compression",
                "reasoning": "Removes rumble without thinning chest resonance",
                "confidence": 0.8,
                "sources": ["local_library"]
            },
            ...
        ],
        "confidence": 0.8,
        "sources": ["local_library"],
        "artist": "Kanye West",
        "song": "Ultralight Beam",
        "genre": "gospel hip-hop",
        "meta": {
            "cache_hit": True,
            "cache_type": "local_library",
            "source_file": "ultralight_beam.json",
            "section": "chorus",
            "llm_calls_used": 0
        }
    },
    "message": "Found in library: Ultralight Beam (chorus)",
    "query": "Ultralight Beam chorus",
    "confidence": 0.8,
    "source": "local_library",
    "song_file": "ultralight_beam.json",
    "section": "chorus",
    "param_why_available": True,
    "style_description": "Warm, intimate lead vocal sitting behind the choir",
    "cache_hit": True,
    "research_meta": {
        "cache_hit": True,
        "cache_type": "local_library",
        "llm_calls_used": 0
    },
    "next_step": "Present the found devices to the user for confirmation, then call apply_research_chain."
}

# On failure (song not in library):
{
    "success": False,
    "message": "'Unknown Song' is not in the local library. Available songs: [list]. Use generate_song_data.py to add it.",
    "query": "Unknown Song",
    "source": "local_library_miss"
}
```

### 12.2 Builder Format Contract

The `extractor.to_builder_format()` output must exactly match what
`PluginChainBuilder.build_chain_from_research()` expects:

```python
{
    "artist_or_style": "Kanye West",
    "track_type": "vocal",
    "chain": [
        {
            "type": "cleanup",          # from Device.stage
            "purpose": "Clean up...",    # from Device.why
            "plugin_name": "EQ Eight",  # from Device.plugin
            "name": "EQ Eight",         # from Device.plugin (duplicated for compat)
            "settings": {               # from Device.key_params
                "high_pass_freq": 85,
                "low_mid_cut_freq": 300,
                "low_mid_cut_gain": -2.5
            }
        },
        ...
    ],
    "confidence": 0.8,
    "sources": ["local_library"],
    "from_research": False,
    "from_library": True
}
```

### 12.3 Teacher Return Contract

```python
# explain_setting return:
{
    "found": True,
    "plugin": "Compressor",
    "param": "ratio",
    "value": 4,
    "reason": "4:1 tames peaks without pumping, keeps the vocal natural",
    "device_context": "Even out the vocal dynamics so it sits consistently with choir",
    "section_intent": "Warm, intimate lead vocal sitting behind the choir",
    "section": "verse",
    "song": "Ultralight Beam",
    "artist": "Kanye West"
}

# When no active chain or param not found:
{
    "found": False,
    "message": "No chain currently loaded. Load a chain first, then ask about parameters."
}
```

---

## 13. Open Questions and Future Considerations

### 13.1 Parameter Name Alignment

The JSON schema uses semantic parameter names (e.g., `high_pass_freq`, `ratio`, `attack`).
The `reliable_params.py` module uses device-specific parameter indices and mappings. The
`extractor.py` module may need a translation layer if the semantic names in the JSON don't
match what the parameter application pipeline expects.

**Action needed during Phase 2**: Audit the `key_params` names in the first generated JSONs
against `reliable_params.py`'s `SEMANTIC_PARAM_MAPPINGS` to identify any mismatches.

### 13.2 Handling Songs with Non-Standard Sections

Some songs may not have all four sections (verse, chorus, background_vocals, adlibs). For
example, an ambient track might only have a "verse" and "background_vocals". The schema
requires all four keys, but some may have empty chains.

**Decision**: All four keys are required. If a section doesn't apply, set `intent` to
"Not applicable for this song" and `chain` to an empty list `[]`.

### 13.3 Cross-Song Chain Mixing

User scenario: "Give me Kanye's vocal compression but with Billie Eilish's reverb settings."
This requires pulling devices from multiple song files and composing a hybrid chain.

**Current plan**: Not in scope for initial implementation. Future enhancement. For now, the
system loads one section from one song at a time. The user can manually modify after loading.

### 13.4 Library Growth Strategy

The library starts with ~10 songs. How it grows:

1. **Manual**: User runs `generate_song_data.py` per song
2. **Batch**: User provides a playlist/list of songs, generator processes them all
3. **Community**: Future possibility of sharing JSON files (they're self-contained)
4. **Import**: Future possibility of importing from other formats

### 13.5 Local LLM Swap (Future)

The architecture is designed to permit replacing the cloud LLM with a local one:

- The Librarian itself makes zero LLM calls (pure JSON lookup)
- The Teacher provides raw text that could be read directly (no LLM rephrasing needed)
- The only LLM dependency at runtime is the conversational voice interface
- Swapping to Ollama/llama.cpp would only require changing `jarvis_engine.py`'s session
  setup, not the Librarian

### 13.6 CLAUDE.md Protocol Updates

After implementation, the CLAUDE.md protocol needs updating:

- Step 3 (Inventory Verification) expands: check local library BEFORE checking plugins
- New step between Step 1 and Step 2: "Library Lookup" — check if the song exists locally
- The Thinking Protocol gains a "Library-First" mandate: always try the local DB before
  any other data source

---

## Appendix A: Existing Prompt Template Format

For reference, this is the exact prompt format used in the `.prompt.txt` seed files:

```
You are an elite vocal production analyst helping build an offline vocal-chain
database for an AI DAW assistant.
Song to analyze - ({title} - {artist})
Return EXACTLY one valid JSON object (no markdown, no commentary) that follows
this schema intent:
{"song":{"title":string,"artist":string,"year":integer|null,"genre":string|null},
"global_tags":string[],"sections":{"verse":{"intent":string,"chain":Device[]},
"chorus":{"intent":string,"chain":Device[]},"background_vocals":{"intent":string,
"chain":Device[]},"adlibs":{"intent":string,"chain":Device[]}},
"confidence":number(0..1),"notes":string,"sources":string[]}
Where each Device is:
{"plugin":string,"stage":"cleanup"|"tone"|"dynamics"|"space"|"creative"|"utility",
"key_params":{...},"param_why":{"param_name":"short reason"},"why":string}
Song to analyze:
- title: "{title}"
- artist: "{artist}"
- spotify_url: "{url}"
- optional context: "JarvisAbleton training export"
Hard requirements:
1) Include all 4 sections: verse, chorus, background_vocals, adlibs.
2) For each section, provide an ORDERED chain (5-10 devices typical).
3) key_params must be practical and machine-usable.
4) Prefer common plugins and/or stock-equivalent naming.
5) Do NOT fabricate false precision.
6) Add global_tags for retrieval.
7) Ensure param_why covers key_params entries.
Return JSON only.
```

---

## Appendix B: Critical File Quick Reference

| File | Lines | Role | Pivot Status |
|------|-------|------|-------------|
| `jarvis_engine.py` | ~3623 | Main orchestration | MODIFY |
| `jarvis_tools.py` | ~1159 | Gemini tool defs | MODIFY |
| `agents/router_agent.py` | ~220 | Intent routing | MODIFY |
| `plugins/chain_builder.py` | ~968 | Chain building | UNCHANGED |
| `research/research_coordinator.py` | ~1460 | Web research | BYPASSED |
| `research_bot.py` | ~2013 | Autonomous research | BYPASSED |
| `knowledge/artifact_chain_store.py` | ~258 | Artifact cache | DEPRECATED |
| `knowledge/plugin_semantic_kb.json` | ~1980 | Param semantics | UNCHANGED |
| `ableton_controls/controller.py` | ~1000 | OSC control | UNCHANGED |
| `ableton_controls/reliable_params.py` | ~1500 | Param normalization | UNCHANGED |
| `discovery/plugin_name_resolver.py` | ~600 | Name resolution | UNCHANGED |
| `discovery/device_intelligence.py` | ~1200 | Semantic params | UNCHANGED |

---

*This document serves as the single source of truth for the Jarvis-Ableton Local Librarian
architecture pivot. Any AI agent or developer working on this codebase should read this
document first to understand the project trajectory, confirmed decisions, and implementation
plan.*
