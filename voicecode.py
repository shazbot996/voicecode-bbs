#!/usr/bin/env python3
"""
VoiceCode - Voice-driven CLI agent interaction.

Modes:
  Push-to-talk: Hold SPACE to record, release to transcribe.
  Hands-free:   VAD detects speech, say "send it" (or press Enter) to commit.

Architecture:
  Mic → Silero VAD → faster-whisper STT → Review Buffer → CLI stdin
"""

import sys
import os
import signal
import threading
import queue
import subprocess
import time
import argparse
import select
import termios
import tty
from pathlib import Path

import numpy as np
import sounddevice as sd
import torch

# Lazy imports for startup speed
_whisper_model = None
_vad_model = None


def get_vad_model():
    global _vad_model
    if _vad_model is None:
        print("Loading Silero VAD model...")
        _vad_model, _ = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            onnx=False,
        )
    return _vad_model


def get_whisper_model(model_size="base.en"):
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        print(f"Loading Whisper model ({model_size})...")
        _whisper_model = WhisperModel(
            model_size, device="cpu", compute_type="int8"
        )
        print("Model loaded.")
    return _whisper_model


SAMPLE_RATE = 16000
CHANNELS = 1
BLOCK_DURATION_MS = 30  # VAD chunk size
BLOCK_SIZE = int(SAMPLE_RATE * BLOCK_DURATION_MS / 1000)

# VAD thresholds
VAD_THRESHOLD = 0.5
SILENCE_AFTER_SPEECH_SEC = 1.5  # silence needed to end an utterance
MIN_SPEECH_DURATION_SEC = 0.3   # ignore very short blips


class AudioBuffer:
    """Thread-safe accumulator for audio frames."""

    def __init__(self):
        self.frames = []
        self.lock = threading.Lock()

    def add(self, frame: np.ndarray):
        with self.lock:
            self.frames.append(frame.copy())

    def get_and_clear(self) -> np.ndarray | None:
        with self.lock:
            if not self.frames:
                return None
            data = np.concatenate(self.frames)
            self.frames.clear()
            return data

    def clear(self):
        with self.lock:
            self.frames.clear()

    def duration_sec(self) -> float:
        with self.lock:
            total_samples = sum(f.shape[0] for f in self.frames)
            return total_samples / SAMPLE_RATE


