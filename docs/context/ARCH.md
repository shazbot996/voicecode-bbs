---
title: VoiceCode BBS Architecture
scope: Full application — ~/projects/voicecode
date: 2026-03-21
---

## 1. Overview

VoiceCode BBS is a voice-driven terminal application for interacting with AI coding agents (Claude, Gemini). Users dictate speech fragments, refine them into polished prompts via AI-assisted synthesis, and execute those prompts against AI agent CLIs — all from a retro BBS-themed curses interface with three panes. Optional text-to-speech (Piper TTS) and Google Cast output provide audio feedback of agent responses.

The architecture follows a **single-process, event-driven composition pattern** built on Python curses. The main thread owns the UI and runs a tight 60fps event loop, while background daemon threads handle audio capture, speech-to-text, prompt refinement, agent execution, and TTS playback. Cross-thread communication is centralized through a single `queue.Queue`, keeping the rendering path lock-free and the threading model simple.

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Entry Points                              │
│  voicecode_bbs.py / python -m voicecode ──► __main__.py          │
└────────────────────────────┬────────────────────────────────────┘
                             │ creates
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     BBSApp  (app.py)                             │
│  Owns all state, wires together helpers via composition          │
│                                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
│  │ UI Layer │ │  Agent   │ │  Audio   │ │   Persistence    │   │
│  │          │ │  Layer   │ │  Layer   │ │                  │   │
│  │ drawing  │ │ runner   │ │ capture  │ │ settings.py      │   │
│  │ input    │ │ execution│ │ vad      │ │ history/browser  │   │
│  │ panes    │ │ refine   │ │ whisper  │ │ history/favorites│   │
│  │ overlays │ │ providers│ │          │ │                  │   │
│  │ animation│ │          │ │          │ │                  │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘   │
│                                                                  │
│  ┌──────────┐ ┌──────────────┐                                  │
│  │TTS Layer │ │  Publish     │                                  │
│  │ engine   │ │  agents      │                                  │
│  │ voices   │ │  (ARCH, ...) │                                  │
│  │ cast     │ │              │                                  │
│  └──────────┘ └──────────────┘                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Layers

1. **Entry layer** — `voicecode_bbs.py` and `voicecode/__main__.py` parse args, instantiate `BBSApp`, wrap it in `curses.wrapper`, and handle restart via `os.execv`.
2. **Orchestration** — `BBSApp` (`voicecode/app.py`) is the central God object. It holds all mutable state and composes ~12 helper objects that each own a slice of behavior.
3. **UI** — `voicecode/ui/` renders three panes plus modal overlays, handles keyboard dispatch, and drives animations. Everything renders synchronously on the main thread.
4. **Agent** — `voicecode/agent/` manages prompt refinement (via lightweight LLM call) and full agent execution (streaming subprocess with JSON event parsing).
5. **Audio** — `voicecode/audio/` captures mic input via sounddevice, runs Silero VAD, and `voicecode/stt/` transcribes with faster-whisper.
6. **TTS** — `voicecode/tts/` synthesizes speech via Piper CLI and optionally casts to Google Cast devices.
7. **Providers** — `voicecode/providers/` abstracts CLI differences between Claude and Gemini behind `CLIProvider`.
8. **Persistence** — `voicecode/settings.py` manages JSON settings and text shortcuts; `voicecode/history/` handles prompt/response file storage and favorites slots.
9. **Publish** — `voicecode/publish/` provides templated prompt agents for generating structured documents (currently ARCH.md).

### Communication

All inter-thread communication flows through `BBSApp.ui_queue` (a `queue.Queue`). Background threads post tuples like `("fragment", text)`, `("agent_state", AgentState.DONE)`, or `("typewriter_char", ch)`. The main loop drains this queue every frame in `process_ui_queue()`.

## 3. Component Deep-Dive

### 3.1 BBSApp (`voicecode/app.py`)

**Purpose**: Central orchestrator. Holds all application state and wires together the helper composition.

