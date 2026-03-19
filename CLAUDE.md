# VoiceCode — Claude Code Instructions

> **Shared project context is in [AGENTS.md](./AGENTS.md).** Read that file first for architecture, conventions, tech stack, and UI details.

## Claude-Specific Notes

- This is a single-file Python application (`voicecode_bbs.py`) — no build system, no modules, no tests
- All code lives in one file; keep it that way unless there's a strong reason to split
- The `ClaudeProvider` class (in `voicecode_bbs.py`) handles Claude CLI integration — session continuity uses `--resume` with session IDs
- When editing `voicecode_bbs.py`, be aware it's a large curses application with background threads — changes to shared state must be thread-safe (use `queue.Queue` for UI updates)
