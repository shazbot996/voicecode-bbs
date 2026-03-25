# VoiceCode — Claude Code Instructions

> **Shared project context is in [AGENTS.md](./AGENTS.md).** Read that file first for architecture, conventions, tech stack, and UI details.

## Claude-Specific Notes

- The app is structured as the `voicecode/` Python package — `voicecode_bbs.py` is a thin entry-point wrapper
- Dependencies in `requirements.txt`, virtualenv in `venv/`; smoke tests in `tests/` (run with `make test`)
- The `ClaudeProvider` class (in `voicecode/providers/claude.py`) handles Claude CLI integration — session continuity uses `--resume` with session IDs
- This is a curses application with background threads — changes to shared state must be thread-safe (use `queue.Queue` for UI updates)
- The `publish/` module contains 9 document publishing agents (ADR, ARCH, PLAN, SPEC, GLOSSARY, CONSTRAINTS, CONVENTIONS, SCHEMA, README) — each subclasses `PublishAgent` with a prompt template. The `publish/maintenance/` subpackage provides document upkeep agents (Reconcile, Refresh, Coverage, CTX_DRIFT, CTX_UPDATE). See AGENTS.md for full details.
