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
    """Extract the [TTS_SUMMARY] block from agent response text."""
    match = re.search(r'\[TTS_SUMMARY\]\s*(.*?)\s*\[/TTS_SUMMARY\]', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


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
