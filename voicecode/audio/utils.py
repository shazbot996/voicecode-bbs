"""Audio utility functions — ALSA suppression, device selection, playback."""

import os
import ctypes
import platform

# WSL has no sound hardware; audio reaches Windows through the PulseAudio
# socket WSLg exports.  Shells started outside a WSL login session (systemd
# units, tmux servers, ssh) lose PULSE_SERVER, so point at the socket before
# PortAudio initialises.
_WSLG_PULSE_SOCKET = "/mnt/wslg/PulseServer"
if "PULSE_SERVER" not in os.environ and os.path.exists(_WSLG_PULSE_SOCKET):
    os.environ["PULSE_SERVER"] = f"unix:{_WSLG_PULSE_SOCKET}"

import sounddevice as sd
import numpy as np

from voicecode.constants import SAMPLE_RATE, CHANNELS, BLOCK_SIZE

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


# Virtual/alias PCM names exposed by ALSA that duplicate system routing
_ALSA_IGNORED_ALIASES = {
    "default", "sysdefault", "pipewire", "pulse",
    "dmix", "dsnoop", "samplerate", "speex", "lavrate",
}


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
        name = d.get("name", f"Device {i}").strip()
        # Filter out redundant ALSA pseudo-device aliases
        if name.lower() in _ALSA_IGNORED_ALIASES:
            continue
        # PortAudio sometimes exposes the same device under multiple host APIs;
        # de-dupe by name to keep the picker readable.
        if name in seen_names:
            continue
        seen_names.add(name)
        result.append((i, name))
    return result


def refresh_devices():
    """Re-scan audio hardware.

    PortAudio snapshots the device list when it initialises, so a mic plugged
    in (or a sound server started) afterwards stays invisible until we
    re-initialise.  This invalidates open streams — only call it when idle.
    """
    try:
        sd._terminate()
        sd._initialize()
    except (sd.PortAudioError, OSError):
        pass


def _default_input_index() -> int | None:
    """Index of the system default input device, or None if there isn't one."""
    try:
        idx = sd.default.device[0]
    except (sd.PortAudioError, OSError):
        return None
    return idx if idx is not None and idx >= 0 else None


def resolve_input_device(name: str | None) -> int | None:
    """Resolve a persisted device name to a current PortAudio index.

    A saved name that is still present wins.  Otherwise (no name saved, or the
    device was unplugged) use the system default, and where the host has no
    default input — common with bare ALSA and no sound server — the first
    capture device found.  Returns None when there is nothing to record from.
    """
    devices = list_input_devices()
    if name:
        for idx, dev_name in devices:
            if dev_name == name:
                return idx
    default = _default_input_index()
    if default is not None:
        return default
    return devices[0][0] if devices else None


def _is_wsl() -> bool:
    return "microsoft" in platform.uname().release.lower()


def no_input_device_message() -> str:
    """Explain why there is no mic, as specifically as the platform allows."""
    if _is_wsl():
        if not os.path.exists(_WSLG_PULSE_SOCKET):
            return ("WSL audio bridge (WSLg) is off — remove "
                    "guiApplications=false from .wslconfig, then wsl --shutdown")
        return ("WSLg audio not reachable from ALSA — "
                "install libasound2-plugins (see README)")
    if platform.system() == "Linux":
        return ("No audio input device found — check the mic is connected "
                "and shared with this machine/VM")
    return "No audio input device found."


def check_audio_input_device(device: int | None = None) -> str | None:
    """Return an error message if *device* cannot capture, else None.

    *device* is an index from resolve_input_device(); None means no input
    device exists at all.
    """
    if device is None:
        return no_input_device_message()
    try:
        dev = sd.query_devices(device)
        if dev.get("max_input_channels", 0) < 1:
            return f"Input device '{dev.get('name', '?')}' has no input channels."
        return None
    except sd.PortAudioError as e:
        return f"Audio device error: {e}"
    except Exception as e:
        return f"Cannot query audio devices: {e}"


def find_input_device(name: str | None) -> tuple[int | None, str | None]:
    """Pre-flight for capture: return (device index, error message or None).

    If nothing usable is found, re-scans hardware once so a mic plugged in
    since startup is picked up without restarting the app.
    """
    device = resolve_input_device(name)
    if device is None:
        refresh_devices()
        device = resolve_input_device(name)
    return device, check_audio_input_device(device)


def _to_mono_16k(indata: np.ndarray, source_rate: int) -> np.ndarray:
    """Convert an int16 capture block to mono float32 [-1, 1] at SAMPLE_RATE."""
    mono = indata.astype(np.float32).mean(axis=1) / 32768.0
    if source_rate == SAMPLE_RATE or len(mono) == 0:
        return mono
    step, remainder = divmod(source_rate, SAMPLE_RATE)
    if remainder == 0 and len(mono) % step == 0:
        # Whole-number ratio (48k, 32k): averaging each group also low-passes.
        return mono.reshape(-1, step).mean(axis=1)
    out_len = max(1, round(len(mono) * SAMPLE_RATE / source_rate))
    positions = np.linspace(0, len(mono) - 1, out_len)
    return np.interp(positions, np.arange(len(mono)), mono).astype(np.float32)


def open_input_stream(device: int | None, on_audio) -> sd.InputStream:
    """Open and start a capture stream that works across mic hardware.

    *on_audio(samples, status)* always receives mono float32 at SAMPLE_RATE.
    Sound servers (PulseAudio, PipeWire, CoreAudio, WASAPI) convert to that
    for us, but raw ALSA hardware — typical in a Chromebook Linux VM — only
    accepts the device's own format, and USB mics are often 44.1/48 kHz or
    stereo-only.  So if the direct open is refused, capture in the device's
    native rate/channels and convert here.  int16 is requested throughout
    because it is the one sample format every capture device supports.
    """
    def open_with(rate: int, channels: int) -> sd.InputStream:
        def callback(indata, frames, time_info, status):
            on_audio(_to_mono_16k(indata, rate), status)

        stream = sd.InputStream(
            samplerate=rate, channels=channels, dtype="int16",
            blocksize=round(BLOCK_SIZE * rate / SAMPLE_RATE),
            callback=callback, device=device)
        try:
            stream.start()
        except Exception:
            stream.close()
            raise
        return stream

    try:
        return open_with(SAMPLE_RATE, CHANNELS)
    except (sd.PortAudioError, OSError) as first_error:
        try:
            info = sd.query_devices(device, kind="input")
            native_rate = int(info["default_samplerate"])
            max_channels = int(info["max_input_channels"])
        except Exception:
            raise first_error
        attempts = [(native_rate, c) for c in (1, 2) if c <= max_channels]
        for rate, channels in attempts:
            if (rate, channels) == (SAMPLE_RATE, CHANNELS):
                continue
            try:
                return open_with(rate, channels)
            except (sd.PortAudioError, OSError):
                continue
        raise first_error


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
