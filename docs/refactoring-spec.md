---
type: spec
title: "VoiceCode Refactoring Spec — Multi-File Architecture"
scope: "Full application — ~/projects/voicecode"
date: 2026-03-19
---

> **Status:** Draft — for review and discussion before implementation.

## Motivation

`voicecode_bbs.py` is 5,850+ lines in a single file. While the single-file approach
kept things simple early on, the codebase has grown to the point where navigation,
readability, and independent reasoning about subsystems are suffering. This spec
proposes a modular layout that groups code by responsibility while avoiding
over-fragmentation.

## Guiding Principles

1. **One concern per module.** Each file should have a clear, single reason to exist.
2. **Minimize cross-module state.** Shared state flows through well-defined interfaces
   (constructor injection, queues), not global variables.
3. **Keep files in the 200–600 line range.** Smaller files are fine; larger files should
   have a strong justification.
4. **No behavioral changes.** This is a pure structural refactor — identical functionality
   before and after.
5. **Incremental migration.** The plan is designed so modules can be extracted one at a
   time, with the app remaining functional after each step.

## Proposed Directory Layout

```
voicecode/
├── __init__.py              # Package marker (empty or minimal)
├── __main__.py              # Entry point: argparse, curses.wrapper, launches BBSApp
├── app.py                   # BBSApp core: run(), main loop, _process_ui_queue()
├── constants.py             # Shared constants (sample rates, thresholds, paths, version)
├── settings.py              # Settings/shortcuts persistence (load/save JSON, defaults)
├── providers/
│   ├── __init__.py          # Provider registry, _detect_providers(), _get_provider_by_name()
│   ├── base.py              # CLIProvider abstract base class
│   ├── claude.py            # ClaudeProvider
│   └── gemini.py            # GeminiProvider
├── audio/
│   ├── __init__.py
│   ├── capture.py           # Mic recording, audio_callback, sounddevice stream mgmt
│   ├── vad.py               # Silero VAD model loading, voice activity detection
│   └── utils.py             # Stderr suppression, device checking, safe playback
├── stt/
│   ├── __init__.py
│   ├── whisper.py           # faster-whisper model loading, transcribe(), transcribe_with_timestamps()
│   └── live.py              # Live transcription loop, merge_injections()
├── tts/
│   ├── __init__.py
│   ├── engine.py            # speak_text(), stop_speaking(), piper process mgmt
│   ├── voices.py            # Voice presets, cycling, download, cleanup
│   └── cast.py              # Google Cast discovery, _cast_tts_to_devices()
├── ui/
│   ├── __init__.py
│   ├── panes.py             # TextPane class
│   ├── colors.py            # Color pair definitions, _init_colors()
│   ├── drawing.py           # _draw() main render, header, dividers, status bars
│   ├── overlays.py          # Help, about, escape menu, settings, folder slug, shortcut editor
│   ├── input.py             # _handle_input() dispatcher, paste handling
│   └── animation.py         # ZMODEM frames, _draw_agent_xfer(), typewriter effect
├── agent/
│   ├── __init__.py
│   ├── runner.py            # _run_agent() stream processing, event parsing
│   ├── refine.py            # refine_with_llm(), _start_refine(), _do_refine()
│   └── execution.py         # _execute_prompt(), _execute_raw(), _save_prompt()
└── history/
    ├── __init__.py
    ├── browser.py           # Prompt history scanning, loading, navigation
    └── favorites.py         # Favorites slot management (load/save/assign/quick-load)

voicecode_bbs.py             # Thin wrapper: `from voicecode.__main__ import main; main()`
```

**Total: ~25 files** across 8 directories (including `__init__.py` files).

## Module Responsibilities — Detail

### `__main__.py` (~50 lines)
- Argument parsing (currently inlined in the bottom of the monolith)
- `curses.wrapper()` call
- Signal handling setup
- Imports and launches `BBSApp.run()`

### `app.py` (~400–500 lines)
The application shell. Owns:
- `BBSApp.__init__()` — but delegates subsystem creation to imported modules
- `run()` — main loop, key dispatch (delegates to `ui/input.py`)
- `_process_ui_queue()` — drains the cross-thread queue
- `_process_typewriter()` — ticks the typewriter buffer
- References to subsystem objects (providers, recorder, TTS engine, etc.) as instance attributes

This is the "wiring" module — it connects subsystems but contains minimal logic of its own.

