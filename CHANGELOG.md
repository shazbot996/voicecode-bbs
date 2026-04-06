# Changelog

All notable changes to VoiceCode BBS are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/) starting at v4.1.0.

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