**Key members**:
- Three `TextPane` instances: `prompt_pane`, `dictation_pane`, `agent_pane`
- `ui_queue` — the single cross-thread communication channel
- `fragments` — list of dictated speech fragments awaiting refinement
- `current_prompt` — the refined prompt text
- `session_id` / `session_turns` — AI provider session continuity state
- 12 composed helpers (drawing, overlays, settings_overlay, publish_overlay, input_handler, animation, runner, execution, browser, favorites, recording_helper)

**Internal structure**: The `__init__` method runs ~300 lines, initializing all state and helpers. The `run()` method is the main loop: load models, then loop `process_ui_queue() → process_typewriter() → draw() → handle_input()`. The `process_ui_queue()` method is the central dispatcher that translates background thread messages into state mutations.

**Why a God object?** Curses applications are inherently stateful and tightly coupled to screen geometry. The composition pattern (helpers that receive `self` as `app`) allows splitting behavior across files without the overhead of a full dependency injection framework. Each helper can read and mutate `app` state directly, which is pragmatic for a single-user desktop tool.

### 3.2 UI Layer (`voicecode/ui/`)

**`panes.py` — `TextPane`**: A reusable scrollable text region with box-drawing borders, scroll indicators, line-level color overrides, and a welcome art mode. Supports both bulk `set_text()` and character-at-a-time `add_char_to_last_line()` for the typewriter effect. Trims at `MAX_LINES` (2000 for agent, 500 for dictation) to bound memory.

**`drawing.py` — `DrawingHelper`**: The main `draw()` method renders the full three-pane layout every frame: header bar, info divider, prompt browser (top-left), dictation buffer (bottom-left), agent terminal (right, full height), data-flow hint labels (`=^R^=`, `E>`, `D>`), favorites indicators, context meter, help bar, status bar. Overlays are drawn last so they layer on top.

**`input.py` — `InputHandler`**: Routes keystrokes through a priority chain: bracketed paste detection → overlay-specific handlers (help, about, escape menu, settings, publish, shortcuts, shortcut editor) → confirmation dialogs → typing mode → recording mode → normal mode. Normal mode dispatches ~25 hotkeys (SPACE, R, E, D, N, S, F, etc.). Also handles buffer persistence to disk for crash recovery.

**`overlays.py` — `OverlayRenderer`**: Renders help, about, escape menu, shortcuts browser (categorized: Shortcuts / Project Folders / Documents), and shortcut editor as modal box-drawing overlays.

**`animation.py` — `AnimationHelper`**: Two responsibilities: (1) the ZMODEM transfer animation shown during the 3-second delay before agent output, and (2) the time-budgeted typewriter effect that emits characters at a configurable rate (default 200 chars/sec) from `typewriter_queue`.

**`colors.py`**: Defines 25 named color pair constants and `init_colors()` which maps them to curses color pairs. Uses 256-color mode when available (dark blue background for headers/status).

**`settings_overlay.py` — `SettingsOverlay`**: A data-driven settings panel with sections, toggle items, text-editable fields, and submenus for voice settings, AI models, TTS options, Cast devices, and test tools. Builds a list of item dicts that drive both rendering and input handling.

**`publish_overlay.py` — `PublishOverlay`**: A two-step modal (document type → destination folder) that feeds into the publish agent pipeline. Shows a reference docs tree on the left and a selection list on the right.

### 3.3 Agent Layer (`voicecode/agent/`)

**`execution.py` — `ExecutionHelper`**: Orchestrates the full prompt lifecycle: `execute_prompt()` saves to history, triggers the ZMODEM animation, and launches the agent thread; `execute_raw()` skips refinement; `start_refine()` / `do_refine()` runs prompt refinement in a background thread; `save_to_history()` / `save_response_to_history()` persist prompt/response pairs.

**`runner.py` — `RunnerHelper`**: The core agent execution engine. `run_agent()` runs in a background thread: waits 3 seconds for the ZMODEM animation, then spawns the provider CLI as a subprocess with `--output-format stream-json`. Reads stdout line-by-line, parsing JSON events through the provider's event parsers. Text goes to `emit_typewriter()` which detects `[TTS_SUMMARY]` markers and switches typewriter color. Tool uses, thinking, and tool results get formatted summaries. After completion, extracts the TTS summary and speaks it. `kill_agent()` sends SIGTERM then SIGKILL after 3 seconds.

