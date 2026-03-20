"""Audio utility functions — ALSA suppression, stderr redirection, playback."""

import os
import ctypes

import sounddevice as sd
import numpy as np

# ── Suppress ALSA error/warning messages (e.g. "underrun occurred") that
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
saved_stderr_fd: int | None = None


def suppress_stderr():
    """Redirect fd 2 → /dev/null to silence PortAudio/ALSA C-level noise."""
    global saved_stderr_fd
    try:
        saved_stderr_fd = os.dup(2)
        _devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(_devnull, 2)
        os.close(_devnull)
    except OSError:
        saved_stderr_fd = None


def restore_stderr():
    """Restore original stderr so post-exit tracebacks are visible."""
    global saved_stderr_fd
    if saved_stderr_fd is not None:
        try:
            os.dup2(saved_stderr_fd, 2)
            os.close(saved_stderr_fd)
        except OSError:
            pass
        saved_stderr_fd = None


def check_audio_input_device() -> str | None:
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


def safe_sd_play(audio, samplerate):
    """Play audio via sounddevice, swallowing PortAudio errors.

    Uses a dedicated OutputStream per call so concurrent playback from
    multiple threads works without interference (polyphonic previews).
    """
    try:
        stream = sd.OutputStream(samplerate=samplerate, channels=1, dtype='int16')
        stream.start()
        stream.write(audio.reshape(-1, 1))
        stream.stop()
        stream.close()
    except (sd.PortAudioError, OSError):
        pass  # output device disappeared — nothing we can do