### `constants.py` (~60 lines)
- `SAMPLE_RATE`, `CHANNELS`, `BLOCK_SIZE`
- `VAD_THRESHOLD`, `SILENCE_AFTER_SPEECH_SEC`, `MIN_SPEECH_DURATION_SEC`
- `SETTINGS_DIR`, `SETTINGS_FILE`, `SHORTCUTS_FILE`
- `TTS_PROMPT_SUFFIX`
- `BANNER` text

### `settings.py` (~120 lines)
- `_load_settings()`, `_save_settings()`
- `_load_shortcuts()`, `_save_shortcuts()`
- `_persist_setting()` helper
- Settings path editing logic (`_start_editing_*`, `_commit_*`)
- Default settings values

### `providers/` (~300 lines total)

| File | Lines (est.) | Content |
|------|-------------|---------|
| `base.py` | ~60 | `CLIProvider` ABC with `_get_base_cmd()`, `is_installed()`, `get_version()`, abstract parse methods |
| `claude.py` | ~90 | `ClaudeProvider` — stream-json event parsing, `--resume` session handling |
| `gemini.py` | ~80 | `GeminiProvider` — `--yolo` mode, different event structure |
| `__init__.py` | ~30 | `_detect_providers()`, `_get_provider_by_name()` registry |

### `audio/` (~200 lines total)

| File | Lines (est.) | Content |
|------|-------------|---------|
| `capture.py` | ~80 | `_start_recording()`, `_stop_recording()`, `_audio_callback()`, sounddevice stream lifecycle |
| `vad.py` | ~40 | `get_vad_model()`, Silero lazy-loading |
| `utils.py` | ~60 | `_suppress_stderr()`, `_restore_stderr()`, `_check_audio_input_device()`, `_safe_sd_play()` |

### `stt/` (~150 lines total)

| File | Lines (est.) | Content |
|------|-------------|---------|
| `whisper.py` | ~50 | `get_whisper_model()`, `transcribe()`, `transcribe_with_timestamps()` |
| `live.py` | ~80 | `_live_transcribe_loop()`, `_do_final_transcribe()`, `_merge_injections()` |

### `tts/` (~400 lines total)

| File | Lines (est.) | Content |
|------|-------------|---------|
| `engine.py` | ~100 | `speak_text()`, `stop_speaking()`, piper subprocess management |
| `voices.py` | ~120 | `PIPER_VOICES`, `VOICE_PRESETS`, `cycle_tts_voice()`, `download_all_voices()`, `download_single_voice_model()`, `delete_unused_voices()` |
| `cast.py` | ~150 | `CAST_AVAILABLE`, `_discover_cast_devices()`, `_cast_tts_to_devices()` |

### `ui/` (~2,000 lines total — the largest subsystem)

| File | Lines (est.) | Content |
|------|-------------|---------|
| `panes.py` | ~130 | `TextPane` class (content management, scrolling, rendering) |
| `colors.py` | ~60 | 23 color pair definitions, `_init_colors()` |
| `drawing.py` | ~400 | `_draw()` main render function, header, dividers, pane layout, status bars |
| `overlays.py` | ~600 | `_draw_help_overlay()`, `_draw_about_overlay()`, `_draw_escape_menu()`, `_draw_settings_overlay()`, `_draw_folder_slug_overlay()`, shortcut editor |
| `input.py` | ~500 | `_handle_input()` dispatcher, `_read_paste_content()`, `_inject_paste()`, modal key routing |
| `animation.py` | ~150 | `ZMODEM_FRAMES`, `_draw_agent_xfer()`, `_emit_typewriter()`, `_flush_tts_detect_buf()` |

**Note on `overlays.py`:** At ~600 lines this is the largest proposed file. The settings
overlay alone is ~270 lines. If it feels too large, the settings overlay and its submenu
builders could be split into `ui/settings_overlay.py` (~400 lines) separately from a
smaller `ui/overlays.py` (~200 lines) for help/about/escape/folder. Recommend deferring
this sub-split until after the initial extraction to see how it feels.

### `agent/` (~500 lines total)

| File | Lines (est.) | Content |
|------|-------------|---------|
| `runner.py` | ~300 | `_run_agent()` — stream processing loop, event parsing, stall detection, context metering |
| `refine.py` | ~60 | `refine_with_llm()`, `_start_refine()`, `_do_refine()` |
| `execution.py` | ~120 | `_execute_prompt()`, `_execute_raw()`, `_save_prompt()`, `_save_to_history()`, `_save_response_to_history()` |

