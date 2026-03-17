#!/usr/bin/env python3
"""
VoiceCode BBS - A retro BBS-style voice-driven prompt workshop & agent terminal.

          ╔═══════════════════════════════════════╗
          ║  V O I C E C O D E   B B S   v2.0     ║
          ║  "Your voice, your prompt, your way"  ║
          ╚═══════════════════════════════════════╝

Layout:
  ┌─ Prompt Browser ─────┬─ Agent Terminal ──────┐
  │  (view/edit prompts) │   (full height)       │
  ├─ Dictation Buffer ───┤   ZMODEM download     │
  │  (voice fragments)   │   animation +         │
  │                      │   typewriter response │
  └──────────────────────┴───────────────────────┘

Workflow:
  1. Dictate fragments → [R]efine into prompt
  2. [S]ave prompt to <library>/voicecode/YYYY/MM/DD/
  3. [←→] Browse saved prompts
  4. [E]xecute — sends prompt to Claude agent (right pane)
  5. Watch the ZMODEM transfer animation + typewriter response
"""

import curses
import sys
import os
import threading
import queue
import subprocess
import time
import datetime
import textwrap
import argparse
import random
import collections
from pathlib import Path

import json
import numpy as np
import sounddevice as sd
import torch


# ─── Settings persistence ────────────────────────────────────────────

SETTINGS_DIR = Path.home() / ".config" / "voicecode"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"
SHORTCUTS_FILE = SETTINGS_DIR / "shortcuts.txt"


def _load_settings() -> dict:
    """Load settings from disk, returning empty dict on any error."""
    try:
        return json.loads(SETTINGS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_settings(settings: dict):
    """Persist settings to disk."""
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2) + "\n")


def _load_shortcuts() -> list[str]:
    """Load user-defined shortcut strings from disk."""
    try:
        lines = SHORTCUTS_FILE.read_text().splitlines()
        return [l for l in lines if l.strip()]
    except (FileNotFoundError, OSError):
        return []


def _save_shortcuts(shortcuts: list[str]):
    """Persist shortcut strings to disk."""
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    SHORTCUTS_FILE.write_text("\n".join(shortcuts) + "\n" if shortcuts else "")


# ─── TTS globals ──────────────────────────────────────────────────────

PIPER_VOICES_DIR = Path.home() / ".local/share/piper-voices"
PIPER_VOICES = [
    "en_US-amy-medium",
    "en_US-lessac-medium",
    "en_US-libritts-high",
    "en_US-ryan-medium",
    "en_GB-alan-medium",
    "en_GB-jenny_dioco-medium",
    "en_US-arctic-medium",
    "en_US-hfc_female-medium",
    "en_US-hfc_male-medium",
    "en_US-joe-medium",
]

# Virtual voice presets — use an existing model with custom piper parameters
VOICE_PRESETS = {}

# Restore saved voice selection, falling back to index 0
_saved_voice = _load_settings().get("tts_voice")
_tts_voice_index = PIPER_VOICES.index(_saved_voice) if _saved_voice in PIPER_VOICES else 0
_tts_process = None  # Track running TTS playback for cancellation
_tts_enabled = _load_settings().get("tts_enabled", True)


TTS_PROMPT_SUFFIX = """

IMPORTANT: At the very end of your response, include a brief spoken summary
for text-to-speech. This must be plain text with NO markdown formatting
whatsoever — no asterisks, backticks, hash symbols, bullet points, dashes,
or any other markup. Write it as natural speech that sounds good read aloud.
Keep it concise (1-3 sentences). Wrap it exactly like this:

[TTS_SUMMARY]
Your plain text summary here.
[/TTS_SUMMARY]"""