**`refine.py` — `refine_with_llm()`**: A stateless function that builds either `INITIAL_REFINE_PROMPT` or `MODIFY_REFINE_PROMPT` from `constants.py`, runs the provider CLI synchronously with `subprocess.run()`, and returns the refined text.

### 3.4 Provider Layer (`voicecode/providers/`)

**`base.py` — `CLIProvider`**: Abstract base with `build_refine_cmd()`, `build_execute_cmd()`, and event parsing methods (`parse_init_event`, `parse_text_event`, `parse_thinking_event`, `parse_tool_result_event`, `parse_context_usage`, `is_result_event`). Also provides `is_installed()` (checks `shutil.which`) and `get_version()`.

**`claude.py` — `ClaudeProvider`**: Builds `claude --print --verbose --output-format stream-json --dangerously-skip-permissions [-p prompt]` for execution. Session continuity via `--resume <session_id>`. Parses Claude's JSON streaming format: `type: "system"` for init, `type: "assistant"` for text/tool_use blocks, `type: "user"` for tool results, `type: "result"` for final output and context usage.

**`gemini.py` — `GeminiProvider`**: Builds `gemini --yolo -o stream-json [-p prompt]`. Supports `--proxy=false` and `--resume <session_id>`. Parses Gemini's streaming JSON: `type: "message"` with `role: "assistant"` for text, `role: "tool"` for tool results. Context usage from `stats.models.*.tokens`.

**`__init__.py`**: Singleton registry of provider instances. `detect_providers()` returns installed ones; `get_provider_by_name()` does case-insensitive lookup.

### 3.5 Audio Pipeline (`voicecode/audio/`, `voicecode/stt/`)

**`capture.py` — `RecordingHelper`**: Opens a sounddevice `InputStream` at 16kHz/mono/30ms blocks. The `audio_callback` appends frames to `audio_frames` under `audio_lock`. A `live_transcribe_loop` thread transcribes accumulated audio every 2 seconds for real-time preview in the dictation pane. On stop, `do_final_transcribe` runs full-audio transcription for best accuracy. Supports mid-recording injections (shortcut strings inserted at timestamp-accurate positions using word-level timestamps).

**`vad.py`**: Lazy-loads Silero VAD model via `torch.hub.load()`. Forces CPU-only via `CUDA_VISIBLE_DEVICES=""`.

**`utils.py`**: Suppresses ALSA/PortAudio stderr noise that would corrupt curses by redirecting fd 2 to /dev/null. Provides `check_audio_input_device()` for pre-flight validation and `safe_sd_play()` for thread-safe audio playback.

**`whisper.py`**: Lazy-loads faster-whisper model (configurable: tiny.en through medium.en, default base.en, CPU int8). `transcribe()` returns text; `transcribe_with_timestamps()` returns text plus word-level `(start, end, word)` tuples for injection merging.

### 3.6 TTS Layer (`voicecode/tts/`)

**`engine.py`**: `speak_text()` runs Piper TTS in a background thread: pipes text to `piper --model <voice> --output-raw`, reads PCM bytes, applies volume gain, plays via `safe_sd_play()` at 22050Hz. `extract_tts_summary()` uses regex to pull `[TTS_SUMMARY]...[/TTS_SUMMARY]` blocks. `stop_speaking()` kills any active TTS process.

**`voices.py`**: Manages 10 Piper voice models (en_US and en_GB variants). Persists selection to settings. `cycle_tts_voice()` rotates through the list. `download_all_voices()` and `download_single_voice_model()` fetch models via piper's `download_voice()`. `delete_unused_voices()` cleans up all except the current model.

**`cast.py`**: Google Cast integration. `discover_cast_devices()` uses pychromecast to scan the LAN. `cast_tts_to_devices()` generates a WAV via Piper, starts a temporary HTTP server, and streams the audio URL to selected Chromecast/Nest devices. Saves and restores device volume levels. Polls playback status with a 60-second timeout.

