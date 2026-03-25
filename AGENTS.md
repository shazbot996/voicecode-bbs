# VoiceCode — Shared Project Context

Voice-driven CLI interface for interacting with AI agents (Claude, Gemini). Dictate prompts, refine them with AI, and execute them — all by voice. Optional Google Cast output to Nest/Chromecast speakers.

## Architecture

- **`voicecode_bbs.py`** — Thin entry-point wrapper that delegates to the `voicecode` package
- **`voicecode/`** — Main package: retro BBS-style voice-driven prompt engineering workshop
  - `app.py` — Application orchestrator and main curses loop
  - `constants.py`, `settings.py` — Configuration and runtime settings
  - `agent/` — Agent execution, prompt refinement, runner logic
  - `audio/` — Mic capture, VAD, audio utilities
  - `history/` — Prompt/response history browser and favorites
  - `providers/` — AI provider adapters (Claude, Gemini) with base class
  - `stt/` — Speech-to-text (faster-whisper)
  - `tts/` — Text-to-speech engine, voice config, Google Cast
  - `publish/` — Document publishing agents (9 types) with base class and prompt templates; `maintenance/` subpackage for document upkeep agents; `frontmatter.py` for YAML front matter parsing
  - `data/` — Built-in reference data (tool library definitions for Claude/Gemini)
  - `ui/` — Curses UI: panes, overlays, drawing, colors, animation, input handling, publish overlay, settings overlay

### Audio Pipeline

```
Mic (16kHz mono) → Silero VAD → faster-whisper STT → Review/Dictation Buffer → CLI stdin
```

### Key Parameters

- Sample rate: 16kHz, mono, 30ms blocks (480 samples)
- VAD threshold: 0.5, silence timeout: 1.5s, min speech: 0.3s
- Typewriter effect: time-based budget at configurable speed (default 200 chars/sec)

## Tech Stack

- **Python 3.12** — modular package structure under `voicecode/`, Makefile for common tasks
- **faster-whisper** — speech-to-text (models: tiny.en, base.en, small.en, medium.en)
- **silero-vad** / **torch** (CPU-only) — voice activity detection
- **sounddevice** / **numpy** — audio capture
- **piper-tts** — text-to-speech via `piper` CLI + `aplay`
- **pychromecast** — Google Cast device discovery and TTS broadcasting (optional)
- **curses** — terminal UI (BBS app)
- Dependencies in `requirements.txt`, virtualenv in `venv/`
- PyTorch installed CPU-only via `--index-url https://download.pytorch.org/whl/cpu`

## Running

```bash
# Activate venv
source venv/bin/activate

# Launch the BBS prompt workshop (any of these work)
python voicecode_bbs.py
python -m voicecode
make voicecode

# Run smoke tests
make test
```

## Conventions

- Models (VAD, Whisper) are lazy-loaded on first use for fast startup
- Background threads use `daemon=True`
- Prompt/response pairs saved to `{prompt_library}/voicecode/history/` as `NNN_slug_prompt.md` + `NNN_slug_response.md` (flat directory, sequentially indexed)
- Response files contain the TTS summary (or error) from the agent run
- Comment lines (`#`) in prompt files are stripped before execution
- TTS summaries extracted from `[TTS_SUMMARY]...[/TTS_SUMMARY]` blocks in agent responses
- Thread-safe UI updates via `queue.Queue`
- Session continuity across prompts via `--resume` with session IDs (Claude) or `--resume latest` (Gemini)
- Mid-recording shortcuts injection merges paths into transcripts using word-level timestamps
- App expects a working folder (typically repo root) with `prompts/` and `docs/` subfolders
- **Publish system** — `publish/` contains 9 specialized agents that generate structured docs: ADR, ARCH, PLAN, SPEC, GLOSSARY, CONSTRAINTS, CONVENTIONS, SCHEMA, README. Each agent subclasses `PublishAgent` (in `publish/base.py`) and has a prompt template loaded from `publish/prompts/<DOC_TYPE>.md` with `{scope}` and `{dest_folder}` placeholders. GLOSSARY, CONSTRAINTS, CONVENTIONS, SCHEMA, and README agents override `build_prompt()` to use a fixed destination (`context/` or project root). The publish overlay (`ui/publish_overlay.py`) is a two-step modal: pick doc type → pick destination folder under `docs/`. The built prompt is sent through the shared `execute_agent_prompt()` helper.
- **Maintenance system** — `publish/maintenance/` provides agents that operate on existing documents: Reconcile (check drift), Refresh (update in-place), Coverage (find gaps), plus CTX_DRIFT and CTX_UPDATE for root context files. Each subclasses `MaintenanceAgent` (in `publish/maintenance/base.py`) with prompt templates in `publish/maintenance/prompts/`. Accessible via `M` key in the document reader or from the document actions overlay in the browser. Uses the same `execute_agent_prompt()` pipeline as publish.
- **Document type styling** — Published documents have YAML front matter with a `type` field parsed by `publish/frontmatter.py`. The browser shows color-coded `[TYPE]` badges and the document reader uses type-based border colors. Root context files (AGENTS.md, CLAUDE.md, GEMINI.md) appear at the top of the Documents tab with `[CONTEXT]` badges.
- Smoke test suite in `tests/` (pytest); `requirements-dev.txt` has test dependencies; no CI currently

## BBS App Three-Pane Layout

```
┌── PROMPT BROWSER ──────┐┌── AGENT TERMINAL ──────────────┐
│  Refined prompt text    ││  Agent response streams here   │
│  ready to review/edit  E>│  with typewriter effect...     │
├────────=^R^=───────────┤│                                │
┌── DICTATION BUFFER ────┐│                                │
│  ◌ voice fragments    D>│                                │
│  ◌ accumulate here     ││                                │
└────────────────────────┘└────────────────────────────────┘
```

- **Prompt Browser** (top-left) — View and browse refined prompts; history entries show combined prompt + response
- **Dictation Buffer** (bottom-left) — Voice fragments accumulate in real-time
- **Agent Terminal** (right, full height) — ZMODEM animation, then typewriter-streamed responses with activity spinner and stall detection
- Data-flow hints: `=^R^=` (refine up), `E>` (execute right), `D>` (direct right)

## BBS App Keyboard Controls

| Key | Action |
|-----|--------|
| SPACE | Toggle recording |
| R | Refine fragments into prompt |
| S | Save current prompt to history |
| E | Execute current prompt |
| D | Direct execute (skip refinement) |
| F | Toggle favorites view / add history prompt to favorites |
| 1-9, 0 | Quick-load favorites slot 1-10 |
| N | New prompt (clear buffer, keep session) |
| U | Undo last dictation entry |
| C | Clear dictation buffer |
| Enter | Type text directly into dictation buffer (Enter to submit, ESC to cancel) |
| Tab | Browser overlay — 4 tabs: Shortcuts, Project Folders, Documents, Tools (works mid-recording) |
| ←/→ | Browse prompt history |
| ↑/↓ | Scroll prompt pane |
| Home | Return to current prompt |
| PgUp/PgDn | Scroll agent terminal |
| End | Scroll agent terminal to bottom |
| O | Settings / voice config |
| K | Kill running agent |
| W | New session (clear conversation context) |
| P | Publish document (open publish overlay) |
| Y | Replay TTS summary |
| M | Toggle AI provider (Claude/Gemini) |
| T | Cycle status bar tip |
| [/] | Cycle TTS voice |
| H | Help overlay |
| ESC | Escape menu (settings, help, about, restart, quit) |
| A | About / title screen |
| X | Restart application |
| Q | Quit |