class TerminalUI:
    """Minimal terminal UI for the review buffer."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    RED = "\033[31m"
    CLEAR_LINE = "\033[2K"

    def __init__(self):
        self.lock = threading.Lock()

    def status(self, msg: str, color: str = ""):
        c = getattr(self, color.upper(), "") if color else ""
        with self.lock:
            sys.stderr.write(f"\r{self.CLEAR_LINE}{c}{msg}{self.RESET}")
            sys.stderr.flush()

    def info(self, msg: str):
        with self.lock:
            sys.stderr.write(f"\r{self.CLEAR_LINE}{self.CYAN}{msg}{self.RESET}\n")
            sys.stderr.flush()

    def show_transcription(self, text: str):
        with self.lock:
            sys.stderr.write(
                f"\r{self.CLEAR_LINE}{self.GREEN}{self.BOLD}>> {text}{self.RESET}\n"
            )
            sys.stderr.flush()

    def show_buffer(self, lines: list[str]):
        with self.lock:
            sys.stderr.write(f"\r{self.CLEAR_LINE}")
            sys.stderr.write(
                f"{self.YELLOW}--- Buffer ---{self.RESET}\n"
            )
            for line in lines:
                sys.stderr.write(f"  {line}\n")
            sys.stderr.write(
                f"{self.YELLOW}--------------{self.RESET}\n"
            )
            sys.stderr.flush()

    def show_response(self, text: str):
        with self.lock:
            sys.stderr.write(f"{text}")
            sys.stderr.flush()


def transcribe(audio: np.ndarray, model_size: str = "base.en") -> str:
    """Transcribe audio numpy array to text using faster-whisper."""
    model = get_whisper_model(model_size)
    # faster-whisper expects float32 in [-1, 1]
    if audio.dtype != np.float32:
        audio = audio.astype(np.float32)
    segments, _ = model.transcribe(audio, beam_size=3, vad_filter=True)
    text = " ".join(seg.text.strip() for seg in segments).strip()
    return text


def is_command(text: str) -> tuple[str, str] | None:
    """Check if transcription contains a voice command.

    Returns (command_name, remaining_text) or None.
    """
    lower = text.lower().strip()

    # Commit commands - send the buffer
    for trigger in ["send it", "send that", "go ahead", "execute", "run it", "run that"]:
        if lower.endswith(trigger):
            remaining = text[: -len(trigger)].strip()
            return ("send", remaining)
        if lower == trigger:
            return ("send", "")

    # Cancel commands
    for trigger in ["cancel", "never mind", "nevermind", "scratch that", "clear buffer"]:
        if lower == trigger:
            return ("cancel", "")

    return None


class VoiceCodeApp:
    """Main application."""

    def __init__(self, args):
        self.args = args
        self.ui = TerminalUI()
        self.audio_buf = AudioBuffer()
        self.text_buffer: list[str] = []  # accumulated transcriptions
        self.text_lock = threading.Lock()
        self.running = True
        self.recording = False  # for push-to-talk
        self.cli_process = None
        self._old_term_settings = None

    def run(self):
        signal.signal(signal.SIGINT, lambda *_: self.shutdown())
        signal.signal(signal.SIGTERM, lambda *_: self.shutdown())

        # Preload models
        get_vad_model()
        get_whisper_model(self.args.model)

        self.ui.info("VoiceCode ready!")
        if self.args.mode == "ptt":
            self.ui.info("Push-to-talk: Hold SPACE to record. Release to transcribe.")
            self.ui.info("Press Enter to send buffer to CLI. 'c' to clear. 'q' to quit.")
            self.run_ptt()
        else:
            self.ui.info("Hands-free: Speak naturally. Say 'send it' to commit.")
            self.ui.info("Press Enter to force-send. 'c' to clear. 'q' to quit.")
            self.run_handsfree()

    def run_ptt(self):
        """Push-to-talk mode using SPACE bar."""
        self._setup_raw_terminal()
        try:
            self._ptt_loop()
        finally:
            self._restore_terminal()

    def _setup_raw_terminal(self):
        fd = sys.stdin.fileno()
        self._old_term_settings = termios.tcgetattr(fd)
        tty.setcbreak(fd)

    def _restore_terminal(self):
        if self._old_term_settings:
            termios.tcsetattr(
                sys.stdin.fileno(), termios.TCSADRAIN, self._old_term_settings
            )

    def _ptt_loop(self):
        while self.running:
            self.ui.status("[SPACE=record] [Enter=send] [c=clear] [q=quit]", "dim")

            # Non-blocking key check
            if select.select([sys.stdin], [], [], 0.1)[0]:
                ch = sys.stdin.read(1)

                if ch == " ":
                    self._do_ptt_recording()
                elif ch in ("\r", "\n"):
                    self._send_buffer()
                elif ch == "c":
                    self._clear_buffer()
                elif ch == "q":
                    self.shutdown()
                    break

    def _do_ptt_recording(self):
        """Record while SPACE is held, transcribe on release."""
        self.audio_buf.clear()
        self.ui.status("Recording... (release SPACE to stop)", "red")

        # Start audio stream
        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            blocksize=BLOCK_SIZE,
            callback=lambda indata, *_: self.audio_buf.add(indata[:, 0]),
        )
        stream.start()

        # Wait for SPACE release (any key, really, since we detect key-up
        # via absence of repeated space in cbreak mode)
        while self.running:
            if select.select([sys.stdin], [], [], 0.05)[0]:
                ch = sys.stdin.read(1)
                if ch != " ":
                    # Non-space key pressed, stop recording but process the key
                    break
            else:
                # No key pressed - space was released
                # In cbreak mode, holding space sends repeated chars.
                # A gap means released.
                break

        stream.stop()
        stream.close()

        audio = self.audio_buf.get_and_clear()
        if audio is None or len(audio) / SAMPLE_RATE < MIN_SPEECH_DURATION_SEC:
            self.ui.status("Too short, discarded.", "dim")
            time.sleep(0.5)
            return

        self.ui.status("Transcribing...", "yellow")
        text = transcribe(audio, self.args.model)
        if not text:
            self.ui.status("(no speech detected)", "dim")
            time.sleep(0.5)
            return

        # Check for voice commands
        cmd = is_command(text)
        if cmd:
            name, remaining = cmd
            if remaining:
                self._add_to_buffer(remaining)
            if name == "send":
                self._send_buffer()
            elif name == "cancel":
                self._clear_buffer()
            return

        self._add_to_buffer(text)

    def run_handsfree(self):
        """Hands-free mode with VAD."""
        self._setup_raw_terminal()
        vad = get_vad_model()

        audio_queue = queue.Queue()

        def audio_callback(indata, frames, time_info, status):
            audio_queue.put(indata[:, 0].copy())

        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            blocksize=BLOCK_SIZE,
            callback=audio_callback,
        )
        stream.start()

        speech_frames = []
        is_speaking = False
        silence_start = None

        try:
            while self.running:
                # Check for keyboard input (non-blocking)
                if select.select([sys.stdin], [], [], 0)[0]:
                    ch = sys.stdin.read(1)
                    if ch in ("\r", "\n"):
                        self._send_buffer()
                    elif ch == "c":
                        self._clear_buffer()
                    elif ch == "q":
                        self.shutdown()
                        break

                # Process audio
                try:
                    frame = audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                # Run VAD
                tensor = torch.from_numpy(frame)
                speech_prob = vad(tensor, SAMPLE_RATE).item()

                if speech_prob >= VAD_THRESHOLD:
                    if not is_speaking:
                        is_speaking = True
                        self.ui.status("Listening...", "green")
                    speech_frames.append(frame)
                    silence_start = None
                elif is_speaking:
                    speech_frames.append(frame)  # keep recording during short pauses
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start > SILENCE_AFTER_SPEECH_SEC:
                        # End of utterance
                        is_speaking = False
                        silence_start = None
                        audio = np.concatenate(speech_frames)
                        speech_frames.clear()

                        if len(audio) / SAMPLE_RATE < MIN_SPEECH_DURATION_SEC:
                            continue

                        self.ui.status("Transcribing...", "yellow")
                        text = transcribe(audio, self.args.model)
                        if text:
                            cmd = is_command(text)
                            if cmd:
                                name, remaining = cmd
                                if remaining:
                                    self._add_to_buffer(remaining)
                                if name == "send":
                                    self._send_buffer()
                                elif name == "cancel":
                                    self._clear_buffer()
                            else:
                                self._add_to_buffer(text)
                        self.ui.status(
                            "[listening] Enter=send, c=clear, q=quit", "dim"
                        )
        finally:
            stream.stop()
            stream.close()
            self._restore_terminal()

    def _add_to_buffer(self, text: str):
        with self.text_lock:
            self.text_buffer.append(text)
        self.ui.show_transcription(text)
        with self.text_lock:
            self.ui.show_buffer(self.text_buffer)

    def _clear_buffer(self):
        with self.text_lock:
            self.text_buffer.clear()
        self.ui.info("Buffer cleared.")

    def _send_buffer(self):
        with self.text_lock:
            if not self.text_buffer:
                self.ui.status("Buffer is empty, nothing to send.", "dim")
                time.sleep(0.5)
                return
            full_text = " ".join(self.text_buffer)
            self.text_buffer.clear()

        self.ui.info(f"Sending: {full_text}")

        if self.args.command:
            self._send_to_cli(full_text)
        else:
            # No CLI target - just print to stdout
            print(full_text)
            sys.stdout.flush()

    def _send_to_cli(self, text: str):
        """Send text to the configured CLI command."""
        cmd = self.args.command
        self.ui.info(f"Running: {cmd}")

        try:
            result = subprocess.run(
                cmd,
                input=text,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.stdout:
                self.ui.info("--- Response ---")
                self.ui.show_response(result.stdout)
                self.ui.show_response("\n")
            if result.stderr:
                self.ui.show_response(f"(stderr: {result.stderr.strip()})\n")
        except subprocess.TimeoutExpired:
            self.ui.info("Command timed out (300s)")
        except Exception as e:
            self.ui.info(f"Error running command: {e}")

    def shutdown(self):
        self.running = False
        self.ui.info("\nShutting down...")


def main():
    parser = argparse.ArgumentParser(
        description="VoiceCode - voice-driven CLI interaction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Push-to-talk, just print transcriptions
  python voicecode.py

  # Hands-free mode
  python voicecode.py --mode handsfree

  # Send to a CLI tool
  python voicecode.py --command "gemini"
  python voicecode.py --command "claude --print"

  # Use a larger model for better accuracy
  python voicecode.py --model small.en
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["ptt", "handsfree"],
        default="ptt",
        help="Interaction mode (default: ptt = push-to-talk)",
    )
    parser.add_argument(
        "--model",
        default="base.en",
        help="Whisper model size (default: base.en). Options: tiny.en, base.en, small.en, medium.en",
    )
    parser.add_argument(
        "--command",
        default=None,
        help="CLI command to send transcriptions to (e.g. 'gemini', 'claude --print')",
    )
    args = parser.parse_args()

    app = VoiceCodeApp(args)
    app.run()


if __name__ == "__main__":
    main()