### 3.7 History & Favorites (`voicecode/history/`)

**`browser.py` — `BrowserHelper`**: Scans `{history_base}/NNN_slug_prompt.md` files. `load_browser_prompt()` renders the prompt pane content based on current view (active prompt, history entry with paired response, or favorites). `get_active_prompt_text()` returns the current executable prompt from whichever source is active.

**`favorites.py` — `FavoritesHelper`**: Manages 10 numbered slots (keys 1-9, 0) stored as file paths in settings JSON. Supports quick-load, add-with-slot-selection, overwrite confirmation, and removal. Favorites reference history files by path, so they survive across sessions.

### 3.8 Publish System (`voicecode/publish/`)

**`base.py` — `PublishAgent`**: Abstract base with `doc_type`, `prompt_template`, and `build_prompt(scope, dest_folder)`. Templates use `{scope}` and `{dest_folder}` placeholders.

**`arch.py` — `ArchAgent`**: Concrete agent for generating architecture documents. Contains a detailed prompt template that instructs the AI to analyze code and produce a structured ARCH.md with 9 sections.

**`publish_overlay.py`**: The UI surface. Two-step modal: select document type (only ARCH is currently implemented; 12 others are planned), then select destination folder (context/, decisions/, plans/, specs/, runbooks/). Feeds the assembled prompt into the standard `runner.run_agent()` pipeline.

### 3.9 Settings & Persistence (`voicecode/settings.py`)

**Purpose**: JSON-based settings storage at `settings/settings.json` and line-based shortcuts at `settings/shortcuts.txt`.

**Key functions**: `load_settings()` / `save_settings()` — full read/write; `persist_setting(key, val)` — atomic single-key update; `load_shortcuts()` / `save_shortcuts()` — shortcut string list; `slug_from_text()` — filesystem-safe slug generation; `next_seq()` — sequential numbering for history files.

## 4. Data Flow

### 4.1 Voice-to-Prompt (Happy Path)

```
1. User presses SPACE → RecordingHelper.start_recording()
   → Opens sounddevice InputStream (16kHz mono)
   → Starts live_transcribe_loop thread

2. Audio callback accumulates frames in audio_frames[]
   → Every 2s, live_transcribe_loop transcribes accumulated audio
   → Posts ("live_preview", text) to ui_queue
   → Main thread shows "◌ preview..." in dictation pane

3. User presses SPACE again → stop_recording()
   → Joins live transcribe thread
   → Launches do_final_transcribe in background thread
   → Full-audio transcription with optional injection merging
   → Posts ("fragment", text) to ui_queue
   → Fragment added to self.fragments[] and dictation pane

4. User presses R → ExecutionHelper.start_refine()
   → Background thread calls refine_with_llm()
   → Builds INITIAL_REFINE_PROMPT or MODIFY_REFINE_PROMPT
   → Runs provider CLI synchronously (subprocess.run)
   → Posts ("refined", result) to ui_queue
   → current_prompt updated, fragments cleared, prompt pane refreshed
```

### 4.2 Prompt Execution

```
1. User presses E → ExecutionHelper.execute_prompt()
   → Saves prompt to history (NNN_slug_prompt.md)
   → Sets AgentState.DOWNLOADING, clears agent pane
   → Starts ZMODEM animation (3-second visual delay)
   → Launches RunnerHelper.run_agent() in daemon thread

2. run_agent() builds CLI command via provider.build_execute_cmd()
   → Spawns subprocess with stream-json output
   → Reads stdout line-by-line via select() with 0.5s timeout

3. Each JSON event is parsed through provider-specific methods:
   → parse_init_event → captures session_id
   → parse_text_event → text goes to emit_typewriter()
   → parse_thinking_event → prefixed with ".." markers
   → parse_tool_result_event → prefixed with "◀"
   → is_result_event → final result, extracts context usage

4. emit_typewriter() detects [TTS_SUMMARY] markers:
   → Before marker: chars queued normally
   → Inside marker: color switched to CP_TTS (white)
   → After marker: color reset

5. Main thread's process_typewriter() dequeues characters
   → Time-budgeted at _typewriter_chars_per_sec (default 200)
   → Each char appended to agent_pane via add_char_to_last_line()

6. After subprocess ends:
   → TTS summary extracted, spoken via Piper
   → Optionally cast to Google Cast devices
   → Response saved to NNN_slug_response.md
   → AgentState set to DONE
```

