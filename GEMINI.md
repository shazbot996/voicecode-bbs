# VoiceCode — Gemini CLI Instructions

> **Shared project context is in [AGENTS.md](./AGENTS.md).** Read that file first for architecture, conventions, tech stack, and UI details.

## Gemini-Specific Notes

- The app is structured as the `voicecode/` Python package — `voicecode_bbs.py` is a thin entry-point wrapper
- No build system or tests; dependencies in `requirements.txt`, virtualenv in `venv/`
- The `GeminiProvider` class (in `voicecode/providers/gemini.py`) handles Gemini CLI integration — uses `--yolo -o stream-json` flags, session continuity via `--resume latest`
- This is a curses application with background threads — changes to shared state must be thread-safe (use `queue.Queue` for UI updates)
