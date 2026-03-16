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
> A retro BBS-style voice-driven prompt workshop for AI agents.
> Dictate prompts, refine them with AI, and execute them — all by voice.

---

## What Is This?

VoiceCode is a voice-first CLI interface for working with Claude and other AI agents. Speak your ideas, let AI shape them into well-crafted prompts, then fire them off — no keyboard required.
VoiceCode is a CLI voice dictation system that is built to dictate prompts for AI agents. It can be used to dictate direct commands to an AI agent, as well as to iteratively construct and refine a prompt.  Note: This system is not intended to produce a spec! This document replaces the hand prompt curation folder of my original prompt library design - the prompts/personal/ folder was where I usually do the majority of "new" thinking in building with AI.  I build prompts there to instruct code assist to build the specs themselves!  So my builds are always indirect: describe what I want in as much detail as I can, and ask code assist to generate either a spec for the solution, or a plan for the implementation of the idea.  In every case, my first step is the hard part, since sometimes I work directly with code assisst, and other times I write a prompt file. Prompt file histories are often important to have!  

This application is intended to bridge the gap between hand prompt file editing and extemporaneous vibe code editing.

It ships with two interfaces:

| | **Simple Mode** | **BBS Mode** |
|---|---|---|
| **File** | `voicecode.py` | `voicecode_bbs.py` |
| **UI** | Minimal terminal | Full curses three-pane TUI |
| **Modes** | Push-to-talk / hands-free | Voice-driven prompt workshop |
| **Features** | Record & transcribe | Refine, execute, save, browse, TTS |
| **Aesthetic** | Clean | 1990s BBS with ZMODEM animations |

---

## The BBS Experience

The flagship app is a retro terminal UI inspired by 1980s/90s bulletin board systems. Author was a SysOp of a very famous Wildcat! BBS in 1991. He had a dedicated phone line of his own. In his room!

### Three-Pane Layout

Here's what the BBS interface looks like in the terminal:

```
 VOICECODE BBS v2.0                     Voice: hfc_female  SysOp: falken  21:37:42
──Session v3 │ Saved: 12 │ History: 5 │ Frags: 3 │ Agent: IDLE────────────────────
┌── PROMPT BROWSER ────────────────┐┌── AGENT TERMINAL ──────────────────────────┐
│                                  ││                                            │
│  Write a Python function that    ││  ═══ INCOMING TRANSMISSION ═══             │
│  implements a binary search      ││                                            │
│  algorithm with the following    ││  Here's a binary search implementation     │
│  requirements:                   ││  that handles all the edge cases you       │
│                                  ││  mentioned:                                │
│  1. Accept a sorted list and    E>│                                            │
│     a target value               ││  ```python                                │
│  2. Return the index if found    ││  def binary_search(arr, target,            │
│  3. Return -1 if not found       ││      return_nearest=False):                │
│                                  ││      if not arr:                           │
│  Include type hints and handle   ││          return -1                         │
│  edge cases (empty list, single  ││      lo, hi = 0, len(arr) - 1             │
│  element).                       ││      while lo <= hi:                       │
├──────────=^R^=───────────────────┤│          mid = (lo + hi) // 2             │
┌── DICTATION BUFFER ──────────────┐│          if arr[mid] == target:            │
│                                  ││              return mid                    │
│  ◌ write a binary search         ││          elif arr[mid] < target:           │
│  ◌ in python                     ││              lo = mid + 1                  │
│  ◌ handle edge cases            D>│          else:                             │
│  ◌ type hints please             ││              hi = mid - 1                  │
│                                  ││      return -1                             │
│                                  ││  ```                                       │
│                                  ││                                            │
└──────────────────────────────────┘└────────────────────────────────────────────┘
 [Q]uit | [SPC]Rec [R]efine [E]xec [D]irect [S]ave [N]ew [←→]Browse | [ESC]Voice
 Ready — 12 prompts saved                                    Protocol: ZMODEM/1.0
```

- **Prompt Browser** (top-left) — View and browse your refined prompts
- **Dictation Buffer** (bottom-left) — Watch voice fragments accumulate in real-time
- **Agent Terminal** (right) — ZMODEM transfer animation, then typewriter-streamed responses

### The Workflow

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

### Voice Commands

Press **ESC** to enter voice command mode — then speak any action:

> *"record"* · *"refine"* · *"execute"* · *"save"* · *"next"* · *"previous"* · *"settings"* · *"quit"*

Every keyboard action has a voice equivalent. Go fully hands-free.

---

## How It Works

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
- **Piper TTS** provides local text-to-speech output with 10 voice options
- Models are **lazy-loaded** on first use — startup takes ~1 second

### Agent Streaming

The agent terminal streams Claude's response in real-time by parsing `--output-format stream-json` events. You see tool calls, thinking blocks, and text arrive character-by-character with a typewriter effect.

### Prompt Library

Prompts are automatically organized into a dated hierarchy:

```
~/prompts/voicecode/
  └── 2026/
      └── 03/
          └── 16/
              ├── prompt_001.md
              ├── prompt_002.md
              └── prompt_003.md
```

Browse saved prompts with **Left/Right** arrows. Run any saved prompt later with the `ask` helper.

---

## Getting Started

### Prerequisites

- Python 3.12+
- A working microphone
- [Claude CLI](https://docs.anthropic.com/en/docs/claude-cli) installed and authenticated
- Linux with ALSA (for `aplay` TTS playback)

### Install

```bash
git clone <repo-url> && cd voicecode

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

### Run

```bash
# Activate the virtualenv
source venv/bin/activate

# Launch the BBS prompt workshop
python voicecode_bbs.py

# Or with a larger Whisper model for better accuracy
python voicecode_bbs.py --model small.en

# Simple push-to-talk mode
python voicecode.py

# Hands-free mode (VAD auto-detects speech)
python voicecode.py --mode handsfree

# Run a saved prompt through Claude
./ask latest
./ask ~/prompts/2026/03/16/prompt_001.md
```

---

## Keyboard Controls

| Key | Action |
|:---:|--------|
| `SPACE` | Toggle recording |
| `R` | Refine fragments into a prompt |
| `D` | Direct execute (skip refinement) |
| `E` | Execute current prompt |
| `S` | Save prompt to library |
| `N` | New prompt (clear session) |
| `C` | Clear dictation buffer |
| `←` `→` | Browse saved prompts |
| `↑` `↓` | Scroll prompt pane |
| `PgUp` `PgDn` | Scroll agent terminal |
| `O` | Settings / voice configuration |
| `ESC` | Voice command mode |
| `K` | Kill running agent |
| `P` | Replay TTS summary |
| `H` | Help overlay |
| `Q` | Quit |

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12 |
| Speech-to-Text | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (tiny.en / base.en / small.en / medium.en) |
| Voice Activity Detection | [Silero VAD](https://github.com/snakers4/silero-vad) + PyTorch |
| Text-to-Speech | [Piper TTS](https://github.com/rhasspy/piper) |
| Audio Capture | sounddevice + NumPy |
| Terminal UI | Python curses |
| AI Backend | Claude CLI |

---

## Configuration

Settings are persisted to `~/.config/voicecode/settings.json` and can be changed in-app via the **O** key:

- Whisper model size
- VAD sensitivity threshold
- Silence timeout duration
- Minimum speech duration
- TTS voice selection (10 voices)
- Prompt library path

---

<p align="center">
  <code>Protocol: ZMODEM-VOICE/1.0 · Connection: LOCAL · BPS: 115200</code>
</p>