### 4.3 Mid-Recording Shortcut Injection

```
1. User presses Tab while recording → shortcuts browser opens
2. User selects a shortcut/folder/document → Enter
3. Injection recorded as (audio_seconds, text) tuple
4. On stop: transcribe_with_timestamps() gets word-level timings
5. merge_injections() interleaves injection text at correct positions
6. Final merged text becomes the fragment
```

## 5. Control Flow & Lifecycle

### Startup

1. `__main__.py:main()` parses args, creates `BBSApp()`, calls `curses.wrapper(app.run)`.
2. `BBSApp.__init__()`:
   - Creates three `TextPane` instances with welcome art
   - Loads settings from `settings/settings.json`
   - Derives working directory paths (`save_base`, `history_base`)
   - Scans history prompts, loads favorites slots
   - Detects available AI providers, restores saved provider choice
   - Initializes all state variables (recording, agent, session, animation, overlay states)
   - Composes 12 helper objects, each receiving `self`
3. `BBSApp.run(stdscr)`:
   - Suppresses stderr (ALSA/PortAudio noise)
   - Initializes curses colors, disables cursor, enables nodelay + 16ms timeout
   - Enables bracketed paste mode (`ESC[?2004h`)
   - Shows loading screen, lazy-loads Silero VAD and Whisper models
   - Loads browser prompt, dictation info, persisted buffer, agent welcome

### Main Loop

```python
while self.running:
    self.process_ui_queue()       # drain cross-thread messages
    self.animation.process_typewriter()  # emit budgeted chars
    self.drawing.draw()           # full-screen render
    self.input_handler.handle_input()    # non-blocking getch + dispatch
```

The loop runs at ~60fps (16ms curses timeout). `getch()` returns -1 when no key is pressed, so the loop spins continuously for smooth animations.

### Shutdown

1. User presses Q (or X for restart) → sets `self.running = False`
2. Loop exits → `finally` block disables bracketed paste mode
3. `curses.wrapper` restores terminal state
4. `__main__.py` calls `restore_stderr()`
5. If `app.restart` is True, `os.execv()` re-launches the process

### Background Threads

All background threads use `daemon=True` so they die with the main process:

| Thread | Trigger | Purpose |
|--------|---------|---------|
| `live_transcribe_loop` | SPACE (start recording) | Periodic interim transcription every 2s |
| `do_final_transcribe` | SPACE (stop recording) | Full-accuracy final transcription |
| `do_refine` | R key | LLM refinement via synchronous subprocess |
| `run_agent` | E/D/Publish | Streaming agent execution + event parsing |
| `_reap` (kill_agent) | K key | SIGTERM → wait 3s → SIGKILL cleanup |
| `speak_text._run` | Agent completion | Piper TTS synthesis + playback |
| `cast_tts_to_devices._run` | Agent completion (if Cast enabled) | WAV generation + HTTP server + Cast |
| `discover_cast_devices` | Settings → Cast submenu | pychromecast LAN scan |
| `download_all_voices._run` | Settings → TTS submenu | Batch voice model download |

## 6. State Management

### In-Memory State

All mutable state lives on the `BBSApp` instance. Key categories:

- **Prompt state**: `fragments[]`, `current_prompt`, `prompt_version`, `prompt_saved`, `executed_prompt_text`
- **Agent state**: `agent_state` (enum: IDLE/DOWNLOADING/RECEIVING/DONE), `agent_process`, `session_id`, `session_turns`, `context_tokens_used`
- **Recording state**: `recording`, `audio_frames[]`, `audio_lock`, `_recording_injections[]`
- **UI state**: ~20 overlay/modal flags, cursor positions, scroll offsets
- **Animation state**: `typewriter_queue` (deque), `xfer_progress`, `_typewriter_budget`

