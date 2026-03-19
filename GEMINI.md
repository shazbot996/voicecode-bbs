# VoiceCode — Gemini CLI Instructions

> **Shared project context is in [AGENTS.md](./AGENTS.md).** Read that file first for architecture, conventions, tech stack, and UI details.

## Gemini-Specific Notes

- This is a single-file Python application (`voicecode_bbs.py`) — no build system, no modules, no tests
- All code lives in one file; keep it that way unless there's a strong reason to split
- The `GeminiProvider` class (in `voicecode_bbs.py`) handles Gemini CLI integration — uses `--yolo -o stream-json` flags, session continuity via `--resume latest`
- When editing `voicecode_bbs.py`, be aware it's a large curses application with background threads — changes to shared state must be thread-safe (use `queue.Queue` for UI updates)
