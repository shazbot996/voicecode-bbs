#!/usr/bin/env python3
"""
VoiceCode BBS - A retro BBS-style voice-driven prompt workshop & agent terminal.

          ╔═══════════════════════════════════════╗
          ║  V O I C E C O D E   B B S   v2.2     ║
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
  2. [E]xecute — sends prompt to Claude agent (right pane)
  3. [←→] Browse prompt history
  4. Watch the ZMODEM transfer animation + typewriter response
"""

import curses
import sys
import os
import threading
import queue
import signal
import subprocess
import time
import datetime
import textwrap
import argparse
import random
import collections
import shutil
from pathlib import Path

from version import __version__

import json
import re
import numpy as np
import ctypes

# Suppress ALSA error/warning messages (e.g. "underrun occurred") that
# bleed into stderr and corrupt the curses terminal.  Must run before
# sounddevice or any ALSA client is initialised.
_ALSA_ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(
    None, ctypes.c_char_p, ctypes.c_int,
    ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p)
_alsa_error_handler = _ALSA_ERROR_HANDLER_FUNC(lambda *_: None)

try:
    _asound = ctypes.cdll.LoadLibrary("libasound.so.2")
    _asound.snd_lib_error_set_handler(_alsa_error_handler)
except OSError:
    pass  # not Linux / no ALSA — nothing to suppress

# ── Suppress PortAudio C-level stderr (pthread_join errors, etc.) ───
# PortAudio writes errors directly to C stderr via fprintf().  These corrupt
# the curses display.  We redirect file descriptor 2 to /dev/null while the
# TUI is active and restore it on exit.
_saved_stderr_fd: int | None = None

def _suppress_stderr():
    """Redirect fd 2 → /dev/null to silence PortAudio/ALSA C-level noise."""
    global _saved_stderr_fd
    try:
        _saved_stderr_fd = os.dup(2)
        _devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(_devnull, 2)
        os.close(_devnull)
    except OSError:
        _saved_stderr_fd = None

def _restore_stderr():
    """Restore original stderr so post-exit tracebacks are visible."""
    global _saved_stderr_fd
    if _saved_stderr_fd is not None:
        try:
            os.dup2(_saved_stderr_fd, 2)
            os.close(_saved_stderr_fd)
        except OSError:
            pass
        _saved_stderr_fd = None

def _check_audio_input_device() -> str | None:
    """Return an error message if no working input device, else None."""
    try:
        dev = sd.query_devices(kind="input")
        if dev is None:
            return "No audio input device found."
        if dev.get("max_input_channels", 0) < 1:
            return f"Input device '{dev.get('name', '?')}' has no input channels."
        return None
    except sd.PortAudioError as e:
        return f"Audio device error: {e}"
    except Exception as e:
        return f"Cannot query audio devices: {e}"

def _safe_sd_play(audio, samplerate):
    """Play audio via sounddevice, swallowing PortAudio errors."""
    try:
        sd.play(audio, samplerate=samplerate)
        sd.wait()
    except (sd.PortAudioError, OSError):
        pass  # output device disappeared — nothing we can do

import sounddevice as sd


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


def _slug_from_text(text: str, max_words: int = 5) -> str:
    """Derive a short filesystem-safe slug from prompt text."""
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            break
    else:
        stripped = text.strip()
    words = re.sub(r"[^a-z0-9\s]", "", stripped.lower()).split()[:max_words]
    return "_".join(words) if words else "prompt"


def _next_seq(directory: Path) -> int:
    """Return the next sequence number for flat-indexed files in directory."""
    max_seq = 0
    if directory.exists():
        for p in directory.iterdir():
            m = re.match(r"(\d+)_", p.name)
            if m:
                max_seq = max(max_seq, int(m.group(1)))
    return max_seq + 1


# ─── CLI Provider abstraction ─────────────────────────────────────────

class CLIProvider:
    """Base class for AI CLI providers (Claude, Gemini, etc.)."""

    name: str = "unknown"
    binary: str = "unknown"

    def is_installed(self) -> bool:
        return shutil.which(self.binary) is not None

    def get_version(self) -> str | None:
        try:
            result = subprocess.run(
                [self.binary, "--version"],
                capture_output=True, text=True, timeout=10)
            return result.stdout.strip() or result.stderr.strip()
        except Exception:
            return None

    def build_refine_cmd(self, prompt: str) -> list[str]:
        raise NotImplementedError

    def build_execute_cmd(self, prompt: str, session_id: str | None = None) -> list[str]:
        raise NotImplementedError

    def parse_init_event(self, event: dict) -> str | None:
        """Extract session_id from an init/system event. Return None if not an init event."""
        raise NotImplementedError

    def parse_text_event(self, event: dict) -> tuple[str, list] | None:
        """Parse a streaming event, returning (text, tool_uses) or None if not a text event.
        tool_uses is a list of (name, detail_str) tuples."""
        raise NotImplementedError

    def parse_thinking_event(self, event: dict) -> str | None:
        """Extract thinking text from an event, or None."""
        raise NotImplementedError

    def parse_tool_result_event(self, event: dict) -> str | None:
        """Extract tool result preview from a user/tool_result event, or None."""
        raise NotImplementedError

    def parse_context_usage(self, event: dict) -> tuple[int, int] | None:
        """Extract (tokens_used, context_window_size) from a result event, or None."""
        raise NotImplementedError

    def is_result_event(self, event: dict) -> str | None:
        """If this is a result event, return the result text. Otherwise None."""
        raise NotImplementedError


class ClaudeProvider(CLIProvider):
    name = "Claude"
    binary = "claude"

    def build_refine_cmd(self, prompt: str) -> list[str]:
        return [self.binary, "--print", "-p", prompt]

    def build_execute_cmd(self, prompt: str, session_id: str | None = None) -> list[str]:
        cmd = [self.binary, "--print", "--verbose", "--output-format",
               "stream-json", "--dangerously-skip-permissions"]
        if session_id:
            cmd += ["--resume", session_id]
        cmd += ["-p", prompt]
        return cmd

    def parse_init_event(self, event: dict) -> str | None:
        if event.get("type") == "system" and event.get("subtype") == "init":
            return event.get("session_id") or None
        return None

    def parse_text_event(self, event: dict) -> tuple[str, list] | None:
        if event.get("type") != "assistant":
            return None
        text_parts = []
        tool_uses = []
        msg = event.get("message", {})
        for block in msg.get("content", []):
            bt = block.get("type", "")
            if bt == "text":
                text_parts.append(block.get("text", ""))
            elif bt == "tool_use":
                tool_uses.append((block.get("name", "?"), block.get("input", {})))
        return ("".join(text_parts), tool_uses) if text_parts or tool_uses else None

    def parse_thinking_event(self, event: dict) -> str | None:
        if event.get("type") != "assistant":
            return None
        msg = event.get("message", {})
        thinking_parts = []
        for block in msg.get("content", []):
            if block.get("type") == "thinking":
                t = block.get("thinking", "")
                if t:
                    thinking_parts.append(t)
        return "\n".join(thinking_parts) if thinking_parts else None

    def parse_tool_result_event(self, event: dict) -> str | None:
        if event.get("type") != "user":
            return None
        content = event.get("content", [])
        if not isinstance(content, list):
            return None
        previews = []
        for item in content:
            if item.get("type") == "tool_result":
                tool_text = item.get("content", "")
                if isinstance(tool_text, list):
                    tool_text = " ".join(
                        c.get("text", "") for c in tool_text if c.get("type") == "text")
                if tool_text:
                    preview = tool_text[:200].replace("\n", " ")
                    if len(tool_text) > 200:
                        preview += f"... ({len(tool_text)} chars)"
                    previews.append(preview)
        return "\n".join(previews) if previews else None

    def parse_context_usage(self, event: dict) -> tuple[int, int] | None:
        if event.get("type") != "result":
            return None
        model_usage = event.get("modelUsage", {})
        for _model, usage_data in model_usage.items():
            ctx_window = usage_data.get("contextWindow", 0)
            input_t = usage_data.get("inputTokens", 0)
            output_t = usage_data.get("outputTokens", 0)
            cache_read = usage_data.get("cacheReadInputTokens", 0)
            cache_create = usage_data.get("cacheCreationInputTokens", 0)
            total = input_t + output_t + cache_read + cache_create
            return (total, ctx_window)
        return None

    def is_result_event(self, event: dict) -> str | None:
        if event.get("type") == "result":
            return event.get("result", "")
        return None


class GeminiProvider(CLIProvider):
    name = "Gemini"
    binary = "gemini"

    def build_refine_cmd(self, prompt: str) -> list[str]:
        return [self.binary, "-p", prompt]

    def build_execute_cmd(self, prompt: str, session_id: str | None = None) -> list[str]:
        cmd = [self.binary, "--yolo", "-o", "stream-json"]
        if session_id:
            cmd += ["--resume", "latest"]
        cmd += ["-p", prompt]
        return cmd

    def parse_init_event(self, event: dict) -> str | None:
        if event.get("type") == "init":
            return event.get("session_id") or None
        return None

    def parse_text_event(self, event: dict) -> tuple[str, list] | None:
        if event.get("type") != "message":
            return None
        if event.get("role") != "assistant":
            return None
        text = event.get("content", "")
        tool_uses = []
        # Gemini may include tool_calls in the event
        for tc in event.get("tool_calls", []):
            tool_uses.append((tc.get("name", "?"), tc.get("args", {})))
        return (text, tool_uses) if text or tool_uses else None

    def parse_thinking_event(self, event: dict) -> str | None:
        if event.get("type") != "message" or event.get("role") != "assistant":
            return None
        thinking = event.get("thinking", "")
        return thinking if thinking else None

    def parse_tool_result_event(self, event: dict) -> str | None:
        if event.get("type") != "message" or event.get("role") != "tool":
            return None
        content = event.get("content", "")
        if content:
            preview = str(content)[:200].replace("\n", " ")
            if len(str(content)) > 200:
                preview += f"... ({len(str(content))} chars)"
            return preview
        return None

    def parse_context_usage(self, event: dict) -> tuple[int, int] | None:
        if event.get("type") != "result":
            return None
        stats = event.get("stats", {})
        models = stats.get("models", {})
        total_tokens = 0
        ctx_window = 0
        for _model, model_data in models.items():
            tokens = model_data.get("tokens", {})
            total_tokens += tokens.get("total", 0)
            # Gemini doesn't report context window in the same way;
            # use a reasonable default for the model
            if not ctx_window:
                ctx_window = tokens.get("contextWindow", 1_000_000)
        # Fallback: check flat stats fields (stream-json format)
        if not total_tokens:
            total_tokens = stats.get("total_tokens", 0)
        return (total_tokens, ctx_window) if total_tokens else None

    def is_result_event(self, event: dict) -> str | None:
        if event.get("type") == "result":
            return event.get("response", event.get("result", ""))
        return None


# Registry of all known providers
ALL_PROVIDERS = [ClaudeProvider(), GeminiProvider()]


def _detect_providers() -> list[CLIProvider]:
    """Return list of providers whose CLI binary is installed."""
    return [p for p in ALL_PROVIDERS if p.is_installed()]


def _get_provider_by_name(name: str) -> CLIProvider | None:
    """Look up a provider by name (case-insensitive)."""
    for p in ALL_PROVIDERS:
        if p.name.lower() == name.lower():
            return p
    return None


# ─── TTS globals ──────────────────────────────────────────────────────

TTS_AVAILABLE = False
try:
    from piper.download_voices import download_voice
    TTS_AVAILABLE = True

except ImportError:
    pass

if TTS_AVAILABLE:
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
else:
    PIPER_VOICES_DIR = None
    PIPER_VOICES = []


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
    if not PIPER_VOICES:
        return Path()
    voice = PIPER_VOICES[_tts_voice_index]
    preset = VOICE_PRESETS.get(voice)
    model_name = preset["model"] if preset else voice
    return PIPER_VOICES_DIR / (model_name + ".onnx")


def get_tts_piper_extra_args() -> list[str]:
    """Return extra piper CLI args for the current voice (e.g. preset tuning)."""
    if not PIPER_VOICES:
        return []
    voice = PIPER_VOICES[_tts_voice_index]
    preset = VOICE_PRESETS.get(voice)
    return list(preset["piper_args"]) if preset else []


def get_tts_voice_name() -> str:
    """Return the short display name of the currently selected voice."""
    if not PIPER_VOICES:
        return "N/A"
    return PIPER_VOICES[_tts_voice_index]



