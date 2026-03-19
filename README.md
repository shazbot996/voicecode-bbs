```
██╗   ██╗ ██████╗ ██╗ ██████╗███████╗ ██████╗ ██████╗ ██████╗ ███████╗
██║   ██║██╔═══██╗██║██╔════╝██╔════╝██╔════╝██╔═══██╗██╔══██╗██╔════╝
██║   ██║██║   ██║██║██║     █████╗  ██║     ██║   ██║██║  ██║█████╗
╚██╗ ██╔╝██║   ██║██║██║     ██╔══╝  ██║     ██║   ██║██║  ██║██╔══╝
 ╚████╔╝ ╚██████╔╝██║╚██████╗███████╗╚██████╗╚██████╔╝██████╔╝███████╗
  ╚═══╝   ╚═════╝ ╚═╝ ╚═════╝╚══════╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝
```

# VoiceCode BBS

> *"GREETINGS PROFESSOR FALKEN."*
>
> A retro BBS-style voice-driven prompt workshop for AI agents (Claude, Gemini).
> Dictate prompts, refine them with AI, and execute them in a novel dictation and refinement workflow that builds its own prompt history.


**Supports Claude CLI and Gemini CLI.**

![VoiceCode BBS Screenshot](voicecode-bbs-shot.png)

---

## Quick Start

### Prerequisites

