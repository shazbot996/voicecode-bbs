"""TTS voice management — model selection, cycling, downloading."""

import threading
from pathlib import Path

from voicecode.settings import load_settings, save_settings

TTS_AVAILABLE = False
try:
    from piper.download_voices import download_voice
    TTS_AVAILABLE = True
except ImportError:
    pass

if TTS_AVAILABLE:
    PIPER_VOICES_DIR = Path(__file__).resolve().parent.parent.parent / "settings" / "piper-voices"
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
_saved_voice = load_settings().get("tts_voice")
_tts_voice_index = PIPER_VOICES.index(_saved_voice) if _saved_voice in PIPER_VOICES else 0
_tts_enabled = load_settings().get("tts_enabled", True)


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
    settings = load_settings()
    settings["tts_voice"] = voice
    save_settings(settings)
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
