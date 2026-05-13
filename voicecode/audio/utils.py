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


def list_input_devices() -> list[tuple[int, str]]:
    """Return [(index, name), ...] for all input-capable devices."""
    try:
        devices = sd.query_devices()
    except (sd.PortAudioError, OSError):
        return []
    result: list[tuple[int, str]] = []
    seen_names: set[str] = set()
    for i, d in enumerate(devices):
        if d.get("max_input_channels", 0) < 1:
            continue
        name = d.get("name", f"Device {i}")
        # PortAudio sometimes exposes the same device under multiple host APIs;
        # de-dupe by name to keep the picker readable.
        if name in seen_names:
            continue
        seen_names.add(name)
        result.append((i, name))
    return result


def resolve_input_device(name: str | None) -> int | None:
    """Resolve a persisted device name to a current PortAudio index.

    Returns None when the name is empty/None (meaning system default) OR when
    the named device is no longer present (so we fall back to the default
    rather than failing outright).
    """
    if not name:
        return None
    for idx, dev_name in list_input_devices():
        if dev_name == name:
            return idx
    return None


def check_audio_input_device(device: int | None = None) -> str | None:
    """Return an error message if no working input device, else None.

    When *device* is None, checks the system default input device.
    """
    try:
        if device is not None:
            dev = sd.query_devices(device, kind="input")
        else:
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
