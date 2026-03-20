"""Whisper-based speech-to-text transcription."""

import numpy as np

_whisper_model = None


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