def extract_tts_summary(text: str) -> str:
    """Extract the [TTS_SUMMARY] block from agent response text."""
    import re
    match = re.search(r'\[TTS_SUMMARY\]\s*(.*?)\s*\[/TTS_SUMMARY\]', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def get_tts_voice_model() -> Path:
    """Return the path to the currently selected Piper voice model."""
    voice = PIPER_VOICES[_tts_voice_index]
    preset = VOICE_PRESETS.get(voice)
    model_name = preset["model"] if preset else voice
    return PIPER_VOICES_DIR / (model_name + ".onnx")


def get_tts_piper_extra_args() -> list[str]:
    """Return extra piper CLI args for the current voice (e.g. preset tuning)."""
    voice = PIPER_VOICES[_tts_voice_index]
    preset = VOICE_PRESETS.get(voice)
    return list(preset["piper_args"]) if preset else []


def get_tts_voice_name() -> str:
    """Return the short display name of the currently selected voice."""
    return PIPER_VOICES[_tts_voice_index]


def cycle_tts_voice(direction: int) -> str:
    """Cycle the TTS voice forward (+1) or backward (-1). Returns new voice name."""
    global _tts_voice_index
    _tts_voice_index = (_tts_voice_index + direction) % len(PIPER_VOICES)
    voice = PIPER_VOICES[_tts_voice_index]
    settings = _load_settings()
    settings["tts_voice"] = voice
    _save_settings(settings)
    return voice


def delete_unused_voices() -> tuple[int, str]:
    """Delete all voice files except the currently selected one.

    Returns (count_deleted, current_voice_name).
    """
    current = PIPER_VOICES[_tts_voice_index]
    # Resolve preset to its underlying model name
    preset = VOICE_PRESETS.get(current)
    keep_model = preset["model"] if preset else current
    deleted = 0
    for voice in PIPER_VOICES:
        if voice in VOICE_PRESETS:
            continue  # preset voices share another model's files
        if voice == keep_model:
            continue
        for ext in (".onnx", ".onnx.json"):
            p = PIPER_VOICES_DIR / (voice + ext)
            if p.exists():
                p.unlink()
                deleted += 1
    return deleted, current


def download_all_voices(on_progress=None, on_done=None):
    """Download all configured voice files in a background thread.

    on_progress(voice_name, index, total) is called after each voice.
    on_done(success_count, fail_count) is called when finished.
    """
    from piper.download_voices import download_voice

    def _run():
        PIPER_VOICES_DIR.mkdir(parents=True, exist_ok=True)
        ok = 0
        fail = 0
        for i, voice in enumerate(PIPER_VOICES):
            try:
                # Preset voices reuse another model's files — download that instead
                model = VOICE_PRESETS[voice]["model"] if voice in VOICE_PRESETS else voice
                download_voice(model, PIPER_VOICES_DIR)
                ok += 1
            except Exception:
                fail += 1
            if on_progress:
                on_progress(voice, i + 1, len(PIPER_VOICES))
        if on_done:
            on_done(ok, fail)

    threading.Thread(target=_run, daemon=True).start()


def speak_text(text: str, on_done=None):
    """Speak text using Piper TTS + aplay in a background thread."""
    global _tts_process
    if not _tts_enabled:
        if on_done:
            on_done()
        return
    voice_model = get_tts_voice_model()
    extra_args = get_tts_piper_extra_args()

    def _run():
        global _tts_process
        try:
            if not voice_model.exists():
                return
            # Pipe text through piper as raw PCM, then play with aplay.
            # Using --output-raw avoids per-sentence WAV headers that cause
            # aplay to stop after the first sentence.
            piper_cmd = ["piper", "--model", str(voice_model),
                         "--output-raw", "--output_file", "/dev/stdout"] + extra_args
            piper_proc = subprocess.Popen(
                piper_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            play_proc = subprocess.Popen(
                ["aplay", "-q", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-c", "1"],
                stdin=piper_proc.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _tts_process = play_proc
            # Piper reads stdin line-by-line; collapse to one line so the
            # entire summary is synthesised, not just the first sentence.
            single_line = " ".join(text.split())
            piper_proc.stdin.write((single_line + "\n").encode("utf-8"))
            piper_proc.stdin.close()
            piper_proc.stdout.close()
            play_proc.wait()
        except Exception:
            pass
        finally:
            _tts_process = None
            if on_done:
                on_done()

    threading.Thread(target=_run, daemon=True).start()


def stop_speaking():
    """Stop any currently playing TTS audio."""
    global _tts_process
    if _tts_process:
        try:
            _tts_process.kill()
        except Exception:
            pass
        _tts_process = None


# ─── Audio / STT globals ───────────────────────────────────────────────

SAMPLE_RATE = 16000
CHANNELS = 1
BLOCK_SIZE = int(SAMPLE_RATE * 0.03)
VAD_THRESHOLD = 0.5
SILENCE_AFTER_SPEECH_SEC = 1.5
MIN_SPEECH_DURATION_SEC = 0.3

_whisper_model = None
_vad_model = None


def get_vad_model():
    global _vad_model
    if _vad_model is None:
        _vad_model, _ = torch.hub.load(
            "snakers4/silero-vad", "silero_vad", force_reload=False, onnx=False
        )
    return _vad_model


def get_whisper_model(model_size="base.en"):
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _whisper_model


def transcribe(audio: np.ndarray, model_size: str = "base.en") -> str:
    model = get_whisper_model(model_size)
    if audio.dtype != np.float32:
        audio = audio.astype(np.float32)
    segments, _ = model.transcribe(audio, beam_size=3, vad_filter=True)
    return " ".join(seg.text.strip() for seg in segments).strip()


def transcribe_with_timestamps(audio: np.ndarray, model_size: str = "base.en") -> tuple[str, list[tuple[float, float, str]]]:
    """Transcribe audio and return (full_text, [(start, end, word), ...])."""
    model = get_whisper_model(model_size)
    if audio.dtype != np.float32:
        audio = audio.astype(np.float32)
    segments, _ = model.transcribe(audio, beam_size=3, vad_filter=True, word_timestamps=True)
    words = []
    text_parts = []
    for seg in segments:
        text_parts.append(seg.text.strip())
        if seg.words:
            for w in seg.words:
                words.append((w.start, w.end, w.word))
    return " ".join(text_parts).strip(), words


# ─── Scrollable text pane ──────────────────────────────────────────────

class TextPane:
    """A scrollable text region within a curses window."""

    def __init__(self, title: str, color_pair: int):
        self.title = title
        self.lines: list[str] = []
        self.line_colors: dict[int, int] = {}  # line index -> color pair override
        self.scroll_offset = 0
        self.color_pair = color_pair
        self.welcome_art: list[str] = []  # shown centered when lines is empty

    def set_text(self, text: str, width: int):
        self.lines = []
        for paragraph in text.split("\n"):
            if not paragraph.strip():
                self.lines.append("")
            else:
                wrapped = textwrap.wrap(paragraph, width=max(1, width - 2))
                self.lines.extend(wrapped if wrapped else [""])

    def add_line(self, text: str, width: int):
        wrapped = textwrap.wrap(text, width=max(1, width - 2))
        self.lines.extend(wrapped if wrapped else [text])
        self.scroll_to_bottom(self._last_height if hasattr(self, '_last_height') else 10)

    def add_char_to_last_line(self, ch: str, width: int):
        """Append a character, wrapping if needed. For typewriter effect."""
        if not self.lines:
            self.lines.append("")
        if ch == "\n":
            self.lines.append("")
        else:
            last = self.lines[-1]
            if len(last) >= max(1, width - 3):
                self.lines.append(ch)
            else:
                self.lines[-1] = last + ch
        self.scroll_to_bottom(self._last_height if hasattr(self, '_last_height') else 10)

    def scroll_to_bottom(self, visible_height: int):
        max_offset = max(0, len(self.lines) - visible_height)
        self.scroll_offset = max_offset

    def scroll_up(self, amount=1):
        self.scroll_offset = max(0, self.scroll_offset - amount)

    def scroll_down(self, visible_height: int, amount=1):
        max_offset = max(0, len(self.lines) - visible_height)
        self.scroll_offset = min(max_offset, self.scroll_offset + amount)

    def draw(self, win, y: int, x: int, height: int, width: int):
        if height < 3 or width < 5:
            return
        self._last_height = height - 2

        border_attr = curses.color_pair(self.color_pair) | curses.A_BOLD
        title_str = f" {self.title} "
        # Truncate title if too long
        max_title = width - 6
        if len(title_str) > max_title:
            title_str = title_str[:max_title - 1] + "…"

        top = "╔══" + title_str + "═" * max(0, width - 3 - len(title_str) - 1) + "╗"

        try:
            win.addnstr(y, x, top, width, border_attr)
        except curses.error:
            pass

        visible_height = height - 2
        content_width = width - 2  # inside the ║ borders

        # Use welcome art left-justified in pane when no content
        if not self.lines and self.welcome_art:
            art_lines = self.welcome_art
            for i in range(visible_height):
                try:
                    win.addstr(y + 1 + i, x, "║", border_attr)
                    if i < len(art_lines):
                        art_line = art_lines[i]
                        art_line = art_line[:content_width - 1]
                        padding = " " * max(0, content_width - 1 - len(art_line))
                        win.addstr(y + 1 + i, x + 1, " " + art_line + padding,
                                   curses.color_pair(self.color_pair) | curses.A_DIM)
                    else:
                        win.addstr(y + 1 + i, x + 1, " " * max(0, content_width),
                                   curses.color_pair(self.color_pair))
                    win.addnstr(y + 1 + i, x + width - 1, "║", 1, border_attr)
                except curses.error:
                    pass
        else:
            visible_lines = self.lines[self.scroll_offset:self.scroll_offset + visible_height]
            for i in range(visible_height):
                try:
                    win.addstr(y + 1 + i, x, "║", border_attr)
                    if i < len(visible_lines):
                        line = visible_lines[i][:content_width - 1]
                        padding = " " * max(0, content_width - 1 - len(line))
                        line_idx = self.scroll_offset + i
                        line_cp = self.line_colors.get(line_idx, self.color_pair)
                        win.addstr(y + 1 + i, x + 1, " " + line + padding,
                                   curses.color_pair(line_cp))
                    else:
                        win.addstr(y + 1 + i, x + 1, " " * max(0, content_width),
                                   curses.color_pair(self.color_pair))
                    win.addnstr(y + 1 + i, x + width - 1, "║", 1, border_attr)
                except curses.error:
                    pass

        bottom = "╚" + "═" * max(0, width - 2) + "╝"
        try:
            win.addnstr(y + height - 1, x, bottom, width, border_attr)
        except curses.error:
            pass

        # Scroll indicator
        if len(self.lines) > visible_height and visible_height > 0:
            total = len(self.lines)
            pos = self.scroll_offset / max(1, total - visible_height)
            indicator_y = y + 1 + int(pos * max(0, visible_height - 1))
            try:
                win.addstr(indicator_y, x + width - 1, "█", border_attr)
            except curses.error:
                pass


# ─── Refinement engine ─────────────────────────────────────────────────

INITIAL_REFINE_PROMPT = """\
You are a prompt engineer. The user has dictated the following speech fragments \
while thinking about what they want to ask an AI coding assistant. \
Your job is to synthesize these fragments into a single, clear, well-structured prompt \
that faithfully captures their intent, meaning, and all details mentioned.

Rules:
- Be faithful to what they said. Do not add requirements they didn't mention.
- Organize the prompt logically even if they jumped around.
- Use clear, direct language.
- If they mentioned specific files, tools, or technologies, include those.
- Output ONLY the refined prompt, nothing else. No preamble, no explanation.

Speech fragments:
---
{fragments}
---

Refined prompt:"""

MODIFY_REFINE_PROMPT = """\
You are a prompt engineer. The user previously built this prompt through voice dictation:

CURRENT PROMPT:
---
{current_prompt}
---

They have now dictated additional fragments to modify or extend this prompt. \
Apply their changes faithfully. They may want to:
- Add new requirements or details
- Change or clarify existing parts
- Remove something
- Restructure the prompt

New dictation fragments:
---
{fragments}
---

Rules:
- Output ONLY the updated prompt, nothing else.
- Preserve parts of the original that aren't being changed.
- Be faithful to their intent.

Updated prompt:"""


def refine_with_llm(fragments: list[str], current_prompt: str | None,
                    status_callback=None) -> str:
    if status_callback:
        status_callback("Refining with Claude...")

    fragment_text = "\n".join(f"- {f}" for f in fragments)

    if current_prompt:
        meta_prompt = MODIFY_REFINE_PROMPT.format(
            current_prompt=current_prompt, fragments=fragment_text)
    else:
        meta_prompt = INITIAL_REFINE_PROMPT.format(fragments=fragment_text)

    try:
        result = subprocess.run(
            ["claude", "--print", "-p", meta_prompt],
            capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        else:
            return f"[Error: {result.stderr.strip() or 'empty response'}]"
    except FileNotFoundError:
        return "[Error: 'claude' CLI not found]"
    except subprocess.TimeoutExpired:
        return "[Error: timed out after 120s]"
    except Exception as e:
        return f"[Error: {e}]"


# ─── Agent execution states ───────────────────────────────────────────

class AgentState:
    IDLE = "idle"
    DOWNLOADING = "downloading"  # ZMODEM animation
    RECEIVING = "receiving"      # typewriter output
    DONE = "done"


# ─── ZMODEM download art ──────────────────────────────────────────────

ZMODEM_FRAMES = [
    "rz waiting to receive.",
    "rz waiting to receive..",
    "rz waiting to receive...",
    "Starting zmodem transfer.",
    "Transferring prompt data...",
]


# ─── Main BBS Application ─────────────────────────────────────────────

BANNER = r"""
██╗   ██╗ ██████╗ ██╗ ██████╗███████╗ ██████╗ ██████╗ ██████╗ ███████╗
 ██║   ██║██╔═══██╗██║██╔════╝██╔════╝██╔════╝██╔═══██╗██╔══██╗██╔════╝
 ██║   ██║██║   ██║██║██║     █████╗  ██║     ██║   ██║██║  ██║█████╗
 ╚██╗ ██╔╝██║   ██║██║██║     ██╔══╝  ██║     ██║   ██║██║  ██║██╔══╝
  ╚████╔╝ ╚██████╔╝██║╚██████╗███████╗╚██████╗╚██████╔╝██████╔╝███████╗
   ╚═══╝   ╚═════╝ ╚═╝ ╚═════╝╚══════╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝
                                                            @schiele
                  ╔════════════════════════════════╗
                  ║     B  ·  B  ·  S    v2.0      ║
                  ║  Voice-Driven Prompt Workshop  ║
                  ╚════════════════════════════════╝                   """


class BBSApp:
    """The main curses application — three-pane BBS terminal."""

    # Color pair IDs
    CP_HEADER = 1
    CP_PROMPT = 2
    CP_DICTATION = 3
    CP_STATUS = 4
    CP_HELP = 5
    CP_RECORDING = 6
    CP_BANNER = 7
    CP_ACCENT = 8
    CP_AGENT = 9
    CP_XFER = 10
    CP_VOICE = 11
    CP_CTX_GREEN = 12
    CP_CTX_YELLOW = 13
    CP_CTX_RED = 14
    CP_XTREE_BG = 15
    CP_XTREE_SEL = 16
    CP_XTREE_BORDER = 17
    CP_TTS = 18

    def __init__(self, args):
        self.args = args

        # Left panes
        self.prompt_pane = TextPane("PROMPT BROWSER", self.CP_PROMPT)
        self.dictation_pane = TextPane("DICTATION BUFFER", self.CP_DICTATION)

        # Right pane
        self.agent_pane = TextPane("AGENT TERMINAL", self.CP_AGENT)

        # Retro welcome art shown when panes are empty
        self.prompt_pane.welcome_art = [
            "╔══════════════════════════════════════╗",
            "║       ◆  PROMPT  WORKSHOP  ◆         ║",
            "║   Press SPACE to start dictating...  ║",
            "╚══════════════════════════════════════╝",
            "",
            "  [SPACE] Record   [R] Refine   [D] Direct execute",
            "  [END] Clear working prompt & buffer",
            "",
            "  ←→ to browse saved prompts",
            "  ↑↓ cycle active/favorites/history",
        ]
        self.dictation_pane.welcome_art = [
            "╔══════════════════════════════════════╗",
            "║      ◆  DICTATION  BUFFER  ◆         ║",
            "║   Voice fragments appear here as     ║",
            "║   you record with SPACE.             ║",
            "╚══════════════════════════════════════╝",
            "",
            "  This is your scratchpad for voice input.",
            "  Fragments collect here, then:",
            "",
            "  [R] Refine → merges into the Prompt above",
            "  [D] Direct → sends straight to the Agent",
            "  [C] Clear  → wipe and start over",
            "",
            "                         [P] Replay TTS ♪",
        ]
        self.agent_pane.welcome_art = [
            "╔═══════════════════════════════════════╗",
            "║   GREETINGS PROFESSOR FALKEN.         ║",
            "╚═══════════════════════════════════════╝",
            "",
            "  READY TO RECEIVE TRANSMISSION.",
            "",
            "  Awaiting prompt upload...",
            "  Protocol: ZMODEM-VOICE/1.0",
            "  Connection: LOCAL",
            "",
            "  ── Quick Start ─────────────────",
            "",
            "  SPACE ··· Record voice",
            "  R     ··· Refine into prompt",
            "  E     ··· Execute prompt",
            "  D     ··· Direct execute",
            "  W     ··· New session (clear context)",
            "  H     ··· Full help screen",
            "  ESC   ··· Main menu",
        ]

        self.fragments: list[str] = []
        self.current_prompt: str | None = None
        self.prompt_version = 0

        self.status_msg = "Welcome to VoiceCode BBS v2.0!"
        self.status_color = self.CP_STATUS
        self.running = True
        self.restart = False
        self.recording = False
        self.refining = False

        # Audio
        self.audio_frames: list[np.ndarray] = []
        self.audio_lock = threading.Lock()

        # Event queue for cross-thread UI updates
        self.ui_queue: queue.Queue = queue.Queue()

        # Prompt library & save dir
        # Priority: CLI --save-dir (explicit) > persisted setting > default ~/prompts
        saved = _load_settings()
        cli_save_dir_explicit = any(a in sys.argv for a in ("--save-dir",))
        if cli_save_dir_explicit:
            self.prompt_library = str(Path(args.save_dir).expanduser())
        else:
            self.prompt_library = saved.get(
                "prompt_library", str(Path(args.save_dir).expanduser()))
        # Voicecode writes into a dedicated subfolder within the library
        self.save_base = Path(self.prompt_library).expanduser() / "voicecode"
        self.history_base = self.save_base / "history"
        self.favorites_base = self.save_base / "favorites"
        self.saved_prompts: list[Path] = []
        self.history_prompts: list[Path] = []
        self.favorites_prompts: list[Path] = []
        self.browser_index: int = -1
        self.browser_view: str = "active"  # "active", "history", or "favorites"
        self._scan_saved_prompts()
        self._scan_history_prompts()
        self._scan_favorites_prompts()

        # Prompt saved state
        self.prompt_saved = True  # no unsaved prompt at start
        self.confirming_new = False  # for [N] save confirmation dialog

        # Working directory for folder slug mode
        self.working_dir = saved.get("working_dir", "")

        # Help overlay state
        self.show_help_overlay = False
        self.show_about_overlay = False

        # Escape menu overlay state
        self.show_escape_menu = False
        self.escape_menu_cursor = 0
        self._escape_menu_items = [
            ("Options", "settings"),
            ("Help", "help"),
            ("About", "about"),
            ("Restart", "restart"),
            ("Quit", "quit"),
        ]

        # Shortcuts overlay state (was folder slug)
        self.show_folder_slug = False
        self.folder_slug_cursor = 0
        self.folder_slug_list: list[str] = []
        self.folder_slug_scroll = 0
        self._shortcut_strings: list[str] = _load_shortcuts()
        self._shortcut_count = 0  # how many items at the top are shortcuts

        # Shortcut editor overlay state
        self.show_shortcut_editor = False
        self.shortcut_editor_cursor = 0
        self.shortcut_editor_scroll = 0
        self.shortcut_editing_text = False
        self.shortcut_edit_buffer = ""
        self.shortcut_edit_cursor_pos = 0

        # Mid-recording folder injections: [(audio_seconds, text), ...]
        self._recording_injections: list[tuple[float, str]] = []

        # Settings overlay state
        self.show_settings_overlay = False
        self.settings_cursor = 0
        self.settings_editing_text = False  # True when inline text editing is active
        self.settings_edit_buffer = ""      # current text being edited
        self.settings_edit_cursor = 0       # cursor position within buffer

        # TTS sub-menu state
        self.tts_submenu_open = False
        self.tts_submenu_cursor = 0
        self.tts_enabled = saved.get("tts_enabled", True)
        global _tts_enabled
        _tts_enabled = self.tts_enabled

        # Voice settings (mutable, persisted) — `saved` loaded above for prompt_library
        self.vad_threshold = saved.get("vad_threshold", VAD_THRESHOLD)
        self.silence_timeout = saved.get("silence_timeout", SILENCE_AFTER_SPEECH_SEC)
        self.min_speech_duration = saved.get("min_speech_duration", MIN_SPEECH_DURATION_SEC)
        self.whisper_model = args.model  # from CLI, overrideable in settings
        if "whisper_model" in saved and not any(
                a in sys.argv for a in ("--model",)):
            self.whisper_model = saved["whisper_model"]

        # Settings definitions: (key, label, description, options, get_current, set_fn)
        self._build_settings_items()

        # Agent state
        self.agent_state = AgentState.IDLE
        self.agent_process = None
        self.last_tts_summary = ""

        # Session continuity — reuse session_id across prompts
        self.session_id: str | None = None
        self.session_turns = 0
        self.context_tokens_used = 0
        self.context_window_size = 0

        # ZMODEM animation state
        self.xfer_progress = 0.0
        self.xfer_frame = 0
        self.xfer_bytes = 0
        self.xfer_start_time = 0.0
        self.xfer_prompt_text = ""

        # Typewriter state
        self.typewriter_queue: collections.deque = collections.deque()
        self.typewriter_last_time = 0.0
        self.typewriter_char_delay = 0.006  # seconds per char (~167 cps)
        self.typewriter_line_delay = 0.02   # extra delay at newlines
        self._typewriter_line_color = None  # per-line color override (None = default)
        self.agent_first_output = False      # tracks if agent has produced any output
        self.agent_welcome_shown = False     # True after initial welcome art displayed

        # Pending source pane tracking (yellow border while agent processes)
        self._agent_source_pane = None       # which pane sent the prompt
        self._agent_source_original_color = None  # original color_pair to restore

        # Executed prompt display — persists in prompt browser until new prompt
        self.executed_prompt_text: str | None = None
        self._prompt_pane_original_color: int | None = None

    # ─── Settings items ────────────────────────────────────────────

    def _build_settings_items(self):
        """Build the list of settings for the settings modal."""
        self.settings_items = [
            {
                "key": "prompt_library",
                "label": "Prompt Library",
                "desc": "Path to prompt library (voicecode/ subfolder auto-created)",
                "options": None,
                "get": lambda: self.prompt_library,
                "set": None,
                "editable": True,
                "action": self._start_editing_prompt_library,
            },
            {
                "key": "working_dir",
                "label": "Working Directory",
                "desc": "Source repo root for folder shortcuts (Enter key)",
                "options": None,
                "get": lambda: self.working_dir or "(not set)",
                "set": None,
                "editable": True,
                "action": self._start_editing_working_dir,
            },
            {
                "key": "whisper_model",
                "label": "Whisper Model",
                "desc": "Speech-to-text model (larger = slower but more accurate)",
                "options": ["tiny.en", "base.en", "small.en", "medium.en"],
                "get": lambda: self.whisper_model,
                "set": self._set_whisper_model,
            },
            {
                "key": "vad_threshold",
                "label": "VAD Threshold",
                "desc": "Voice activity sensitivity (lower = more sensitive)",
                "options": [0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
                "get": lambda: self.vad_threshold,
                "set": self._set_vad_threshold,
            },
            {
                "key": "silence_timeout",
                "label": "Silence Timeout",
                "desc": "Seconds of silence before auto-stop (handsfree mode)",
                "options": [0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
                "get": lambda: self.silence_timeout,
                "set": self._set_silence_timeout,
            },
            {
                "key": "min_speech_duration",
                "label": "Min Speech Duration",
                "desc": "Minimum seconds of speech to accept a recording",
                "options": [0.1, 0.2, 0.3, 0.5, 0.7, 1.0],
                "get": lambda: self.min_speech_duration,
                "set": self._set_min_speech,
            },
            {
                "key": "_action_tts_submenu",
                "label": "[Enter] Text-to-Speech Settings",
                "desc": "Configure TTS voices, libraries, and enable/disable",
                "options": None,
                "get": lambda: "ON" if self.tts_enabled else "OFF",
                "set": None,
                "action": self._open_tts_submenu,
            },
            {
                "key": "_action_echo_test",
                "label": "[Enter] Echo / Mic Test",
                "desc": "Record 1s of audio and play it back to test your mic",
                "options": None,
                "get": lambda: "",
                "set": None,
                "action": self._echo_test,
            },
            {
                "key": "_action_edit_shortcuts",
                "label": "[Enter] Edit Shortcuts",
                "desc": "Manage shortcut strings for the Shortcuts browser (Enter key)",
                "options": None,
                "get": lambda: f"{len(self._shortcut_strings)} shortcut(s)",
                "set": None,
                "action": self._open_shortcut_editor,
            },
        ]

    def _build_tts_submenu_items(self):
        """Build the TTS sub-menu items list."""
        return [
            {
                "key": "tts_enabled",
                "label": "Enable/Disable TTS",
                "desc": "Turn text-to-speech on or off entirely",
                "options": ["ON", "OFF"],
                "get": lambda: "ON" if self.tts_enabled else "OFF",
                "set": self._set_tts_enabled,
            },
            {
                "key": "tts_voice",
                "label": "Configure Voices",
                "desc": "Text-to-speech voice for spoken summaries",
                "options": PIPER_VOICES,
                "get": get_tts_voice_name,
                "set": self._set_tts_voice,
            },
            {
                "key": "_action_download_voices",
                "label": "[Enter] Download All Voice Models",
                "desc": "⚠ WARNING: Large download — fetches all Piper voice files",
                "options": None,
                "get": lambda: "",
                "set": None,
                "action": self._action_download_voices,
            },
            {
                "key": "_action_clean_voices",
                "label": "[Enter] Clean Unused Voice Models",
                "desc": "Delete downloaded voice models not currently selected",
                "options": None,
                "get": lambda: "",
                "set": None,
                "action": self._action_clean_voices,
            },
        ]

    def _open_tts_submenu(self):
        """Open the TTS settings sub-menu."""
        self.tts_submenu_open = True
        self.tts_submenu_cursor = 0
        self.tts_submenu_items = self._build_tts_submenu_items()
        self.show_settings_overlay = True  # keep modal open

    def _set_tts_enabled(self, val):
        global _tts_enabled
        self.tts_enabled = (val == "ON")
        _tts_enabled = self.tts_enabled
        self._persist_setting("tts_enabled", self.tts_enabled)
        state = "enabled" if self.tts_enabled else "disabled"
        self._set_status(f"Text-to-speech {state}")

    def _tts_submenu_cycle(self, direction):
        """Cycle the current TTS sub-menu setting's value."""
        item = self.tts_submenu_items[self.tts_submenu_cursor]
        if item.get("options") is None:
            return
        options = item["options"]
        current = item["get"]()
        try:
            idx = options.index(current)
        except ValueError:
            idx = 0
        new_idx = (idx + direction) % len(options)
        item["set"](options[new_idx])

    def _set_whisper_model(self, val):
        global _whisper_model
        if val != self.whisper_model:
            self.whisper_model = val
            _whisper_model = None  # force reload on next use
            self._persist_setting("whisper_model", val)
            self._set_status(f"Whisper model → {val} (will load on next recording)")

    def _set_vad_threshold(self, val):
        global VAD_THRESHOLD
        self.vad_threshold = val
        VAD_THRESHOLD = val
        self._persist_setting("vad_threshold", val)

    def _set_silence_timeout(self, val):
        global SILENCE_AFTER_SPEECH_SEC
        self.silence_timeout = val
        SILENCE_AFTER_SPEECH_SEC = val
        self._persist_setting("silence_timeout", val)

    def _set_min_speech(self, val):
        global MIN_SPEECH_DURATION_SEC
        self.min_speech_duration = val
        MIN_SPEECH_DURATION_SEC = val
        self._persist_setting("min_speech_duration", val)

    def _set_tts_voice(self, val):
        global _tts_voice_index
        if val in PIPER_VOICES:
            _tts_voice_index = PIPER_VOICES.index(val)
            settings = _load_settings()
            settings["tts_voice"] = val
            _save_settings(settings)

    def _action_download_voices(self):
        self._set_status("Downloading all voice files...")
        def _on_progress(name, i, total):
            self._set_status(f"Downloading voices... {i}/{total}: {name}")
        def _on_done(ok, fail):
            if fail:
                self._set_status(f"Downloaded {ok} voices, {fail} failed.")
                speak_text(f"Downloaded {ok} voices. {fail} failed.")
            else:
                self._set_status(f"All {ok} voices downloaded.")
                speak_text(f"All {ok} voices downloaded successfully.")
        download_all_voices(on_progress=_on_progress, on_done=_on_done)

    def _action_clean_voices(self):
        deleted, kept = delete_unused_voices()
        if deleted:
            self._set_status(f"Deleted {deleted} unused voice files, kept {kept}")
            speak_text(f"Deleted {deleted} unused voice files.")
        else:
            self._set_status(f"No unused voice files to delete.")

    def _start_editing_prompt_library(self):
        """Enter inline text editing mode for the prompt library path."""
        self.settings_editing_text = True
        self.settings_edit_buffer = self.prompt_library
        self.settings_edit_cursor = len(self.settings_edit_buffer)
        self.show_settings_overlay = True  # keep modal open

    def _commit_prompt_library(self):
        """Apply the edited prompt library path."""
        new_path = self.settings_edit_buffer.strip()
        if not new_path:
            new_path = str(Path("~/prompts").expanduser())
        self.prompt_library = new_path
        self.save_base = Path(new_path).expanduser() / "voicecode"
        self._persist_setting("prompt_library", new_path)
        self._scan_saved_prompts()
        self.settings_editing_text = False
        self._set_status(f"Prompt library → {new_path}/voicecode/")

    def _cancel_text_edit(self):
        """Cancel inline text editing."""
        self.settings_editing_text = False

    def _commit_text_edit(self):
        """Dispatch text edit commit based on which setting is being edited."""
        item = self.settings_items[self.settings_cursor]
        if item["key"] == "prompt_library":
            self._commit_prompt_library()
        elif item["key"] == "working_dir":
            self._commit_working_dir()

    def _start_editing_working_dir(self):
        """Enter inline text editing mode for the working directory path."""
        self.settings_editing_text = True
        self.settings_edit_buffer = self.working_dir
        self.settings_edit_cursor = len(self.settings_edit_buffer)
        self.show_settings_overlay = True

    def _commit_working_dir(self):
        """Apply the edited working directory path."""
        new_path = self.settings_edit_buffer.strip()
        self.working_dir = new_path
        self._persist_setting("working_dir", new_path)
        self.settings_editing_text = False
        if new_path:
            self._set_status(f"Working directory → {new_path}")
        else:
            self._set_status("Working directory cleared.")

    def _persist_setting(self, key, val):
        settings = _load_settings()
        settings[key] = val
        _save_settings(settings)

    def _settings_cycle(self, direction):
        """Cycle the current setting's value left (-1) or right (+1)."""
        item = self.settings_items[self.settings_cursor]
        if item.get("options") is None:
            return  # action item, no cycling
        options = item["options"]
        current = item["get"]()
        try:
            idx = options.index(current)
        except ValueError:
            idx = 0
        new_idx = (idx + direction) % len(options)
        item["set"](options[new_idx])

    # ─── Prompt browser ────────────────────────────────────────────

    def _scan_saved_prompts(self):
        self.saved_prompts = sorted(
            p for p in self.save_base.rglob("prompt_*.md")
            if not str(p).startswith(str(self.history_base))
            and not str(p).startswith(str(self.favorites_base))
        )

    def _scan_history_prompts(self):
        self.history_prompts = sorted(self.history_base.rglob("prompt_*.md"))

    def _scan_favorites_prompts(self):
        self.favorites_prompts = sorted(self.favorites_base.rglob("prompt_*.md"))

    def _current_browser_list(self) -> list[Path]:
        """Return the prompt list for the current browser view."""
        if self.browser_view == "history":
            return self.history_prompts
        if self.browser_view == "favorites":
            return self.favorites_prompts
        return self.saved_prompts

    def _load_browser_prompt(self, width: int):
        prompt_list = self._current_browser_list()
        view_labels = {"history": "HISTORY", "favorites": "FAVORITES", "active": "PROMPTS"}
        view_label = view_labels.get(self.browser_view, "PROMPTS")

        if self.browser_index < 0 or self.browser_index >= len(prompt_list):
            self.browser_index = -1
            if self.browser_view == "favorites":
                self.prompt_pane.title = "FAVORITES BROWSER"
                self.prompt_pane.set_text(
                    "(no favorite selected)\n\n"
                    f"Favorite prompts: {len(self.favorites_prompts)}  ←→ to browse\n"
                    "↑↓ switch views\n"
                    "HOME reset to new prompt", width)
            elif self.browser_view == "history":
                self.prompt_pane.title = "HISTORY BROWSER"
                self.prompt_pane.set_text(
                    "(no history entry selected)\n\n"
                    f"Executed prompts: {len(self.history_prompts)}  ←→ to browse\n"
                    "↑↓ switch views\n"
                    "HOME reset to new prompt", width)
            elif self.executed_prompt_text:
                self.prompt_pane.title = "EXECUTING PROMPT"
                self.prompt_pane.set_text(self.executed_prompt_text, width)
            elif self.current_prompt:
                self.prompt_pane.title = f"PROMPT WORKSHOP — session v{self.prompt_version}"
                self.prompt_pane.set_text(self.current_prompt, width)
            else:
                self.prompt_pane.title = "NEW PROMPT — ready for dictation"
                # Clear lines so welcome_art renders (left-justified & dimmed)
                self.prompt_pane.lines = []
            self.prompt_pane.scroll_offset = 0
            return

        path = prompt_list[self.browser_index]
        base = (self.history_base if self.browser_view == "history"
                else self.favorites_base if self.browser_view == "favorites"
                else self.save_base)
        try:
            rel = path.relative_to(base)
        except ValueError:
            rel = path
        n = len(prompt_list)
        idx = self.browser_index + 1
        self.prompt_pane.title = f"[{idx}/{n}] {view_label}: {rel}"

        try:
            content = path.read_text()
        except Exception as e:
            content = f"[Error: {e}]"

        self.prompt_pane.set_text(content, width)
        self.prompt_pane.scroll_offset = 0

    def _set_dictation_info(self, width: int):
        """Show info box in dictation buffer when it's empty."""
        if self.dictation_pane.lines:
            return  # don't overwrite existing content
        # Clear lines so welcome_art renders (left-justified & dimmed)
        self.dictation_pane.lines = []
        self.dictation_pane.scroll_offset = 0

    def _set_agent_welcome(self, width: int):
        """Show welcome/help text in the agent terminal pane (first launch only)."""
        if self.agent_welcome_shown:
            return
        self.agent_welcome_shown = True
        # Clear lines so welcome_art renders (left-justified & dimmed)
        self.agent_pane.lines = []
        self.agent_pane.line_colors = {}
        self.agent_pane.scroll_offset = 0

    def _get_active_prompt_text(self) -> str | None:
        """Get the prompt text currently shown in the browser, for execution."""
        prompt_list = self._current_browser_list()
        if self.browser_index >= 0 and self.browser_index < len(prompt_list):
            path = prompt_list[self.browser_index]
            try:
                raw = path.read_text()
                # Strip comment headers
                lines = [l for l in raw.split("\n") if not l.startswith("#")]
                return "\n".join(lines).strip()
            except Exception:
                return None
        elif self.current_prompt:
            return self.current_prompt
        elif self.executed_prompt_text:
            return self.executed_prompt_text
        return None

    # ─── Main loop ─────────────────────────────────────────────────

    def run(self, stdscr):
        self.stdscr = stdscr
        self._init_colors()
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.timeout(16)  # ~60fps for smooth animations

        self._draw_loading("Loading Silero VAD model...")
        get_vad_model()
        self._draw_loading("Loading Whisper model...")
        get_whisper_model(self.whisper_model)
        self._draw_loading("Ready!")
        time.sleep(2.0)

        self._load_browser_prompt(80)
        self._set_dictation_info(80)
        self._set_agent_welcome(40)

        while self.running:
            self._process_ui_queue()
            self._process_typewriter()
            self._draw()
            self._handle_input()

    def _init_colors(self):
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(self.CP_HEADER, curses.COLOR_YELLOW, curses.COLOR_BLUE)
        curses.init_pair(self.CP_PROMPT, curses.COLOR_WHITE, curses.COLOR_BLACK)
        curses.init_pair(self.CP_DICTATION, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(self.CP_STATUS, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(self.CP_HELP, curses.COLOR_YELLOW, curses.COLOR_BLUE)
        curses.init_pair(self.CP_RECORDING, curses.COLOR_WHITE, curses.COLOR_RED)
        curses.init_pair(self.CP_BANNER, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(self.CP_ACCENT, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
        curses.init_pair(self.CP_AGENT, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(self.CP_XFER, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(self.CP_VOICE, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(self.CP_CTX_GREEN, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(self.CP_CTX_YELLOW, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(self.CP_CTX_RED, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(self.CP_XTREE_BG, curses.COLOR_BLACK, curses.COLOR_YELLOW)
        curses.init_pair(self.CP_XTREE_SEL, curses.COLOR_YELLOW, curses.COLOR_BLUE)
        curses.init_pair(self.CP_XTREE_BORDER, curses.COLOR_WHITE, curses.COLOR_YELLOW)
        curses.init_pair(self.CP_TTS, curses.COLOR_WHITE, curses.COLOR_BLACK)

    def _draw_loading(self, msg: str):
        self.stdscr.clear()
        h, w = self.stdscr.getmaxyx()
        lines = BANNER.strip().split("\n")
        max_line_w = max(len(l) for l in lines)
        start_y = max(0, (h - len(lines) - 4) // 2)
        block_x = max(0, (w - max_line_w) // 2)
        for i, line in enumerate(lines):
            try:
                cp = self.CP_BANNER if i < 7 else self.CP_ACCENT
                self.stdscr.addstr(start_y + i, block_x, line[:w-1],
                                   curses.color_pair(cp) | curses.A_BOLD)
            except curses.error:
                pass
        msg_x = max(0, (w - len(msg)) // 2)
        try:
            self.stdscr.addstr(start_y + len(lines) + 2, msg_x, msg,
                               curses.color_pair(self.CP_STATUS) | curses.A_BOLD)
        except curses.error:
            pass
        self.stdscr.refresh()

    # ─── Drawing ───────────────────────────────────────────────────

    def _draw(self):
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()

        if h < 12 or w < 60:
            try:
                self.stdscr.addstr(0, 0, "Terminal too small! Need 60x12 minimum.")
            except curses.error:
                pass
            self.stdscr.refresh()
            return

        # ── Header bar ──
        header = " VOICECODE BBS v2.0"
        now = datetime.datetime.now().strftime("%H:%M:%S")
        sysop = f"SysOp: {os.getenv('USER', '?')}"
        voice_tag = f"Voice: {get_tts_voice_name()}"
        right = f"{voice_tag}  {sysop}  {now} "
        header_line = header + " " * max(0, w - len(header) - len(right)) + right
        try:
            self.stdscr.addnstr(0, 0, header_line, w,
                                curses.color_pair(self.CP_HEADER) | curses.A_BOLD)
        except curses.error:
            pass

        # ── Divider ──
        prompt_list = self._current_browser_list()
        view_labels = {"history": "History", "favorites": "Favorites", "active": "Prompts"}
        view_label = view_labels.get(self.browser_view, "Prompts")
        if self.browser_index >= 0:
            browse_info = f"{view_label}: {self.browser_index + 1}/{len(prompt_list)}"
        else:
            browse_info = f"Session v{self.prompt_version}"
        node_info = (f" {browse_info} │ Saved: {len(self.saved_prompts)} │ "
                     f"Favs: {len(self.favorites_prompts)} │ "
                     f"History: {len(self.history_prompts)} │ "
                     f"Frags: {len(self.fragments)} │ Agent: {self.agent_state.upper()} ")
        divider = "─" * 2 + node_info + "─" * max(0, w - 2 - len(node_info))
        try:
            self.stdscr.addnstr(1, 0, divider, w - 1,
                                curses.color_pair(self.CP_ACCENT))
        except curses.error:
            pass

        # ── Three-pane layout ──
        # content_height = everything between divider and help/status bars
        content_height = h - 4  # header + divider + help + status
        left_width = w // 2
        right_width = w - left_width
        prompt_height = content_height // 2
        dictation_height = content_height - prompt_height

        content_y = 2

        # Top-left: Prompt browser
        self.prompt_pane.draw(self.stdscr, content_y, 0,
                              prompt_height, left_width)

        # Bottom-left: Dictation buffer
        self.dictation_pane.draw(self.stdscr, content_y + prompt_height, 0,
                                 dictation_height, left_width)

        # Right: Agent terminal (full height)
        if self.agent_state == AgentState.DOWNLOADING:
            self._draw_agent_xfer(content_y, left_width, content_height, right_width)
        else:
            self.agent_pane.draw(self.stdscr, content_y, left_width,
                                 content_height, right_width)

        # Yellow spinner in agent pane header while agent is active
        if self.agent_state in (AgentState.DOWNLOADING, AgentState.RECEIVING):
            spin_chars = "|/-\\"
            spin_ch = spin_chars[int(time.time() * 4) % len(spin_chars)]
            # Place spinner right after the title text in the header
            title_text = " AGENT TERMINAL " if self.agent_state != AgentState.DOWNLOADING else " FILE TRANSFER "
            spin_x = left_width + 3 + len(title_text)
            if spin_x < left_width + right_width - 2:
                try:
                    self.stdscr.addstr(
                        content_y, spin_x, spin_ch,
                        curses.color_pair(self.CP_XFER) | curses.A_BOLD)
                except curses.error:
                    pass
            # Show thinking indicator while waiting for agent output
            if (self.agent_state == AgentState.RECEIVING
                    and not self.typewriter_queue
                    and not self.agent_first_output):
                elapsed = time.time() - self.xfer_start_time - 3.0  # subtract ZMODEM time
                spinners = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
                spin = spinners[int(elapsed * 6) % len(spinners)]
                dots = "." * (int(elapsed * 2) % 4)
                thinking_text = f" {spin} Agent processing{dots}"
                # Draw over last content line of agent pane
                think_y = content_y + 1 + len(self.agent_pane.lines)
                if think_y < content_y + content_height - 1:
                    try:
                        self.stdscr.addnstr(
                            think_y, left_width + 1, thinking_text,
                            right_width - 2,
                            curses.color_pair(self.CP_XFER) | curses.A_BOLD)
                    except curses.error:
                        pass

        # ── Agent terminal bottom border: context meter + session info ──
        agent_bottom_y = content_y + content_height - 1
        if self.context_window_size > 0:
            ratio = min(1.0, self.context_tokens_used / self.context_window_size)
            if ratio < 0.5:
                ctx_cp = self.CP_CTX_GREEN
            elif ratio < 0.8:
                ctx_cp = self.CP_CTX_YELLOW
            else:
                ctx_cp = self.CP_CTX_RED
            pct = int(ratio * 100)
            ctx_label = f" CTX:{pct}% "
        else:
            ctx_cp = self.CP_CTX_GREEN
            ctx_label = ""

        # Session info tag
        if self.session_id:
            sess_label = f" Session: {self.session_turns} turn{'s' if self.session_turns != 1 else ''} "
        else:
            sess_label = " No session "
        hint_label = " [W]New session "

        # Draw colored bottom border for agent pane
        bar_inner_w = right_width - 2  # inside ╚ ╝
        info_text = sess_label + ctx_label
        # Pad bar to fill, then overlay info on the right
        if bar_inner_w > 0:
            ctx_attr = curses.color_pair(ctx_cp) | curses.A_BOLD
            # Build the bottom border with session/context info
            bar = "═" * max(0, bar_inner_w - len(info_text) - len(hint_label))
            full_bar = "╚" + hint_label + bar + info_text + "╝"
            try:
                self.stdscr.addnstr(agent_bottom_y, left_width, full_bar,
                                    right_width, ctx_attr)
            except curses.error:
                pass

        # ── Favorites hint on prompt pane top border ──
        if self.browser_view == "history" and self.browser_index >= 0:
            fav_hint = " [F] ★ Favorite "
            fav_x = left_width - len(fav_hint) - 1
            if fav_x > 4:
                try:
                    self.stdscr.addstr(content_y, fav_x, fav_hint,
                                       curses.color_pair(self.CP_RECORDING) | curses.A_BOLD)
                except curses.error:
                    pass
        elif self.browser_view == "favorites" and self.browser_index >= 0:
            fav_hint = " [F] Remove "
            fav_x = left_width - len(fav_hint) - 1
            if fav_x > 4:
                try:
                    self.stdscr.addstr(content_y, fav_x, fav_hint,
                                       curses.color_pair(self.CP_RECORDING) | curses.A_BOLD)
                except curses.error:
                    pass

        # ── Data-flow hotkey hints (drawn after panes so they overlay borders) ──
        hint_attr = curses.color_pair(self.CP_VOICE) | curses.A_BOLD
        # R: bottom border of Prompt Browser — dictation ^ refines into prompt
        r_label = "=^R^="
        r_y = content_y + prompt_height - 1  # bottom border of prompt pane
        r_x = max(1, (left_width - len(r_label)) // 2)
        try:
            self.stdscr.addstr(r_y, r_x, r_label, hint_attr)
        except curses.error:
            pass
        # E: right edge of Prompt Browser — prompt > executes in agent
        e_label = "E>"
        e_y = content_y + prompt_height // 2
        try:
            self.stdscr.addstr(e_y, left_width - 1, e_label, hint_attr)
        except curses.error:
            pass
        # D: right edge of Dictation Buffer — dictation > direct to agent
        d_label = "D>"
        d_y = content_y + prompt_height + dictation_height // 2
        try:
            self.stdscr.addstr(d_y, left_width - 1, d_label, hint_attr)
        except curses.error:
            pass

        # ── Help bar ──
        help_y = h - 2
        if self.recording:
            help_text = " [SPC] Stop recording"
            self._draw_bar(help_y, help_text, self.CP_HELP)
        elif self.confirming_new:
            help_text = " ██ UNSAVED PROMPT — [Y] Save first  [N] Discard  [other] Cancel ██"
            self._draw_bar(help_y, help_text, self.CP_RECORDING)
        elif self.agent_state in (AgentState.DOWNLOADING, AgentState.RECEIVING):
            help_text = " ◌ Agent working... [K] to kill"
            self._draw_bar(help_y, help_text, self.CP_STATUS)
        else:
            voice_label = "[V]oice"
            keys = " [Q]uit [X]Restart | [S]ave [N]ew [C]lear [K]ill [W]NewSess [←→]Browse [↑↓]View"
            self._draw_bar(help_y, keys, self.CP_HELP)
            # Draw [V]oice in red, right-justified
            w = self.stdscr.getmaxyx()[1]
            vx = w - len(voice_label) - 1
            if vx > len(keys):
                try:
                    self.stdscr.addnstr(help_y, vx, voice_label, w - vx - 1,
                                        curses.color_pair(self.CP_CTX_RED) | curses.A_BOLD)
                except curses.error:
                    pass

        # ── Status bar ──
        self._draw_bar(h - 1, f" {self.status_msg}", self.status_color)

        # ── Overlays (drawn last so they're on top) ──
        if self.show_help_overlay:
            self._draw_help_overlay()
        if self.show_about_overlay:
            self._draw_about_overlay()
        if self.show_settings_overlay:
            self._draw_settings_overlay()
        if self.show_folder_slug:
            self._draw_folder_slug_overlay()
        if self.show_shortcut_editor:
            self._draw_shortcut_editor()
        if self.show_escape_menu:
            self._draw_escape_menu()

        self.stdscr.refresh()

    def _draw_bar(self, y: int, text: str, color: int):
        w = self.stdscr.getmaxyx()[1]
        padded = text + " " * max(0, w - len(text))
        try:
            self.stdscr.addnstr(y, 0, padded, w - 1,
                                curses.color_pair(color) | curses.A_BOLD)
        except curses.error:
            pass

    def _draw_help_overlay(self):
        """Draw a 90s BBS-style help modal overlay on top of the UI."""
        h, w = self.stdscr.getmaxyx()

        # Overlay dimensions — leave a border of surrounding UI visible
        overlay_w = min(64, w - 6)
        overlay_h = min(30, h - 4)
        if overlay_w < 40 or overlay_h < 16:
            return

        start_y = max(1, (h - overlay_h) // 2)
        start_x = max(2, (w - overlay_w) // 2)

        border_attr = curses.color_pair(self.CP_HEADER) | curses.A_BOLD
        text_attr = curses.color_pair(self.CP_HELP) | curses.A_BOLD
        body_attr = curses.color_pair(self.CP_HELP)
        accent_attr = curses.color_pair(self.CP_HEADER) | curses.A_BOLD

        inner_w = overlay_w - 2

        # Content lines for the help overlay
        content = [
            "",
            "  V O I C E C O D E   B B S   v2.0",
            "  Voice-Driven Prompt Workshop",
            "",
            "  ── How It Works ──────────────────",
            "  Dictate speech fragments, refine",
            "  them into polished prompts with AI,",
            "  then execute via Claude agent.",
            "",
            "  ── Keyboard Controls ─────────────",
            "  SPACE  Toggle recording on/off",
            "  R      Refine fragments → prompt",
            "  E      Execute current prompt",
            "  D      Direct execute (skip refine)",
            "  S      Save prompt to disk",
            "  F      Add/remove favorites",
            "  N      New prompt",
            "  C      Clear dictation buffer",
            "  K      Kill running agent",
            "  W      New session (clear context)",
            "  ←/→    Browse within current view",
            "  ↑/↓    Cycle active/favorites/history",
            "  Enter  Shortcuts browser",
            "  PgUp/Dn  Scroll agent pane",
            "  [/]    Cycle TTS voice",
            "  P      Replay last TTS summary",
            "  H      This help screen",
            "  Q      Quit",
            "  ESC    Main menu (Options/About...)",
            "",
            "  Press H, ESC, or Q to close",
        ]

        # Truncate if overlay is too small
        content = content[:overlay_h - 2]

        try:
            # Top border
            top = "╔" + "═" * inner_w + "╗"
            self.stdscr.addnstr(start_y, start_x, top, overlay_w, border_attr)

            # Title bar
            title = " HELP — SYSTEM GUIDE "
            title_line = "║" + title.center(inner_w) + "║"
            self.stdscr.addnstr(start_y + 1, start_x, title_line, overlay_w, accent_attr)

            # Title separator
            sep = "╠" + "═" * inner_w + "╣"
            self.stdscr.addnstr(start_y + 2, start_x, sep, overlay_w, border_attr)

            # Body lines
            for i, line in enumerate(content):
                row = start_y + 3 + i
                if row >= start_y + overlay_h - 1:
                    break
                padded = line + " " * max(0, inner_w - len(line))
                body_line = "║" + padded[:inner_w] + "║"
                self.stdscr.addnstr(row, start_x, body_line, overlay_w, body_attr)

            # Fill remaining rows
            for row in range(start_y + 3 + len(content), start_y + overlay_h - 1):
                if row >= start_y + overlay_h - 1:
                    break
                empty_line = "║" + " " * inner_w + "║"
                self.stdscr.addnstr(row, start_x, empty_line, overlay_w, body_attr)

            # Bottom border
            bottom = "╚" + "═" * inner_w + "╝"
            self.stdscr.addnstr(start_y + overlay_h - 1, start_x, bottom, overlay_w, border_attr)
        except curses.error:
            pass

    def _draw_about_overlay(self):
        """Draw a BBS-style about / title screen overlay."""
        h, w = self.stdscr.getmaxyx()

        overlay_w = min(64, w - 6)
        overlay_h = min(26, h - 4)
        if overlay_w < 40 or overlay_h < 16:
            return

        start_y = max(1, (h - overlay_h) // 2)
        start_x = max(2, (w - overlay_w) // 2)

        border_attr = curses.color_pair(self.CP_HEADER) | curses.A_BOLD
        body_attr = curses.color_pair(self.CP_HELP)
        accent_attr = curses.color_pair(self.CP_HEADER) | curses.A_BOLD

        inner_w = overlay_w - 2

        content = [
            "",
            "  ╦  ╦╔═╗╦╔═╗╔═╗╔═╗╔═╗╔╦╗╔═╗",
            "  ╚╗╔╝║ ║║║  ║╣ ║  ║ ║ ║║║╣ ",
            "   ╚╝ ╚═╝╩╚═╝╚═╝╚═╝╚═╝═╩╝╚═╝",
            "          B  B  S   v2.0",
            "",
            "  ── About ─────────────────────",
            "  Voice-driven prompt workshop",
            "  for interacting with AI agents.",
            "  Dictate, refine, and execute",
            "  prompts — all by voice.",
            "",
            "  ── Author ────────────────────",
            "  Charles Schiele",
            "  charles.schiele@gmail.com",
            "  github.com/shazbot996/voicecode-bbs",
            "",
            "  ── Built With ────────────────",
            "  Python, faster-whisper, Silero VAD",
            "  Piper TTS, curses",
            "",
            "  Press A, ESC, or Q to close",
        ]

        content = content[:overlay_h - 2]

        try:
            top = "╔" + "═" * inner_w + "╗"
            self.stdscr.addnstr(start_y, start_x, top, overlay_w, border_attr)

            title = " ABOUT — VOICECODE BBS "
            title_line = "║" + title.center(inner_w) + "║"
            self.stdscr.addnstr(start_y + 1, start_x, title_line, overlay_w, accent_attr)

            sep = "╠" + "═" * inner_w + "╣"
            self.stdscr.addnstr(start_y + 2, start_x, sep, overlay_w, border_attr)

            for i, line in enumerate(content):
                row = start_y + 3 + i
                if row >= start_y + overlay_h - 1:
                    break
                padded = line + " " * max(0, inner_w - len(line))
                body_line = "║" + padded[:inner_w] + "║"
                self.stdscr.addnstr(row, start_x, body_line, overlay_w, body_attr)

            for row in range(start_y + 3 + len(content), start_y + overlay_h - 1):
                if row >= start_y + overlay_h - 1:
                    break
                empty_line = "║" + " " * inner_w + "║"
                self.stdscr.addnstr(row, start_x, empty_line, overlay_w, body_attr)

            bottom = "╚" + "═" * inner_w + "╝"
            self.stdscr.addnstr(start_y + overlay_h - 1, start_x, bottom, overlay_w, border_attr)
        except curses.error:
            pass

    def _draw_escape_menu(self):
        """Draw a centered BBS/DOS-style Escape menu modal."""
        h, w = self.stdscr.getmaxyx()

        num_items = len(self._escape_menu_items)
        # Box: title bar (3 rows) + items + blank top/bottom padding + bottom border
        overlay_h = num_items + 6  # top border + title + sep + blank + items + blank + bottom
        overlay_w = 36
        if overlay_w > w - 4 or overlay_h > h - 2:
            return

        start_y = max(1, (h - overlay_h) // 2)
        start_x = max(2, (w - overlay_w) // 2)

        border_attr = curses.color_pair(self.CP_HEADER) | curses.A_BOLD
        body_attr = curses.color_pair(self.CP_HELP)
        accent_attr = curses.color_pair(self.CP_HEADER) | curses.A_BOLD
        sel_attr = curses.color_pair(self.CP_VOICE) | curses.A_BOLD

        inner_w = overlay_w - 2

        try:
            # Top border
            self.stdscr.addnstr(start_y, start_x,
                                "╔" + "═" * inner_w + "╗", overlay_w, border_attr)
            # Title
            title = " MAIN MENU "
            title_line = "║" + title.center(inner_w) + "║"
            self.stdscr.addnstr(start_y + 1, start_x, title_line, overlay_w, accent_attr)
            # Separator
            self.stdscr.addnstr(start_y + 2, start_x,
                                "╠" + "═" * inner_w + "╣", overlay_w, border_attr)

            # Blank line above items
            self.stdscr.addnstr(start_y + 3, start_x,
                                "║" + " " * inner_w + "║", overlay_w, body_attr)

            # Menu items
            for i, (label, _action) in enumerate(self._escape_menu_items):
                row = start_y + 4 + i
                if i == self.escape_menu_cursor:
                    line = f"  ► {label}  "
                    attr = sel_attr
                else:
                    line = f"    {label}  "
                    attr = body_attr
                padded = line + " " * max(0, inner_w - len(line))
                self.stdscr.addnstr(row, start_x,
                                    "║" + padded[:inner_w] + "║", overlay_w, attr)

            # Blank line below items
            blank_row = start_y + 4 + num_items
            self.stdscr.addnstr(blank_row, start_x,
                                "║" + " " * inner_w + "║", overlay_w, body_attr)

            # Bottom border
            self.stdscr.addnstr(blank_row + 1, start_x,
                                "╚" + "═" * inner_w + "╝", overlay_w, border_attr)
        except curses.error:
            pass

    def _draw_settings_overlay(self):
        """Draw a BBS-style settings modal overlay on top of the UI."""
        h, w = self.stdscr.getmaxyx()

        # Determine which items/cursor/title to render
        if self.tts_submenu_open:
            render_items = self.tts_submenu_items
            render_cursor = self.tts_submenu_cursor
            render_title = " TEXT-TO-SPEECH SETTINGS "
            render_footer = " ↑↓ Navigate  ←→ Change  Enter Action  Q/Esc Back "
        else:
            render_items = self.settings_items
            render_cursor = self.settings_cursor
            render_title = " SETTINGS — VOICE CONFIG "
            render_footer = " ↑↓ Navigate  ←→ Change  Enter Action  O/Esc Close "

        overlay_w = min(72, w - 6)
        overlay_h = min(4 + len(render_items) * 3 + 3, h - 4)
        if overlay_w < 44 or overlay_h < 12:
            return

        start_y = max(1, (h - overlay_h) // 2)
        start_x = max(2, (w - overlay_w) // 2)

        border_attr = curses.color_pair(self.CP_HEADER) | curses.A_BOLD
        body_attr = curses.color_pair(self.CP_HELP)
        accent_attr = curses.color_pair(self.CP_HEADER) | curses.A_BOLD
        sel_attr = curses.color_pair(self.CP_RECORDING) | curses.A_BOLD
        val_attr = curses.color_pair(self.CP_AGENT) | curses.A_BOLD

        inner_w = overlay_w - 2

        try:
            # Top border
            top = "╔" + "═" * inner_w + "╗"
            self.stdscr.addnstr(start_y, start_x, top, overlay_w, border_attr)

            # Title bar
            title_line = "║" + render_title.center(inner_w) + "║"
            self.stdscr.addnstr(start_y + 1, start_x, title_line, overlay_w, accent_attr)

            # Title separator
            sep = "╠" + "═" * inner_w + "╣"
            self.stdscr.addnstr(start_y + 2, start_x, sep, overlay_w, border_attr)

            row = start_y + 3
            for i, item in enumerate(render_items):
                if row + 2 >= start_y + overlay_h - 1:
                    break

                is_selected = (i == render_cursor)
                is_action = item.get("options") is None
                line_attr = sel_attr if is_selected else body_attr

                # Setting label line
                cursor = "►" if is_selected else " "
                label = f" {cursor} {item['label']}"

                is_editable = item.get("editable", False)

                if is_editable:
                    # Editable text field — show path on the desc line
                    if is_selected and self.settings_editing_text:
                        label = f" {cursor} {item['label']}  [editing]"
                    else:
                        label = f" {cursor} {item['label']}  [Enter to edit]"
                    padded = label + " " * max(0, inner_w - len(label))
                    body_line = "║" + padded[:inner_w] + "║"
                    self.stdscr.addnstr(row, start_x, body_line, overlay_w, line_attr)
                    row += 1

                    # Show the editable path value
                    if is_selected and self.settings_editing_text:
                        buf = self.settings_edit_buffer
                        cur = self.settings_edit_cursor
                        # Scroll the visible window if path is too long
                        max_vis = inner_w - 7
                        if cur > max_vis:
                            vis_start = cur - max_vis + 1
                        else:
                            vis_start = 0
                        vis_text = buf[vis_start:vis_start + max_vis]
                        vis_cursor = cur - vis_start
                        path_line = f"  >> {vis_text}"
                        path_padded = path_line + " " * max(0, inner_w - len(path_line))
                        body_line = "║" + path_padded[:inner_w] + "║"
                        self.stdscr.addnstr(row, start_x, body_line, overlay_w, val_attr)
                        # Draw cursor character with reverse video
                        cursor_x = start_x + 1 + 5 + vis_cursor  # "║  >> " = 5 chars
                        if cursor_x < start_x + overlay_w - 1:
                            ch_under = buf[cur] if cur < len(buf) else " "
                            self.stdscr.addnstr(
                                row, cursor_x, ch_under, 1,
                                curses.color_pair(self.CP_AGENT) | curses.A_REVERSE)
                    else:
                        val_text = f"  >> {item['get']()}"
                        val_padded = val_text + " " * max(0, inner_w - len(val_text))
                        body_line = "║" + val_padded[:inner_w] + "║"
                        attr = val_attr if is_selected else body_attr
                        self.stdscr.addnstr(row, start_x, body_line, overlay_w, attr)
                    row += 1

                    # Blank separator
                    blank = "║" + " " * inner_w + "║"
                    self.stdscr.addnstr(row, start_x, blank, overlay_w, body_attr)
                    row += 1
                    continue

                elif is_action:
                    # Action item — show status hint if get() returns non-empty
                    action_val = item["get"]() if callable(item.get("get")) else ""
                    if action_val:
                        hint = f"  ({action_val})"
                        full = label + hint
                        padded = full + " " * max(0, inner_w - len(full))
                    else:
                        padded = label + " " * max(0, inner_w - len(label))
                    body_line = "║" + padded[:inner_w] + "║"
                    self.stdscr.addnstr(row, start_x, body_line, overlay_w, line_attr)
                else:
                    current_val = str(item["get"]())
                    # Build value display with ◄ ► arrows when selected
                    if is_selected:
                        val_display = f"◄ {current_val} ►"
                    else:
                        val_display = f"  {current_val}  "
                    # Right-align the value
                    space = inner_w - len(label) - len(val_display) - 1
                    full_line = label + " " * max(1, space) + val_display + " "

                    padded = full_line[:inner_w]
                    padded += " " * max(0, inner_w - len(padded))
                    body_line = "║" + padded + "║"
                    self.stdscr.addnstr(row, start_x, body_line, overlay_w, line_attr)

                    # Overwrite just the value portion in green if selected
                    if is_selected:
                        val_x = start_x + 1 + max(1, inner_w - len(val_display) - 1)
                        self.stdscr.addnstr(row, val_x, val_display, len(val_display), val_attr)

                row += 1

                # Description line (dimmer)
                desc = f"     {item['desc']}"
                desc_padded = desc + " " * max(0, inner_w - len(desc))
                desc_line = "║" + desc_padded[:inner_w] + "║"
                self.stdscr.addnstr(row, start_x, desc_line, overlay_w, body_attr)
                row += 1

                # Blank separator line
                blank = "║" + " " * inner_w + "║"
                self.stdscr.addnstr(row, start_x, blank, overlay_w, body_attr)
                row += 1

            # Fill remaining rows
            for r in range(row, start_y + overlay_h - 2):
                blank = "║" + " " * inner_w + "║"
                self.stdscr.addnstr(r, start_x, blank, overlay_w, body_attr)

            # Footer help line
            footer_padded = render_footer.center(inner_w)
            footer_line = "║" + footer_padded[:inner_w] + "║"
            self.stdscr.addnstr(start_y + overlay_h - 2, start_x, footer_line,
                                overlay_w, accent_attr)

            # Bottom border
            bottom = "╚" + "═" * inner_w + "╝"
            self.stdscr.addnstr(start_y + overlay_h - 1, start_x, bottom, overlay_w, border_attr)
        except curses.error:
            pass

    def _scan_folder_slugs(self):
        """Build shortcuts list: user shortcuts first, then folder entries."""
        shortcuts = list(self._shortcut_strings)
        self._shortcut_count = len(shortcuts)
        dirs = []
        root = Path(self.working_dir).expanduser()
        if root.is_dir():
            try:
                for entry in sorted(root.iterdir()):
                    if entry.is_dir() and not entry.name.startswith("."):
                        rel = entry.name
                        dirs.append(rel + "/")
                        try:
                            for sub in sorted(entry.iterdir()):
                                if sub.is_dir() and not sub.name.startswith("."):
                                    dirs.append(rel + "/" + sub.name + "/")
                        except PermissionError:
                            pass
            except PermissionError:
                pass
        self.folder_slug_list = shortcuts + dirs

    def _draw_folder_slug_overlay(self):
        """Draw the Shortcuts overlay on the agent pane."""
        h, w = self.stdscr.getmaxyx()

        # Agent pane geometry
        content_height = h - 4
        left_width = w // 2
        right_width = w - left_width
        content_y = 2

        # Overlay is inset from agent pane borders so terminal peeks through
        overlay_x = left_width + 3
        overlay_y = content_y + 2
        overlay_w = right_width - 6
        overlay_h = content_height - 4
        if overlay_w < 20 or overlay_h < 6:
            return

        bg_attr = curses.color_pair(self.CP_XTREE_BG)
        sel_attr = curses.color_pair(self.CP_XTREE_SEL) | curses.A_BOLD
        border_attr = curses.color_pair(self.CP_XTREE_BORDER) | curses.A_BOLD

        inner_w = overlay_w - 2
        inner_h = overlay_h - 4  # top border + title + footer + bottom border

        try:
            # Top border
            top = "╔" + "═" * inner_w + "╗"
            self.stdscr.addnstr(overlay_y, overlay_x, top, overlay_w, border_attr)

            # Title bar
            title = " SHORTCUTS "
            title_line = "║" + title.center(inner_w) + "║"
            self.stdscr.addnstr(overlay_y + 1, overlay_x, title_line, overlay_w, border_attr)

            # Title separator
            sep = "╠" + "═" * inner_w + "╣"
            self.stdscr.addnstr(overlay_y + 2, overlay_x, sep, overlay_w, border_attr)

            # Scrolling: keep cursor visible
            if self.folder_slug_cursor < self.folder_slug_scroll:
                self.folder_slug_scroll = self.folder_slug_cursor
            elif self.folder_slug_cursor >= self.folder_slug_scroll + inner_h:
                self.folder_slug_scroll = self.folder_slug_cursor - inner_h + 1

            # List rows: shortcuts first, then folders (continuous)
            for i in range(inner_h):
                row_y = overlay_y + 3 + i
                idx = self.folder_slug_scroll + i
                if idx < len(self.folder_slug_list):
                    entry = self.folder_slug_list[idx]
                    is_sel = (idx == self.folder_slug_cursor)
                    is_shortcut = idx < self._shortcut_count
                    if is_shortcut:
                        icon = "⚡ " if is_sel else "⚡ "
                    else:
                        icon = "📂 " if is_sel else "📁 "
                    text = f" {icon}{entry}"
                    # len() counts emoji as 1 char but it displays as 2 cells
                    display_w = len(text) + 1  # +1 for double-width emoji
                    padded = text[:inner_w] + " " * max(0, inner_w - display_w)
                    line = "║" + padded + "║"
                    attr = sel_attr if is_sel else bg_attr
                    self.stdscr.addnstr(row_y, overlay_x, line, overlay_w, attr)
                else:
                    blank = "║" + " " * inner_w + "║"
                    self.stdscr.addnstr(row_y, overlay_x, blank, overlay_w, bg_attr)

            # Footer
            footer_text = " ↑↓ Select  Enter Insert  Esc Cancel "
            footer_padded = footer_text.center(inner_w)
            footer_line = "║" + footer_padded[:inner_w] + "║"
            self.stdscr.addnstr(overlay_y + overlay_h - 2, overlay_x,
                                footer_line, overlay_w, border_attr)

            # Bottom border
            bottom = "╚" + "═" * inner_w + "╝"
            self.stdscr.addnstr(overlay_y + overlay_h - 1, overlay_x,
                                bottom, overlay_w, border_attr)
        except curses.error:
            pass

    def _open_shortcut_editor(self):
        """Open the shortcut editor overlay."""
        self._shortcut_strings = _load_shortcuts()
        self.show_shortcut_editor = True
        self.shortcut_editor_cursor = 0
        self.shortcut_editor_scroll = 0
        self.shortcut_editing_text = False

    def _draw_shortcut_editor(self):
        """Draw the shortcut editor overlay."""
        h, w = self.stdscr.getmaxyx()

        overlay_w = min(68, w - 6)
        # +1 for the [Add New] row
        num_entries = len(self._shortcut_strings) + 1
        overlay_h = min(4 + num_entries + 2, h - 4)
        if overlay_w < 40 or overlay_h < 6:
            return

        start_y = max(1, (h - overlay_h) // 2)
        start_x = max(2, (w - overlay_w) // 2)

        border_attr = curses.color_pair(self.CP_HEADER) | curses.A_BOLD
        body_attr = curses.color_pair(self.CP_HELP)
        accent_attr = curses.color_pair(self.CP_HEADER) | curses.A_BOLD
        sel_attr = curses.color_pair(self.CP_RECORDING) | curses.A_BOLD
        val_attr = curses.color_pair(self.CP_AGENT) | curses.A_BOLD

        inner_w = overlay_w - 2
        inner_h = overlay_h - 5  # borders + title + footer

        try:
            # Top border
            top = "╔" + "═" * inner_w + "╗"
            self.stdscr.addnstr(start_y, start_x, top, overlay_w, border_attr)

            # Title bar
            title = " EDIT SHORTCUTS "
            title_line = "║" + title.center(inner_w) + "║"
            self.stdscr.addnstr(start_y + 1, start_x, title_line, overlay_w, accent_attr)

            # Title separator
            sep = "╠" + "═" * inner_w + "╣"
            self.stdscr.addnstr(start_y + 2, start_x, sep, overlay_w, border_attr)

            # Scrolling
            if self.shortcut_editor_cursor < self.shortcut_editor_scroll:
                self.shortcut_editor_scroll = self.shortcut_editor_cursor
            elif self.shortcut_editor_cursor >= self.shortcut_editor_scroll + inner_h:
                self.shortcut_editor_scroll = self.shortcut_editor_cursor - inner_h + 1

            # List rows
            for i in range(inner_h):
                row_y = start_y + 3 + i
                idx = self.shortcut_editor_scroll + i
                is_sel = (idx == self.shortcut_editor_cursor)
                line_attr = sel_attr if is_sel else body_attr

                if idx < len(self._shortcut_strings):
                    entry = self._shortcut_strings[idx]
                    cursor = "►" if is_sel else " "
                    if is_sel and self.shortcut_editing_text:
                        # Inline editing mode
                        buf = self.shortcut_edit_buffer
                        cur = self.shortcut_edit_cursor_pos
                        max_vis = inner_w - 7
                        vis_start = max(0, cur - max_vis + 1) if cur > max_vis else 0
                        vis_text = buf[vis_start:vis_start + max_vis]
                        vis_cur = cur - vis_start
                        text = f" {cursor} {vis_text}"
                        padded = text + " " * max(0, inner_w - len(text))
                        line = "║" + padded[:inner_w] + "║"
                        self.stdscr.addnstr(row_y, start_x, line, overlay_w, val_attr)
                        # Draw cursor
                        cursor_x = start_x + 1 + 4 + vis_cur
                        if cursor_x < start_x + overlay_w - 1:
                            ch_under = buf[cur] if cur < len(buf) else " "
                            self.stdscr.addnstr(
                                row_y, cursor_x, ch_under, 1,
                                curses.color_pair(self.CP_AGENT) | curses.A_REVERSE)
                    else:
                        text = f" {cursor} {entry}"
                        padded = text + " " * max(0, inner_w - len(text))
                        line = "║" + padded[:inner_w] + "║"
                        self.stdscr.addnstr(row_y, start_x, line, overlay_w, line_attr)
                elif idx == len(self._shortcut_strings):
                    # [Add New] row
                    cursor = "►" if is_sel else " "
                    if is_sel and self.shortcut_editing_text:
                        buf = self.shortcut_edit_buffer
                        cur = self.shortcut_edit_cursor_pos
                        max_vis = inner_w - 7
                        vis_start = max(0, cur - max_vis + 1) if cur > max_vis else 0
                        vis_text = buf[vis_start:vis_start + max_vis]
                        vis_cur = cur - vis_start
                        text = f" {cursor} {vis_text}"
                        padded = text + " " * max(0, inner_w - len(text))
                        line = "║" + padded[:inner_w] + "║"
                        self.stdscr.addnstr(row_y, start_x, line, overlay_w, val_attr)
                        cursor_x = start_x + 1 + 4 + vis_cur
                        if cursor_x < start_x + overlay_w - 1:
                            ch_under = buf[cur] if cur < len(buf) else " "
                            self.stdscr.addnstr(
                                row_y, cursor_x, ch_under, 1,
                                curses.color_pair(self.CP_AGENT) | curses.A_REVERSE)
                    else:
                        text = f" {cursor} [Add New Shortcut]"
                        padded = text + " " * max(0, inner_w - len(text))
                        line = "║" + padded[:inner_w] + "║"
                        self.stdscr.addnstr(row_y, start_x, line, overlay_w, line_attr)
                else:
                    blank = "║" + " " * inner_w + "║"
                    self.stdscr.addnstr(row_y, start_x, blank, overlay_w, body_attr)

            # Footer
            if self.shortcut_editing_text:
                footer_text = " Enter Save  Esc Cancel "
            else:
                footer_text = " Enter Edit  Del Remove  Esc Close "
            footer_padded = footer_text.center(inner_w)
            footer_line = "║" + footer_padded[:inner_w] + "║"
            self.stdscr.addnstr(start_y + overlay_h - 2, start_x, footer_line,
                                overlay_w, accent_attr)

            # Bottom border
            bottom = "╚" + "═" * inner_w + "╝"
            self.stdscr.addnstr(start_y + overlay_h - 1, start_x, bottom,
                                overlay_w, border_attr)
        except curses.error:
            pass

    def _draw_agent_xfer(self, y: int, x: int, height: int, width: int):
        """Draw the ZMODEM-style transfer animation in the right pane."""
        border_attr = curses.color_pair(self.CP_XFER) | curses.A_BOLD
        content_attr = curses.color_pair(self.CP_XFER)
        green_attr = curses.color_pair(self.CP_AGENT) | curses.A_BOLD

        # Draw border
        title = " FILE TRANSFER "
        top = "╔══" + title + "═" * max(0, width - 3 - len(title) - 1) + "╗"
        try:
            self.stdscr.addnstr(y, x, top, width, border_attr)
        except curses.error:
            pass

        for i in range(1, height - 1):
            try:
                self.stdscr.addstr(y + i, x, "║", border_attr)
                self.stdscr.addstr(y + i, x + 1, " " * max(0, width - 2), content_attr)
                self.stdscr.addnstr(y + i, x + width - 1, "║", 1, border_attr)
            except curses.error:
                pass

        bottom = "╚" + "═" * max(0, width - 2) + "╝"
        try:
            self.stdscr.addnstr(y + height - 1, x, bottom, width, border_attr)
        except curses.error:
            pass

        # Content
        inner_w = width - 4
        cx = x + 2
        elapsed = time.time() - self.xfer_start_time
        self.xfer_progress = min(0.99, elapsed / 3.0)  # ~3 sec animation

        lines_content = [
            ("Protocol", "ZMODEM-VOICE/1.0"),
            ("Filename", "prompt_upload.md"),
            ("   Bytes", f"{self.xfer_bytes:,}"),
            ("     BPS", f"{random.randint(28800, 115200):,}"),
            ("  Errors", "0"),
            ("  Status", ZMODEM_FRAMES[self.xfer_frame % len(ZMODEM_FRAMES)]),
        ]

        # Update animation frame
        self.xfer_frame = int(elapsed * 4)

        row = y + 2
        # ASCII art modem
        modem_art = [
            "   ┌──────────────────┐",
            "   │ ≈≈≈ SENDING ≈≈≈  │",
            "   │ ◄══════════════► │",
            "   └──────────────────┘",
        ]
        for line in modem_art:
            try:
                self.stdscr.addnstr(row, cx, line[:inner_w], inner_w, green_attr)
            except curses.error:
                pass
            row += 1

        row += 1
        for label, val in lines_content:
            try:
                text = f"  {label}: {val}"
                self.stdscr.addnstr(row, cx, text[:inner_w], inner_w, content_attr)
            except curses.error:
                pass
            row += 1

        # Progress bar
        row += 1
        bar_w = min(inner_w - 12, 30)
        filled = int(self.xfer_progress * bar_w)
        bar = "█" * filled + "░" * (bar_w - filled)
        pct = f" {int(self.xfer_progress * 100):3d}%"
        try:
            self.stdscr.addnstr(row, cx, f"  [{bar}]{pct}", inner_w, green_attr)
        except curses.error:
            pass

        # Spinning chars
        row += 2
        spinners = "|/-\\"
        spin_ch = spinners[int(elapsed * 8) % len(spinners)]
        try:
            self.stdscr.addnstr(row, cx, f"  {spin_ch} Transmitting...", inner_w, content_attr)
        except curses.error:
            pass

    # ─── Input handling ────────────────────────────────────────────

    def _handle_input(self):
        try:
            ch = self.stdscr.getch()
        except curses.error:
            return

        if ch == -1:
            return

        # Handle help overlay dismiss (before anything else)
        if self.show_help_overlay:
            if ch in (ord("h"), ord("H"), ord("q"), ord("Q"), 27):
                self.show_help_overlay = False
                # Consume any follow-up byte from ESC sequence
                if ch == 27:
                    self.stdscr.nodelay(True)
                    self.stdscr.getch()
            return

        # Handle about overlay dismiss
        if self.show_about_overlay:
            if ch in (ord("a"), ord("A"), ord("q"), ord("Q"), 27):
                self.show_about_overlay = False
                if ch == 27:
                    self.stdscr.nodelay(True)
                    self.stdscr.getch()
            return

        # Handle escape menu overlay
        if self.show_escape_menu:
            if ch == curses.KEY_UP:
                self.escape_menu_cursor = (self.escape_menu_cursor - 1) % len(self._escape_menu_items)
            elif ch == curses.KEY_DOWN:
                self.escape_menu_cursor = (self.escape_menu_cursor + 1) % len(self._escape_menu_items)
            elif ch in (10, 13, curses.KEY_ENTER):
                _label, action = self._escape_menu_items[self.escape_menu_cursor]
                self.show_escape_menu = False
                if action == "settings":
                    self.show_settings_overlay = True
                    self.settings_cursor = 0
                elif action == "help":
                    self.show_help_overlay = True
                elif action == "about":
                    self.show_about_overlay = True
                elif action == "restart":
                    self._kill_agent()
                    self.restart = True
                    self.running = False
                elif action == "quit":
                    self._kill_agent()
                    self.running = False
            elif ch == 27:
                self.show_escape_menu = False
                self.stdscr.nodelay(True)
                self.stdscr.getch()
            elif ch in (ord("q"), ord("Q")):
                self.show_escape_menu = False
            return

        # Handle folder slug overlay
        if self.show_folder_slug:
            if ch == curses.KEY_UP:
                if self.folder_slug_cursor > 0:
                    self.folder_slug_cursor -= 1
                return
            elif ch == curses.KEY_DOWN:
                if self.folder_slug_cursor < len(self.folder_slug_list) - 1:
                    self.folder_slug_cursor += 1
                return
            elif ch in (10, 13, curses.KEY_ENTER):
                if self.folder_slug_list:
                    slug = self.folder_slug_list[self.folder_slug_cursor]
                    if self.recording:
                        # Inject into the ongoing recording stream — will be
                        # merged into the final transcript at the right position.
                        with self.audio_lock:
                            audio_secs = (sum(len(f) for f in self.audio_frames)
                                          / SAMPLE_RATE) if self.audio_frames else 0.0
                        self._recording_injections.append((audio_secs, slug))
                        # Update live preview to show slug inline
                        preview = self._live_preview_text
                        combined = f"{preview} {slug}" if preview else slug
                        self.ui_queue.put(("live_preview", combined))
                        self._set_status(f"Injected: {slug}")
                    else:
                        left_width = self.stdscr.getmaxyx()[1] * 2 // 5
                        self.fragments.append(slug)
                        ts = datetime.datetime.now().strftime("%H:%M:%S")
                        self.dictation_pane.add_line(f"[{ts}] {slug}", left_width)
                        self._set_status(f"Inserted: {slug}")
                return
            elif ch == 27:
                self.show_folder_slug = False
                self.stdscr.nodelay(True)
                self.stdscr.getch()
                return
            # Other keys (including SPACE) fall through to main handler

        # Handle shortcut editor overlay
        if self.show_shortcut_editor:
            if self.shortcut_editing_text:
                if ch in (10, 13, curses.KEY_ENTER):
                    # Save the edited/new shortcut
                    text = self.shortcut_edit_buffer.strip()
                    if text:
                        idx = self.shortcut_editor_cursor
                        if idx < len(self._shortcut_strings):
                            self._shortcut_strings[idx] = text
                        else:
                            self._shortcut_strings.append(text)
                            self.shortcut_editor_cursor = len(self._shortcut_strings)
                        _save_shortcuts(self._shortcut_strings)
                    self.shortcut_editing_text = False
                elif ch == 27:
                    self.stdscr.nodelay(True)
                    self.stdscr.getch()
                    self.shortcut_editing_text = False
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    if self.shortcut_edit_cursor_pos > 0:
                        b = self.shortcut_edit_buffer
                        c = self.shortcut_edit_cursor_pos
                        self.shortcut_edit_buffer = b[:c-1] + b[c:]
                        self.shortcut_edit_cursor_pos -= 1
                elif ch == curses.KEY_DC:
                    b = self.shortcut_edit_buffer
                    c = self.shortcut_edit_cursor_pos
                    if c < len(b):
                        self.shortcut_edit_buffer = b[:c] + b[c+1:]
                elif ch == curses.KEY_LEFT:
                    self.shortcut_edit_cursor_pos = max(0, self.shortcut_edit_cursor_pos - 1)
                elif ch == curses.KEY_RIGHT:
                    self.shortcut_edit_cursor_pos = min(
                        len(self.shortcut_edit_buffer), self.shortcut_edit_cursor_pos + 1)
                elif ch == curses.KEY_HOME or ch == 1:  # Ctrl+A
                    self.shortcut_edit_cursor_pos = 0
                elif ch == curses.KEY_END or ch == 5:  # Ctrl+E
                    self.shortcut_edit_cursor_pos = len(self.shortcut_edit_buffer)
                elif 32 <= ch <= 126:
                    b = self.shortcut_edit_buffer
                    c = self.shortcut_edit_cursor_pos
                    self.shortcut_edit_buffer = b[:c] + chr(ch) + b[c:]
                    self.shortcut_edit_cursor_pos += 1
                return

            if ch == 27:
                self.show_shortcut_editor = False
                self.stdscr.nodelay(True)
                self.stdscr.getch()
            elif ch == curses.KEY_UP:
                if self.shortcut_editor_cursor > 0:
                    self.shortcut_editor_cursor -= 1
            elif ch == curses.KEY_DOWN:
                if self.shortcut_editor_cursor < len(self._shortcut_strings):
                    self.shortcut_editor_cursor += 1
            elif ch in (10, 13, curses.KEY_ENTER):
                idx = self.shortcut_editor_cursor
                if idx < len(self._shortcut_strings):
                    self.shortcut_edit_buffer = self._shortcut_strings[idx]
                else:
                    self.shortcut_edit_buffer = ""
                self.shortcut_edit_cursor_pos = len(self.shortcut_edit_buffer)
                self.shortcut_editing_text = True
            elif ch in (curses.KEY_DC, 330):  # Delete key
                idx = self.shortcut_editor_cursor
                if idx < len(self._shortcut_strings):
                    del self._shortcut_strings[idx]
                    _save_shortcuts(self._shortcut_strings)
                    if self.shortcut_editor_cursor > len(self._shortcut_strings):
                        self.shortcut_editor_cursor = len(self._shortcut_strings)
            return

        # Handle settings overlay navigation
        if self.show_settings_overlay:
            # Inline text editing mode (e.g. prompt library path)
            if self.settings_editing_text:
                if ch in (10, 13, curses.KEY_ENTER):
                    self._commit_text_edit()
                elif ch == 27:
                    self.stdscr.nodelay(True)
                    self.stdscr.getch()
                    self._cancel_text_edit()
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    if self.settings_edit_cursor > 0:
                        b = self.settings_edit_buffer
                        c = self.settings_edit_cursor
                        self.settings_edit_buffer = b[:c-1] + b[c:]
                        self.settings_edit_cursor -= 1
                elif ch == curses.KEY_DC:  # Delete key
                    b = self.settings_edit_buffer
                    c = self.settings_edit_cursor
                    if c < len(b):
                        self.settings_edit_buffer = b[:c] + b[c+1:]
                elif ch == curses.KEY_LEFT:
                    self.settings_edit_cursor = max(0, self.settings_edit_cursor - 1)
                elif ch == curses.KEY_RIGHT:
                    self.settings_edit_cursor = min(
                        len(self.settings_edit_buffer), self.settings_edit_cursor + 1)
                elif ch == curses.KEY_HOME or ch == 1:  # Ctrl+A
                    self.settings_edit_cursor = 0
                elif ch == curses.KEY_END or ch == 5:  # Ctrl+E
                    self.settings_edit_cursor = len(self.settings_edit_buffer)
                elif 32 <= ch <= 126:  # printable ASCII
                    b = self.settings_edit_buffer
                    c = self.settings_edit_cursor
                    self.settings_edit_buffer = b[:c] + chr(ch) + b[c:]
                    self.settings_edit_cursor += 1
                return

            # TTS sub-menu navigation
            if self.tts_submenu_open:
                if ch in (ord("q"), ord("Q"), 27):
                    self.tts_submenu_open = False
                    if ch == 27:
                        self.stdscr.nodelay(True)
                        self.stdscr.getch()
                elif ch == curses.KEY_UP:
                    self.tts_submenu_cursor = (self.tts_submenu_cursor - 1) % len(self.tts_submenu_items)
                elif ch == curses.KEY_DOWN:
                    self.tts_submenu_cursor = (self.tts_submenu_cursor + 1) % len(self.tts_submenu_items)
                elif ch == curses.KEY_LEFT:
                    self._tts_submenu_cycle(-1)
                elif ch == curses.KEY_RIGHT:
                    self._tts_submenu_cycle(1)
                elif ch in (10, 13, curses.KEY_ENTER):
                    item = self.tts_submenu_items[self.tts_submenu_cursor]
                    if item.get("action"):
                        self.tts_submenu_open = False
                        self.show_settings_overlay = False
                        item["action"]()
                return

            if ch in (ord("o"), ord("O"), ord("q"), ord("Q"), 27):
                self.show_settings_overlay = False
                self.tts_submenu_open = False
                if ch == 27:
                    self.stdscr.nodelay(True)
                    self.stdscr.getch()
            elif ch == curses.KEY_UP:
                self.settings_cursor = (self.settings_cursor - 1) % len(self.settings_items)
            elif ch == curses.KEY_DOWN:
                self.settings_cursor = (self.settings_cursor + 1) % len(self.settings_items)
            elif ch == curses.KEY_LEFT:
                self._settings_cycle(-1)
            elif ch == curses.KEY_RIGHT:
                self._settings_cycle(1)
            elif ch in (10, 13, curses.KEY_ENTER):
                item = self.settings_items[self.settings_cursor]
                if item.get("action"):
                    if item.get("editable"):
                        item["action"]()  # keep modal open for editing
                    else:
                        self.show_settings_overlay = False
                        item["action"]()
            return

        # Handle confirmation dialog for [N]ew prompt
        if self.confirming_new:
            if ch == ord("y") or ch == ord("Y"):
                self.confirming_new = False
                self._save_prompt()
                self._do_new_prompt()
            elif ch == ord("n") or ch == ord("N"):
                self.confirming_new = False
                self._do_new_prompt()
            else:
                # Any other key cancels
                self.confirming_new = False
                self._set_status("New prompt cancelled.")
            return

        if ch == ord("q") or ch == ord("Q"):
            self._kill_agent()
            self.running = False

        elif ch == ord("x") or ch == ord("X"):
            self._kill_agent()
            self.restart = True
            self.running = False

        elif ch == ord("k") or ch == ord("K"):
            if self.agent_state in (AgentState.DOWNLOADING, AgentState.RECEIVING):
                self._kill_agent()

        elif ch == ord("w") or ch == ord("W"):
            if self.agent_state in (AgentState.IDLE, AgentState.DONE):
                self._clear_session()

        elif ch == ord(" "):
            if self.recording:
                self._stop_recording()
            elif not self.refining:
                self._start_recording()

        elif ch == ord("r") or ch == ord("R"):
            if not self.refining and not self.recording:
                self._start_refine()

        elif ch == ord("d") or ch == ord("D"):
            if not self.refining and not self.recording:
                self._execute_raw()

        elif ch == ord("s") or ch == ord("S"):
            if not self.refining and not self.recording:
                self._save_prompt()

        elif ch == ord("f") or ch == ord("F"):
            if not self.refining and not self.recording:
                if self.browser_view == "favorites" and self.browser_index >= 0:
                    self._remove_from_favorites()
                else:
                    self._add_to_favorites()

        elif ch == ord("e") or ch == ord("E"):
            if self.agent_state in (AgentState.IDLE, AgentState.DONE):
                self._execute_prompt()

        elif ch == ord("n") or ch == ord("N"):
            if not self.refining and not self.recording:
                self._new_prompt()

        elif ch == ord("c") or ch == ord("C"):
            self.fragments.clear()
            self.dictation_pane.lines.clear()
            self.dictation_pane.scroll_offset = 0
            self._set_dictation_info(self.stdscr.getmaxyx()[1] // 2)
            self._set_status("Dictation buffer cleared.")

        elif ch == ord("p") or ch == ord("P"):
            if self.last_tts_summary:
                stop_speaking()
                speak_text(self.last_tts_summary, on_done=lambda: self.ui_queue.put(
                    ("status", "Ready for next prompt.", self.CP_STATUS)))
                self._set_status("Replaying summary...", self.CP_STATUS)
            else:
                self._set_status("No summary to replay.")

        elif ch == curses.KEY_LEFT:
            prompt_list = self._current_browser_list()
            if not prompt_list:
                view_names = {"history": "history", "favorites": "favorite", "active": "saved"}
                self._set_status(f"No {view_names.get(self.browser_view, 'saved')} prompts to browse.")
            elif self.browser_index == -1:
                self.browser_index = len(prompt_list) - 1
                self._load_browser_prompt(self.stdscr.getmaxyx()[1] // 2)
            elif self.browser_index > 0:
                self.browser_index -= 1
                self._load_browser_prompt(self.stdscr.getmaxyx()[1] // 2)
            else:
                self._set_status("Already at oldest prompt.")

        elif ch == curses.KEY_RIGHT:
            prompt_list = self._current_browser_list()
            if self.browser_index == -1:
                self._set_status("Already at current session.")
            elif self.browser_index < len(prompt_list) - 1:
                self.browser_index += 1
                self._load_browser_prompt(self.stdscr.getmaxyx()[1] // 2)
            else:
                self.browser_index = -1
                self._load_browser_prompt(self.stdscr.getmaxyx()[1] // 2)

        elif ch == curses.KEY_UP:
            # Cycle order (up): active → history → favorites → active
            view_cycle_up = {"active": "history", "history": "favorites", "favorites": "active"}
            if self.prompt_pane.scroll_offset == 0:
                next_view = view_cycle_up[self.browser_view]
                if next_view == "history":
                    self._scan_history_prompts()
                elif next_view == "favorites":
                    self._scan_favorites_prompts()
                self.browser_view = next_view
                self.browser_index = -1
                self._load_browser_prompt(self.stdscr.getmaxyx()[1] // 2)
                h = self.stdscr.getmaxyx()[0]
                content_height = h - 4
                visible = content_height // 2 - 2
                max_off = max(0, len(self.prompt_pane.lines) - visible)
                self.prompt_pane.scroll_offset = max_off
                view_names = {"active": "active prompts", "history": "history", "favorites": "favorites"}
                count = len(self._current_browser_list())
                self._set_status(f"Switched to {view_names[next_view]}. ({count} entries)")
            else:
                self.prompt_pane.scroll_up(2)

        elif ch == curses.KEY_DOWN:
            # Cycle order (down): active → favorites → history → active
            view_cycle_down = {"active": "favorites", "favorites": "history", "history": "active"}
            h = self.stdscr.getmaxyx()[0]
            content_height = h - 4
            visible = content_height // 2 - 2
            max_off = max(0, len(self.prompt_pane.lines) - visible)
            if self.prompt_pane.scroll_offset >= max_off:
                next_view = view_cycle_down[self.browser_view]
                if next_view == "history":
                    self._scan_history_prompts()
                elif next_view == "favorites":
                    self._scan_favorites_prompts()
                self.browser_view = next_view
                self.browser_index = -1
                self._load_browser_prompt(self.stdscr.getmaxyx()[1] // 2)
                view_names = {"active": "active prompts", "history": "history", "favorites": "favorites"}
                count = len(self._current_browser_list())
                self._set_status(f"Switched to {view_names[next_view]}. ({count} entries)")
            else:
                self.prompt_pane.scroll_down(visible, 2)

        elif ch == curses.KEY_END:
            if not self.refining and not self.recording:
                self._new_prompt()

        elif ch == curses.KEY_PPAGE:
            self.agent_pane.scroll_up(5)

        elif ch == curses.KEY_NPAGE:
            h = self.stdscr.getmaxyx()[0]
            content_height = h - 4
            self.agent_pane.scroll_down(content_height - 2, 5)

        elif ch == ord("["):
            name = cycle_tts_voice(-1)
            self._set_status(f"Voice: {name}", self.CP_VOICE)
            speak_text(f"Voice changed to {name.replace('-', ' ').replace('_', ' ')}")

        elif ch == ord("]"):
            name = cycle_tts_voice(1)
            self._set_status(f"Voice: {name}", self.CP_VOICE)
            speak_text(f"Voice changed to {name.replace('-', ' ').replace('_', ' ')}")

        elif ch in (10, 13, curses.KEY_ENTER):
            # Enter opens shortcuts browser (allowed during recording for injection)
            if (not self.refining
                    and self.agent_state in (AgentState.IDLE, AgentState.DONE)
                    and (self.working_dir or self._shortcut_strings)):
                self._scan_folder_slugs()
                if self.folder_slug_list:
                    self.show_folder_slug = True
                    self.folder_slug_cursor = 0
                    self.folder_slug_scroll = 0
                else:
                    self._set_status("No shortcuts or folders found.")
            elif not self.working_dir and not self._shortcut_strings:
                self._set_status("Set working directory or add shortcuts in ESC → Options.")

        elif ch == ord("h") or ch == ord("H"):
            self.show_help_overlay = True

        elif ch == 27:
            # ESC key — open the main menu
            # Consume any follow-up byte from ESC sequence (arrow keys etc.)
            self.stdscr.nodelay(True)
            next_ch = self.stdscr.getch()
            if next_ch == -1:
                # Pure ESC press — open menu
                self.show_escape_menu = True
                self.escape_menu_cursor = 0

    # ─── Recording ─────────────────────────────────────────────────

    def _start_recording(self):
        self.recording = True
        self._rec_stop_event = threading.Event()
        with self.audio_lock:
            self.audio_frames.clear()
        self._live_preview_text = ""  # current interim transcription
        self._recording_injections.clear()

        # Clear intro/info text from dictation buffer only on first recording;
        # preserve existing fragments so SPACE adds to (not replaces) the buffer.
        if not self.fragments:
            self.dictation_pane.lines.clear()
            self.dictation_pane.scroll_offset = 0

        self._set_status("██ RECORDING — press SPACE to stop ██", self.CP_RECORDING)

        self._audio_stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32",
            blocksize=BLOCK_SIZE, callback=self._audio_callback)
        self._audio_stream.start()

        # Start live transcription thread
        self._live_transcribe_thread = threading.Thread(
            target=self._live_transcribe_loop, daemon=True)
        self._live_transcribe_thread.start()

    def _audio_callback(self, indata, frames, time_info, status):
        with self.audio_lock:
            self.audio_frames.append(indata[:, 0].copy())

    def _live_transcribe_loop(self):
        """Periodically transcribe accumulated audio while recording."""
        CHUNK_INTERVAL = 2.0  # transcribe every 2 seconds
        last_transcribed_samples = 0

        while not self._rec_stop_event.is_set():
            self._rec_stop_event.wait(CHUNK_INTERVAL)

            with self.audio_lock:
                if not self.audio_frames:
                    continue
                audio = np.concatenate(self.audio_frames)

            total_samples = len(audio)
            # Only re-transcribe if we have meaningful new audio
            new_samples = total_samples - last_transcribed_samples
            if new_samples < SAMPLE_RATE * 0.5:  # at least 0.5s of new audio
                continue

            if total_samples / SAMPLE_RATE < self.min_speech_duration:
                continue

            text = transcribe(audio, self.whisper_model)
            last_transcribed_samples = total_samples
            if text:
                self._live_preview_text = text
                # Include any mid-recording injections in the preview
                if self._recording_injections:
                    preview = text + " " + " ".join(
                        inj[1] for inj in self._recording_injections)
                    self.ui_queue.put(("live_preview", preview))
                else:
                    self.ui_queue.put(("live_preview", text))

    def _stop_recording(self):
        self.recording = False
        self._rec_stop_event.set()

        try:
            self._audio_stream.stop()
            self._audio_stream.close()
        except Exception:
            pass

        # Wait for live transcribe thread to finish so no stale preview
        # arrives after the final fragment is added to the dictation buffer.
        if hasattr(self, '_live_transcribe_thread'):
            self._live_transcribe_thread.join(timeout=5.0)

        with self.audio_lock:
            if not self.audio_frames:
                self._set_status("No audio captured.")
                return
            audio = np.concatenate(self.audio_frames)
            self.audio_frames.clear()

        duration = len(audio) / SAMPLE_RATE
        if duration < self.min_speech_duration:
            self._set_status(f"Too short ({duration:.1f}s), discarded.")
            return

        # Final transcription (full audio for best accuracy)
        self._set_status(f"Final transcription of {duration:.1f}s...")
        injections = list(self._recording_injections)
        self._recording_injections.clear()
        threading.Thread(target=self._do_final_transcribe, args=(audio, injections), daemon=True).start()

    def _do_final_transcribe(self, audio: np.ndarray,
                             injections: list[tuple[float, str]] | None = None):
        # Remove live preview line, replace with final
        self.ui_queue.put(("remove_live_preview", None))

        if injections:
            # Use word timestamps to insert folder paths at the right positions
            text, words = transcribe_with_timestamps(audio, self.whisper_model)
            if text and words:
                text = self._merge_injections(words, injections)
            elif text:
                # Fallback: append injections at the end
                text = text + " " + " ".join(inj[1] for inj in injections)
            else:
                # No speech detected, just use injections as the fragment
                text = " ".join(inj[1] for inj in injections)
        else:
            text = transcribe(audio, self.whisper_model)

        if not text:
            self.ui_queue.put(("status", "No speech detected.", self.CP_STATUS))
            return
        self.ui_queue.put(("fragment", text))
        label = f"Added: \"{text[:50]}\"" if len(text) > 50 else f"Added: \"{text}\""
        self.ui_queue.put(("status", label, self.CP_STATUS))

    @staticmethod
    def _merge_injections(words: list[tuple[float, float, str]],
                          injections: list[tuple[float, str]]) -> str:
        """Merge injected text into the word stream at the right timestamps."""
        # Build a combined timeline of words and injections
        result_parts: list[str] = []
        inj_idx = 0
        injections_sorted = sorted(injections, key=lambda x: x[0])

        for w_start, w_end, word in words:
            # Insert any injections that should appear before this word
            while inj_idx < len(injections_sorted) and injections_sorted[inj_idx][0] <= w_start:
                result_parts.append(injections_sorted[inj_idx][1])
                inj_idx += 1
            result_parts.append(word)

        # Append any remaining injections after all words
        while inj_idx < len(injections_sorted):
            result_parts.append(injections_sorted[inj_idx][1])
            inj_idx += 1

        return " ".join(part.strip() for part in result_parts if part.strip())

    # ─── Echo test ─────────────────────────────────────────────────

    def _echo_test(self):
        """Record 1 second of audio and play it back immediately."""
        self._set_status("Echo test: recording 1 second...", self.CP_RECORDING)
        threading.Thread(target=self._do_echo_test, daemon=True).start()

    def _do_echo_test(self):
        frames = []

        def callback(indata, frame_count, time_info, status):
            frames.append(indata.copy())

        # Record 1 second
        stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32",
            blocksize=BLOCK_SIZE, callback=callback)
        stream.start()
        time.sleep(1.0)
        stream.stop()
        stream.close()

        if not frames:
            self.ui_queue.put(("status", "Echo test: no audio captured.", self.CP_STATUS))
            return

        audio = np.concatenate(frames)
        peak = np.max(np.abs(audio))
        rms = np.sqrt(np.mean(audio ** 2))

        self.ui_queue.put(("status",
                           f"Echo test: playing back (peak={peak:.3f}, rms={rms:.4f})...",
                           self.CP_STATUS))

        # Play it back at the default output device
        sd.play(audio, samplerate=SAMPLE_RATE)
        sd.wait()

        self.ui_queue.put(("status",
                           f"Echo test done. Peak={peak:.3f} RMS={rms:.4f} "
                           f"({'good signal' if peak > 0.05 else 'very quiet!'})",
                           self.CP_STATUS))

    # ─── Refine ────────────────────────────────────────────────────

    def _start_refine(self):
        if not self.fragments:
            self._set_status("No fragments to refine. Dictate something first!")
            return
        self.refining = True
        self._set_status("Sending to Claude for refinement...", self.CP_STATUS)
        threading.Thread(target=self._do_refine, daemon=True).start()

    def _do_refine(self):
        fragments_copy = list(self.fragments)
        current = self.current_prompt
        result = refine_with_llm(
            fragments_copy, current,
            status_callback=lambda msg: self.ui_queue.put(("status", msg, self.CP_STATUS)))
        self.ui_queue.put(("refined", result))
        self.ui_queue.put(("status", f"Prompt refined! (v{self.prompt_version + 1})", self.CP_STATUS))

    # ─── Save ──────────────────────────────────────────────────────

    def _save_prompt(self):
        if not self.current_prompt:
            self._set_status("No prompt to save. Refine first!")
            return

        now = datetime.datetime.now()
        date_dir = self.save_base / now.strftime("%Y/%m/%d")
        date_dir.mkdir(parents=True, exist_ok=True)

        existing = sorted(date_dir.glob("prompt_*.md"))
        seq = len(existing) + 1
        filename = date_dir / f"prompt_{seq:03d}.md"

        with open(filename, "w") as f:
            f.write(f"# Prompt v{self.prompt_version}\n")
            f.write(f"# Generated: {now.isoformat()}\n")
            f.write(f"# Fragments: {len(self.fragments)}\n\n")
            f.write(self.current_prompt)
            f.write("\n")

        self._scan_saved_prompts()
        self.browser_index = -1
        self.prompt_saved = True
        self._set_status(f"Saved: {filename}")

    def _save_to_history(self, prompt_text):
        """Auto-save every executed prompt to the history subfolder."""
        if not prompt_text:
            return
        now = datetime.datetime.now()
        date_dir = self.history_base / now.strftime("%Y/%m/%d")
        date_dir.mkdir(parents=True, exist_ok=True)
        existing = sorted(date_dir.glob("prompt_*.md"))
        seq = len(existing) + 1
        filename = date_dir / f"prompt_{seq:03d}.md"
        with open(filename, "w") as f:
            f.write(f"# Executed: {now.isoformat()}\n\n")
            f.write(prompt_text)
            f.write("\n")
        self._scan_history_prompts()

    def _add_to_favorites(self):
        """Add the currently browsed prompt to favorites."""
        prompt_text = self._get_active_prompt_text()
        if not prompt_text and self.current_prompt:
            prompt_text = self.current_prompt
        if not prompt_text:
            self._set_status("No prompt to favorite. Browse or refine one first!")
            return

        now = datetime.datetime.now()
        date_dir = self.favorites_base / now.strftime("%Y/%m/%d")
        date_dir.mkdir(parents=True, exist_ok=True)
        existing = sorted(date_dir.glob("prompt_*.md"))
        seq = len(existing) + 1
        filename = date_dir / f"prompt_{seq:03d}.md"
        with open(filename, "w") as f:
            f.write(f"# Favorited: {now.isoformat()}\n\n")
            f.write(prompt_text)
            f.write("\n")
        self._scan_favorites_prompts()
        self._set_status(f"★ Added to favorites! ({len(self.favorites_prompts)} total)")

    def _remove_from_favorites(self):
        """Remove the currently browsed favorite and return it to history."""
        if self.browser_view != "favorites" or self.browser_index < 0:
            self._set_status("No favorite selected to remove.")
            return
        if self.browser_index >= len(self.favorites_prompts):
            self._set_status("No favorite selected to remove.")
            return

        path = self.favorites_prompts[self.browser_index]
        try:
            # Read content before deleting
            content = path.read_text()
            path.unlink()
            # Clean up empty parent directories
            parent = path.parent
            while parent != self.favorites_base:
                try:
                    parent.rmdir()  # only removes if empty
                except OSError:
                    break
                parent = parent.parent
        except Exception as e:
            self._set_status(f"Error removing favorite: {e}")
            return

        # Save to history so it's not lost
        now = datetime.datetime.now()
        date_dir = self.history_base / now.strftime("%Y/%m/%d")
        date_dir.mkdir(parents=True, exist_ok=True)
        existing = sorted(date_dir.glob("prompt_*.md"))
        seq = len(existing) + 1
        filename = date_dir / f"prompt_{seq:03d}.md"
        with open(filename, "w") as f:
            f.write(content)
        self._scan_history_prompts()

        self._scan_favorites_prompts()
        # Adjust browser index
        if self.favorites_prompts:
            self.browser_index = min(self.browser_index, len(self.favorites_prompts) - 1)
        else:
            self.browser_index = -1
        self._load_browser_prompt(self.stdscr.getmaxyx()[1] // 2)
        self._set_status(f"Removed from favorites. ({len(self.favorites_prompts)} remaining)")

    # ─── New prompt ─────────────────────────────────────────────────

    def _new_prompt(self):
        """Start a new prompt. If current is unsaved, ask to save first."""
        if self.current_prompt and not self.prompt_saved:
            self.confirming_new = True
            self._set_status("Unsaved prompt! Save first? [Y]es / [N]o / any key to cancel")
            return
        self._do_new_prompt()

    def _clear_executed_prompt(self):
        """Clear the executed prompt display from the prompt browser."""
        if self.executed_prompt_text is not None:
            self.executed_prompt_text = None
            if self._prompt_pane_original_color is not None:
                self.prompt_pane.color_pair = self._prompt_pane_original_color
                self._prompt_pane_original_color = None

    def _do_new_prompt(self):
        """Actually reset to a new prompt."""
        self._clear_executed_prompt()
        self.fragments.clear()
        self.current_prompt = None
        self.prompt_version = 0
        self.prompt_saved = True
        self.dictation_pane.lines.clear()
        self.dictation_pane.scroll_offset = 0
        self.browser_view = "active"
        self.browser_index = -1
        w = self.stdscr.getmaxyx()[1] // 2
        self._load_browser_prompt(w)
        self._set_dictation_info(w)
        self._set_agent_welcome(w)
        self._set_status("New prompt started. Dictate away!")

    # ─── Direct execution (skip refinement) ────────────────────────

    def _execute_raw(self):
        """Execute raw dictation fragments directly, skipping refinement."""
        if not self.fragments:
            self._set_status("No fragments to execute. Dictate something first!")
            return
        if self.agent_state not in (AgentState.IDLE, AgentState.DONE):
            self._set_status("Agent is busy. Wait or kill it first.")
            return
        prompt_text = " ".join(self.fragments)
        self.fragments.clear()
        self._save_to_history(prompt_text)
        # Show executed prompt in yellow in the prompt browser (persists until new prompt)
        self.executed_prompt_text = prompt_text
        if self._prompt_pane_original_color is None:
            self._prompt_pane_original_color = self.prompt_pane.color_pair
        self.prompt_pane.color_pair = self.CP_XFER
        self.browser_view = "active"
        self.browser_index = -1
        w = self.stdscr.getmaxyx()[1] // 2
        self._load_browser_prompt(w)
        # Clear dictation buffer
        self.dictation_pane.lines.clear()
        self.dictation_pane.scroll_offset = 0
        self._set_status("Executing raw dictation directly...")
        # Reuse the standard execution path
        self.xfer_prompt_text = prompt_text
        self.xfer_bytes = len(prompt_text.encode())
        self.xfer_progress = 0.0
        self.xfer_frame = 0
        self.xfer_start_time = time.time()
        self.agent_state = AgentState.DOWNLOADING
        self.typewriter_queue.clear()
        self.agent_first_output = False
        self._typewriter_line_color = None
        self._tts_detect_buf = ''
        self._tts_in_summary = False
        self._set_agent_welcome(40)
        threading.Thread(target=self._run_agent, daemon=True).start()

    # ─── Agent execution ──────────────────────────────────────────

    def _execute_prompt(self):
        prompt_text = self._get_active_prompt_text()
        if not prompt_text:
            self._set_status("No prompt to execute. Refine or browse to one first!")
            return

        # Show executed prompt in yellow in the prompt browser (persists until new prompt)
        self.executed_prompt_text = prompt_text
        if self._prompt_pane_original_color is None:
            self._prompt_pane_original_color = self.prompt_pane.color_pair
        self.prompt_pane.color_pair = self.CP_XFER
        self.browser_view = "active"
        self.browser_index = -1
        w = self.stdscr.getmaxyx()[1] // 2
        self._load_browser_prompt(w)

        self._save_to_history(prompt_text)

        self.xfer_prompt_text = prompt_text
        self.xfer_bytes = len(prompt_text.encode())
        self.xfer_progress = 0.0
        self.xfer_frame = 0
        self.xfer_start_time = time.time()
        self.agent_state = AgentState.DOWNLOADING
        self.typewriter_queue.clear()
        self.agent_first_output = False
        self._typewriter_line_color = None
        self._tts_detect_buf = ''
        self._tts_in_summary = False

        # Reset agent pane with welcome text (visible until output arrives)
        self._set_agent_welcome(40)

        self._set_status("Initiating ZMODEM transfer to agent...")

        # Start agent after a brief animation delay
        threading.Thread(target=self._run_agent, daemon=True).start()

    def _emit_typewriter(self, text):
        """Queue text for typewriter display in the agent pane.

        Detects [TTS_SUMMARY] / [/TTS_SUMMARY] markers and switches
        typewriter color to white for the TTS summary block.
        """
        self._tts_detect_buf = getattr(self, '_tts_detect_buf', '')
        self._tts_in_summary = getattr(self, '_tts_in_summary', False)

        self._tts_detect_buf += text

        while self._tts_detect_buf:
            if not self._tts_in_summary:
                idx = self._tts_detect_buf.find('[TTS_SUMMARY]')
                if idx == -1:
                    # Flush all but last 13 chars (tag length) in case tag spans chunks
                    safe = max(0, len(self._tts_detect_buf) - 13)
                    for ch in self._tts_detect_buf[:safe]:
                        self.ui_queue.put(("typewriter_char", ch))
                    self._tts_detect_buf = self._tts_detect_buf[safe:]
                    break
                else:
                    # Flush text before the tag
                    for ch in self._tts_detect_buf[:idx]:
                        self.ui_queue.put(("typewriter_char", ch))
                    # Skip the tag itself, emit color change
                    self._tts_detect_buf = self._tts_detect_buf[idx + 13:]
                    self._tts_in_summary = True
                    self.ui_queue.put(("typewriter_color", self.CP_TTS))
            else:
                idx = self._tts_detect_buf.find('[/TTS_SUMMARY]')
                if idx == -1:
                    safe = max(0, len(self._tts_detect_buf) - 14)
                    for ch in self._tts_detect_buf[:safe]:
                        self.ui_queue.put(("typewriter_char", ch))
                    self._tts_detect_buf = self._tts_detect_buf[safe:]
                    break
                else:
                    # Flush text before the closing tag
                    for ch in self._tts_detect_buf[:idx]:
                        self.ui_queue.put(("typewriter_char", ch))
                    # Skip the closing tag, reset color
                    self._tts_detect_buf = self._tts_detect_buf[idx + 14:]
                    self._tts_in_summary = False
                    self.ui_queue.put(("typewriter_color", None))

    def _flush_tts_detect_buf(self):
        """Flush any remaining chars in the TTS detection buffer."""
        buf = getattr(self, '_tts_detect_buf', '')
        if buf:
            for ch in buf:
                self.ui_queue.put(("typewriter_char", ch))
            self._tts_detect_buf = ''

    def _format_tool_input(self, name, inp):
        """Format a tool_use input dict into a concise display string."""
        if name == "Read":
            path = inp.get("file_path", "")
            parts = []
            if path:
                parts.append(path.split("/")[-1] if "/" in path else path)
            if inp.get("offset"):
                parts.append(f"L{inp['offset']}")
            if inp.get("limit"):
                parts.append(f"+{inp['limit']}")
            return " ".join(parts) if parts else ""
        elif name == "Edit":
            path = inp.get("file_path", "")
            short = path.split("/")[-1] if "/" in path else path
            old = inp.get("old_string", "")
            preview = old[:60].replace("\n", "\\n") + ("..." if len(old) > 60 else "")
            return f"{short}: {preview}" if preview else short
        elif name == "Write":
            path = inp.get("file_path", "")
            return path.split("/")[-1] if "/" in path else path
        elif name in ("Bash", "Task"):
            cmd = inp.get("command", inp.get("prompt", ""))
            return cmd[:80] + ("..." if len(cmd) > 80 else "")
        elif name in ("Grep", "Glob"):
            pat = inp.get("pattern", "")
            path = inp.get("path", "")
            return f"{pat}" + (f" in {path}" if path else "")
        elif name == "Agent":
            desc = inp.get("description", "")
            return desc
        else:
            s = json.dumps(inp)
            return s[:80] + ("..." if len(s) > 80 else "")

    def _run_agent(self):
        """Run claude agent in background, streaming verbose output."""
        # Let the download animation play for ~3 seconds
        time.sleep(3.0)

        self.ui_queue.put(("agent_state", AgentState.RECEIVING))
        self.ui_queue.put(("status", "Agent receiving transmission...", self.CP_STATUS))

        # Add the "incoming transmission" header via typewriter
        self._emit_typewriter("\n═══ INCOMING TRANSMISSION ═══\n\n")

        try:
            prompt_with_tts = self.xfer_prompt_text + TTS_PROMPT_SUFFIX
            cmd = ["claude", "--print", "--verbose", "--output-format",
                   "stream-json", "--dangerously-skip-permissions"]
            if self.session_id:
                cmd += ["--resume", self.session_id]
            cmd += ["-p", prompt_with_tts]
            self.agent_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            result_text = ""
            response_text_parts = []

            while True:
                line = self.agent_process.stdout.readline()
                if not line:
                    break
                if self.agent_state == AgentState.IDLE:
                    break

                if not self.agent_first_output:
                    self.agent_first_output = True

                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    # Non-JSON output (e.g. stderr), show as-is
                    self._emit_typewriter(line + "\n")
                    continue

                ev_type = event.get("type", "")

                # Capture session_id from init event
                if ev_type == "system" and event.get("subtype") == "init":
                    sid = event.get("session_id", "")
                    if sid:
                        self.ui_queue.put(("session_id", sid))

                if ev_type == "assistant":
                    msg = event.get("message", {})
                    for block in msg.get("content", []):
                        bt = block.get("type", "")
                        if bt == "text":
                            text = block.get("text", "")
                            response_text_parts.append(text)
                            self._emit_typewriter(text)
                        elif bt == "tool_use":
                            name = block.get("name", "?")
                            inp = block.get("input", {})
                            detail = self._format_tool_input(name, inp)
                            self._emit_typewriter(
                                f"\n▶ {name}: {detail}\n"
                            )
                        elif bt == "thinking":
                            thinking = block.get("thinking", "")
                            if thinking:
                                # Show thinking with prefix
                                lines = thinking.split("\n")
                                for tl in lines:
                                    self._emit_typewriter(f"  .. {tl}\n")

                elif ev_type == "user":
                    # Tool results - show abbreviated
                    content = event.get("content", [])
                    if isinstance(content, list):
                        for item in content:
                            if item.get("type") == "tool_result":
                                tool_text = item.get("content", "")
                                if isinstance(tool_text, list):
                                    # Extract text from content blocks
                                    tool_text = " ".join(
                                        c.get("text", "")
                                        for c in tool_text
                                        if c.get("type") == "text"
                                    )
                                if tool_text:
                                    preview = tool_text[:200].replace("\n", " ")
                                    if len(tool_text) > 200:
                                        preview += f"... ({len(tool_text)} chars)"
                                    self._emit_typewriter(
                                        f"  ◀ {preview}\n"
                                    )

                elif ev_type == "result":
                    result_text = event.get("result", "")
                    # Extract context usage from modelUsage
                    model_usage = event.get("modelUsage", {})
                    for _model, usage_data in model_usage.items():
                        ctx_window = usage_data.get("contextWindow", 0)
                        input_t = usage_data.get("inputTokens", 0)
                        output_t = usage_data.get("outputTokens", 0)
                        cache_read = usage_data.get("cacheReadInputTokens", 0)
                        cache_create = usage_data.get("cacheCreationInputTokens", 0)
                        # Total tokens in context = all input + output tokens
                        total = input_t + output_t + cache_read + cache_create
                        self.ui_queue.put(("context_usage", total, ctx_window))

                # Skip system, rate_limit_event, etc.

            self.agent_process.wait()

            # Flush any remaining TTS detection buffer
            self._flush_tts_detect_buf()

            # End marker — reset color to default for the transmission footer
            self.ui_queue.put(("typewriter_color", None))
            self._emit_typewriter("\n\n═══ END TRANSMISSION ═══\n")

            self.ui_queue.put(("agent_state", AgentState.DONE))
            self.ui_queue.put(("status", "Agent complete. Ready for next prompt.", self.CP_STATUS))

            # Speak the summary via TTS
            full_response = result_text or "".join(response_text_parts)
            summary = extract_tts_summary(full_response)
            if summary:
                self.last_tts_summary = summary
                stop_speaking()
                speak_text(summary, on_done=lambda: self.ui_queue.put(
                    ("status", "Ready for next prompt.", self.CP_STATUS)))
                self.ui_queue.put(("status", "Speaking summary...", self.CP_STATUS))

        except FileNotFoundError:
            self.ui_queue.put(("agent_state", AgentState.DONE))
            self.ui_queue.put(("status", "Error: 'claude' CLI not found!", self.CP_STATUS))
        except Exception as e:
            self.ui_queue.put(("agent_state", AgentState.DONE))
            self.ui_queue.put(("status", f"Agent error: {e}", self.CP_STATUS))

    def _kill_agent(self):
        if self.agent_process:
            try:
                self.agent_process.kill()
            except Exception:
                pass
            self.agent_process = None
        stop_speaking()
        self.agent_state = AgentState.IDLE
        self.typewriter_queue.clear()
        # Restore source pane if still pending
        if self._agent_source_pane is not None:
            self._agent_source_pane.color_pair = self._agent_source_original_color
            self._agent_source_pane = None
            self._agent_source_original_color = None
        self._set_status("Agent terminated.")

    def _clear_session(self):
        """Clear the current Claude session, starting fresh next execution."""
        self.session_id = None
        self.session_turns = 0
        self.context_tokens_used = 0
        self.context_window_size = 0
        self._set_status("Session cleared. Next prompt starts a new conversation.")

    # ─── Typewriter effect ─────────────────────────────────────────

    def _process_typewriter(self):
        """Process queued characters for the typewriter effect."""
        if not self.typewriter_queue:
            return

        now = time.time()
        right_width = self.stdscr.getmaxyx()[1] - self.stdscr.getmaxyx()[1] // 2

        # Process multiple chars per frame to keep up, but with timing
        chars_this_frame = 0
        max_chars = 20  # burst up to 20 chars per frame for verbose streaming

        while self.typewriter_queue and chars_this_frame < max_chars:
            ch = self.typewriter_queue[0]

            # Handle color-change sentinel tuples
            if isinstance(ch, tuple) and ch[0] == "color":
                self.typewriter_queue.popleft()
                self._typewriter_line_color = ch[1]  # None to reset
                # Tag current last line with the new color
                if self._typewriter_line_color is not None and self.agent_pane.lines:
                    idx = len(self.agent_pane.lines) - 1
                    self.agent_pane.line_colors[idx] = self._typewriter_line_color
                continue

            delay = self.typewriter_line_delay if ch == "\n" else self.typewriter_char_delay

            if now - self.typewriter_last_time >= delay:
                self.typewriter_queue.popleft()
                prev_count = len(self.agent_pane.lines)
                self.agent_pane.add_char_to_last_line(ch, right_width)
                # Tag any newly created lines with the current override color
                if self._typewriter_line_color is not None:
                    for idx in range(prev_count, len(self.agent_pane.lines)):
                        self.agent_pane.line_colors[idx] = self._typewriter_line_color
                self.typewriter_last_time = now
                chars_this_frame += 1
            else:
                break

    # ─── UI queue processing ───────────────────────────────────────

    def _process_ui_queue(self):
        left_width = self.stdscr.getmaxyx()[1] * 2 // 5

        while True:
            try:
                msg = self.ui_queue.get_nowait()
            except queue.Empty:
                break

            if msg[0] == "status":
                self.status_msg = msg[1]
                self.status_color = msg[2] if len(msg) > 2 else self.CP_STATUS

            elif msg[0] == "live_preview":
                # Update or add the live preview lines (shown dimly while recording)
                text = msg[1]
                # Remove previous preview lines
                while self.dictation_pane.lines and self.dictation_pane.lines[-1].startswith("  ◌ "):
                    self.dictation_pane.lines.pop()
                # Wrap the preview text to fit within the pane
                wrap_width = max(1, left_width - 2)
                prefix = "  ◌ "
                wrapped = textwrap.wrap(text, width=max(1, wrap_width - len(prefix)))
                if wrapped:
                    self.dictation_pane.lines.append(f"{prefix}{wrapped[0]}")
                    for continuation in wrapped[1:]:
                        self.dictation_pane.lines.append(f"  ◌  {continuation}")
                else:
                    self.dictation_pane.lines.append(f"{prefix}{text}")
                self.dictation_pane.scroll_to_bottom(
                    self.dictation_pane._last_height if hasattr(self.dictation_pane, '_last_height') else 10)

            elif msg[0] == "remove_live_preview":
                # Remove all live preview lines before adding final fragment
                while self.dictation_pane.lines and self.dictation_pane.lines[-1].startswith("  ◌ "):
                    self.dictation_pane.lines.pop()

            elif msg[0] == "fragment":
                text = msg[1]
                # New dictation clears the executed prompt from the browser
                if self.executed_prompt_text is not None:
                    self._clear_executed_prompt()
                    self._load_browser_prompt(left_width)
                self.fragments.append(text)
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                self.dictation_pane.add_line(f"[{ts}] {text}", left_width)

            elif msg[0] == "refined":
                self.current_prompt = msg[1]
                self.prompt_version += 1
                self.prompt_saved = False  # track unsaved state
                self.browser_index = -1
                self._load_browser_prompt(left_width)
                # Clear fragments and dictation after refinement
                self.fragments.clear()
                self.dictation_pane.lines.clear()
                self.dictation_pane.scroll_offset = 0
                self._set_dictation_info(left_width)
                self.refining = False

            elif msg[0] == "agent_state":
                self.agent_state = msg[1]
                if msg[1] == AgentState.DONE:
                    self.session_turns += 1

            elif msg[0] == "session_id":
                self.session_id = msg[1]

            elif msg[0] == "context_usage":
                self.context_tokens_used = msg[1]
                if msg[2]:
                    self.context_window_size = msg[2]

            elif msg[0] == "typewriter_char":
                self.typewriter_queue.append(msg[1])

            elif msg[0] == "typewriter_color":
                self.typewriter_queue.append(("color", msg[1]))

    def _set_status(self, msg: str, color: int = None):
        color = color if color is not None else self.CP_STATUS
        # Recording indicator has highest priority — suppress non-recording
        # alerts while recording is active so the red bar stays visible.
        if self.recording and color != self.CP_RECORDING:
            return
        self.status_msg = msg
        self.status_color = color


def main():
    parser = argparse.ArgumentParser(
        description="VoiceCode BBS v2.0 - Voice-Driven Prompt Workshop & Agent Terminal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            ╔═══════════════════════════════════════════════════════╗
            ║  Three-Pane Layout:                                   ║
            ║    Top-Left:    Prompt Browser / Editor               ║
            ║    Bottom-Left: Dictation Buffer                      ║
            ║    Right:       Agent Terminal (full height)          ║
            ║                                                       ║
            ║  Controls:                                            ║
            ║    SPACE    Toggle voice recording                    ║
            ║    R        Refine fragments into prompt              ║
            ║    S        Save prompt to dated folder               ║
            ║    N        New prompt (prompts save if unsaved)      ║
            ║    E        Execute prompt (send to agent)            ║
            ║    C        Clear dictation buffer                    ║
            ║    ←→       Browse saved prompts                      ║
            ║    ↑↓       Scroll prompt pane                        ║
            ║    PgUp/Dn  Scroll agent pane                         ║
            ║    K        Kill running agent                        ║
            ║    W        New session (clear context)               ║
            ║    X        Restart application                       ║
            ║    Q        Quit                                      ║
            ╚═══════════════════════════════════════════════════════╝
        """),
    )
    parser.add_argument(
        "--model", default="base.en",
        help="Whisper model (default: base.en)")
    parser.add_argument(
        "--save-dir", default="~/prompts",
        help="Prompt library path (saves to <path>/voicecode/). "
             "Overrides persisted setting. Default: ~/prompts")
    args = parser.parse_args()

    app = BBSApp(args)
    curses.wrapper(lambda stdscr: app.run(stdscr))

    if app.restart:
        os.execv(sys.executable, [sys.executable] + sys.argv)


if __name__ == "__main__":
    main()
