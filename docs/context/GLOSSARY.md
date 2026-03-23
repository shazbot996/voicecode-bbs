---
title: Glossary
scope: VoiceCode BBS — ~/projects/voicecode
date: 2026-03-22
---

# Glossary

## A

**ADR** (Architecture Decision Record)
: A planned publish document type that captures a single significant technical decision, its context, alternatives considered, and consequences. Numbered sequentially in `docs/decisions/`.

**Agent Pane**
: The right-side full-height pane in the three-pane BBS layout. Displays streaming agent output with the typewriter effect. See also: **Typewriter Effect**.

**Agent State**
: An enumeration (`AgentState` in `constants.py`) tracking the execution lifecycle: `IDLE` (no agent running), `DOWNLOADING` (ZMODEM animation playing), `RECEIVING` (streaming output), `DONE` (execution complete).

**Agent Terminal**
: Synonym for **Agent Pane**. The right column of the three-pane layout where AI agent responses stream in.

## B

**BBS App**
: The main curses application class (`BBSApp` in `app.py`). Central orchestrator and "God object" that holds all mutable state, composes ~12 helper objects, and runs the 60fps event loop.

**Bracketed Paste**
: A terminal protocol mode (`ESC[?2004h`) enabled at startup so multi-line pastes are detected as a single input event rather than individual keystrokes.

**Browser Helper**
: The `BrowserHelper` class (`history/browser.py`) that manages prompt history navigation. Scans numbered history files and renders the prompt pane based on the current view (active prompt, history entry, or favorites).

## C

**Cast**
: Google Cast integration (`tts/cast.py`). Discovers Chromecast and Nest devices on the LAN via pychromecast, generates a WAV via Piper, and streams it to selected speakers via a temporary HTTP server.

**CLI Provider**
: The abstract base class (`CLIProvider` in `providers/base.py`) that normalizes CLI differences between AI agents. Defines methods for building commands and parsing JSON streaming events. See also: **Claude Provider**, **Gemini Provider**.

**Claude Provider**
: Concrete `CLIProvider` implementation (`providers/claude.py`) for the Claude CLI. Uses `--output-format stream-json` and `--resume <session_id>` for session continuity.

**Color Pair (CP_*)**
: Named constants in `ui/colors.py` (e.g., `CP_HEADER`, `CP_AGENT`, `CP_XFER`, `CP_TTS`) that map to curses color pair IDs. Used throughout the UI to apply consistent theming.

**Context Meter**
: A visual indicator in the UI showing how much of the AI provider's context window has been consumed (`context_tokens_used`). Changes color from green to yellow to red as usage increases.

## D

**Data-Flow Hints**
: The labels rendered at pane boundaries showing how data moves between panes: `=^R^=` (refine up from dictation to prompt), `E>` (execute right from prompt to agent), `D>` (direct execute right from dictation to agent), `P>` (publish from dictation).

**Dictation Buffer**
: The bottom-left pane where voice-transcribed fragments accumulate in real-time before refinement. Capped at 500 lines. Each fragment is prefixed with `◌`.

**Direct Execute**
: The `D` key action that sends raw dictation fragments directly to the agent without first refining them into a polished prompt. Implemented via `execute_raw()` in `ExecutionHelper`.

## E

**Executed Prompt Text**
: The `executed_prompt_text` field on `BBSApp` that stores the most recently executed prompt. Displayed in the prompt pane with yellow (`CP_XFER`) coloring until the agent finishes and the pane resets.

**Execution Helper**
: The `ExecutionHelper` class (`agent/execution.py`) that orchestrates the full prompt lifecycle: saving to history, triggering the ZMODEM animation, launching the agent thread, and managing refinement.

## F

**Favorites**
: Ten numbered slots (keys 1-9 and 0) that store references to history prompt files for quick access. Managed by `FavoritesHelper` in `history/favorites.py` and persisted in `settings.json`.

**Fragment**
: A single transcribed speech segment produced by one recording session (press SPACE to start, SPACE to stop). Fragments accumulate in the dictation buffer until refined or executed.

## G

**Gemini Provider**
: Concrete `CLIProvider` implementation (`providers/gemini.py`) for the Gemini CLI. Uses `--yolo` flag and `--resume` for session continuity.

**God Object**
: The `BBSApp` class pattern where a single instance holds all mutable application state. A pragmatic choice for curses applications where nearly everything needs access to screen geometry and shared flags.

## H

**History**
: Prompt/response pairs stored as sequentially numbered Markdown files in `{working_dir}/prompts/history/`. Named as `NNN_slug_prompt.md` and `NNN_slug_response.md`. Browsable with left/right arrow keys.

## I

**Injection**
: A shortcut string or file path inserted into a recording at a specific timestamp. When the user presses Tab during recording, the selected shortcut is merged into the final transcript at the correct position using word-level timestamps. See also: **Shortcut**.

## L

**Live Preview**
: The interim transcription shown in the dictation pane during recording. Updated every 2 seconds by the `live_transcribe_loop` thread, displayed with a `◌ preview...` prefix.

