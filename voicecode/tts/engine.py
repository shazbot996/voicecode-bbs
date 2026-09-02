"""TTS playback engine — speak text via Piper, stop playback."""

import re
import subprocess
import sys
import threading
from pathlib import Path

import numpy as np

from voicecode.audio.utils import safe_sd_play
from voicecode.settings import load_settings
from voicecode.tts.voices import get_tts_voice_model, get_tts_piper_extra_args, _tts_enabled, TTS_AVAILABLE

# Resolve piper from the same venv as the running interpreter so TTS works
# even when the venv isn't activated (e.g. invoked via parent Makefile).
_PIPER_BIN = str(Path(sys.executable).parent / "piper")

_tts_process = None  # Track running TTS playback for cancellation


def extract_tts_summary(text: str) -> str:
    """Extract the [TTS_SUMMARY] block from agent response text.

    The summary is requested at the very end of the response, so the LAST
    complete block wins.  Earlier blocks are usually the agent quoting the
    instruction back, or -- when the task is about this codebase -- the
    markers appearing in quoted source.  Empty blocks are skipped for the
    same reason.
    """
    if not text:
        return ""
    matches = re.findall(r'\[TTS_SUMMARY\]\s*(.*?)\s*\[/TTS_SUMMARY\]', text,
                         re.DOTALL)
    for candidate in reversed(matches):
        if candidate.strip():
            return candidate.strip()
    return ""


def clean_spoken_text(text: str) -> str:
    """Clean arbitrary response or error text for natural TTS playback."""
    if not text:
        return ""
    # Strip ANSI escape sequences and OSC codes
    text = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', text)
    text = re.sub(r'\x1B\][^\x07\x1B]*(?:\x07|\x1B\\)?', '', text)
    # Strip markdown code blocks
    text = re.sub(r'```[\s\S]*?```', ' ', text)
    # Strip inline code backticks
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # Strip markdown headers (#, ##, etc.)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Strip markdown links [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Strip markdown formatting (*, **, _, __, ~~)
    text = re.sub(r'[*_~]{1,3}', '', text)
    # Strip blockquotes (> )
    text = re.sub(r'^\s*>\s*', '', text, flags=re.MULTILINE)
    # Strip list bullets (*, -, +, 1.)
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    # Strip remaining TTS tags if any
    text = text.replace('[TTS_SUMMARY]', '').replace('[/TTS_SUMMARY]', '')
    # Collapse whitespace
    text = " ".join(text.split())
    return text.strip()


def _truncate_sentences(text: str, max_sentences: int = 3, max_chars: int = 350) -> str:
    """Truncate text to at most max_sentences and max_chars at sentence boundaries."""
    if not text:
        return ""
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    if not sentences:
        return text[:max_chars].rsplit(' ', 1)[0] if len(text) > max_chars else text
    result = []
    total_len = 0
    for s in sentences:
        if len(result) >= max_sentences or (total_len + len(s) > max_chars and result):
            break
        result.append(s)
        total_len += len(s) + 1
    out = " ".join(result).strip()
    if not out and sentences:
        out = sentences[0][:max_chars].rsplit(' ', 1)[0] if len(sentences[0]) > max_chars else sentences[0]
    return out


def extract_fallback_summary(text: str, max_sentences: int = 3, max_chars: int = 350) -> str:
    """Extract a clean fallback summary from response text when no complete [TTS_SUMMARY] block is found."""
    if not text:
        return ""
    # Check if there is an unclosed [TTS_SUMMARY]
    idx = text.rfind('[TTS_SUMMARY]')
    if idx != -1:
        tail = text[idx + len('[TTS_SUMMARY]'):]
        cleaned = clean_spoken_text(tail)
        if cleaned:
            return _truncate_sentences(cleaned, max_sentences, max_chars)

    cleaned = clean_spoken_text(text)
    if not cleaned:
        return ""
    return _truncate_sentences(cleaned, max_sentences, max_chars)


def format_error_readout(error_msg: str = "", provider_name: str = "Agent",
                         exit_code: int | None = None) -> str:
    """Generate a clear, natural spoken explanation for premature termination or errors."""
    provider_str = provider_name.strip() if provider_name else "Agent"
    err_lower = (error_msg or "").lower()

    # Check for container / backend timeouts
    if any(k in err_lower for k in [
        "container timed out", "container timeout", "containers timing out",
        "context deadline exceeded", "deadline exceeded", "sandbox timeout",
        "timed out", "timeout expired", "task timeout", "step timeout",
        "timeout waiting for response", "timeout waiting", "print-timeout",
    ]) or exit_code == 124:
        return "The session ended early because the execution container timed out while working on the task."

    # Check for rate limit / quota
    if any(k in err_lower for k in [
        "rate limit", "quota", "resource exhausted", "429", "too many requests"
    ]):
        return f"The {provider_str} session ended early due to API rate limits or quota exceeded."

    # Check for CLI not found
    if any(k in err_lower for k in [
        "not found", "no such file or directory", "executable not found", "cannot find"
    ]):
        return f"The {provider_str} command line tool was not found on your system."

    # Check for connection / network issues
    if any(k in err_lower for k in [
        "connection refused", "connection reset", "network error", "econnreset", "socket hang up", "connect error"
    ]):
        return f"The {provider_str} session ended early due to a network connection failure."

    # Check for memory limits / SIGKILL (137)
    if exit_code == 137 or "out of memory" in err_lower or "oom" in err_lower:
        return f"The {provider_str} process was terminated by the operating system, possibly due to memory limits."

    # Check if there is a specific error message
    clean_err = clean_spoken_text(error_msg)
    if clean_err:
        clean_err = re.sub(r'^(?:error|fatal|exception)\s*:\s*', '', clean_err, flags=re.IGNORECASE).strip()
        if clean_err:
            short_err = _truncate_sentences(clean_err, max_sentences=2, max_chars=200)
            return f"The {provider_str} task ended prematurely: {short_err}"

    # If non-zero exit code
    if exit_code is not None and exit_code != 0:
        return f"The {provider_str} process terminated unexpectedly with exit code {exit_code}."

    return f"The {provider_str} session ended prematurely without returning a response."


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

            gain = float(load_settings().get("tts_volume_gain", 1.0))

            # Pipe text through piper as raw PCM, then play with aplay.

            # Using --output-raw avoids per-sentence WAV headers that cause
            # aplay to stop after the first sentence.
            piper_cmd = [_PIPER_BIN, "--model", str(voice_model),
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

                safe_sd_play(audio_array, samplerate=22050)

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
