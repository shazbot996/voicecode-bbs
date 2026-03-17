# VoiceCode

Voice-driven CLI interface for interacting with AI agents (Claude). Dictate prompts, refine them with AI, and execute them — all by voice.

## Architecture

Two main applications sharing a common audio pipeline:

- **`voicecode.py`** — Simple push-to-talk / hands-free voice-to-CLI tool. Records audio, transcribes with Whisper, sends to a CLI command.
- **`voicecode_bbs.py`** — Advanced retro BBS-style prompt engineering workshop with three-pane curses UI (Prompt Browser, Dictation Buffer, Agent Terminal), ZMODEM animations, typewriter streaming, TTS output, and voice commands.
- **`ask`** — Bash helper to run saved prompts through Claude CLI.

### Audio Pipeline

```
Mic (16kHz mono) → Silero VAD → faster-whisper STT → Review/Dictation Buffer → CLI stdin
```

### Key Parameters

- Sample rate: 16kHz, mono, 30ms blocks (480 samples)
- VAD threshold: 0.5, silence timeout: 1.5s, min speech: 0.3s
- Typewriter effect: 12ms/char (~83 CPS)

## Tech Stack

- **Python 3.12** — no build system, pure Python
- **faster-whisper** — speech-to-text (models: tiny.en, base.en, small.en, medium.en)
- **silero-vad** / **torch** — voice activity detection
- **sounddevice** / **numpy** — audio capture
- **piper-tts** — text-to-speech via `piper` CLI + `aplay`
- **curses** — terminal UI (BBS app)
- Dependencies in `requirements.txt`, virtualenv in `venv/`

## Running

```bash
# Activate venv
source venv/bin/activate

# Simple mode
python voicecode.py
python voicecode.py --mode handsfree
python voicecode.py --model small.en --command "claude --print"

# BBS mode
python voicecode_bbs.py
python voicecode_bbs.py --model small.en --save-dir ~/my-prompts

# Run a saved prompt
./ask latest
./ask ~/prompts/2026/03/15/prompt_001.md
```

## Conventions

- Models (VAD, Whisper) are lazy-loaded on first use for fast startup
- Background threads use `daemon=True`
- Prompts saved to `~/prompts/YYYY/MM/DD/prompt_NNN.md` (dated hierarchy)
- Comment lines (`#`) in prompt files are stripped before execution
- TTS summaries extracted from `[TTS_SUMMARY]...[/TTS_SUMMARY]` blocks in agent responses
- Thread-safe UI updates via `queue.Queue`
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

- **Prompt Browser** (top-left) — View and browse refined prompts
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
| S | Save prompt |
| F | Add prompt to favorites |
| N | New prompt (clear session) |
| C | Clear dictation buffer |
| ←/→ | Browse saved prompts |
| ↑/↓ | Cycle active/favorites/history views |
| PgUp/PgDn | Scroll agent terminal |
| O | Settings / voice config |
| K | Kill running agent |
| W | New session (clear conversation context) |
| P | Replay TTS summary |
| H | Help overlay |
| A | About / title screen |
| X | Restart application |
| ESC | Voice command mode |
| Q | Quit |