## M

**Main Loop**
: The core event loop in `BBSApp.run()` that cycles at ~60fps: `process_ui_queue()` → `process_typewriter()` → `draw()` → `handle_input()`. Runs until `self.running` is set to `False`.

## O

**Overlay**
: A modal UI panel drawn on top of the three-pane layout. Examples include help, about, settings, publish, shortcuts browser, and escape menu. Overlays intercept keyboard input before normal dispatch.

## P

**Piper TTS**
: The text-to-speech engine used for audio feedback. Runs the `piper` CLI to synthesize speech from text, outputting raw PCM audio at 22050Hz. Supports 10 voice models (en_US and en_GB variants).

**Prompt Browser**
: The top-left pane that displays the current refined prompt, or when browsing history, shows a combined prompt + response view. Managed by `BrowserHelper`.

**Prompt Refinement**
: The process of synthesizing raw voice fragments into a polished, well-structured prompt via a lightweight LLM call. Triggered by the `R` key. Uses templates from `publish/prompts/REFINE.md`.

**Publish Agent**
: The abstract base class (`PublishAgent` in `publish/base.py`) for document-generating agents. Each subclass sets a `doc_type` and loads a prompt template from `publish/prompts/<DOC_TYPE>.md` with `{scope}` and `{dest_folder}` placeholders.

**Publish Overlay**
: A two-step modal UI (`ui/publish_overlay.py`) for generating structured documents: first select a document type (ARCH, PLAN, SPEC, etc.), then select a destination folder under `docs/`. The assembled prompt feeds into the normal agent execution pipeline.

## R

**Recording Helper**
: The `RecordingHelper` class (`audio/capture.py`) that manages mic capture via sounddevice. Opens a 16kHz mono input stream, accumulates frames, runs live transcription, and performs final transcription on stop.

**Runner Helper**
: The `RunnerHelper` class (`agent/runner.py`). The core agent execution engine that spawns the provider CLI as a subprocess, parses streaming JSON events, feeds text to the typewriter queue, extracts TTS summaries, and triggers speech on completion.

## S

**Scope**
: In the publish system, the user's description of what the agent should focus on. Passed as the `{scope}` placeholder in publish agent prompt templates. Falls back to the dictation buffer contents or "the entire repository" if empty.

**Session Continuity**
: The mechanism for maintaining conversational context across multiple prompts within a session. Uses `--resume <session_id>` (Claude) or `--resume latest` (Gemini). A new session is started with the `W` key.

**Shortcuts**
: User-defined strings or file paths stored in `settings/shortcuts.txt`. Browsable via the Tab overlay and injectable into recordings mid-capture. Organized into categories: Shortcuts, Project Folders, and Documents.

**Silero VAD**
: The voice activity detection model (loaded via `torch.hub.load()`) that determines when the user is speaking. Uses a 0.5 threshold with 1.5s silence timeout and 0.3s minimum speech duration.

**Stall Detection**
: Logic in the agent terminal that detects when the agent subprocess has stopped producing output for an extended period, showing a visual indicator to the user.

**Stream-JSON**
: The output format used by both Claude and Gemini CLIs (`--output-format stream-json` / `-o stream-json`). Produces line-delimited JSON events that are parsed in real-time by the runner.

## T

**TextPane**
: A reusable scrollable text region (`ui/panes.py`) with box-drawing borders, scroll indicators, line-level color overrides, and welcome art mode. Used for all three panes in the layout.

**TTS Summary**
: A plain-text spoken summary extracted from agent responses using `[TTS_SUMMARY]...[/TTS_SUMMARY]` markers. Spoken aloud via Piper TTS after agent completion and saved as the response history file.

**Typewriter Effect**
: The character-by-character display of agent output in the agent pane. Uses a time-budgeted approach at a configurable rate (default 200 chars/sec) to produce smooth, consistent output regardless of frame timing. Managed by `AnimationHelper`.

## U

**UI Queue**
: The single `queue.Queue` instance (`BBSApp.ui_queue`) used for all background-to-main-thread communication. Background threads post tagged tuples (e.g., `("fragment", text)`, `("agent_state", state)`); the main loop drains them synchronously each frame.

## V

**VAD** (Voice Activity Detection)
: The process of detecting whether audio contains speech. VoiceCode uses the Silero VAD model running on CPU to determine recording start/stop boundaries. See also: **Silero VAD**.

## W

**Whisper**
: The speech-to-text engine (faster-whisper library) used for transcription. Supports model sizes from tiny.en to medium.en (default base.en, CPU int8). Provides both plain transcription and word-level timestamps for injection merging.

**Working Directory**
: The project directory the app operates against (configurable via settings). Determines where prompts, history, and docs subfolders are located. Defaults to the repository root.

## Z

**ZMODEM Animation**
: A retro-themed transfer animation displayed for 3 seconds when a prompt is sent to the agent. Provides visual feedback while the AI CLI initializes and starts producing output. Named after the classic BBS file-transfer protocol for thematic consistency.
