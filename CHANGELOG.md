# Changelog

All notable changes to VoiceCode BBS are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/) starting at v4.1.0.

## [4.2.2] - 2026-08-30

### Fixed
- **ALSA hardware microphone capture** — Request native `int16` PCM audio from ALSA hardware devices and normalize to `float32` in Python, fixing silent zero-buffer recording on devices that fail to convert float32 directly
- **Microphone picker de-duplication** — Filter out virtual ALSA pseudo-device aliases (`default`, `sysdefault`, `pipewire`, `pulse`, etc.) to keep the device selection list clean
- **Echo test error handling** — Gracefully handle missing or inaccessible audio output devices during mic echo tests

## [4.2.1] - 2026-08-30

### Fixed
- **Shell output no longer corrupts the curses UI** — `agy` runs shell commands on a PTY, so `run_command` output arrives CRLF-terminated and tab-indented. Curses executed those bytes as cursor movement (`\r` jumps to column 0 of the physical row, `\t` overshoots the pane border), painting tool output over the left-hand panes. All agent-pane text now passes through `sanitize_text()`, which strips ANSI CSI/OSC sequences and carriage returns, expands tabs, and drops remaining control characters
- **TTS summary extraction is no longer confused by quoted markers** — `extract_tts_summary()` now returns the *last* non-empty `[TTS_SUMMARY]` block rather than the first, so an agent echoing the instruction back (or quoting this repo's own source) can't win over the real summary
- Summary extraction falls back to the accumulated stream deltas when the provider's result event carries an abridged response

## [4.2.0] - 2026-08-30

### Added
- **Antigravity CLI (`agy`) support** — replaces Gemini CLI as the second AI provider, with full parity for streaming, session continuity, tool display, tool-result previews, and context metering
- **Explicit model selection for both providers** — Claude uses family aliases (`opus`, `sonnet`, `haiku`, `fable`); Antigravity's list is read live from `agy models` (cached, with a static fallback)
- **Per-provider CLI command override** — an editable base-invocation field (so extra flags can be appended) plus a read-only preview of the full command line VoiceCode will run
- **Build/plan execution mode** — `PublishAgent` and `MaintenanceAgent` carry a `run_mode` that maps to `--permission-mode plan` (Claude) or `--mode plan` (Antigravity); the routing banner announces plan mode. All agents default to build mode, since plan mode is read-only and every agent writes its output to disk
- Antigravity tool library (26 entries) in the Tools browser tab

### Changed
- Header ribbon now shows provider **and** model as `Model:<Provider>:<Model>` (e.g. `Model:Claude:Opus 5`), degrading gracefully on narrow terminals
- `AGENTS.md` is now the single maintained root context file; `CLAUDE.md` is reduced to a one-line `@AGENTS.md` import stub
- `M` toggles Antigravity / Claude
- Command overrides are parsed with `shlex` (quoted paths now work), and `--version` probes use the binary only
- Claude's context meter falls back to a shared 1M-token constant when the CLI reports no `contextWindow`

### Removed
- Gemini CLI provider, `GEMINI.md`, the `GEMINI_TOOLS` library, and the `gemini_disable_proxy` proxy workaround
- `gemini_command` / `gemini_disable_proxy` settings keys — dropped automatically on load; a saved `ai_provider` of `Gemini` migrates to `Antigravity`

## [4.1.2] - 2026-04-06

### Fixed
- Publish agents now receive historical prompt context when browsing history
- Dictation buffer preserved until agent confirms success (no longer lost on agent failure)

## [4.1.1] - 2026-04-02

### Added
- CHANGELOG.md shown in document browser alongside README
- Secure sandbox launch script (`sandbox-launch.sh`) and Makefile targets
- Enhanced help documentation in Makefile
- Additional CLI config whitelisting in sandbox (git, docker, npm, claude, gemini)

### Fixed
- Publish workflow now uses dictation buffer when new prompt is empty
- Added missing `requests` dependency to requirements.txt

## [4.1.0] - 2026-04-01

### Added
- Animated theme showcase GIF and three new color themes
- MIT license

### Fixed
- TTS streaming buffer to avoid mid-word freezes

## [4.0] - 2026-03-25

### Added
- Theme system with selectable color schemes
- Page Up/Down support in document browser
- Default working directory set to cwd on first run
- Workflow diagram and source materials in README

### Changed
- Document browser sorts by type and recency, highlights active tab

## [3.9] - 2026-03-18

### Added
- Root-context maintenance agents (CTX_DRIFT, CTX_UPDATE)
- Child document nesting in browser
- Browser delete confirmation dialog
- Coverage reports as view-only browser items
- README.md as standalone root context item in document browser
- xlsx/docx export dependencies

### Fixed
- Portable document paths across environments
- Sub-context display requires primary context presence
- TTS invocation without venv activation
- Piper binary path symlink dereferencing

### Changed
- Renamed reconcile output to drift-report

## [3.8] - 2026-03-11

### Added
- Gemini tool reference library with browser tab
- Maintenance agent framework with overlay UI
- Document actions overlay for browser with maintenance integration
- Document type badges and color-coded browser/reader UI
- Document type field to all publish agent front matter

## [3.6] - 2026-03-04

### Added
- GLOSSARY publish agent with dynamic agent info panel
- CONSTRAINTS publish agent with incremental workflow
- ADR publish agent for architecture decision records
- CONVENTIONS publish agent for team practices documentation
- SCHEMA publish agent for data layer reference
- README publish agent (replaced RUNBOOK, WORKFLOW, CHANGELOG agents)
- Publish-from-dictation hint
- Refine prompt editing in publish overlay
- Prompt templates extracted to disk with editor support

### Removed
- RUNBOOK, WORKFLOW, and CHANGELOG publish agent types

## [3.5] - 2026-02-25

### Added
- Publish overlay for document type and folder selection
- Document reader/editor overlay
- On-close callback for document reader

## [3.3] - 2026-02-18

### Added
- Gemini proxy toggle setting
- Hotkey [T] to cycle tips in agent terminal welcome screen

### Changed
- Settings and Piper voices moved to local `settings/` directory
- Configurable typewriter speed
- Reworked navigation UX with dedicated scroll keys, favorites toggle, auto-scroll

### Fixed
- Stall warning reset behavior
- Chromecast playback now polls status instead of sleeping 30s

## [3.2] - 2026-02-11

### Changed
- Refactored monolith `voicecode_bbs.py` into `voicecode/` package
- Singleton providers with Gemini `--proxy=false` flag

## [3.1] - 2026-02-04

### Added
- Google Cast integration with volume restore and mute-local-TTS option
- Polyphonic audio playback
- Time-based typewriter effect

### Changed
- Reduced minimum overlay height threshold from 12 to 8

## [3.0] - 2026-01-28

### Added
- Model toggle between providers
- Gemini command override support
- Status bar model display
- Agent stall detection and idle indicator
- Gemini yolo mode
- BBS-style routing announcement before incoming transmission

### Fixed
- Paste in typing mode inserts at cursor instead of replacing buffer

## [2.5] - 2026-01-21

### Added
- Gemini CLI provider support
- Agent documentation system
- Response history saving
- All AI providers shown in options menu even if not installed

### Fixed
- TTS buffer flush on transmission end
- Text alignment issues

## [2.4] - 2026-01-14

### Added
- Flat prompt storage with slugs
- 10-slot favorites with undo
- Direct text entry mode via Enter key
- System dependency check in Makefile for PortAudio and ALSA

### Changed
- Simplified browser to active/favorites/history views

## [2.3] - 2026-01-07

### Added
- Persistent dictation buffer with historical prompt editing
- Instant streaming mode
- Bracketed paste support for text injection
- Categorized browser with documents tab
- String injector subtitle in shortcut editor

### Changed
- Browse/view hints moved to prompt pane border
- Documents sorted by mtime

## [2.1] - 2025-12-31

### Added
- Session continuity with context meter
- Folder slug browser with mid-recording injection
- Favorites system with prompt browser navigation
- ESC main menu overlay (Options, Help, About, Restart, Quit)
- Settings modal sections with test tools submenu
- Joshua voice preset

### Changed
- Centralized version to single-source `version.py`
- Voice settings moved into submenu
- Yellow title bar

### Fixed
- Text alignment, brightness overlays, and audio streaming with gain

### Removed
- Voice command feature

## [1.0] - 2025-12-24

### Added
- Initial release
- Curses-based BBS terminal UI
- Voice dictation with Whisper
- Text-to-speech with Piper
- Claude CLI provider integration
- History browser and info panels
- About overlay and welcome art