### File State

| Path | Format | Contents |
|------|--------|----------|
| `settings/settings.json` | JSON | All persisted settings (working_dir, voice, provider, favorites_slots, thresholds, etc.) |
| `settings/shortcuts.txt` | Line-delimited text | User-defined shortcut strings |
| `settings/piper-voices/*.onnx` | Binary | Piper TTS voice model files |
| `{working_dir}/prompts/history/NNN_slug_prompt.md` | Markdown | Saved/executed prompts with comment headers |
| `{working_dir}/prompts/history/NNN_slug_response.md` | Markdown | Paired TTS summaries or error messages |

### Thread Safety

- **`ui_queue`** (`queue.Queue`): The sole channel for background → main thread communication. All background threads post tuples; the main thread drains them synchronously in `process_ui_queue()`.
- **`audio_lock`** (`threading.Lock`): Protects `audio_frames[]` shared between the sounddevice callback (audio thread) and the transcription/stop-recording threads.
- **`_agent_cancel`** (`threading.Event`): Signals the agent thread to abort. Checked during the ZMODEM animation wait and the stdout read loop.
- **No other locks**: The main thread exclusively owns all other state. Background threads only write to `ui_queue` (plus `audio_frames` under lock), never to app state directly.

## 7. External Interfaces

### CLI Interfaces

- **Claude CLI**: `claude --print --verbose --output-format stream-json --dangerously-skip-permissions [--resume <session_id>] -p <prompt>`. Stream-JSON output parsed line-by-line.
- **Gemini CLI**: `gemini --yolo -o stream-json [--proxy=false] [--resume <session_id>] -p <prompt>`. Similar JSON streaming protocol.
- **Piper CLI**: `piper --model <model.onnx> --output-raw --output_file /dev/stdout` for local TTS; `--output_file <path.wav>` for Cast playback. Text piped via stdin.

### Audio Devices

- **Input**: sounddevice/PortAudio — 16kHz, mono, float32, 480-sample blocks (30ms)
- **Output**: sounddevice for local playback (TTS at 22050Hz, echo test at 16kHz)

### Network

- **Google Cast**: pychromecast for device discovery (mDNS/SSDP). HTTP server on ephemeral port serves WAV files to Cast devices.
- **Model downloads**: Piper voice models downloaded via `piper.download_voices` (HTTPS).
- **PyTorch Hub**: Silero VAD model loaded via `torch.hub.load()` (HTTPS on first run, cached thereafter).

### File Formats

- **History files**: Markdown with comment-line headers (`# Executed: <ISO timestamp>`). Prompt and response files are paired by naming convention (`NNN_slug_prompt.md` / `NNN_slug_response.md`).
- **Settings**: JSON object, human-readable, at `settings/settings.json`.
- **Shortcuts**: Plain text, one shortcut per line, at `settings/shortcuts.txt`.

### Configuration

- Settings persisted in `settings/settings.json` (loaded at startup, saved on change)
- Working directory configurable via settings overlay (drives prompt/history paths and docs browsing)
- Audio parameters tunable: VAD threshold, silence timeout, min speech duration, Whisper model size
- Typewriter speed configurable (default 200 chars/sec)
- TTS volume gain, voice selection, Cast device selection all persisted

## 8. Key Design Decisions

### Composition over Inheritance for Helpers

The 12 helper objects (`DrawingHelper`, `InputHandler`, `RunnerHelper`, etc.) each receive the `BBSApp` instance and operate on its state directly. This is a pragmatic choice for a curses application where nearly everything needs access to screen geometry, pane state, and application flags. It avoids deep class hierarchies and keeps related logic in separate files without a formal plugin system.

### Single UI Queue for Cross-Thread Communication

Rather than using callbacks, shared state with locks, or an async framework, all background threads communicate via a single `queue.Queue` with tagged tuples. This keeps the main render loop completely synchronous and lock-free (aside from `audio_lock`), making the curses rendering predictable and avoiding deadlocks.

### Provider Abstraction via CLI Subprocesses

