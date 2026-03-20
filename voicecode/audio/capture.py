"""Mic recording and audio capture."""

import threading
import time
import numpy as np
import sounddevice as sd

from voicecode.constants import SAMPLE_RATE, CHANNELS, BLOCK_SIZE
from voicecode.audio.utils import check_audio_input_device
from voicecode.stt.whisper import transcribe, transcribe_with_timestamps
from voicecode.ui.colors import *


class RecordingHelper:
    def __init__(self, app):
        self.app = app

    def start_recording(self):
        app = self.app
        # Pre-flight: check audio input device is available
        dev_err = check_audio_input_device()
        if dev_err:
            app.set_status(f"Mic error: {dev_err}", CP_RECORDING)
            return

        app.recording = True
        app._rec_stop_event = threading.Event()
        with app.audio_lock:
            app.audio_frames.clear()
        app._live_preview_text = ""  # current interim transcription
        app._recording_injections.clear()

        # Clear intro/info text from dictation buffer only on first recording;
        # preserve existing fragments so SPACE adds to (not replaces) the buffer.
        if not app.fragments:
            app.dictation_pane.lines.clear()
            app.dictation_pane.scroll_offset = 0

        app.set_status("██ RECORDING — press SPACE to stop ██", CP_RECORDING)

        try:
            app._audio_stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32",
                blocksize=BLOCK_SIZE, callback=self.audio_callback)
            app._audio_stream.start()
        except (sd.PortAudioError, OSError) as e:
            app.recording = False
            app.set_status(f"Audio device error: {e}", CP_RECORDING)
            return

        # Start live transcription thread
        app._live_transcribe_thread = threading.Thread(
            target=self.live_transcribe_loop, daemon=True)
        app._live_transcribe_thread.start()

    def audio_callback(self, indata, frames, time_info, status):
        app = self.app
        if status:
            # Device error (e.g. input overflow, device disconnected)
            app.ui_queue.put(("status",
                               f"Audio: {status}",
                               CP_RECORDING))
        with app.audio_lock:
            app.audio_frames.append(indata[:, 0].copy())

    def live_transcribe_loop(self):
        """Periodically transcribe accumulated audio while recording."""
        app = self.app
        CHUNK_INTERVAL = 2.0  # transcribe every 2 seconds
        last_transcribed_samples = 0

        while not app._rec_stop_event.is_set():
            app._rec_stop_event.wait(CHUNK_INTERVAL)

            with app.audio_lock:
                if not app.audio_frames:
                    continue
                audio = np.concatenate(app.audio_frames)

            total_samples = len(audio)
            # Only re-transcribe if we have meaningful new audio
            new_samples = total_samples - last_transcribed_samples
            if new_samples < SAMPLE_RATE * 0.5:  # at least 0.5s of new audio
                continue

            if total_samples / SAMPLE_RATE < app.min_speech_duration:
                continue

            text = transcribe(audio, app.whisper_model)
            last_transcribed_samples = total_samples
            if text:
                app._live_preview_text = text
                # Include any mid-recording injections in the preview
                if app._recording_injections:
                    preview = text + " " + " ".join(
                        inj[1] for inj in app._recording_injections)
                    app.ui_queue.put(("live_preview", preview))
                else:
                    app.ui_queue.put(("live_preview", text))

    def stop_recording(self):
        app = self.app
        app.recording = False
        app._rec_stop_event.set()

        try:
            app._audio_stream.stop()
            app._audio_stream.close()
        except Exception:
            pass

        # Wait for live transcribe thread to finish so no stale preview
        # arrives after the final fragment is added to the dictation buffer.
        if hasattr(app, '_live_transcribe_thread'):
            app._live_transcribe_thread.join(timeout=5.0)

        with app.audio_lock:
            if not app.audio_frames:
                app.set_status("No audio captured.")
                return
            audio = np.concatenate(app.audio_frames)
            app.audio_frames.clear()

        duration = len(audio) / SAMPLE_RATE
        if duration < app.min_speech_duration:
            app.set_status(f"Too short ({duration:.1f}s), discarded.")
            return

        # Final transcription (full audio for best accuracy)
        app.set_status(f"Final transcription of {duration:.1f}s...")
        injections = list(app._recording_injections)
        app._recording_injections.clear()
        threading.Thread(target=self.do_final_transcribe, args=(audio, injections), daemon=True).start()

    def do_final_transcribe(self, audio: np.ndarray,
                            injections: list[tuple[float, str]] | None = None):
        app = self.app
        # Remove live preview line, replace with final
        app.ui_queue.put(("remove_live_preview", None))

        peak = np.max(np.abs(audio)) if len(audio) > 0 else 0

        if injections:
            # Use word timestamps to insert folder paths at the right positions
            text, words = transcribe_with_timestamps(audio, app.whisper_model)
            if text and words:
                text = self.merge_injections(words, injections)
            elif text:
                # Fallback: append injections at the end
                text = text + " " + " ".join(inj[1] for inj in injections)
            else:
                # No speech detected, just use injections as the fragment
                text = " ".join(inj[1] for inj in injections)
        else:
            text = transcribe(audio, app.whisper_model)

        if not text:
            msg = "No speech detected."
            if peak < 0.005:
                # Help diagnose Crostini mic drop issues
                msg = "No speech detected (Mic volume too low?)"
            app.ui_queue.put(("status", msg, CP_STATUS))
            return
        app.ui_queue.put(("fragment", text))
        label = f"Added: \"{text[:50]}\"" if len(text) > 50 else f"Added: \"{text}\""
        app.ui_queue.put(("status", label, CP_STATUS))

    @staticmethod
    def merge_injections(words: list[tuple[float, float, str]],
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

    def echo_test(self):
        """Record 1 second of audio and play it back immediately."""
        app = self.app
        dev_err = check_audio_input_device()
        if dev_err:
            app.set_status(f"Echo test failed: {dev_err}", CP_RECORDING)
            return
        app.set_status("Echo test: recording 1 second...", CP_RECORDING)
        threading.Thread(target=self.do_echo_test, daemon=True).start()

    def do_echo_test(self):
        app = self.app
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
            app.ui_queue.put(("status",
                               f"Echo test: mic open failed — {e}",
                               CP_RECORDING))
            return

        time.sleep(1.0)

        try:
            stream.stop()
            stream.close()
        except Exception:
            pass  # stream teardown errors are non-fatal

        if not frames:
            app.ui_queue.put(("status", "Echo test: no audio captured.", CP_STATUS))
            return

        audio = np.concatenate(frames)
        peak = np.max(np.abs(audio))
        rms = np.sqrt(np.mean(audio ** 2))

        app.ui_queue.put(("status",
                           f"Echo test: playing back (peak={peak:.3f}, rms={rms:.4f})...",
                           CP_STATUS))

        # Play it back at the default output device
        try:
            sd.play(audio, samplerate=SAMPLE_RATE)
            sd.wait()
        except (sd.PortAudioError, OSError) as e:
            app.ui_queue.put(("status",
                               f"Echo test: playback failed — {e}",
                               CP_RECORDING))
            return

        app.ui_queue.put(("status",
                           f"Echo test done. Peak={peak:.3f} RMS={rms:.4f} "
                           f"({'good signal' if peak > 0.05 else 'very quiet!'})",
                           CP_STATUS))