### `history/` (~300 lines total)

| File | Lines (est.) | Content |
|------|-------------|---------|
| `browser.py` | ~200 | `_scan_history_prompts()`, `_load_browser_prompt()`, `_current_browser_list()`, `_set_dictation_info()`, `_set_agent_welcome()`, `_get_active_prompt_text()`, `_slug_from_text()`, `_next_seq()` |
| `favorites.py` | ~120 | `_load_favorites_slots()`, `_save_favorites_slots()`, `_add_to_favorites()`, `_assign_to_fav_slot()`, `_remove_from_favorites()`, `_quick_load_favorite()`, `_key_to_fav_slot()` |

## Handling `BBSApp` — The Central Challenge

`BBSApp` is ~4,700 lines with 250+ instance attributes. The key decision is how to
decompose it without creating an unmanageable web of cross-references.

### Recommended approach: Composition with mixins for the transition period

**Phase 1 — Extract pure functions first.** Many functions in `BBSApp` don't actually need
`self` or need only 1-2 attributes passed as arguments. These become standalone module
functions (TTS, audio, providers, history I/O, etc.). This is the safest first step and
covers roughly half the code.

**Phase 2 — Extract UI subsystems as helper objects.** The drawing and overlay code
references `self` heavily (panes, colors, dimensions, state flags). Rather than passing
20+ arguments, create helper objects that receive a reference to the app:

```python
# ui/overlays.py
class OverlayRenderer:
    def __init__(self, app):
        self.app = app

    def draw_help(self):
        # accesses self.app.stdscr, self.app.width, etc.
        ...
```

`BBSApp.__init__` creates these helpers:
```python
self.overlays = OverlayRenderer(self)
self.input_handler = InputHandler(self)
```

This keeps the wiring simple and avoids passing dozens of parameters, while still
physically separating the code into focused files.

**Phase 3 — Reduce `BBSApp` instance variables.** Once subsystems are extracted, group
related state into small data classes (e.g., `RecordingState`, `BrowserState`,
`AgentState`) to shrink the flat attribute namespace.

## Migration Order

Recommended extraction sequence, from least coupled to most coupled:

| Step | Module(s) | Risk | Notes |
|------|-----------|------|-------|
| 1 | `constants.py` | Trivial | Pure data, no dependencies |
| 2 | `providers/` | Low | Self-contained classes, clean interfaces |
| 3 | `audio/utils.py` | Low | Standalone utility functions |
| 4 | `audio/vad.py`, `stt/whisper.py` | Low | Lazy-loaded singletons |
| 5 | `tts/voices.py`, `tts/engine.py` | Low | Global state but well-isolated |
| 6 | `tts/cast.py` | Low | Optional subsystem, already loosely coupled |
| 7 | `settings.py` | Low | File I/O, minimal coupling |
| 8 | `ui/panes.py`, `ui/colors.py` | Low | `TextPane` is self-contained |
| 9 | `ui/animation.py` | Medium | Typewriter reads/writes BBSApp state |
| 10 | `history/` | Medium | References BBSApp for paths and pane updates |
| 11 | `stt/live.py`, `audio/capture.py` | Medium | Threaded, touches recording state |
| 12 | `agent/` | Medium | Core logic, threading, event parsing |
| 13 | `ui/drawing.py` | High | Deep coupling to all app state |
| 14 | `ui/overlays.py` | High | Complex modal state, many cross-references |
| 15 | `ui/input.py` | High | Touches everything; extract last |
| 16 | `app.py` + `__main__.py` | Final | What remains of BBSApp becomes the app shell |

## Backwards Compatibility

- `voicecode_bbs.py` remains as a thin entry point (`python voicecode_bbs.py` still works)
- `python -m voicecode` also works via `__main__.py`
- No changes to CLI arguments, settings files, history format, or any user-facing behavior

## Open Questions

1. **`ui/overlays.py` granularity** — Should the settings overlay (with its submenu
   builders) be its own file from the start, or wait until after initial extraction?
2. **State dataclasses** — Should we introduce `RecordingState`, `BrowserState`, etc.
   during this refactor or defer to a follow-up?
3. **Testing** — Should we add basic smoke tests as part of this refactor to catch
   regressions, or treat testing as a separate initiative?
4. **Import structure** — Should modules import from each other freely, or should we
   enforce a strict dependency direction (e.g., `ui` → `agent` → `tts` → `audio` but
   never the reverse)?
