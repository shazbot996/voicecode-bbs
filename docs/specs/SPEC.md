---
title: "Speech-to-Text Subsystem"
scope: voicecode/stt/
date: 2026-03-21
---

## 1. Problem Statement

VoiceCode is a voice-driven prompt engineering workshop — users dictate prompts by speaking into a microphone. Raw audio must be converted to text before it can be refined, edited, or sent to an AI agent. Without a speech-to-text subsystem, the entire voice-driven workflow is impossible.

The STT subsystem must serve two distinct use cases:

1. **Live preview** — low-latency interim transcriptions while the user is still speaking, so they can see what's being captured.
2. **Final transcription** — a high-accuracy pass over the complete recording once the user stops, optionally enriched with word-level timestamps to support mid-recording shortcut injection (merging file paths or other strings into the transcript at the correct temporal position).

## 2. Goals & Non-Goals

### Goals

- Provide accurate English speech-to-text transcription using locally-run models (no cloud API dependency).
- Support multiple model sizes (tiny, base, small, medium) so users can trade accuracy for speed.
- Lazy-load models on first use to keep application startup fast.
- Allow runtime model switching from the settings overlay without restarting the app.
- Expose both plain transcription and timestamp-annotated transcription for shortcut injection.
- Run on CPU-only hardware (no GPU required).

### Non-Goals

- Multi-language support (all models use `.en` English-only variants).
- Streaming/online decoding (the subsystem transcribes accumulated audio buffers, not a continuous stream).
- Speaker diarization or speaker identification.
- Audio preprocessing (normalization, noise reduction) — this is handled upstream.
- Direct user interaction — the STT module is a pure computation layer with no UI of its own.

## 3. Proposed Solution