def cycle_tts_voice(direction: int) -> str:
    """Cycle the TTS voice forward (+1) or backward (-1). Returns new voice name."""
    if not PIPER_VOICES:
        return "N/A"
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
    if not PIPER_VOICES:
        return 0, "N/A"
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
    if not TTS_AVAILABLE:
        if on_done:
            on_done(0, 0)
        return

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


def download_single_voice_model(voice: str, on_done=None):
    """Download a single voice model file in a background thread."""
    if not TTS_AVAILABLE:
        if on_done:
            on_done(False, "TTS not available")
        return

    def _run():
        PIPER_VOICES_DIR.mkdir(parents=True, exist_ok=True)
        try:
            from piper.download_voices import download_voice
            # Preset voices reuse another model's files — download that instead
            model = voice
            # VOICE_PRESETS is not defined globally, but let's check or use direct
            # Wait, let's look if VOICE_PRESETS exists!
            download_voice(model, PIPER_VOICES_DIR)
            if on_done:
                on_done(True, voice)
        except Exception as e:
            if on_done:
                on_done(False, str(e))

    threading.Thread(target=_run, daemon=True).start()



def speak_text(text: str, on_done=None):
    """Speak text using Piper TTS + aplay in a background thread."""
    global _tts_process
    if not TTS_AVAILABLE:
        if on_done:
            on_done()
        return
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
            
            gain = float(_load_settings().get("tts_volume_gain", 1.0))

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
            
            # Piper reads stdin line-by-line; collapse to one line so the
            # entire summary is synthesised, not just the first sentence.
            single_line = " ".join(text.split())
            piper_proc.stdin.write((single_line + "\n").encode("utf-8"))
            piper_proc.stdin.close()

            # Read all output bytes
            audio_bytes = piper_proc.stdout.read()
            piper_proc.stdout.close()
            piper_proc.wait()

            if audio_bytes:
                audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
                if gain != 1.0:
                    audio_array = (audio_array * gain).clip(-32768, 32767).astype(np.int16)

                _safe_sd_play(audio_array, samplerate=22050)

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
        os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
        import torch
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
                                   curses.color_pair(self.color_pair) | curses.A_BOLD)
                    else:
                        win.addstr(y + 1 + i, x + 1, " " * max(0, content_width),
                                   curses.color_pair(self.color_pair) | curses.A_BOLD)
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
                                   curses.color_pair(line_cp) | curses.A_BOLD)

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
                    status_callback=None, provider: CLIProvider | None = None) -> str:
    if provider is None:
        provider = ClaudeProvider()
    if status_callback:
        status_callback(f"Refining with {provider.name}...")

    fragment_text = "\n".join(f"- {f}" for f in fragments)

    if current_prompt:
        meta_prompt = MODIFY_REFINE_PROMPT.format(
            current_prompt=current_prompt, fragments=fragment_text)
    else:
        meta_prompt = INITIAL_REFINE_PROMPT.format(fragments=fragment_text)

    try:
        cmd = provider.build_refine_cmd(meta_prompt)
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        else:
            return f"[Error: {result.stderr.strip() or 'empty response'}]"
    except FileNotFoundError:
        return f"[Error: '{provider.binary}' CLI not found]"
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

