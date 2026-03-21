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

**Supports Claude CLI and Gemini CLI. Optional Google Cast output to Nest/Chromecast speakers.**

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
make voicecode

# Or manually:
source venv/bin/activate
python voicecode_bbs.py
```

### Run from a parent repo

This application is designed to live inside a deployment or monorepo alongside your project code. The `make init-sub` command installs a `voicecode` target into the parent folder's Makefile so you can launch from the repo root:

```bash
make init-sub   # one-time setup — adds target to ../Makefile
make voicecode   # run from repo root
```

### Folder Layout

VoiceCode expects a single **working folder** — typically the root of your repo. Within that folder it looks for:

- `prompts/` — your prompt library (templates, reference prompts)
- `docs/` — markdown documents browsable via the shortcuts overlay

Point the **Working Directory** setting (in the **O** settings menu) at your repo root and VoiceCode will pick up both subfolders automatically. Prompt history is saved separately under `{prompt_library}/voicecode/history/`.

All paths are configurable via the in-app settings menu (**O** key).

---

## What Is This?

VoiceCode is a voice-first CLI for working with AI agents. I built it after many iterations with code assist cli tools, vs code, and various prompt editors. Once an AI developer starts getting more structural with code generating, there is still an extremely distilled need to write as much of your own context as possible to focus the builds and control as much as possible. In other words, typing boatloads of long form prompts by hand, and it takes a lot of time. If you are short-cutting this, then you aren't really controlling what you are making.

So I built an voice dictation system that I vibe coded with and refined until I really feel like it has a workflow that speeds me up, and improves my capture of historical context. It's a great context generator for a prompt library!

This is not a general-purpose dictation tool. It is purpose-built for the prompt engineering workflow: you dictate fragments of what you want, refine them into a structured prompt with AI assistance, then execute that prompt against an agent. Prompt histories are preserved so you can browse and re-execute previous work. The trick is the fluidity with how you can build a prompt by combining your voice dictation, hand direct editing, copy/paste integration, and an interactive "string injector" that can paste critical syntax strings from your project into your prompt with a single keystroke.

The interface is a full curses TUI styled after 1990s bulletin board systems with all the retro charm you remember (or wish you did). Yeah I'm an old head and I feel all warm and cozy in a curses UI. But it's all keyboard shortcuts and fairly fast workflow.

---

## The Prompt Refinery Workflow

```
  1. DICTATE       2. REFINE        3. ITERATE       4. EXECUTE       5. LISTEN
 ┌──────────┐   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
 │  Speak   │   │ AI turns │    │ Add more │    │  Prompt  │    │ Response │
 │  your    │──►│ fragments│───►│ fragments│───►│  sent to │───►│ streamed │
 │  ideas   │   │ into a   │    │ re-refine│    │  Claude/ │    │ back w/  │
 │          │   │ prompt   │    │ repeat   │    │  Gemini  │    │ TTS      │
 └──────────┘   └──────────┘    └──────────┘    └──────────┘    └──────────┘
    [SPACE]         [R]          [SPACE] [R]        [E]              [P]
```

1. **Dictate** — Press SPACE to record. Speak naturally; fragments accumulate in the buffer. Start and stop repeatedly. Undo mistakes.
2. **Refine** — Press R to have AI synthesize your fragments into a polished prompt.
3. **Iterate** — Continue dictating additional fragments and refine again. The AI merges new dictations into the ongoing refined prompt, building on what's already there. This loop is the core of the Prompt Refinery — you can circle back through dictate and refine as many times as needed until the prompt captures exactly what you mean.
4. **Execute** — Press E to send the prompt to your agent. Watch the ZMODEM animation, then the response streams in with a typewriter effect.
5. **Listen** — The agent's TTS summary is read aloud locally (and on Cast speakers if configured). Press P to replay.

**Direct Query** — Not every prompt needs refinement. In fact, many are damaged by it. Press **D** to skip the refinery entirely and send your dictation straight to the agent. The value here is still the multimodal dictation buffer — combining voice, keyboard edits, and shortcut injection gives you a better first draft than voice dictating into a text field. When your dictation comes out clean, just fire it. Mess up? Just press "U" and try the last section again. The dictation system is meant to append repeated "chunks" of vocal capture. The user will quickly learn a balance between a long monologue of text, and smaller fragment captures to assemble a layered dictation transcript. 

---

## DRE Prompt Execution

**Direct, Refine, Execute** — a prompt execution strategy that should be standard practice for anyone working with AI agents.

We spend far more time managing prompts than we do managing agents. The bottleneck in AI-assisted development isn't the agent — it's getting the right prompt to the agent in the first place. DRE gives you two paths to execution: **Direct** for clean dictations that need no revision, and **Refine** for complex prompts that benefit from the iterative Prompt Refinery loop. Both paths converge at **Execute**. In future, I can imagine having different kinds of refinement models to enhance this greatly. The refinement models as they are are just best-effort. I haven't tuned them greatly. 

This is the philosophy behind VoiceCode's three-pane layout:

![VoiceCode BBS Screenshot](voicecode-bbs-shot.png)

- **Prompt Browser** (top-left) — View and browse your refined prompts. History entries show both the prompt and agent response in a combined scrollable view. Favorites indicators on the left border.
- **Dictation Buffer** (bottom-left) — Watch voice fragments accumulate in real-time. This is where the refinement loop lives — dictate, refine, dictate more, refine again.
- **Agent Terminal** (right) — ZMODEM transfer animation, then typewriter-streamed responses with context meter. Activity spinner shows agent status and stall warnings.

The DRE model is also why VoiceCode is a retro CLI and not a web app. Everything in this application is keyboard shortcuts — the thing you lose in a modern web UI is often found in the simplicity of a command line interface. When your workflow is about fast iteration between voice and text, every millisecond of friction matters. Curses gives you that speed and simplicity. 

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
| `PgUp` `PgDn` | Scroll prompt browser (history) or agent terminal |
| `O` | Settings / voice configuration |
| `W` | New session (clear conversation context) |
| `K` | Kill running agent |
| `P` | Publish document (open publish overlay) |
| `Y` | Replay TTS summary |
| `H` | Help overlay |
| `A` | About / title screen |
| `X` | Restart application |
| `Q` | Quit |

---

## Features

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

### Prompt History & Response Archive

Every executed prompt is saved as a paired set of files — the prompt and its agent response:

```
{prompt_library}/voicecode/history/
  ├── 001_binary_search_function_prompt.md
  ├── 001_binary_search_function_response.md
  ├── 002_refactor_auth_middleware_prompt.md
  ├── 002_refactor_auth_middleware_response.md
  └── 003_add_unit_tests_prompt.md