The subsystem wraps the `faster-whisper` library (a CTranslate2-based reimplementation of OpenAI's Whisper) behind a thin Python module at `voicecode/stt/whisper.py`. It exposes three public functions:

| Function | Purpose |
|----------|---------|
| `get_whisper_model(model_size)` | Lazy-load and cache the Whisper model singleton |
| `transcribe(audio, model_size)` | Transcribe audio to plain text |
| `transcribe_with_timestamps(audio, model_size)` | Transcribe audio and return word-level `(start, end, word)` tuples |

This approach was chosen because:

- **Local inference** avoids network latency and cloud costs, which matters for an interactive voice loop.
- **`faster-whisper`** is significantly faster than the original Whisper on CPU, using INT8 quantization via CTranslate2.
- **Singleton model caching** avoids repeated multi-second model loads.
- **Two transcription modes** cleanly separate the common case (plain text) from the specialized case (timestamp-aware injection), keeping the API minimal.

## 4. Technical Design

### 4.1 Module Structure

```
voicecode/stt/
├── __init__.py          # Package marker (comment-only)
└── whisper.py           # All STT logic
```

### 4.2 Model Management — `get_whisper_model()`

**File:** `voicecode/stt/whisper.py:8-13`

A module-level global `_whisper_model` holds the singleton. On first call, `faster_whisper.WhisperModel` is instantiated with:

- `device="cpu"` — CPU-only inference (no CUDA dependency)
- `compute_type="int8"` — quantized weights for speed on CPU

The `from faster_whisper import WhisperModel` is deferred inside the function body to avoid import-time overhead (torch/ctranslate2 are heavy).

**Model invalidation:** When the user changes the model size in the settings overlay, `voicecode/ui/settings_overlay.py:703-708` sets `_whisper_mod._whisper_model = None`, forcing a fresh load on the next transcription call.

**Startup preload:** `voicecode/app.py:422` calls `get_whisper_model(self.whisper_model)` during the loading screen to warm the cache before the user starts recording.

### 4.3 Plain Transcription — `transcribe()`

**File:** `voicecode/stt/whisper.py:16-21`

Accepts a NumPy `float32` array (16 kHz mono) and returns a single string. Key parameters passed to `model.transcribe()`:

- `beam_size=3` — moderate beam search for accuracy without excessive latency.
- `vad_filter=True` — `faster-whisper`'s built-in Silero VAD filter to skip silence segments, reducing hallucinations on quiet audio.

Auto-casts `audio` to `float32` if needed.

### 4.4 Timestamp Transcription — `transcribe_with_timestamps()`

**File:** `voicecode/stt/whisper.py:24-37`

Same as `transcribe()` but additionally passes `word_timestamps=True`. Returns a tuple of `(full_text, words)` where `words` is a list of `(start_sec, end_sec, word_str)` triples.

This is used exclusively by `RecordingHelper.do_final_transcribe()` in `voicecode/audio/capture.py:145` when mid-recording shortcut injections need to be merged into the transcript at the correct temporal positions.

### 4.5 Data Flow

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│ sounddevice  │────▸│ audio_frames │────▸│ stt.transcribe  │
│ InputStream  │     │ (app state)  │     │ or _with_stamps │
└─────────────┘     └──────────────┘     └────────┬────────┘
                                                   │
                                                   ▼
                                          ┌────────────────┐
                                          │ ui_queue events │
                                          │ ("live_preview" │
                                          │  or "fragment") │
                                          └────────────────┘
```

1. `sounddevice.InputStream` feeds 30ms audio blocks (480 samples at 16 kHz) into `app.audio_frames` via `audio_callback()`.
2. **Live preview path:** `live_transcribe_loop()` runs on a daemon thread, waking every 2 seconds. If at least 0.5s of new audio has accumulated (and total duration exceeds `min_speech_duration`), it calls `transcribe()` and pushes a `("live_preview", text)` event to `app.ui_queue`.
3. **Final path:** After `stop_recording()`, `do_final_transcribe()` runs on a fresh daemon thread. It calls either `transcribe_with_timestamps()` (if injections exist) or `transcribe()`, then pushes a `("fragment", text)` event.

### 4.6 Configurable Model Sizes

Available model sizes are defined in `voicecode/ui/settings_overlay.py:225`:

```python
["tiny.en", "base.en", "small.en", "medium.en"]
```

The user's choice is persisted via `persist_setting("whisper_model", val)` and restored at startup from `settings.json` (`voicecode/app.py:259`), defaulting to `"base.en"`.

## 5. UI / UX

The STT module itself has no UI, but it drives two visible behaviors:

1. **Live preview line** in the dictation buffer — updated every ~2 seconds while recording. Shown as interim text that gets replaced by the final transcription.
2. **Settings overlay** (`O` key → Voice/STT submenu) — a menu item labeled "Whisper Model" lets the user cycle through `tiny.en`, `base.en`, `small.en`, `medium.en`. Changing the model sets a status message: *"Whisper model → {val} (will load on next recording)"*.

## 6. Integration Points

| Component | Integration |
|-----------|-------------|
| `voicecode/audio/capture.py` (`RecordingHelper`) | Primary consumer — calls `transcribe()` for live preview and final transcription; calls `transcribe_with_timestamps()` for injection merging |
| `voicecode/app.py` | Preloads the model at startup via `get_whisper_model(self.whisper_model)`; stores `self.whisper_model` (the model size string) |
| `voicecode/ui/settings_overlay.py` | Exposes model selection UI; resets `_whisper_mod._whisper_model = None` to force reload on change |
| `voicecode/constants.py` | Defines `SAMPLE_RATE` (16000), `CHANNELS` (1), `MIN_SPEECH_DURATION_SEC` (0.3) used by callers |

### External Dependencies

- **`faster-whisper`** — CTranslate2-based Whisper inference engine
- **`numpy`** — audio data representation (`np.ndarray` of `float32`)
- **PyTorch (CPU)** — transitive dependency via faster-whisper's Silero VAD filter

## 7. Edge Cases & Error Handling

| Scenario | Handling |
|----------|----------|
| Audio dtype is not `float32` | Both `transcribe()` and `transcribe_with_timestamps()` auto-cast via `audio.astype(np.float32)` |
| Recording too short | Caller checks `duration < min_speech_duration` before calling STT; short recordings are discarded with a status message |
| No speech detected (empty transcript) | Caller checks for empty string; if audio peak < 0.005, shows "Mic volume too low?" hint |
| Live preview during very short recordings | `live_transcribe_loop` requires at least 0.5s of new audio and `min_speech_duration` total before calling `transcribe()` |
| Model size changed mid-recording | The singleton is only nullified on setting change; the in-progress recording continues using the already-loaded model. The new model loads on the next transcription call. |
| Whisper hallucinations on silence | Mitigated by `vad_filter=True` which uses Silero VAD internally to skip non-speech segments |

### Thread Safety

- The STT functions themselves are stateless aside from the model singleton. `get_whisper_model()` uses a simple global with no lock, which is safe in CPython due to the GIL (model loading is a single atomic assignment).
- Audio frames are protected by `app.audio_lock` in the caller.
- The live transcribe thread is joined with a 5-second timeout on recording stop to prevent stale previews.

## 8. Scope & Milestones

The STT subsystem as described is fully implemented. The current scope covers:

- **Delivered:** Singleton model management, plain transcription, timestamp transcription, configurable model sizes, live preview integration, settings UI for model switching.
- **Potential future iterations:**
  - GPU acceleration (device selection beyond `"cpu"`).
  - Non-English model support.
  - Streaming/online decoding for lower-latency previews.
  - Confidence scores or alternative hypotheses exposed to the UI.
  - Model download progress indication for larger models.

## 9. Success Criteria

| Criterion | Verification |
|-----------|-------------|
| Dictated speech is accurately transcribed to text | Speak clearly into mic; resulting fragment matches spoken words |
| Live preview updates during recording | While recording, interim text appears in the dictation buffer within ~2-3 seconds |
| Model switching works without restart | Change model in settings overlay; next recording uses the new model (visible in transcription quality/speed change) |
| Shortcut injection merges at correct position | Press Tab during recording to inject a path; the path appears in the final transcript at the temporal position where it was injected |
| No crash on short/silent recordings | Tap SPACE quickly or record silence; app shows appropriate status message without errors |
| INT8 CPU inference completes in reasonable time | A 10-second recording transcribes in under ~3 seconds on `base.en` |

## 10. Open Questions

- **Model download UX:** Larger models (`small.en`, `medium.en`) require significant downloads on first use. There is currently no progress indicator — the app appears to freeze during the loading screen. Should a download progress bar be added?
- **Concurrent transcription safety:** The singleton model has no mutex. If two threads call `get_whisper_model()` simultaneously before the model is loaded, two models could be instantiated (the second assignment wins, the first is garbage-collected). This is benign but wasteful. Worth adding a lock?
- **VAD redundancy:** The app runs Silero VAD separately (in `voicecode/audio/vad.py`) for recording segmentation, and `faster-whisper` runs its own internal Silero VAD via `vad_filter=True`. This means VAD runs twice on the same audio. Is this intentional for defense-in-depth, or should one layer be removed?