BANNER = f"""
██╗   ██╗ ██████╗ ██╗ ██████╗███████╗ ██████╗ ██████╗ ██████╗ ███████╗
 ██║   ██║██╔═══██╗██║██╔════╝██╔════╝██╔════╝██╔═══██╗██╔══██╗██╔════╝
 ██║   ██║██║   ██║██║██║     █████╗  ██║     ██║   ██║██║  ██║█████╗
 ╚██╗ ██╔╝██║   ██║██║██║     ██╔══╝  ██║     ██║   ██║██║  ██║██╔══╝
  ╚████╔╝ ╚██████╔╝██║╚██████╗███████╗╚██████╗╚██████╔╝██████╔╝███████╗
   ╚═══╝   ╚═════╝ ╚═╝ ╚═════╝╚══════╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝
                                                            @schiele
                  ╔════════════════════════════════╗
                  ║     B  ·  B  ·  S    v{__version__}      ║
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
    CP_SECT_RED = 19
    CP_SUBMENU = 20
    CP_SETTINGS_TITLE = 21
    CP_FAV_EMPTY = 22
    CP_FAV_FILLED = 23

    def __init__(self):
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
            "  ←→ to browse history",
            "  ↑↓ cycle views  1-0 load favorites",
        ]
        self.dictation_pane.welcome_art = [
            "╔══════════════════════════════════════╗",
            "║      ◆  DICTATION  BUFFER  ◆         ║",
            "║   Voice fragments appear here as     ║",
            "║   you record (SPACE) or type (Enter).║",
            "╚══════════════════════════════════════╝",
            "",
            "  This is your scratchpad for voice input.",
            "  Fragments collect here, then:",
            "",
            "  [R] Refine → merges into the Prompt above",
            "  [D] Direct → sends straight to the Agent",
            "  [U] Undo   → remove last entry",
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
            "  SPACE ··· Record voice / Enter ··· Type text",
            "  R     ··· Refine into prompt",
            "  E     ··· Execute prompt",
            "  D     ··· Direct execute",
            "  W     ··· New session (clear context)",
            "  O     ··· Options / Settings",
            "  H     ··· Full help screen",
            "  ESC   ··· Main menu",
        ]

        self.fragments: list[str] = []
        self.current_prompt: str | None = None
        self.prompt_version = 0

        self.status_msg = f"Welcome to VoiceCode BBS v{__version__}!"
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

        # Prompt library & save dir — from persisted settings or default
        saved = _load_settings()
        self.prompt_library = saved.get(
            "prompt_library", str(Path("~/prompts").expanduser()))
        self.tts_volume_gain = float(saved.get("tts_volume_gain", 1.0))

        # Voicecode writes into a dedicated subfolder within the library
        self.save_base = Path(self.prompt_library).expanduser() / "voicecode"
        self.history_base = self.save_base / "history"
        self.history_prompts: list[Path] = []
        self.favorites_slots: list[str | None] = [None] * 10  # 10 numbered slots (keys 1-9, 0)
        self.browser_index: int = -1
        self.browser_view: str = "active"  # "active" or "favorites"
        self._scan_history_prompts()
        self._load_favorites_slots()

        # Prompt saved state
        self.prompt_saved = True  # no unsaved prompt at start
        self.confirming_new = False  # for [N] save confirmation dialog
        self.confirming_edit_historical = False  # for editing a historical prompt
        self.choosing_fav_slot = False  # for [F] slot selection
        self.confirming_fav_overwrite = False  # for overwrite confirmation
        self._pending_fav_slot: int = -1  # slot index pending overwrite confirm
        self._pending_fav_path: str = ""  # path pending favorites assignment

        # Working directory for folder slug mode
        self.working_dir = saved.get("working_dir", "")
        self.documents_dir = saved.get("documents_dir", "")

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
        # Browser category: 0=Shortcuts, 1=Project Folders, 2=Documents
        self._browser_category = 0
        self._browser_categories = ["Shortcuts", "Project Folders", "Documents"]
        self._browser_cat_lists: list[list[str]] = [[], [], []]

        # Shortcut editor overlay state
        self.show_shortcut_editor = False
        self.shortcut_editor_cursor = 0
        self.shortcut_editor_scroll = 0
        self.shortcut_editing_text = False
        self.shortcut_edit_buffer = ""
        self.shortcut_edit_cursor_pos = 0

        # Mid-recording folder injections: [(audio_seconds, text), ...]
        self._recording_injections: list[tuple[float, str]] = []

        # Direct text entry mode (Enter key in dictation buffer)
        self.typing_mode = False
        self.typing_buffer = ""
        self.typing_cursor = 0

        # Settings overlay state
        self.show_settings_overlay = False
        self.settings_cursor = 0
        self.settings_editing_text = False  # True when inline text editing is active
        self.settings_edit_buffer = ""      # current text being edited
        self.settings_edit_cursor = 0       # cursor position within buffer

        # Sub-menu state
        self.tts_submenu_open = False
        self.tts_submenu_cursor = 0
        self.tts_submenu_items = []
        self.test_tools_submenu_open = False
        self.test_tools_submenu_cursor = 0
        self.voice_submenu_open = False
        self.voice_submenu_cursor = 0
        self.test_tools_submenu_items = []
        self.ai_models_submenu_open = False
        self.ai_models_submenu_cursor = 0
        self.ai_models_submenu_items = []
        self.tts_enabled = saved.get("tts_enabled", True)
        global _tts_enabled
        _tts_enabled = self.tts_enabled

        # Voice settings (mutable, persisted) — `saved` loaded above for prompt_library
        self.vad_threshold = saved.get("vad_threshold", VAD_THRESHOLD)
        self.silence_timeout = saved.get("silence_timeout", SILENCE_AFTER_SPEECH_SEC)
        self.min_speech_duration = saved.get("min_speech_duration", MIN_SPEECH_DURATION_SEC)
        self.whisper_model = saved.get("whisper_model", "base.en")

        # AI provider — detect installed CLIs and restore saved choice
        self.available_providers = _detect_providers()
        saved_provider = saved.get("ai_provider", "Claude")
        self.ai_provider = _get_provider_by_name(saved_provider)
        if not self.ai_provider or not self.ai_provider.is_installed():
            # Fallback to first available, or Claude as default
            self.ai_provider = self.available_providers[0] if self.available_providers else ClaudeProvider()

        # Settings definitions: (key, label, description, options, get_current, set_fn)
        self._build_settings_items()

        # Agent state
        self.agent_state = AgentState.IDLE
        self.agent_process = None
        self._agent_cancel = threading.Event()
        self.last_tts_summary = ""
        self._last_history_prompt_path: Path | None = None

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
        self.typewriter_last_time = 0.0  # unused, kept for compat
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
            {"type": "section", "label": "TOOLS & CONFIGURATION", "style": "yellow"},
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
                "key": "documents_dir",
                "label": "Documents Directory",
                "desc": "Root folder for markdown documents browser (Enter key)",
                "options": None,
                "get": lambda: self.documents_dir or "(not set)",
                "set": None,
                "editable": True,
                "action": self._start_editing_documents_dir,
            },
            {
                "key": "_action_voice_submenu",
                "label": "Voice Settings",
                "desc": "Whisper model, VAD threshold, silence timeout, min speech",
                "options": None,
                "get": lambda: self.whisper_model,
                "set": None,
                "action": self._open_voice_submenu,
                "submenu": True,
            },
            {
                "key": "_action_ai_models_submenu",
                "label": "AI Models",
                "desc": "Select AI provider (Claude, Gemini, etc.)",
                "options": None,
                "get": lambda: self.ai_provider.name,
                "set": None,
                "action": self._open_ai_models_submenu,
                "submenu": True,
            },
        ]
        if TTS_AVAILABLE:
            self.settings_items.append({
                    "key": "_action_tts_submenu",
                    "label": "Text-to-Speech Settings",
                    "desc": "Configure TTS voices, libraries, and enable/disable",
                    "options": None,
                    "get": lambda: "ON" if self.tts_enabled else "OFF",
                    "set": None,
                    "action": self._open_tts_submenu,
                    "submenu": True,
                })
        else:
            self.settings_items.append({
                    "key": "_action_tts_submenu",
                    "label": "Text-to-Speech Settings",
                    "desc": "TTS library not installed.",
                    "options": None,
                    "get": lambda: "UNAVAILABLE",
                    "set": None,
                    "action": None,
                    "submenu": True,
                })

        self.settings_items.append({
            "key": "_action_test_tools_submenu",
            "label": "Test Tools",
            "desc": "Echo test, TTS test sound, and volume controls",
            "options": None,
            "get": lambda: "",
            "set": None,
            "action": self._open_test_tools_submenu,
            "submenu": True,
        })


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
                "key": "tts_volume_gain",
                "label": "Volume Gain",
                "desc": "Digital volume boost multiplier",
                "options": ["1.0", "1.5", "2.0", "2.5", "3.0"],
                "get": lambda: f"{self.tts_volume_gain:.1f}",
                "set": self._set_tts_volume_gain,
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
                "key": "_action_test_speech",
                "label": "[Enter] Test Current Voice",
                "desc": "Speak a test sentence with the active voice profile",
                "options": None,
                "get": lambda: "",
                "set": None,
                "action": self._action_test_speech,
            },
            {
                "key": "_action_download_current_voice",

                "label": "[Enter] Download Current Voice Model",
                "desc": "Fetch only the sound profile currently selected above",
                "options": None,
                "get": lambda: "",
                "set": None,
                "action": self._action_download_current_voice,
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

    def _build_voice_submenu_items(self):
        """Build the Voice Settings sub-menu items list."""
        return [
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
        ]

    def _open_voice_submenu(self):
        """Open the Voice Settings sub-menu."""
        self.voice_submenu_open = True
        self.voice_submenu_cursor = 0
        self.voice_submenu_items = self._build_voice_submenu_items()
        self.show_settings_overlay = True  # keep modal open

    def _voice_submenu_cycle(self, direction):
        """Cycle the current Voice sub-menu setting's value."""
        item = self.voice_submenu_items[self.voice_submenu_cursor]
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

    def _build_ai_models_submenu_items(self):
        """Build the AI Models sub-menu items list."""
        # Always list all known providers, not just installed ones
        all_provider_names = [p.name for p in ALL_PROVIDERS]
        items = []
        if all_provider_names:
            items.append({
                "key": "ai_provider",
                "label": "Active Provider",
                "desc": "AI CLI to use for refinement and agent execution",
                "options": all_provider_names,
                "get": lambda: self.ai_provider.name,
                "set": self._set_ai_provider,
            })
        # Show provider info for all known providers
        for p in ALL_PROVIDERS:
            if p.is_installed():
                ver = p.get_version() or "unknown"
                path = shutil.which(p.binary) or "not found"
                items.append({
                    "key": f"_info_{p.name.lower()}",
                    "label": f"{p.name} CLI",
                    "desc": f"{path}",
                    "options": None,
                    "get": lambda v=ver: v,
                    "set": None,
                })
            else:
                items.append({
                    "key": f"_info_{p.name.lower()}",
                    "label": f"{p.name} CLI",
                    "desc": "not installed",
                    "options": None,
                    "get": lambda: "UNAVAILABLE",
                    "set": None,
                })
        return items

    def _set_ai_provider(self, name):
        """Switch the active AI provider."""
        provider = _get_provider_by_name(name)
        if provider and not provider.is_installed():
            self._set_status(
                f"{name} was not found. Available providers are checked on startup."
            )
            return
        if provider:
            self.ai_provider = provider
            self._persist_setting("ai_provider", name)
            self._clear_session()
            self._set_status(f"AI provider switched to {name}.")

    def _open_ai_models_submenu(self):
        """Open the AI Models sub-menu."""
        self.ai_models_submenu_open = True
        self.ai_models_submenu_cursor = 0
        self.ai_models_submenu_items = self._build_ai_models_submenu_items()
        self.show_settings_overlay = True

    def _ai_models_submenu_cycle(self, direction):
        """Cycle the current AI Models sub-menu setting's value."""
        item = self.ai_models_submenu_items[self.ai_models_submenu_cursor]
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

    def _open_tts_submenu(self):
        """Open the TTS settings sub-menu."""
        self.tts_submenu_open = True
        self.tts_submenu_cursor = 0
        self.tts_submenu_items = self._build_tts_submenu_items()
        self.show_settings_overlay = True  # keep modal open

    def _build_test_tools_items(self):
        """Build the Test Tools sub-menu items list."""
        items = [
            {
                "key": "_action_echo_test",
                "label": "[Enter] Echo / Mic Test",
                "desc": "Record 1s of audio and play it back to test your mic",
                "options": None,
                "get": lambda: "",
                "set": None,
                "action": self._echo_test,
            },
        ]
        if TTS_AVAILABLE:
            items.extend([
                {
                    "key": "_action_test_speech",
                    "label": "[Enter] Play TTS Test Sound",
                    "desc": "Speak a test sentence with the active voice profile",
                    "options": None,
                    "get": lambda: "",
                    "set": None,
                    "action": self._action_test_speech,
                },
                {
                    "key": "tts_volume_gain",
                    "label": "TTS Volume Gain",
                    "desc": "Digital volume boost multiplier",
                    "options": ["1.0", "1.5", "2.0", "2.5", "3.0"],
                    "get": lambda: f"{self.tts_volume_gain:.1f}",
                    "set": self._set_tts_volume_gain,
                },
            ])
        return items

    def _open_test_tools_submenu(self):
        """Open the Test Tools sub-menu."""
        self.test_tools_submenu_open = True
        self.test_tools_submenu_cursor = 0
        self.test_tools_submenu_items = self._build_test_tools_items()
        self.show_settings_overlay = True  # keep modal open

    def _set_tts_enabled(self, val):
        global _tts_enabled
        self.tts_enabled = (val == "ON")
        _tts_enabled = self.tts_enabled
        self._persist_setting("tts_enabled", self.tts_enabled)
        state = "enabled" if self.tts_enabled else "disabled"
        self._set_status(f"Text-to-speech {state}")

    def _set_tts_volume_gain(self, val):
        try:
            self.tts_volume_gain = float(val)
        except ValueError:
            self.tts_volume_gain = 1.0
        self._persist_setting("tts_volume_gain", self.tts_volume_gain)
        self._set_status(f"TTS Volume Gain set to {self.tts_volume_gain:.1f}x")


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

    def _action_test_speech(self):
        curr_voice = get_tts_voice_name()
        if curr_voice == "N/A":
             self._set_status("No voice selected.")
             return
        model_path = get_tts_voice_model()
        if not model_path.exists():
             self._set_status(f"Voice not downloaded! Use the option below.")
             return
        speak_text("Standard system read-back test active. Hello from the Voice Code BBS.")

    def _action_download_current_voice(self):

        curr_voice = get_tts_voice_name()
        if curr_voice == "N/A":
            self._set_status("No voice selected or available.")
            return

        self._set_status(f"Downloading {curr_voice}...")
        def _on_done(success, err_or_name):
            if success:
                self._set_status(f"Voice {err_or_name} downloaded.")
                speak_text(f"Voice {err_or_name} downloaded successfully.")
            else:
                self._set_status(f"Failed to download voice: {err_or_name}")
                speak_text(f"Voice download failed.")

        download_single_voice_model(curr_voice, on_done=_on_done)


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
        self.history_base = self.save_base / "history"
        self._persist_setting("prompt_library", new_path)
        self._scan_history_prompts()
        self.settings_editing_text = False
        self._set_status(f"Prompt library → {new_path}/voicecode/")

    def _cancel_text_edit(self):
        """Cancel inline text editing."""
        self.settings_editing_text = False

    def _commit_text_edit(self):
        """Dispatch text edit commit based on which setting is being edited."""
        item = self._settings_selectable_item()
        if not item:
            return
        if item["key"] == "prompt_library":
            self._commit_prompt_library()
        elif item["key"] == "working_dir":
            self._commit_working_dir()
        elif item["key"] == "documents_dir":
            self._commit_documents_dir()

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

    def _start_editing_documents_dir(self):
        """Enter inline text editing mode for the documents directory path."""
        self.settings_editing_text = True
        self.settings_edit_buffer = self.documents_dir
        self.settings_edit_cursor = len(self.settings_edit_buffer)
        self.show_settings_overlay = True

    def _commit_documents_dir(self):
        """Apply the edited documents directory path."""
        new_path = self.settings_edit_buffer.strip()
        self.documents_dir = new_path
        self._persist_setting("documents_dir", new_path)
        self.settings_editing_text = False
        if new_path:
            self._set_status(f"Documents directory → {new_path}")
        else:
            self._set_status("Documents directory cleared.")

    def _persist_setting(self, key, val):
        settings = _load_settings()
        settings[key] = val
        _save_settings(settings)

    def _settings_selectable_items(self):
        """Return list of selectable (non-section) settings items."""
        return [it for it in self.settings_items if it.get("type") != "section"]

    def _settings_selectable_item(self):
        """Return the currently selected settings item (skipping sections)."""
        selectable = self._settings_selectable_items()
        if 0 <= self.settings_cursor < len(selectable):
            return selectable[self.settings_cursor]
        return None

    def _settings_cursor_move(self, direction):
        """Move settings cursor, skipping section headers."""
        selectable = self._settings_selectable_items()
        if selectable:
            self.settings_cursor = (self.settings_cursor + direction) % len(selectable)

    def _settings_cycle(self, direction):
        """Cycle the current setting's value left (-1) or right (+1)."""
        item = self._settings_selectable_item()
        if not item or item.get("options") is None:
            return  # action item or section, no cycling
        options = item["options"]
        current = item["get"]()
        try:
            idx = options.index(current)
        except ValueError:
            idx = 0
        new_idx = (idx + direction) % len(options)
        item["set"](options[new_idx])

    def _test_tools_submenu_cycle(self, direction):
        """Cycle the current Test Tools sub-menu setting's value."""
        item = self.test_tools_submenu_items[self.test_tools_submenu_cursor]
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

    # ─── Prompt browser ────────────────────────────────────────────

    def _scan_history_prompts(self):
        self.history_prompts = sorted(self.history_base.glob("[0-9]*_*_prompt.md"))

    def _load_favorites_slots(self):
        """Load 10-slot favorites from settings."""
        saved = _load_settings()
        slots = saved.get("favorites_slots", [None] * 10)
        # Ensure exactly 10 slots
        self.favorites_slots = (slots + [None] * 10)[:10]
        # Validate paths still exist
        for i, p in enumerate(self.favorites_slots):
            if p and not Path(p).exists():
                self.favorites_slots[i] = None

    def _save_favorites_slots(self):
        """Persist 10-slot favorites to settings."""
        settings = _load_settings()
        settings["favorites_slots"] = self.favorites_slots
        _save_settings(settings)

    def _favorites_as_paths(self) -> list[Path]:
        """Return list of Path objects for occupied favorites slots, in slot order."""
        return [Path(p) for p in self.favorites_slots if p]

    def _favorites_slot_count(self) -> int:
        """Return number of occupied favorites slots."""
        return sum(1 for p in self.favorites_slots if p)

    # ─── Persistent dictation buffer ──────────────────────────────

    def _active_buffer_path(self) -> Path:
        return self.save_base / "active_buffer.json"

    def _persist_buffer(self):
        """Save current fragments to disk for crash recovery."""
        path = self._active_buffer_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = [{"text": f} for f in self.fragments]
            path.write_text(json.dumps(data), encoding="utf-8")
        except OSError:
            pass

    def _clear_buffer_file(self):
        """Remove the persisted buffer file."""
        try:
            self._active_buffer_path().unlink(missing_ok=True)
        except OSError:
            pass

    def _load_persisted_buffer(self, width: int):
        """Restore fragments from a previous session if present."""
        path = self._active_buffer_path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for entry in data:
                text = entry["text"]
                self.fragments.append(text)
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                self.dictation_pane.add_line(f"[{ts}] {text}", width)
        except (OSError, json.JSONDecodeError, KeyError):
            pass

    def _rebuild_dictation_pane(self):
        """Rebuild dictation pane lines from current fragments list."""
        left_width = self.stdscr.getmaxyx()[1] // 2
        self.dictation_pane.lines.clear()
        self.dictation_pane.scroll_offset = 0
        if self.fragments:
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            for frag in self.fragments:
                self.dictation_pane.add_line(f"[{ts}] {frag}", left_width)
        else:
            self._set_dictation_info(left_width)

    def _current_browser_list(self) -> list[Path]:
        """Return the prompt list for the current browser view."""
        if self.browser_view == "favorites":
            return self._favorites_as_paths()
        return self.history_prompts  # "active" view browses history via ←→

    def _load_browser_prompt(self, width: int):
        prompt_list = self._current_browser_list()

        if self.browser_index < 0 or self.browser_index >= len(prompt_list):
            self.browser_index = -1
            if self.browser_view == "favorites":
                self.prompt_pane.title = "FAVORITES [1-9, 0]"
                slots_info = self._format_favorites_slots()
                self.prompt_pane.set_text(
                    f"★ Favorites — {self._favorites_slot_count()}/10 slots used\n\n"
                    f"{slots_info}\n\n"
                    "Press 1-9/0 to quick-load\n"
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
        if self.browser_view == "favorites":
            # Find which slot this favorite is in
            slot_label = "★"
            for si, sp in enumerate(self.favorites_slots):
                if sp and Path(sp) == path:
                    key = str((si + 1) % 10)
                    slot_label = f"★ Slot {si + 1} [key {key}]"
                    break
            n = len(prompt_list)
            idx = self.browser_index + 1
            self.prompt_pane.title = f"[{idx}/{n}] {slot_label}"
        else:
            try:
                rel = path.relative_to(self.history_base)
            except ValueError:
                rel = path
            n = len(prompt_list)
            idx = self.browser_index + 1
            self.prompt_pane.title = f"[{idx}/{n}] HISTORY: {rel}"

        try:
            content = path.read_text()
        except Exception as e:
            content = f"[Error: {e}]"

        # For history entries, combine prompt and response with ASCII headers
        if self.browser_view != "favorites":
            response_path = Path(str(path).replace("_prompt.md", "_response.md"))
            divider_w = max(1, width - 4)
            combined = f"{'=' * divider_w}\n  PROMPT\n{'=' * divider_w}\n\n{content}"
            if response_path.exists():
                try:
                    response_content = response_path.read_text()
                except Exception as e:
                    response_content = f"[Error: {e}]"
                combined += f"\n\n{'-' * divider_w}\n  RESPONSE\n{'-' * divider_w}\n\n{response_content}"
            else:
                combined += f"\n\n{'-' * divider_w}\n  RESPONSE\n{'-' * divider_w}\n\n(no response recorded)"
            self.prompt_pane.set_text(combined, width)
        else:
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
        _suppress_stderr()   # silence PortAudio C-level noise while TUI is active
        self._init_colors()
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.timeout(16)  # ~60fps for smooth animations

        # Enable bracketed paste mode so pasted text arrives as a single
        # delimited block instead of individual keystrokes.
        sys.stdout.write("\x1b[?2004h")
        sys.stdout.flush()

        self._draw_loading("Loading Silero VAD model...")
        get_vad_model()
        self._draw_loading("Loading Whisper model...")
        get_whisper_model(self.whisper_model)
        self._draw_loading("Ready!")
        time.sleep(2.0)

        self._load_browser_prompt(80)
        self._set_dictation_info(80)
        self._load_persisted_buffer(80)
        self._set_agent_welcome(40)

        try:
            while self.running:
                self._process_ui_queue()
                self._process_typewriter()
                self._draw()
                self._handle_input()
        finally:
            # Disable bracketed paste mode before exiting curses
            sys.stdout.write("\x1b[?2004l")
            sys.stdout.flush()

    def _init_colors(self):
        curses.start_color()
        curses.use_default_colors()

        # Retro deep blue for background (fallback if not 256 color)
        bg_blue = 18 if curses.COLORS >= 256 else curses.COLOR_BLUE

        curses.init_pair(self.CP_HEADER, curses.COLOR_YELLOW, bg_blue)
        curses.init_pair(self.CP_PROMPT, curses.COLOR_WHITE, -1)
        curses.init_pair(self.CP_DICTATION, curses.COLOR_CYAN, -1)
        curses.init_pair(self.CP_STATUS, curses.COLOR_WHITE, bg_blue)

        curses.init_pair(self.CP_HELP, curses.COLOR_YELLOW, bg_blue)
        curses.init_pair(self.CP_RECORDING, curses.COLOR_WHITE, curses.COLOR_RED)
        curses.init_pair(self.CP_BANNER, curses.COLOR_CYAN, -1)
        curses.init_pair(self.CP_ACCENT, curses.COLOR_MAGENTA, -1)
        curses.init_pair(self.CP_AGENT, curses.COLOR_GREEN, -1)
        curses.init_pair(self.CP_XFER, curses.COLOR_YELLOW, -1)
        curses.init_pair(self.CP_VOICE, curses.COLOR_YELLOW, -1)
        curses.init_pair(self.CP_CTX_GREEN, curses.COLOR_GREEN, -1)
        curses.init_pair(self.CP_CTX_YELLOW, curses.COLOR_YELLOW, -1)
        curses.init_pair(self.CP_CTX_RED, curses.COLOR_RED, -1)
        curses.init_pair(self.CP_XTREE_BG, curses.COLOR_BLACK, curses.COLOR_YELLOW)
        curses.init_pair(self.CP_XTREE_SEL, curses.COLOR_YELLOW, bg_blue)

        curses.init_pair(self.CP_XTREE_BORDER, curses.COLOR_WHITE, curses.COLOR_YELLOW)
        curses.init_pair(self.CP_SECT_RED, curses.COLOR_RED, bg_blue)
        curses.init_pair(self.CP_SUBMENU, curses.COLOR_CYAN, bg_blue)
        curses.init_pair(self.CP_SETTINGS_TITLE, curses.COLOR_BLACK, curses.COLOR_YELLOW)
        curses.init_pair(self.CP_FAV_EMPTY, 8, -1)  # gray (bright black)
        curses.init_pair(self.CP_FAV_FILLED, curses.COLOR_RED, -1)
        if TTS_AVAILABLE:
            curses.init_pair(self.CP_TTS, curses.COLOR_WHITE, -1)
        else:
            curses.init_pair(self.CP_TTS, curses.COLOR_GREEN, -1)


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
        header = f" VOICECODE BBS v{__version__}"
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
        if self.browser_index >= 0:
            bar_label = "Favorites" if self.browser_view == "favorites" else "History"
            browse_info = f"{bar_label}: {self.browser_index + 1}/{len(prompt_list)}"
        else:
            browse_info = f"Session v{self.prompt_version}"
        node_info = (f" {browse_info} │ "
                     f"Favs: {self._favorites_slot_count()}/10 │ "
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

        # ── Favorites indicator on left border of Prompt Browser ──
        fav_labels = ["F", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]
        fav_start_y = content_y + 1  # first content row inside pane
        for fi, flabel in enumerate(fav_labels):
            fy = fav_start_y + fi
            if fy >= content_y + prompt_height - 1:  # don't overwrite bottom border
                break
            if fi == 0:
                # "F" label in the pane's border color
                attr = curses.color_pair(self.prompt_pane.color_pair) | curses.A_BOLD
            else:
                slot_idx = fi - 1  # slots 0-9
                has_data = self.favorites_slots[slot_idx] is not None
                if has_data:
                    attr = curses.color_pair(self.CP_FAV_FILLED) | curses.A_BOLD
                else:
                    attr = curses.color_pair(self.CP_FAV_EMPTY)
            try:
                self.stdscr.addstr(fy, 0, flabel, attr)
            except curses.error:
                pass

        # ── Prompt pane bottom border: browse/view hints ──
        prompt_bottom_y = content_y + prompt_height - 1
        hint_attr = curses.color_pair(self.prompt_pane.color_pair) | curses.A_BOLD
        home_hint = " [Home]Current "
        browse_hint = " [←→]Browse [↑↓]View "
        bh_x = left_width - len(browse_hint) - 1
        try:
            if bh_x > 1:
                self.stdscr.addstr(prompt_bottom_y, bh_x, browse_hint, hint_attr)
            if len(home_hint) + 1 < bh_x:
                self.stdscr.addstr(prompt_bottom_y, 1, home_hint, hint_attr)
        except curses.error:
            pass

        # Bottom-left: Dictation buffer
        self.dictation_pane.draw(self.stdscr, content_y + prompt_height, 0,
                                 dictation_height, left_width)

        # ── Typing mode input line (overlays last content line of dictation pane) ──
        if self.typing_mode:
            type_y = content_y + prompt_height + dictation_height - 2  # just above bottom border
            type_x = 1
            type_w = left_width - 2
            if type_w > 4 and type_y > content_y + prompt_height:
                prefix = "▸ "
                avail = type_w - len(prefix)
                buf = self.typing_buffer
                cur = self.typing_cursor
                # Scroll the buffer if cursor is past visible area
                scroll = max(0, cur - avail + 1)
                visible = buf[scroll:scroll + avail]
                cursor_pos_in_vis = cur - scroll
                padded = prefix + visible + " " * max(0, avail - len(visible))
                entry_attr = curses.color_pair(self.CP_VOICE) | curses.A_BOLD
                try:
                    self.stdscr.addnstr(type_y, type_x, padded, type_w, entry_attr)
                    # Draw cursor
                    cx = type_x + len(prefix) + cursor_pos_in_vis
                    if cx < type_x + type_w:
                        ch_under = buf[cur] if cur < len(buf) else " "
                        self.stdscr.addstr(type_y, cx, ch_under,
                                           entry_attr | curses.A_REVERSE)
                except curses.error:
                    pass

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

        # Session info tag (includes active provider name)
        provider_tag = self.ai_provider.name
        if self.session_id:
            sess_label = f" {provider_tag}: {self.session_turns} turn{'s' if self.session_turns != 1 else ''} "
        else:
            sess_label = f" {provider_tag} (no session) "
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

        # ── Arrow key control indicator (yellow, top-right of active pane) ──
        arrow_label = " [←→] "
        arrow_attr = curses.color_pair(self.CP_XFER) | curses.A_BOLD
        if self.show_folder_slug:
            # Shortcuts browser open: agent terminal has arrow key control
            arrow_x = left_width + right_width - len(arrow_label) - 1
            try:
                self.stdscr.addstr(content_y, arrow_x, arrow_label, arrow_attr)
            except curses.error:
                pass
        else:
            # Normal mode: prompt browser has arrow key control
            arrow_x = left_width - len(arrow_label) - 1
            if arrow_x > 4:
                try:
                    self.stdscr.addstr(content_y, arrow_x, arrow_label, arrow_attr)
                except curses.error:
                    pass

        # ── Favorites hint on prompt pane top border (drawn after arrow to take priority) ──
        if self.browser_view == "favorites" and self.browser_index >= 0:
            fav_hint = " [F] Remove "
            fav_x = left_width - len(fav_hint) - 1
            if fav_x > 4:
                try:
                    self.stdscr.addstr(content_y, fav_x, fav_hint,
                                       curses.color_pair(self.CP_RECORDING) | curses.A_BOLD)
                except curses.error:
                    pass
        elif self.browser_index >= 0 or self.current_prompt or self.executed_prompt_text:
            fav_hint = " [F] ★ Fav slot "
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
        if self.typing_mode:
            help_text = " TYPING ▸ [Enter] Submit  [ESC] Cancel  — Type text directly into dictation buffer"
            self._draw_bar(help_y, help_text, self.CP_VOICE)
        elif self.recording:
            help_text = " [SPC] Stop recording"
            self._draw_bar(help_y, help_text, self.CP_HELP)
        elif self.confirming_new:
            help_text = " ██ UNSAVED PROMPT — [Y] Save first  [N] Discard  [other] Cancel ██"
            self._draw_bar(help_y, help_text, self.CP_RECORDING)
        elif self.confirming_edit_historical:
            help_text = " ██ EDIT HISTORICAL PROMPT? — [Y] Copy as new working prompt  [other] Cancel ██"
            self._draw_bar(help_y, help_text, self.CP_RECORDING)
        elif self.choosing_fav_slot:
            help_text = " ██ CHOOSE FAVORITES SLOT — [1-9, 0] to assign  [ESC/other] Cancel ██"
            self._draw_bar(help_y, help_text, self.CP_RECORDING)
        elif self.confirming_fav_overwrite:
            slot_num = self._pending_fav_slot + 1
            help_text = f" ██ SLOT {slot_num} OCCUPIED — [Y] Overwrite  [other] Cancel ██"
            self._draw_bar(help_y, help_text, self.CP_RECORDING)
        elif self.agent_state in (AgentState.DOWNLOADING, AgentState.RECEIVING):
            help_text = " ◌ Agent working... [K] to kill"
            self._draw_bar(help_y, help_text, self.CP_STATUS)
        else:
            voice_label = "[V]oice" if TTS_AVAILABLE else ""
            keys = " [Q]uit [X]Restart | [N]ew [U]ndo [C]lear [K]ill [W]NewSess [Tab]Shortcuts"
            self._draw_bar(help_y, keys, self.CP_HELP)
            # Draw [V]oice in red, right-justified
            w = self.stdscr.getmaxyx()[1]
            vx = w - len(voice_label) - 1
            if TTS_AVAILABLE and vx > len(keys):
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
            f"  V O I C E C O D E   B B S   v{__version__}",
            "  Voice-Driven Prompt Workshop",
            "",
            "  ── How It Works ──────────────────",
            "  Dictate speech fragments, refine",
            "  them into polished prompts with AI,",
            "  then execute via AI agent.",
            "",
            "  ── Keyboard Controls ─────────────",
            "  SPACE  Toggle recording on/off",
            "  R      Refine fragments → prompt",
            "  E      Execute current prompt",
            "  D      Direct execute (skip refine)",
            "  F      Assign to favorites slot",
            "  1-0    Quick-load favorites 1-10",
            "  N      New prompt",
            "  U      Undo last dictation entry",
            "  C      Clear dictation buffer",
            "  K      Kill running agent",
            "  W      New session (clear context)",
            "  ←/→    Browse within current view",
            "  ↑/↓    Cycle active/favorites/history",
            "  Home   Return to current prompt",
            "  Enter  Type text into dictation",
            "  Tab    Shortcuts browser",
            "  PgUp/Dn  Scroll agent pane",
            "  [/]    Cycle TTS voice",
            "  P      Replay last TTS summary",
            "  O      Options / Settings",
            "  H      This help screen",
            "  X      Restart application",
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
            f"          B  B  S   v{__version__}",
            "",
            "  ── About ─────────────────────",
            "  Voice-driven prompt workshop",
            "  for interacting with AI agents.",
            "  Dictate, refine, and execute",
            "  prompts — all by voice.",
            "",
            "  ── Author ────────────────────",
            "  Charles Schiele",
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
        body_attr = curses.color_pair(self.CP_HELP) | curses.A_BOLD
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
                    line = f"  > {label}  "
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
        if self.voice_submenu_open:
            render_items = self.voice_submenu_items
            render_cursor = self.voice_submenu_cursor
            render_title = " VOICE SETTINGS "
            render_footer = " ↑↓ Navigate  ←→ Change  Esc Close "
        elif self.tts_submenu_open:
            render_items = self.tts_submenu_items
            render_cursor = self.tts_submenu_cursor
            render_title = " TEXT-TO-SPEECH SETTINGS "
            render_footer = " ↑↓ Navigate  ←→ Change  Enter Action  Esc Close "
        elif self.test_tools_submenu_open:
            render_items = self.test_tools_submenu_items
            render_cursor = self.test_tools_submenu_cursor
            render_title = " TEST TOOLS "
            render_footer = " ↑↓ Navigate  ←→ Change  Enter Action  Esc Close "
        elif self.ai_models_submenu_open:
            render_items = self.ai_models_submenu_items
            render_cursor = self.ai_models_submenu_cursor
            render_title = " AI MODELS "
            render_footer = " ↑↓ Navigate  ←→ Change  Esc Close "
        else:
            render_items = self.settings_items
            render_cursor = self.settings_cursor
            render_title = " SETTINGS "
            render_footer = " ↑↓ Navigate  ←→ Change  Enter Action  O/Esc Close "

        overlay_w = min(72, w - 6)
        # Count rows: sections take 1 row, regular items take 3 rows
        item_rows = sum(1 if it.get("type") == "section" else 3 for it in render_items)
        overlay_h = min(4 + item_rows + 3, h - 4)
        if overlay_w < 44 or overlay_h < 12:
            return

        start_y = max(1, (h - overlay_h) // 2)
        start_x = max(2, (w - overlay_w) // 2)

        border_attr = curses.color_pair(self.CP_HEADER) | curses.A_BOLD
        body_attr = curses.color_pair(self.CP_HELP) | curses.A_BOLD
        accent_attr = curses.color_pair(self.CP_HEADER) | curses.A_BOLD
        sel_attr = curses.color_pair(self.CP_RECORDING) | curses.A_BOLD
        val_attr = curses.color_pair(self.CP_AGENT) | curses.A_BOLD


        inner_w = overlay_w - 2

        try:
            # Top border
            top = "╔" + "═" * inner_w + "╗"
            self.stdscr.addnstr(start_y, start_x, top, overlay_w, border_attr)

            # Title bar (yellow background)
            title_attr = curses.color_pair(self.CP_SETTINGS_TITLE) | curses.A_BOLD
            title_line = "║" + render_title.center(inner_w) + "║"
            self.stdscr.addnstr(start_y + 1, start_x, title_line, overlay_w, title_attr)

            # Title separator
            sep = "╠" + "═" * inner_w + "╣"
            self.stdscr.addnstr(start_y + 2, start_x, sep, overlay_w, border_attr)

            sect_red_attr = curses.color_pair(self.CP_SECT_RED) | curses.A_BOLD
            sect_yellow_attr = curses.color_pair(self.CP_HEADER) | curses.A_BOLD
            submenu_attr = curses.color_pair(self.CP_SUBMENU) | curses.A_BOLD

            row = start_y + 3
            selectable_idx = -1  # track index among selectable items
            for i, item in enumerate(render_items):
                if row + 1 >= start_y + overlay_h - 1:
                    break

                # Section header — not selectable
                if item.get("type") == "section":
                    s_attr = sect_red_attr if item.get("style") == "red" else sect_yellow_attr
                    sect_label = f" ── {item['label']} "
                    sect_padded = sect_label + "─" * max(0, inner_w - len(sect_label))
                    sect_line = "║" + sect_padded[:inner_w] + "║"
                    self.stdscr.addnstr(row, start_x, sect_line, overlay_w, s_attr)
                    row += 1
                    continue

                selectable_idx += 1
                if row + 2 >= start_y + overlay_h - 1:
                    break

                is_selected = (selectable_idx == render_cursor)
                is_action = item.get("options") is None
                is_submenu = item.get("submenu", False)
                line_attr = sel_attr if is_selected else (submenu_attr if is_submenu else body_attr)

                # Setting label line
                cursor = ">" if is_selected else " "
                if is_submenu:
                    label = f" {cursor} {item['label']}  ▶"
                else:
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
                    # Build value display with < > arrows when selected
                    if is_selected:
                        val_display = f"< {current_val} >"
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
        """Build three category lists: shortcuts, project folders, documents."""
        self._shortcut_strings = _load_shortcuts()
        # Category 0: Shortcuts
        self._browser_cat_lists[0] = list(self._shortcut_strings)

        # Category 1: Project Folders
        dirs: list[str] = []
        root = Path(self.working_dir).expanduser() if self.working_dir else None
        if root and root.is_dir():
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
        self._browser_cat_lists[1] = dirs

        # Category 2: Documents (.md files recursive)
        docs: list[str] = []
        doc_root = Path(self.documents_dir).expanduser() if self.documents_dir else None
        if doc_root and doc_root.is_dir():
            try:
                md_files = [f for f in doc_root.rglob("*.md")
                            if not any(p.startswith(".") for p in f.relative_to(doc_root).parts)]
                for md_file in sorted(md_files, key=lambda f: f.stat().st_mtime, reverse=True):
                    docs.append(str(md_file.relative_to(doc_root)))
            except (PermissionError, OSError):
                pass
        self._browser_cat_lists[2] = docs

        # Flat list is the active category's list (for cursor/scroll compat)
        self.folder_slug_list = self._browser_cat_lists[self._browser_category]

    def _draw_folder_slug_overlay(self):
        """Draw the categorised browser overlay on the agent pane."""
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
        if overlay_w < 20 or overlay_h < 7:
            return

        bg_attr = curses.color_pair(self.CP_XTREE_BG)
        sel_attr = curses.color_pair(self.CP_XTREE_SEL) | curses.A_BOLD
        border_attr = curses.color_pair(self.CP_XTREE_BORDER) | curses.A_BOLD

        inner_w = overlay_w - 2
        inner_h = overlay_h - 6  # border + subtitle + tabs + separator + footer + border

        try:
            # Top border
            top = "╔" + "═" * inner_w + "╗"
            self.stdscr.addnstr(overlay_y, overlay_x, top, overlay_w, border_attr)

            # Subtitle
            subtitle = ' <-- "String Injector"! '
            subtitle_line = "║" + subtitle.center(inner_w) + "║"
            self.stdscr.addnstr(overlay_y + 1, overlay_x, subtitle_line, overlay_w, border_attr)

            # Category tabs row
            cat = self._browser_category
            tabs = ""
            for i, name in enumerate(self._browser_categories):
                count = len(self._browser_cat_lists[i])
                label = f" {name} ({count}) "
                if i == cat:
                    label = f"[{label}]"
                else:
                    label = f" {label} "
                tabs += label
            tabs_padded = tabs.center(inner_w)[:inner_w]
            tabs_line = "║" + tabs_padded + "║"
            # Highlight active tab
            self.stdscr.addnstr(overlay_y + 2, overlay_x, tabs_line, overlay_w, border_attr)

            # Tab separator
            sep = "╠" + "═" * inner_w + "╣"
            self.stdscr.addnstr(overlay_y + 3, overlay_x, sep, overlay_w, border_attr)

            # Scrolling: keep cursor visible
            if self.folder_slug_cursor < self.folder_slug_scroll:
                self.folder_slug_scroll = self.folder_slug_cursor
            elif self.folder_slug_cursor >= self.folder_slug_scroll + inner_h:
                self.folder_slug_scroll = self.folder_slug_cursor - inner_h + 1

            # Icon per category
            cat_icons = {0: "⚡", 1: "📁", 2: "📄"}
            cat_icons_sel = {0: "⚡", 1: "📂", 2: "📄"}
            icon_base = cat_icons.get(cat, "·")
            icon_sel = cat_icons_sel.get(cat, "·")

            # List rows
            # Show hint when Documents tab is active but not configured
            show_not_configured = (cat == 2 and not self.documents_dir
                                   and not self.folder_slug_list)
            if show_not_configured:
                hint_lines = [
                    "",
                    "Documents directory not configured.",
                    "",
                    "Press O to open Options and set",
                    "the Documents Directory path.",
                ]
                hint_attr = curses.color_pair(self.CP_XTREE_BORDER)
                for i in range(inner_h):
                    row_y = overlay_y + 4 + i
                    if i < len(hint_lines):
                        text = hint_lines[i].center(inner_w)[:inner_w]
                    else:
                        text = " " * inner_w
                    line = "║" + text + "║"
                    self.stdscr.addnstr(row_y, overlay_x, line, overlay_w,
                                        hint_attr if i < len(hint_lines) else bg_attr)
            else:
                for i in range(inner_h):
                    row_y = overlay_y + 4 + i
                    idx = self.folder_slug_scroll + i
                    if idx < len(self.folder_slug_list):
                        entry = self.folder_slug_list[idx]
                        is_sel = (idx == self.folder_slug_cursor)
                        icon = icon_sel if is_sel else icon_base
                        text = f" {icon} {entry}"
                        # +1 for double-width emoji
                        display_w = len(text) + 1
                        padded = text[:inner_w] + " " * max(0, inner_w - display_w)
                        line = "║" + padded + "║"
                        attr = sel_attr if is_sel else bg_attr
                        self.stdscr.addnstr(row_y, overlay_x, line, overlay_w, attr)
                    else:
                        blank = "║" + " " * inner_w + "║"
                        self.stdscr.addnstr(row_y, overlay_x, blank, overlay_w, bg_attr)

            # Footer
            edit_hint = "  E Edit" if cat == 0 else ""
            footer_text = f" ←→ Tab  ↑↓ Select  Enter Insert{edit_hint}  Tab/Esc Close "
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
        inner_h = overlay_h - 5  # borders + title + separator + footer

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
                    cursor = ">" if is_sel else " "

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
                    cursor = ">" if is_sel else " "
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

    # ─── Bracketed paste handling ────────────────────────────────

    def _read_paste_content(self) -> str:
        """Read characters until the bracketed-paste end sequence ESC[201~."""
        buf: list[int] = []
        # Switch to short blocking reads so we drain the paste quickly
        self.stdscr.timeout(50)
        max_chars = 10_000  # safety cap
        try:
            while len(buf) < max_chars:
                c = self.stdscr.getch()
                if c == -1:
                    # Small gap — if we already have content, assume paste ended
                    # without a proper close bracket (unsupported terminal)
                    if buf:
                        break
                    continue
                buf.append(c)
                # Check for paste-end: ESC [ 2 0 1 ~ (27 91 50 48 49 126)
                if (len(buf) >= 6
                        and buf[-6:] == [27, 91, 50, 48, 49, 126]):
                    buf = buf[:-6]
                    break
        finally:
            self.stdscr.timeout(16)  # restore normal timeout
        return "".join(chr(c) for c in buf if 0 < c < 0x110000)

    def _inject_paste(self, text: str):
        """Inject pasted text into the active text field, dictation buffer, or recording stream."""
        text = text.strip()
        if not text:
            return

        # If a modal text field is active, insert there instead of dictation
        if self.shortcut_editing_text:
            # Collapse to single line for text field
            flat = " ".join(text.splitlines())
            b = self.shortcut_edit_buffer
            c = self.shortcut_edit_cursor_pos
            self.shortcut_edit_buffer = b[:c] + flat + b[c:]
            self.shortcut_edit_cursor_pos += len(flat)
            self._set_status("Pasted into editor")
            return
        if self.typing_mode:
            flat = " ".join(text.splitlines())
            b = self.typing_buffer
            c = self.typing_cursor
            self.typing_buffer = b[:c] + flat + b[c:]
            self.typing_cursor += len(flat)
            self._set_status("Pasted into text entry")
            return
        if self.settings_editing_text:
            flat = " ".join(text.splitlines())
            b = self.settings_edit_buffer
            c = self.settings_edit_cursor
            self.settings_edit_buffer = b[:c] + flat + b[c:]
            self.settings_edit_cursor += len(flat)
            self._set_status("Pasted into editor")
            return

        # Collapse to single line for dictation (newlines → spaces)
        text = " ".join(text.splitlines())

        truncated = text[:40] + ("…" if len(text) > 40 else "")
        if self.recording:
            # Same injection path as shortcut/folder slug injection
            with self.audio_lock:
                audio_secs = (sum(len(f) for f in self.audio_frames)
                              / SAMPLE_RATE) if self.audio_frames else 0.0
            self._recording_injections.append((audio_secs, text))
            preview = self._live_preview_text
            combined = f"{preview} {text}" if preview else text
            self.ui_queue.put(("live_preview", combined))
            self._set_status(f"Pasted: {truncated}")
        else:
            left_width = self.stdscr.getmaxyx()[1] * 2 // 5
            self.fragments.append(text)
            self._persist_buffer()
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            self.dictation_pane.add_line(f"[{ts}] {text}", left_width)
            self._set_status(f"Pasted: {truncated}")

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
                    self.tts_submenu_open = False
                    self.test_tools_submenu_open = False
                    self.voice_submenu_open = False
                    self.ai_models_submenu_open = False
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
            elif ch == curses.KEY_LEFT:
                # Switch to previous category
                self._browser_category = (self._browser_category - 1) % len(self._browser_categories)
                self.folder_slug_list = self._browser_cat_lists[self._browser_category]
                self.folder_slug_cursor = 0
                self.folder_slug_scroll = 0
                return
            elif ch == curses.KEY_RIGHT:
                # Switch to next category
                self._browser_category = (self._browser_category + 1) % len(self._browser_categories)
                self.folder_slug_list = self._browser_cat_lists[self._browser_category]
                self.folder_slug_cursor = 0
                self.folder_slug_scroll = 0
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
                        self._persist_buffer()
                        ts = datetime.datetime.now().strftime("%H:%M:%S")
                        self.dictation_pane.add_line(f"[{ts}] {slug}", left_width)
                        self._set_status(f"Inserted: {slug}")
                return
            elif ch in (ord("e"), ord("E")):
                # Only allow editing in the Shortcuts category
                if self._browser_category == 0:
                    self.show_folder_slug = False
                    self._open_shortcut_editor()
                return
            elif ch == 9:  # Tab closes shortcuts browser
                self.show_folder_slug = False
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
                    next_ch = self.stdscr.getch()
                    if next_ch == 91:  # '[' — CSI sequence
                        csi = []
                        while True:
                            c = self.stdscr.getch()
                            if c == -1:
                                break
                            csi.append(c)
                            if 64 <= c <= 126:
                                break
                        if csi == [50, 48, 48, 126]:  # "200~" — bracketed paste
                            pasted = self._read_paste_content()
                            self._inject_paste(pasted)
                        # else: ignore unknown CSI sequence
                    else:
                        # Pure ESC — cancel editing
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
                self._scan_folder_slugs()  # refresh to reflect edits
                self.show_folder_slug = True  # return to folder menu
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
                    next_ch = self.stdscr.getch()
                    if next_ch == 91:  # '[' — CSI sequence
                        csi = []
                        while True:
                            c = self.stdscr.getch()
                            if c == -1:
                                break
                            csi.append(c)
                            if 64 <= c <= 126:
                                break
                        if csi == [50, 48, 48, 126]:  # "200~" — bracketed paste
                            pasted = self._read_paste_content()
                            self._inject_paste(pasted)
                        # else: ignore unknown CSI sequence
                    else:
                        # Pure ESC — cancel editing
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

            # Voice sub-menu navigation
            if self.voice_submenu_open:
                if ch in (27,):
                    self.voice_submenu_open = False
                    self.stdscr.nodelay(True)
                    self.stdscr.getch()
                elif ch in (ord("q"), ord("Q")):
                    self.voice_submenu_open = False
                elif ch == curses.KEY_UP:
                    self.voice_submenu_cursor = (self.voice_submenu_cursor - 1) % len(self.voice_submenu_items)
                elif ch == curses.KEY_DOWN:
                    self.voice_submenu_cursor = (self.voice_submenu_cursor + 1) % len(self.voice_submenu_items)
                elif ch == curses.KEY_LEFT:
                    self._voice_submenu_cycle(-1)
                elif ch == curses.KEY_RIGHT:
                    self._voice_submenu_cycle(1)
                return

            # TTS sub-menu navigation
            if self.tts_submenu_open:
                if ch in (27,):
                    self.tts_submenu_open = False
                    self.stdscr.nodelay(True)
                    self.stdscr.getch()
                elif ch in (ord("q"), ord("Q")):
                    self.tts_submenu_open = False
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
                        item["action"]()
                return

            # AI Models sub-menu navigation
            if self.ai_models_submenu_open:
                if ch in (27,):
                    self.ai_models_submenu_open = False
                    self.stdscr.nodelay(True)
                    self.stdscr.getch()
                elif ch in (ord("q"), ord("Q")):
                    self.ai_models_submenu_open = False
                elif ch == curses.KEY_UP:
                    selectable = [i for i, it in enumerate(self.ai_models_submenu_items) if it.get("options") is not None]
                    if selectable:
                        cur_pos = selectable.index(self.ai_models_submenu_cursor) if self.ai_models_submenu_cursor in selectable else 0
                        self.ai_models_submenu_cursor = selectable[(cur_pos - 1) % len(selectable)]
                    elif self.ai_models_submenu_items:
                        self.ai_models_submenu_cursor = (self.ai_models_submenu_cursor - 1) % len(self.ai_models_submenu_items)
                elif ch == curses.KEY_DOWN:
                    selectable = [i for i, it in enumerate(self.ai_models_submenu_items) if it.get("options") is not None]
                    if selectable:
                        cur_pos = selectable.index(self.ai_models_submenu_cursor) if self.ai_models_submenu_cursor in selectable else 0
                        self.ai_models_submenu_cursor = selectable[(cur_pos + 1) % len(selectable)]
                    elif self.ai_models_submenu_items:
                        self.ai_models_submenu_cursor = (self.ai_models_submenu_cursor + 1) % len(self.ai_models_submenu_items)
                elif ch == curses.KEY_LEFT:
                    self._ai_models_submenu_cycle(-1)
                elif ch == curses.KEY_RIGHT:
                    self._ai_models_submenu_cycle(1)
                return

            # Test Tools sub-menu navigation
            if self.test_tools_submenu_open:
                if ch in (27,):
                    self.test_tools_submenu_open = False
                    self.stdscr.nodelay(True)
                    self.stdscr.getch()
                elif ch in (ord("q"), ord("Q")):
                    self.test_tools_submenu_open = False
                elif ch == curses.KEY_UP:
                    self.test_tools_submenu_cursor = (self.test_tools_submenu_cursor - 1) % len(self.test_tools_submenu_items)
                elif ch == curses.KEY_DOWN:
                    self.test_tools_submenu_cursor = (self.test_tools_submenu_cursor + 1) % len(self.test_tools_submenu_items)
                elif ch == curses.KEY_LEFT:
                    self._test_tools_submenu_cycle(-1)
                elif ch == curses.KEY_RIGHT:
                    self._test_tools_submenu_cycle(1)
                elif ch in (10, 13, curses.KEY_ENTER):
                    item = self.test_tools_submenu_items[self.test_tools_submenu_cursor]
                    if item.get("action"):
                        item["action"]()
                return

            if ch in (ord("o"), ord("O"), ord("q"), ord("Q"), 27):
                self.show_settings_overlay = False
                self.tts_submenu_open = False
                self.test_tools_submenu_open = False
                self.voice_submenu_open = False
                self.ai_models_submenu_open = False
                if ch == 27:
                    self.stdscr.nodelay(True)
                    self.stdscr.getch()
            elif ch == curses.KEY_UP:
                self._settings_cursor_move(-1)
            elif ch == curses.KEY_DOWN:
                self._settings_cursor_move(1)
            elif ch == curses.KEY_LEFT:
                self._settings_cycle(-1)
            elif ch == curses.KEY_RIGHT:
                self._settings_cycle(1)
            elif ch in (10, 13, curses.KEY_ENTER):
                item = self._settings_selectable_item()
                if item and item.get("action"):
                    if item.get("editable"):
                        item["action"]()  # keep modal open for editing
                    elif item.get("submenu"):
                        item["action"]()  # submenu openers keep modal open
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

        # Handle confirmation dialog for editing a historical prompt
        if self.confirming_edit_historical:
            if ch == ord("y") or ch == ord("Y"):
                self.confirming_edit_historical = False
                self._copy_historical_to_current()
            else:
                # Any other key cancels
                self.confirming_edit_historical = False
                self._set_status("Edit cancelled.")
            return

        # Handle favorites slot selection
        if self.choosing_fav_slot:
            self.choosing_fav_slot = False
            slot_idx = self._key_to_fav_slot(ch)
            if slot_idx >= 0:
                self._assign_to_fav_slot(slot_idx)
            else:
                self._set_status("Favorites assignment cancelled.")
            return

        # Handle favorites overwrite confirmation
        if self.confirming_fav_overwrite:
            self.confirming_fav_overwrite = False
            if ch == ord("y") or ch == ord("Y"):
                self._do_assign_fav_slot(self._pending_fav_slot)
            else:
                self._pending_fav_slot = -1
                self._set_status("Favorites assignment cancelled.")
            return

        # Handle direct text entry mode in dictation buffer
        if self.typing_mode:
            if ch in (10, 13, curses.KEY_ENTER):
                # Submit the typed text as a fragment
                text = self.typing_buffer.strip()
                if text:
                    left_width = self.stdscr.getmaxyx()[1] // 2
                    self.fragments.append(text)
                    self._persist_buffer()
                    ts = datetime.datetime.now().strftime("%H:%M:%S")
                    self.dictation_pane.add_line(f"[{ts}] {text}", left_width)
                    self._set_status("Text entry added.")
                else:
                    self._set_status("Empty entry discarded.")
                self.typing_mode = False
                self.typing_buffer = ""
                self.typing_cursor = 0
            elif ch == 27:
                # ESC cancels typing mode
                self.typing_mode = False
                self.typing_buffer = ""
                self.typing_cursor = 0
                self._set_status("Text entry cancelled.")
                self.stdscr.nodelay(True)
                next_ch = self.stdscr.getch()
                if next_ch == 91:  # '[' — CSI sequence (could be paste)
                    csi = []
                    while True:
                        c = self.stdscr.getch()
                        if c == -1:
                            break
                        csi.append(c)
                        if 64 <= c <= 126:
                            break
                    if csi == [50, 48, 48, 126]:  # bracketed paste
                        pasted = self._read_paste_content()
                        # Re-enter typing mode with pasted content
                        self.typing_mode = True
                        self.typing_buffer = " ".join(pasted.strip().splitlines())
                        self.typing_cursor = len(self.typing_buffer)
            elif ch == curses.KEY_LEFT:
                if self.typing_cursor > 0:
                    self.typing_cursor -= 1
            elif ch == curses.KEY_RIGHT:
                if self.typing_cursor < len(self.typing_buffer):
                    self.typing_cursor += 1
            elif ch == curses.KEY_HOME:
                self.typing_cursor = 0
            elif ch == curses.KEY_END:
                self.typing_cursor = len(self.typing_buffer)
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                if self.typing_cursor > 0:
                    b = self.typing_buffer
                    self.typing_buffer = b[:self.typing_cursor - 1] + b[self.typing_cursor:]
                    self.typing_cursor -= 1
            elif ch in (curses.KEY_DC, 330):
                if self.typing_cursor < len(self.typing_buffer):
                    b = self.typing_buffer
                    self.typing_buffer = b[:self.typing_cursor] + b[self.typing_cursor + 1:]
            elif 32 <= ch <= 126:
                b = self.typing_buffer
                self.typing_buffer = b[:self.typing_cursor] + chr(ch) + b[self.typing_cursor:]
                self.typing_cursor += 1
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
                if self.browser_index >= 0:
                    self._confirm_edit_historical()
                else:
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
                    self._add_to_favorites(None)

        elif ch == ord("e") or ch == ord("E"):
            if self.agent_state in (AgentState.IDLE, AgentState.DONE):
                self._execute_prompt()

        elif ch == ord("n") or ch == ord("N"):
            if not self.refining and not self.recording:
                self._new_prompt()

        elif ch == ord("u") or ch == ord("U"):
            if self.fragments:
                removed = self.fragments.pop()
                self._persist_buffer()
                self._rebuild_dictation_pane()
                preview = removed[:40] + "…" if len(removed) > 40 else removed
                self._set_status(f"Undid: {preview}")
            else:
                self._set_status("Nothing to undo.")

        elif ch == ord("c") or ch == ord("C"):
            self.fragments.clear()
            self._clear_buffer_file()
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
            if self.browser_view == "active":
                self._scan_history_prompts()
            prompt_list = self._current_browser_list()
            if not prompt_list:
                view_name = "favorite" if self.browser_view == "favorites" else "history"
                self._set_status(f"No {view_name} prompts to browse.")
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
            # Toggle between active and favorites (up)
            if self.prompt_pane.scroll_offset == 0:
                if self.browser_view == "active":
                    self._load_favorites_slots()
                    self.browser_view = "favorites"
                else:
                    self.browser_view = "active"
                self.browser_index = -1
                self._load_browser_prompt(self.stdscr.getmaxyx()[1] // 2)
                h = self.stdscr.getmaxyx()[0]
                content_height = h - 4
                visible = content_height // 2 - 2
                max_off = max(0, len(self.prompt_pane.lines) - visible)
                self.prompt_pane.scroll_offset = max_off
                view_names = {"active": "active prompts", "favorites": "favorites"}
                count = len(self._current_browser_list())
                self._set_status(f"Switched to {view_names[self.browser_view]}. ({count} entries)")
            else:
                self.prompt_pane.scroll_up(2)

        elif ch == curses.KEY_DOWN:
            # Toggle between active and favorites (down)
            h = self.stdscr.getmaxyx()[0]
            content_height = h - 4
            visible = content_height // 2 - 2
            max_off = max(0, len(self.prompt_pane.lines) - visible)
            if self.prompt_pane.scroll_offset >= max_off:
                if self.browser_view == "active":
                    self._load_favorites_slots()
                    self.browser_view = "favorites"
                else:
                    self.browser_view = "active"
                self.browser_index = -1
                self._load_browser_prompt(self.stdscr.getmaxyx()[1] // 2)
                view_names = {"active": "active prompts", "favorites": "favorites"}
                count = len(self._current_browser_list())
                self._set_status(f"Switched to {view_names[self.browser_view]}. ({count} entries)")
            else:
                self.prompt_pane.scroll_down(visible, 2)

        elif ch == curses.KEY_END:
            if not self.refining and not self.recording:
                self._new_prompt()

        elif ch == curses.KEY_HOME:
            # Return to current prompt editor
            self.browser_view = "active"
            self.browser_index = -1
            self._load_browser_prompt(self.stdscr.getmaxyx()[1] // 2)
            self._set_status("Returned to current prompt.")

        elif ch == curses.KEY_PPAGE:
            if self.browser_index >= 0:
                self.prompt_pane.scroll_up(5)
            else:
                self.agent_pane.scroll_up(5)

        elif ch == curses.KEY_NPAGE:
            h = self.stdscr.getmaxyx()[0]
            content_height = h - 4
            visible = content_height // 2 - 2
            if self.browser_index >= 0:
                self.prompt_pane.scroll_down(visible, 5)
            else:
                self.agent_pane.scroll_down(content_height - 2, 5)

        elif ch == ord("["):
            name = cycle_tts_voice(-1)
            self._set_status(f"Voice: {name}", self.CP_VOICE)
            model_path = get_tts_voice_model()
            if not model_path or not model_path.exists():
                self._set_status(f"Voice {name} not downloaded!", self.CP_VOICE)
            else:
                speak_text(f"Voice changed to {name.replace('-', ' ').replace('_', ' ')}")

        elif ch == ord("]"):
            name = cycle_tts_voice(1)
            self._set_status(f"Voice: {name}", self.CP_VOICE)
            model_path = get_tts_voice_model()
            if not model_path or not model_path.exists():
                self._set_status(f"Voice {name} not downloaded!", self.CP_VOICE)
            else:
                speak_text(f"Voice changed to {name.replace('-', ' ').replace('_', ' ')}")


        elif ord("0") <= ch <= ord("9"):
            # Number keys 1-9, 0 → quick-load favorites slots
            if not self.recording and not self.refining:
                self._quick_load_favorite(ch)

        elif ch in (10, 13, curses.KEY_ENTER):
            # Enter starts direct text entry in dictation buffer
            if not self.recording and not self.refining:
                self.typing_mode = True
                self.typing_buffer = ""
                self.typing_cursor = 0
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                self._set_status(f"[{ts}] Type text, Enter to submit, ESC to cancel")

        elif ch == 9:  # Tab
            # Tab opens shortcuts browser (allowed during recording for injection)
            if (not self.refining
                    and self.agent_state in (AgentState.IDLE, AgentState.DONE)
                    and (self.working_dir or self._shortcut_strings
                         or self.documents_dir)):
                self._scan_folder_slugs()
                # Pick first non-empty category, or stay on current
                has_any = any(self._browser_cat_lists)
                if has_any:
                    # If current category is empty, jump to first non-empty
                    if not self._browser_cat_lists[self._browser_category]:
                        for i, lst in enumerate(self._browser_cat_lists):
                            if lst:
                                self._browser_category = i
                                break
                    self.folder_slug_list = self._browser_cat_lists[self._browser_category]
                    self.show_folder_slug = True
                    self.folder_slug_cursor = 0
                    self.folder_slug_scroll = 0
                else:
                    self._set_status("No shortcuts, folders, or documents found.")
            elif (not self.working_dir and not self._shortcut_strings
                  and not self.documents_dir):
                self._set_status("Set working directory or add shortcuts in ESC → Options.")

        elif ch == ord("h") or ch == ord("H"):
            self.show_help_overlay = True

        elif ch == ord("o") or ch == ord("O"):
            self.show_settings_overlay = True
            self.settings_cursor = 0
            self.tts_submenu_open = False
            self.test_tools_submenu_open = False
            self.voice_submenu_open = False
            self.ai_models_submenu_open = False

        elif ch == 27:
            # ESC key — could be menu, arrow key, or bracketed paste start
            self.stdscr.nodelay(True)
            next_ch = self.stdscr.getch()
            if next_ch == -1:
                # Pure ESC press — open menu
                self.show_escape_menu = True
                self.escape_menu_cursor = 0
            elif next_ch == 91:  # '[' — CSI sequence
                # Read remaining CSI params to check for paste start "200~"
                csi = []
                while True:
                    c = self.stdscr.getch()
                    if c == -1:
                        break
                    csi.append(c)
                    # CSI terminates at 0x40-0x7E (letters, ~, etc.)
                    if 64 <= c <= 126:
                        break
                if csi == [50, 48, 48, 126]:  # "200~" — bracketed paste start
                    pasted = self._read_paste_content()
                    self._inject_paste(pasted)
                # Otherwise it was a normal escape sequence (arrow key etc.)
                # which curses already handled via KEY_UP/DOWN/etc.

    # ─── Recording ─────────────────────────────────────────────────

    def _start_recording(self):
        # Pre-flight: check audio input device is available
        dev_err = _check_audio_input_device()
        if dev_err:
            self._set_status(f"Mic error: {dev_err}", self.CP_RECORDING)
            return

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

        try:
            self._audio_stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32",
                blocksize=BLOCK_SIZE, callback=self._audio_callback)
            self._audio_stream.start()
        except (sd.PortAudioError, OSError) as e:
            self.recording = False
            self._set_status(f"Audio device error: {e}", self.CP_RECORDING)
            return

        # Start live transcription thread
        self._live_transcribe_thread = threading.Thread(
            target=self._live_transcribe_loop, daemon=True)
        self._live_transcribe_thread.start()

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            # Device error (e.g. input overflow, device disconnected)
            self.ui_queue.put(("status",
                               f"Audio: {status}",
                               self.CP_RECORDING))
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
        
        peak = np.max(np.abs(audio)) if len(audio) > 0 else 0

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
            msg = "No speech detected."
            if peak < 0.005:
                # Help diagnose Crostini mic drop issues
                msg = "No speech detected (Mic volume too low?)"
            self.ui_queue.put(("status", msg, self.CP_STATUS))
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
        dev_err = _check_audio_input_device()
        if dev_err:
            self._set_status(f"Echo test failed: {dev_err}", self.CP_RECORDING)
            return
        self._set_status("Echo test: recording 1 second...", self.CP_RECORDING)
        threading.Thread(target=self._do_echo_test, daemon=True).start()

    def _do_echo_test(self):
        frames = []

        def callback(indata, frame_count, time_info, status):
            frames.append(indata.copy())

        # Record 1 second
        try:
            stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32",
                blocksize=BLOCK_SIZE, callback=callback)
            stream.start()
        except (sd.PortAudioError, OSError) as e:
            self.ui_queue.put(("status",
                               f"Echo test: mic open failed — {e}",
                               self.CP_RECORDING))
            return

        time.sleep(1.0)

        try:
            stream.stop()
            stream.close()
        except Exception:
            pass  # stream teardown errors are non-fatal

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
        try:
            sd.play(audio, samplerate=SAMPLE_RATE)
            sd.wait()
        except (sd.PortAudioError, OSError) as e:
            self.ui_queue.put(("status",
                               f"Echo test: playback failed — {e}",
                               self.CP_RECORDING))
            return

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
        self._set_status(f"Sending to {self.ai_provider.name} for refinement...", self.CP_STATUS)
        threading.Thread(target=self._do_refine, daemon=True).start()

    def _do_refine(self):
        fragments_copy = list(self.fragments)
        current = self.current_prompt
        result = refine_with_llm(
            fragments_copy, current,
            status_callback=lambda msg: self.ui_queue.put(("status", msg, self.CP_STATUS)),
            provider=self.ai_provider)
        self.ui_queue.put(("refined", result))
        self.ui_queue.put(("status", f"Prompt refined! (v{self.prompt_version + 1})", self.CP_STATUS))

    # ─── Save ──────────────────────────────────────────────────────

    def _save_prompt(self):
        if not self.current_prompt:
            self._set_status("No prompt to save. Refine first!")
            return

        now = datetime.datetime.now()
        self.history_base.mkdir(parents=True, exist_ok=True)

        seq = _next_seq(self.history_base)
        slug = _slug_from_text(self.current_prompt)
        filename = self.history_base / f"{seq:03d}_{slug}_prompt.md"

        with open(filename, "w") as f:
            f.write(f"# Prompt v{self.prompt_version}\n")
            f.write(f"# Saved: {now.isoformat()}\n")
            f.write(f"# Fragments: {len(self.fragments)}\n\n")
            f.write(self.current_prompt)
            f.write("\n")

        self._scan_history_prompts()
        self.browser_index = -1
        self.prompt_saved = True
        self._set_status(f"Saved: {filename}")

    def _save_to_history(self, prompt_text) -> Path | None:
        """Auto-save every executed prompt to the history subfolder.

        Returns the prompt file path so the response can be written later.
        """
        if not prompt_text:
            return None
        now = datetime.datetime.now()
        self.history_base.mkdir(parents=True, exist_ok=True)
        seq = _next_seq(self.history_base)
        slug = _slug_from_text(prompt_text)
        filename = self.history_base / f"{seq:03d}_{slug}_prompt.md"
        with open(filename, "w") as f:
            f.write(f"# Executed: {now.isoformat()}\n\n")
            f.write(prompt_text)
            f.write("\n")
        self._scan_history_prompts()
        return filename

    def _save_response_to_history(self, response_text: str, is_error: bool = False):
        """Write a response file paired with the last saved prompt file."""
        prompt_path = self._last_history_prompt_path
        if not prompt_path:
            return
        response_path = Path(str(prompt_path).replace("_prompt.md", "_response.md"))
        try:
            now = datetime.datetime.now()
            with open(response_path, "w") as f:
                if is_error:
                    f.write(f"# Error: {now.isoformat()}\n\n")
                else:
                    f.write(f"# Response: {now.isoformat()}\n\n")
                f.write(response_text)
                f.write("\n")
        except OSError:
            pass

    def _key_to_fav_slot(self, ch: int) -> int:
        """Convert a key code to a favorites slot index (0-9), or -1 if invalid."""
        if ord("1") <= ch <= ord("9"):
            return ch - ord("1")  # keys 1-9 → slots 0-8
        if ch == ord("0"):
            return 9  # key 0 → slot 9 (10th)
        return -1

    def _format_favorites_slots(self) -> str:
        """Format the 10 favorites slots for display."""
        lines = []
        for i in range(10):
            key = str((i + 1) % 10)  # 1,2,...,9,0
            path = self.favorites_slots[i]
            if path:
                p = Path(path)
                try:
                    content = p.read_text()
                    # Get first non-comment, non-empty line as preview
                    preview = ""
                    for line in content.split("\n"):
                        stripped = line.strip()
                        if stripped and not stripped.startswith("#"):
                            preview = stripped[:50]
                            if len(stripped) > 50:
                                preview += "…"
                            break
                    if not preview:
                        preview = p.name
                except Exception:
                    preview = p.name
                lines.append(f"  [{key}] ★ {preview}")
            else:
                lines.append(f"  [{key}]   (empty)")
        return "\n".join(lines)

    def _add_to_favorites(self, slot_idx: int | None):
        """Start favorites assignment: prompt user for slot if not given."""
        # Determine the source path to favorite
        prompt_list = self._current_browser_list()
        source_path = None
        if self.browser_index >= 0 and self.browser_index < len(prompt_list):
            source_path = prompt_list[self.browser_index]

        if source_path and source_path.exists():
            # Source is a file on disk — store its path directly
            pass
        else:
            # No source file — need to save current prompt text first
            prompt_text = self._get_active_prompt_text()
            if not prompt_text and self.current_prompt:
                prompt_text = self.current_prompt
            if not prompt_text:
                self._set_status("No prompt to favorite. Browse or refine one first!")
                return
            # Write to a file in history
            now = datetime.datetime.now()
            self.history_base.mkdir(parents=True, exist_ok=True)
            seq = _next_seq(self.history_base)
            slug = _slug_from_text(prompt_text)
            dest = self.history_base / f"{seq:03d}_{slug}_prompt.md"
            with open(dest, "w") as f:
                f.write(f"# Favorited: {now.isoformat()}\n\n")
                f.write(prompt_text)
                f.write("\n")
            source_path = dest
            self._scan_history_prompts()

        self._pending_fav_path = str(source_path)

        if slot_idx is not None:
            self._assign_to_fav_slot(slot_idx)
        else:
            self.choosing_fav_slot = True
            self._set_status("Choose favorites slot [1-9, 0] or any other key to cancel")

    def _assign_to_fav_slot(self, slot_idx: int):
        """Assign to slot, with overwrite confirmation if occupied."""
        if self.favorites_slots[slot_idx]:
            self._pending_fav_slot = slot_idx
            self.confirming_fav_overwrite = True
            slot_num = slot_idx + 1
            self._set_status(f"Slot {slot_num} already has a favorite. Overwrite? [Y/other]")
        else:
            self._do_assign_fav_slot(slot_idx)

    def _do_assign_fav_slot(self, slot_idx: int):
        """Actually assign the pending path to the given slot."""
        self.favorites_slots[slot_idx] = self._pending_fav_path
        self._save_favorites_slots()
        self._pending_fav_slot = -1
        slot_num = slot_idx + 1
        key = str(slot_num % 10)
        self._set_status(f"★ Saved to favorites slot {slot_num} [key {key}]! ({self._favorites_slot_count()}/10)")

    def _remove_from_favorites(self):
        """Remove the currently browsed favorite from its slot."""
        if self.browser_view != "favorites" or self.browser_index < 0:
            self._set_status("No favorite selected to remove.")
            return
        # Find which slot corresponds to this browser index
        fav_paths = self._favorites_as_paths()
        if self.browser_index >= len(fav_paths):
            self._set_status("No favorite selected to remove.")
            return
        target = fav_paths[self.browser_index]
        # Find and clear the slot
        for i, p in enumerate(self.favorites_slots):
            if p and Path(p) == target:
                self.favorites_slots[i] = None
                break
        self._save_favorites_slots()
        # Adjust browser index
        remaining = self._favorites_as_paths()
        if remaining:
            self.browser_index = min(self.browser_index, len(remaining) - 1)
        else:
            self.browser_index = -1
        self._load_browser_prompt(self.stdscr.getmaxyx()[1] // 2)
        self._set_status(f"Removed from favorites. ({self._favorites_slot_count()}/10 remaining)")

    def _quick_load_favorite(self, ch: int):
        """Quick-load a favorite by number key."""
        slot_idx = self._key_to_fav_slot(ch)
        if slot_idx < 0:
            return
        path_str = self.favorites_slots[slot_idx]
        slot_num = slot_idx + 1
        if not path_str:
            self._set_status(f"Favorites slot {slot_num} is empty.")
            return
        path = Path(path_str)
        if not path.exists():
            self.favorites_slots[slot_idx] = None
            self._save_favorites_slots()
            self._set_status(f"Favorites slot {slot_num}: file no longer exists (cleared).")
            return
        # Switch to favorites view and select this item
        self.browser_view = "favorites"
        fav_paths = self._favorites_as_paths()
        try:
            self.browser_index = fav_paths.index(path)
        except ValueError:
            self.browser_index = -1
        self._load_browser_prompt(self.stdscr.getmaxyx()[1] // 2)
        self._set_status(f"★ Loaded favorites slot {slot_num}. Press E to execute.")

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
        self._clear_buffer_file()
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

    # ─── Edit historical prompt ──────────────────────────────────

    def _confirm_edit_historical(self):
        """Show confirmation before editing a historical/saved prompt."""
        self.confirming_edit_historical = True
        self._set_status("Edit this historical prompt? [Y] Copy as new working prompt / [other] Cancel")

    def _copy_historical_to_current(self):
        """Copy the currently browsed historical prompt into the current prompt slot."""
        prompt_text = self._get_active_prompt_text()
        if not prompt_text:
            self._set_status("Could not read historical prompt.")
            return
        # Reset state for a fresh working prompt
        self._clear_executed_prompt()
        self.fragments.clear()
        self._clear_buffer_file()
        self.current_prompt = prompt_text
        self.prompt_version = 1
        self.prompt_saved = False
        self.dictation_pane.lines.clear()
        self.dictation_pane.scroll_offset = 0
        self.browser_view = "active"
        self.browser_index = -1
        w = self.stdscr.getmaxyx()[1] // 2
        self._load_browser_prompt(w)
        self._set_dictation_info(w)
        self._set_status("Historical prompt copied as new working prompt. Dictate to refine or press E to execute.")

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
        self._clear_buffer_file()
        self._last_history_prompt_path = self._save_to_history(prompt_text)
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
        self._agent_cancel.clear()
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

        # Clear prompt state so next dictation starts fresh
        self.fragments.clear()
        self._clear_buffer_file()
        self.current_prompt = None
        self.prompt_version = 0
        self.prompt_saved = True
        self.dictation_pane.lines.clear()
        self.dictation_pane.scroll_offset = 0

        self._last_history_prompt_path = self._save_to_history(prompt_text)

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
        self._agent_cancel.clear()
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
        """Run AI agent in background, streaming verbose output."""
        # Let the download animation play for ~3 seconds (cancellable)
        if self._agent_cancel.wait(3.0):
            return  # cancelled during animation

        self.ui_queue.put(("agent_state", AgentState.RECEIVING))
        self.ui_queue.put(("status", "Agent receiving transmission...", self.CP_STATUS))

        # Add the "incoming transmission" header via typewriter
        self._emit_typewriter("\n═══ INCOMING TRANSMISSION ═══\n\n")

        provider = self.ai_provider

        try:
            prompt_with_tts = self.xfer_prompt_text + TTS_PROMPT_SUFFIX
            cmd = provider.build_execute_cmd(prompt_with_tts, self.session_id)
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

                # Capture session_id from init event
                sid = provider.parse_init_event(event)
                if sid:
                    self.ui_queue.put(("session_id", sid))

                # Assistant text + tool use
                text_result = provider.parse_text_event(event)
                if text_result:
                    text, tool_uses = text_result
                    if text:
                        response_text_parts.append(text)
                        self._emit_typewriter(text)
                    for name, inp in tool_uses:
                        detail = self._format_tool_input(name, inp)
                        self._emit_typewriter(f"\n▶ {name}: {detail}\n")

                # Thinking
                thinking = provider.parse_thinking_event(event)
                if thinking:
                    for tl in thinking.split("\n"):
                        self._emit_typewriter(f"  .. {tl}\n")

                # Tool results
                tool_preview = provider.parse_tool_result_event(event)
                if tool_preview:
                    self._emit_typewriter(f"  ◀ {tool_preview}\n")

                # Result event (final)
                result_check = provider.is_result_event(event)
                if result_check is not None:
                    result_text = result_check
                    # Extract context usage
                    ctx = provider.parse_context_usage(event)
                    if ctx:
                        self.ui_queue.put(("context_usage", ctx[0], ctx[1]))

            # If the agent was killed, don't post completion messages
            if self._agent_cancel.is_set():
                return

            if self.agent_process:
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
                self._save_response_to_history(summary)
                stop_speaking()
                speak_text(summary, on_done=lambda: self.ui_queue.put(
                    ("status", "Ready for next prompt.", self.CP_STATUS)))
                self.ui_queue.put(("status", "Speaking summary...", self.CP_STATUS))
            else:
                self._save_response_to_history("(no TTS summary returned)", is_error=True)

        except FileNotFoundError:
            if not self._agent_cancel.is_set():
                self._save_response_to_history(
                    f"ERROR: '{provider.binary}' CLI not found", is_error=True)
                self.ui_queue.put(("agent_state", AgentState.DONE))
                self.ui_queue.put(("status", f"Error: '{provider.binary}' CLI not found!", self.CP_STATUS))
        except Exception as e:
            if not self._agent_cancel.is_set():
                self._save_response_to_history(
                    f"ERROR: {e}", is_error=True)
                self.ui_queue.put(("agent_state", AgentState.DONE))
                self.ui_queue.put(("status", f"Agent error: {e}", self.CP_STATUS))

    def _kill_agent(self):
        # Signal the cancel event so the animation sleep exits early
        self._agent_cancel.set()
        proc = self.agent_process
        self.agent_process = None
        stop_speaking()
        self.agent_state = AgentState.IDLE
        self.typewriter_queue.clear()
        if proc:
            # Terminate in background to avoid blocking the UI thread
            def _reap():
                try:
                    proc.terminate()  # SIGTERM for graceful shutdown
                    try:
                        proc.wait(timeout=3.0)
                    except subprocess.TimeoutExpired:
                        proc.kill()  # SIGKILL as last resort
                except Exception:
                    pass
            threading.Thread(target=_reap, daemon=True).start()
        # Restore source pane if still pending
        if self._agent_source_pane is not None:
            self._agent_source_pane.color_pair = self._agent_source_original_color
            self._agent_source_pane = None
            self._agent_source_original_color = None
        self._set_status("Agent terminated.")

    def _clear_session(self):
        """Clear the current session, starting fresh next execution."""
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

        right_width = self.stdscr.getmaxyx()[1] - self.stdscr.getmaxyx()[1] // 2

        # Drain up to max_chars per frame for fast streaming
        chars_this_frame = 0
        max_chars = 256

        while self.typewriter_queue and chars_this_frame < max_chars:
            ch = self.typewriter_queue.popleft()

            # Handle color-change sentinel tuples
            if isinstance(ch, tuple) and ch[0] == "color":
                self._typewriter_line_color = ch[1]  # None to reset
                # Tag current last line with the new color
                if self._typewriter_line_color is not None and self.agent_pane.lines:
                    idx = len(self.agent_pane.lines) - 1
                    self.agent_pane.line_colors[idx] = self._typewriter_line_color
                continue

            prev_count = len(self.agent_pane.lines)
            self.agent_pane.add_char_to_last_line(ch, right_width)
            # Tag any newly created lines with the current override color
            if self._typewriter_line_color is not None:
                for idx in range(prev_count, len(self.agent_pane.lines)):
                    self.agent_pane.line_colors[idx] = self._typewriter_line_color
            chars_this_frame += 1

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
                self._persist_buffer()
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
                self._clear_buffer_file()
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
        description=f"VoiceCode BBS v{__version__} - Voice-Driven Prompt Workshop & Agent Terminal",
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
            ║    N        New prompt (prompts save if unsaved)      ║
            ║    E        Execute prompt (send to agent)            ║
            ║    U        Undo last dictation entry                  ║
            ║    C        Clear dictation buffer                    ║
            ║    ←→       Browse prompt history                      ║
            ║    ↑↓       Scroll prompt pane                        ║
            ║    PgUp/Dn  Scroll agent pane                         ║
            ║    K        Kill running agent                        ║
            ║    W        New session (clear context)               ║
            ║    X        Restart application                       ║
            ║    Q        Quit                                      ║
            ╚═══════════════════════════════════════════════════════╝
        """),
    )
    parser.parse_args()  # exits on --help, otherwise no args expected

    app = BBSApp()
    try:
        curses.wrapper(lambda stdscr: app.run(stdscr))
    finally:
        _restore_stderr()

    if app.restart:
        os.execv(sys.executable, [sys.executable] + sys.argv)


if __name__ == "__main__":
    main()