- **Python 3.12+**
- **Linux** with ALSA (for TTS playback via `aplay`)
- A working **microphone**
- [**Claude CLI**](https://docs.anthropic.com/en/docs/claude-cli) and/or [**Gemini CLI**](https://github.com/google-gemini/gemini-cli) installed and authenticated

### Install

```bash
git clone https://github.com/shazbot996/voicecode-bbs.git
cd voicecode-bbs

# Automated setup (checks system deps, creates venv, installs everything)
make init

# Or manually:
python -m venv venv
source venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

System dependencies (installed via your package manager):
- `libportaudio2` — audio capture
- `alsa-utils` — TTS playback (`aplay`)

### Run

```bash
source venv/bin/activate
python voicecode_bbs.py
```

Options:
```bash
python voicecode_bbs.py --model small.en    # Use a larger Whisper model for better accuracy
python voicecode_bbs.py --save-dir ~/prompts # Custom prompt library location
```

### Run a Saved Prompt

```bash
./ask latest                                    # Execute the most recent prompt
./ask ~/prompts/voicecode/history/001_my_prompt.md  # Execute a specific prompt
```

---

## What Is This?

VoiceCode is a voice-first CLI for working with AI agents. Speak your ideas, let AI shape them into well-crafted prompts, then fire them off — no keyboard required.

This is not a general-purpose dictation tool. It is purpose-built for the prompt engineering workflow: you dictate fragments of what you want, refine them into a structured prompt with AI assistance, then execute that prompt against an agent. Prompt histories are preserved so you can browse and re-execute previous work.

The interface is a full curses TUI styled after 1990s bulletin board systems, with ZMODEM animations, typewriter streaming, and all the retro charm you remember (or wish you did).

---

## The Workflow

```
  1. DICTATE         2. REFINE           3. EXECUTE          4. LISTEN
 ┌──────────┐     ┌──────────┐       ┌──────────┐       ┌──────────┐
 │  Speak   │     │ AI turns │       │  Prompt  │       │ Response │
 │  your    │ ──► │ fragments│  ──►  │  sent to │  ──►  │ streamed │
 │  ideas   │     │ into a   │       │  Claude  │       │ back w/  │
 │          │     │ prompt   │       │  CLI     │       │ TTS      │
 └──────────┘     └──────────┘       └──────────┘       └──────────┘
    [SPACE]           [R]                [E]                [P]
```

1. **Dictate** — Press SPACE to record. Speak naturally; fragments accumulate in the buffer.
2. **Refine** — Press R to have AI synthesize your fragments into a polished prompt.
3. **Execute** — Press E to send the prompt to Claude. Watch the ZMODEM animation, then the response streams in with a typewriter effect.
4. **Listen** — The agent's TTS summary is read aloud. Press P to replay.

Or press **D** to skip refinement and send raw dictation directly.

---

## Three-Pane Layout

![VoiceCode BBS Screenshot](voicecode-bbs-shot.png)

- **Prompt Browser** (top-left) — View and browse your refined prompts. Favorites indicators on the left border.
- **Dictation Buffer** (bottom-left) — Watch voice fragments accumulate in real-time.
- **Agent Terminal** (right) — ZMODEM transfer animation, then typewriter-streamed responses with context meter.

---

## Keyboard Controls

| Key | Action |
|:---:|--------|
| `SPACE` | Toggle recording |
| `R` | Refine fragments into a prompt |
| `D` | Direct execute (skip refinement) |
| `E` | Execute current prompt |
| `F` | Assign prompt to favorites slot (1-10) |
| `1`-`9`, `0` | Quick-load favorites 1-10 |
| `N` | New prompt (clear buffer, keep session) |
| `U` | Undo last dictation entry |
| `C` | Clear dictation buffer |
| `Enter` | Type text directly into dictation buffer |
| `Tab` | Shortcuts browser (inject paths/strings; works mid-recording) |
| `←` `→` | Browse prompt history |
| `↑` `↓` | Cycle active/favorites views |
| `Home` | Return to current prompt |
| `PgUp` `PgDn` | Scroll agent terminal |
| `O` | Settings / voice configuration |
| `W` | New session (clear conversation context) |
| `ESC` | Voice command mode |
| `K` | Kill running agent |
| `P` | Replay TTS summary |
| `H` | Help overlay |
| `A` | About / title screen |
| `X` | Restart application |
| `Q` | Quit |

---

## Features

### Voice Commands

Press **ESC** to enter voice command mode — then speak any action:

> *"record"* · *"refine"* · *"execute"* · *"next"* · *"previous"* · *"settings"* · *"quit"*

Every keyboard action has a voice equivalent. Go fully hands-free.

### Audio Pipeline

```
Microphone (16kHz mono)
       │
       ▼
   30ms blocks (480 samples)
       │
       ▼
   Silero VAD ──── silence? ──── skip
       │
     speech
       │
       ▼
   faster-whisper STT (int8)
       │
       ▼
   Dictation Buffer / CLI
```

- **Silero VAD** detects speech vs. silence in real-time
- **faster-whisper** transcribes speech locally (no cloud API) with int8 quantization
- **Piper TTS** provides local text-to-speech output with multiple voice options
- Models are **lazy-loaded** on first use — startup takes ~1 second

### Prompt History

Prompts are stored in a flat directory with sequential numbering:

```
~/prompts/voicecode/history/
  ├── 001_binary_search_function.md
  ├── 002_refactor_auth_middleware.md
  └── 003_add_unit_tests.md
```

Browse history with **Left/Right** arrows. Use **Up/Down** to toggle between active and favorites views.

### 10-Slot Favorites

Press **F** to assign a prompt to one of 10 numbered favorites slots (keys 1-9 and 0). Quick-load any favorite by pressing its number. Favorites indicators on the Prompt Browser border show which slots are filled.

### Session Continuity

Each session gets an ID passed to Claude via `--resume`, so conversation context carries across multiple execute cycles. Press **W** to start a fresh session. The context meter on the agent terminal border shows how much of Claude's context window has been used.

### Shortcuts Browser

Press **Tab** to open the shortcuts browser — a navigable overlay for injecting paths, strings, or project folders into the dictation buffer. This works **mid-recording**: the shortcut is timestamped and merged into the final transcript at the correct position using Whisper's word-level timestamps.

### Configuration

Settings are persisted to `~/.config/voicecode/settings.json` and can be changed in-app via the **O** key:

- Whisper model size (tiny.en, base.en, small.en, medium.en)
- VAD sensitivity threshold
- Silence timeout duration
- Minimum speech duration
- TTS voice selection
- TTS volume gain
- Prompt library path
- Working directory for shortcuts browser

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12 |
| Speech-to-Text | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (tiny.en / base.en / small.en / medium.en) |
| Voice Activity Detection | [Silero VAD](https://github.com/snakers4/silero-vad) + PyTorch (CPU-only) |
| Text-to-Speech | [Piper TTS](https://github.com/rhasspy/piper) |
| Audio Capture | sounddevice + NumPy |
| Terminal UI | Python curses |
| AI Backend | Claude CLI, Gemini CLI |

---

## Agent Support

**Supported agents:**
- **Claude CLI** (`claude` command)
- **Gemini CLI** (`gemini` command)

---

<p align="center">
  <code>Protocol: ZMODEM-VOICE/1.0 · Connection: LOCAL · BPS: 115200</code>
</p>