AI providers are integrated by shelling out to their CLI tools (`claude`, `gemini`) rather than using Python SDKs. This means: (a) no SDK dependencies to manage, (b) session management handled by the CLIs themselves, (c) streaming via line-delimited JSON on stdout. The `CLIProvider` base class normalizes the different JSON event formats. The trade-off is dependency on specific CLI tools being installed and their output format stability.

### Lazy Model Loading

VAD (Silero) and STT (faster-whisper) models are loaded once on first use and cached in module-level globals. This keeps startup time reasonable (loading screen shows progress) while avoiding reloading on every recording. The loading happens in `run()` after curses is initialized so the loading screen is visible.

### Time-Budgeted Typewriter Effect

The typewriter doesn't emit one char per frame (which would couple speed to frame rate). Instead, `AnimationHelper.process_typewriter()` tracks a fractional character budget that accumulates based on elapsed time and the configured chars-per-second rate. This produces smooth, consistent output regardless of frame timing jitter. Budget is capped to prevent batch dumps after idle periods.

### ZMODEM Animation as Intentional Delay

The 3-second ZMODEM transfer animation before agent output isn't just decorative — it provides a buffer for the AI CLI to initialize and start producing output, so users see continuous visual feedback rather than a blank screen followed by a sudden dump.

### History as Flat Files

Prompt/response pairs are stored as sequentially numbered Markdown files in a flat directory rather than a database. This makes them trivially browsable in a file manager, diffable with git, and recoverable if the application state is lost. The naming convention (`NNN_slug_prompt.md`) provides natural ordering.

### Known Limitations

- **No tests or CI** — the project relies on manual testing
- **God object pattern** — `BBSApp` holds all state, which makes it hard to test helpers in isolation
- **Publish system** — only ARCH document type is implemented; 12 others are stubbed
- **Single-threaded rendering** — complex overlays on large terminals may cause visible flicker
- **No undo for refinement** — once fragments are refined, the original fragments are cleared

## 9. Extension Points

### Adding a New AI Provider

1. Create `voicecode/providers/<name>.py` with a class extending `CLIProvider`
2. Implement `build_refine_cmd()`, `build_execute_cmd()`, and the 6 event parsing methods
3. Add an instance to the `_PROVIDERS` list in `voicecode/providers/__init__.py`
4. The provider will automatically appear in the settings overlay's AI Models submenu

### Adding a New Publish Document Type

1. Create `voicecode/publish/<type>.py` with a class extending `PublishAgent`
2. Set `doc_type` and `prompt_template` (with `{scope}` and `{dest_folder}` placeholders)
3. Move the type name from `UNIMPLEMENTED_TYPES` to `IMPLEMENTED_TYPES` in `voicecode/ui/publish_overlay.py`
4. Register the agent in `get_publish_agent()` in `publish_overlay.py`

### Adding a New Overlay

1. Create `voicecode/ui/<name>_overlay.py` with a class following the `SettingsOverlay` pattern (receives `app` in constructor)
2. Add state flags to `BBSApp.__init__()` (e.g., `show_<name>_overlay`)
3. Compose the overlay in `BBSApp.__init__()` (e.g., `self.<name>_overlay = <Name>Overlay(self)`)
4. Add draw call in `DrawingHelper.draw()` (drawn after panes, before refresh)
5. Add input routing in `InputHandler.handle_input()` (checked before normal key dispatch)

### Adding a New Keyboard Shortcut

1. Add the key handler in the appropriate section of `InputHandler.handle_input()` (in `voicecode/ui/input.py`)
2. Update the help overlay content in `OverlayRenderer.draw_help()` (in `voicecode/ui/overlays.py`)
3. Update the help bar text in `DrawingHelper.draw()` if appropriate

### Adding a New Settings Item

1. Add a new dict entry in `SettingsOverlay.build_settings_items()` with `key`, `label`, `desc`, `get` (lambda), and either `options` (for cycling) or `editable: True` (for text input)
2. Handle the value change in the appropriate `set` callback or `action` handler
3. Persist via `persist_setting(key, value)` if the setting should survive restarts
