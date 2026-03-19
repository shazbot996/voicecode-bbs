# VoiceCode — Shared Project Context

Voice-driven CLI interface for interacting with AI agents (Claude, Gemini). Dictate prompts, refine them with AI, and execute them — all by voice.

## Architecture

- **`voicecode_bbs.py`** — Retro BBS-style voice-driven prompt engineering workshop with three-pane curses UI (Prompt Browser, Dictation Buffer, Agent Terminal), ZMODEM animations, typewriter streaming, TTS output, favorites, session continuity, shortcuts injection, and context metering.
- **`ask`** — Bash helper to run saved prompts through Claude CLI or Gemini CLI.

### Audio Pipeline

```
Mic (16kHz mono) → Silero VAD → faster-whisper STT → Review/Dictation Buffer → CLI stdin
```

### Key Parameters

- Sample rate: 16kHz, mono, 30ms blocks (480 samples)
- VAD threshold: 0.5, silence timeout: 1.5s, min speech: 0.3s
- Typewriter effect: 1.5ms/char (~667 CPS)

## Tech Stack

- **Python 3.12** — no build system, pure Python
- **faster-whisper** — speech-to-text (models: tiny.en, base.en, small.en, medium.en)
- **silero-vad** / **torch** (CPU-only) — voice activity detection
- **sounddevice** / **numpy** — audio capture
- **piper-tts** — text-to-speech via `piper` CLI + `aplay`
- **curses** — terminal UI (BBS app)
- Dependencies in `requirements.txt`, virtualenv in `venv/`
- PyTorch installed CPU-only via `--index-url https://download.pytorch.org/whl/cpu`

## Running

```bash
# Activate venv
source venv/bin/activate

# Launch the BBS prompt workshop
python voicecode_bbs.py

# Run a saved prompt
./ask latest
./ask ~/prompts/voicecode/001_some_useful_name.md
```

## Conventions

- Models (VAD, Whisper) are lazy-loaded on first use for fast startup
- Background threads use `daemon=True`
- Prompt/response pairs saved to `~/prompts/voicecode/history/` as `NNN_slug_prompt.md` + `NNN_slug_response.md` (flat directory, sequentially indexed)
- Response files contain the TTS summary (or error) from the agent run
- Comment lines (`#`) in prompt files are stripped before execution
- TTS summaries extracted from `[TTS_SUMMARY]...[/TTS_SUMMARY]` blocks in agent responses
- Thread-safe UI updates via `queue.Queue`
- Session continuity across prompts via `--resume` with session IDs
- Mid-recording shortcuts injection merges paths into transcripts using word-level timestamps
- No tests or CI currently

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
- **Agent Terminal** (right, full height) — ZMODEM animation, then typewriter-streamed responses
- Data-flow hints: `=^R^=` (refine up), `E>` (execute right), `D>` (direct right)

## BBS App Keyboard Controls

| Key | Action |
|-----|--------|
| SPACE | Toggle recording |
| R | Refine fragments into prompt |
| E | Execute current prompt |
| D | Direct execute (skip refinement) |
| F | Assign prompt to favorites slot (1-10) |
| 1-9, 0 | Quick-load favorites slot 1-10 |
| N | New prompt (clear buffer, keep session) |
| U | Undo last dictation entry |
| C | Clear dictation buffer |
| Enter | Type text directly into dictation buffer (Enter to submit, ESC to cancel) |
| Tab | Shortcuts browser (inject strings/paths into dictation; works mid-recording) |
| ←/→ | Browse prompt history |
| ↑/↓ | Cycle active/favorites views |
| Home | Return to current prompt |
| PgUp/PgDn | Scroll prompt browser (when browsing history) or agent terminal |
| O | Settings / voice config |
| K | Kill running agent |
| W | New session (clear conversation context) |
| P | Replay TTS summary |
| H | Help overlay |
| A | About / title screen |
| X | Restart application |
| Q | Quit |