```

When browsing history with **Left/Right** arrows, the Prompt Browser shows both the original prompt and the agent's response in a combined view with ASCII section headers. Use **PgUp/PgDn** to scroll through long entries. Use **Up/Down** to toggle between active and favorites views.

### 10-Slot Favorites

Press **F** to assign a prompt to one of 10 numbered favorites slots (keys 1-9 and 0). Quick-load any favorite by pressing its number. Favorites indicators on the Prompt Browser border show which slots are filled.

### Session Continuity

Each session gets an ID passed to Claude via `--resume`, so conversation context carries across multiple execute cycles. Press **W** to start a fresh session. The context meter on the agent terminal border shows how much of Claude's context window has been used.

### Agent Stall Detection

While an agent is running, VoiceCode monitors output activity. If no output is received for 60+ seconds, a stall warning appears with a reminder that you can press **K** to kill the agent. A live activity spinner shows time since last output while the agent is working.

### Shortcuts Browser

Press **Tab** to open the shortcuts browser — a navigable overlay with three categories (cycle with **Up/Down**):

- **Custom shortcuts** — user-defined strings from `~/.config/voicecode/shortcuts.txt`
- **Project folders** — top-level and nested folders from your working directory
- **Documents** — markdown files from your `docs/` folder, sorted by modification time

This works **mid-recording**: the shortcut is timestamped and merged into the final transcript at the correct position using Whisper's word-level timestamps.

### Google Cast / Chromecast

VoiceCode can broadcast TTS summaries to Google Cast devices (Nest speakers, Chromecast, speaker groups) on your local network. Requires the `pychromecast` package to be installed.

Enable via **O** (options) → **Google Cast Notifications**:

- **Scan for Devices** — discovers Cast devices and speaker groups on your network
- **Select devices** — toggle individual devices on/off for broadcast
- **Cast Volume** — force device volume before playback (20–100%)
- **Mute Local TTS** — play speech only on Cast speakers, silencing local output

When enabled, every TTS summary is generated as a WAV file and streamed to all selected Cast devices simultaneously.


### Publish Documents

Press **P** to open the Publish overlay — a two-step modal that generates structured documentation from your codebase using specialized AI agents.

**Step 1 — Pick a document type:**

| Type | Purpose |
|------|---------|
| **ARCH** | High-level architecture overview — components, boundaries, data flow, and deployment topology |
| **PLAN** | Time-boxed implementation plan — scope, milestones, task breakdown, and dependencies |
| **SPEC** | Detailed feature specification — requirements, API contracts, edge cases, and acceptance criteria |

Additional types (BRIEF, SCHEMA, ADR, CONVENTIONS, CONSTRAINTS, GLOSSARY, RUNBOOK, WORKFLOW, CHANGELOG, README) are planned but not yet implemented.

**Step 2 — Pick a destination folder** within `docs/`:

```
docs/
  context/          — what the agent reads every session
  decisions/        — ADRs, numbered sequentially
  plans/            — active and archived plans
  specs/            — feature specs
  runbooks/         — operational docs
```

The publish agent uses your current prompt as its scope (what to focus on), builds a specialized system prompt for the selected document type, and sends it through the normal agent execution pipeline. The result is a well-structured markdown file written to your chosen `docs/` subfolder.

### Configuration

Settings are persisted to `~/.config/voicecode/settings.json` and can be changed in-app via the **O** key:

- **Paths** — Prompt library, working directory, documents directory
- **Voice** — Whisper model size, VAD sensitivity, silence timeout, min speech duration
- **TTS** — Enable/disable, volume gain, voice selection, voice downloads
- **AI** — Provider selection (Claude/Gemini), Gemini CLI command override
- **Cast** — Enable, volume, device selection, mute local TTS
- **Test Tools** — Echo test, TTS test sound, Cast broadcast test

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12 |
| Speech-to-Text | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (tiny.en / base.en / small.en / medium.en) |
| Voice Activity Detection | [Silero VAD](https://github.com/snakers4/silero-vad) + PyTorch (CPU-only) |
| Text-to-Speech | [Piper TTS](https://github.com/rhasspy/piper) |
| Audio Capture | sounddevice + NumPy |
| Cast Output | [PyChromecast](https://github.com/home-assistant-libs/pychromecast) (optional) |
| Terminal UI | Python curses |
| AI Backend | Claude CLI, Gemini CLI |

---

## Agent Support

**Supported agents:**
- **Claude CLI** (`claude` command) — runs with --dangerously-skip-permissions since we don't run in interactive mode - session continuity via `--resume`
- **Gemini CLI** (`gemini` command) — runs with `--yolo` flag since we don't run in interactive mode

---

<p align="center">
  <code>Protocol: ZMODEM-VOICE/1.0 · Connection: LOCAL · BPS: 115200</code>
</p>
