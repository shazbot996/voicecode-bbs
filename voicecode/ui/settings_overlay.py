"""Settings overlay — modal settings panel with submenus."""

import curses
import shutil
import threading
from pathlib import Path

from voicecode.ui.colors import (
    CP_HEADER, CP_HELP, CP_RECORDING, CP_AGENT,
    CP_SETTINGS_TITLE, CP_SECT_RED, CP_SUBMENU,
)
from voicecode.settings import load_settings, save_settings, persist_setting
from voicecode.tts.voices import (
    TTS_AVAILABLE, PIPER_VOICES, get_tts_voice_name, get_tts_voice_model,
    cycle_tts_voice, delete_unused_voices, download_all_voices,
    download_single_voice_model,
)
from voicecode.tts.voices import _tts_voice_index as _voices_tts_voice_index
from voicecode.tts.engine import speak_text, stop_speaking
from voicecode.tts.cast import CAST_AVAILABLE, discover_cast_devices, cast_tts_to_devices
import voicecode.tts.voices as _voices_mod
import voicecode.tts.engine as _engine_mod
from voicecode.stt.whisper import get_whisper_model
import voicecode.stt.whisper as _whisper_mod
import voicecode.constants as _constants_mod


class SettingsOverlay:
    """Settings overlay with submenus.

    Receives a reference to the main BBSApp instance (*app*) so it can
    read and mutate shared application state.
    """

    def __init__(self, app):
        self.app = app

    # ─── helpers ────────────────────────────────────────────────────

    def _set_status(self, msg):
        self.app.set_status(msg)

    # ─── Build main settings list ───────────────────────────────────

    def build_settings_items(self):
        """Build the list of settings for the settings modal."""
        app = self.app
        app.settings_items = [
            {"type": "section", "label": "TOOLS & CONFIGURATION", "style": "yellow"},
            {
                "key": "working_dir",
                "label": "Working Directory",
                "desc": "Project root (prompts/ and docs/ subfolders auto-used)",
                "options": None,
                "get": lambda: app.working_dir or "(not set)",
                "set": None,
                "editable": True,
                "action": self.start_editing_working_dir,
            },
            {
                "key": "_action_voice_submenu",
                "label": "Voice Settings",
                "desc": "Whisper model, VAD threshold, silence timeout, min speech",
                "options": None,
                "get": lambda: app.whisper_model,
                "set": None,
                "action": self.open_voice_submenu,
                "submenu": True,
            },
            {
                "key": "_action_ai_models_submenu",
                "label": "AI Models",
                "desc": "Select AI provider (Claude, Gemini, etc.)",
                "options": None,
                "get": lambda: app.ai_provider.name,
                "set": None,
                "action": self.open_ai_models_submenu,
                "submenu": True,
            },
        ]
        if TTS_AVAILABLE:
            app.settings_items.append({
                "key": "_action_tts_submenu",
                "label": "Text-to-Speech Settings",
                "desc": "Configure TTS voices, libraries, and enable/disable",
                "options": None,
                "get": lambda: "ON" if app.tts_enabled else "OFF",
                "set": None,
                "action": self.open_tts_submenu,
                "submenu": True,
            })
        else:
            app.settings_items.append({
                "key": "_action_tts_submenu",
                "label": "Text-to-Speech Settings",
                "desc": "TTS library not installed.",
                "options": None,
                "get": lambda: "UNAVAILABLE",
                "set": None,
                "action": None,
                "submenu": True,
            })

        app.settings_items.append({
            "key": "typewriter_speed",
            "label": "Typewriter Speed",
            "desc": "Agent text streaming speed (characters per second)",
            "options": [50, 100, 200, 400, 800, 1500],
            "get": lambda: app._typewriter_chars_per_sec,
            "set": self.set_typewriter_speed,
        })

        app.settings_items.append({
            "key": "_action_test_tools_submenu",
            "label": "Test Tools",
            "desc": "Echo test, TTS test sound, and volume controls",
            "options": None,
            "get": lambda: "",
            "set": None,
            "action": self.open_test_tools_submenu,
            "submenu": True,
        })

        if CAST_AVAILABLE:
            app.settings_items.append({
                "key": "_action_cast_submenu",
                "label": "Google Cast Notifications",
                "desc": "Send TTS announcements to Nest / Chromecast speakers",
                "options": None,
                "get": lambda: "ON" if app.cast_enabled else "OFF",
                "set": None,
                "action": self.open_cast_submenu,
                "submenu": True,
            })
        else:
            app.settings_items.append({
                "key": "_action_cast_submenu",
                "label": "Google Cast Notifications",
                "desc": "pychromecast not installed (pip install pychromecast)",
                "options": None,
                "get": lambda: "UNAVAILABLE",
                "set": None,
                "action": None,
                "submenu": True,
            })

    # ─── TTS submenu ────────────────────────────────────────────────

    def build_tts_submenu_items(self):
        """Build the TTS sub-menu items list."""
        app = self.app
        return [
            {
                "key": "tts_enabled",
                "label": "Enable/Disable TTS",
                "desc": "Turn text-to-speech on or off entirely",
                "options": ["ON", "OFF"],
                "get": lambda: "ON" if app.tts_enabled else "OFF",
                "set": self.set_tts_enabled,
            },
            {
                "key": "tts_volume_gain",
                "label": "Volume Gain",
                "desc": "Digital volume boost multiplier",
                "options": ["1.0", "1.5", "2.0", "2.5", "3.0"],
                "get": lambda: f"{app.tts_volume_gain:.1f}",
                "set": self.set_tts_volume_gain,
            },
            {
                "key": "tts_voice",
                "label": "Configure Voices",
                "desc": "Text-to-speech voice for spoken summaries",
                "options": PIPER_VOICES,
                "get": get_tts_voice_name,
                "set": self.set_tts_voice,
            },
            {
                "key": "_action_test_speech",
                "label": "[Enter] Test Current Voice",
                "desc": "Speak a test sentence with the active voice profile",
                "options": None,
                "get": lambda: "",
                "set": None,
                "action": self.action_test_speech,
            },
            {
                "key": "_action_download_current_voice",
                "label": "[Enter] Download Current Voice Model",
                "desc": "Fetch only the sound profile currently selected above",
                "options": None,
                "get": lambda: "",
                "set": None,
                "action": self.action_download_current_voice,
            },
            {
                "key": "_action_download_voices",
                "label": "[Enter] Download All Voice Models",
                "desc": "\u26a0 WARNING: Large download \u2014 fetches all Piper voice files",
                "options": None,
                "get": lambda: "",
                "set": None,
                "action": self.action_download_voices,
            },
            {
                "key": "_action_clean_voices",
                "label": "[Enter] Clean Unused Voice Models",
                "desc": "Delete downloaded voice models not currently selected",
                "options": None,
                "get": lambda: "",
                "set": None,
                "action": self.action_clean_voices,
            },
        ]

    # ─── Voice submenu ──────────────────────────────────────────────

    def build_voice_submenu_items(self):
        """Build the Voice Settings sub-menu items list."""
        app = self.app
        return [
            {
                "key": "whisper_model",
                "label": "Whisper Model",
                "desc": "Speech-to-text model (larger = slower but more accurate)",
                "options": ["tiny.en", "base.en", "small.en", "medium.en"],
                "get": lambda: app.whisper_model,
                "set": self.set_whisper_model,
            },
            {
                "key": "vad_threshold",
                "label": "VAD Threshold",
                "desc": "Voice activity sensitivity (lower = more sensitive)",
                "options": [0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
                "get": lambda: app.vad_threshold,
                "set": self.set_vad_threshold,
            },
            {
                "key": "silence_timeout",
                "label": "Silence Timeout",
                "desc": "Seconds of silence before auto-stop (handsfree mode)",
                "options": [0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
                "get": lambda: app.silence_timeout,
                "set": self.set_silence_timeout,
            },
            {
                "key": "min_speech_duration",
                "label": "Min Speech Duration",
                "desc": "Minimum seconds of speech to accept a recording",
                "options": [0.1, 0.2, 0.3, 0.5, 0.7, 1.0],
                "get": lambda: app.min_speech_duration,
                "set": self.set_min_speech,
            },
        ]

    def open_voice_submenu(self):
        """Open the Voice Settings sub-menu."""
        app = self.app
        app.voice_submenu_open = True
        app.voice_submenu_cursor = 0
        app._settings_scroll_top = 0
        app.voice_submenu_items = self.build_voice_submenu_items()
        app.show_settings_overlay = True

    def voice_submenu_cycle(self, direction):
        """Cycle the current Voice sub-menu setting's value."""
        app = self.app
        item = app.voice_submenu_items[app.voice_submenu_cursor]
        if item.get("options") is None:
            return
        options = item["options"]
        current = item["get"]()
        try:
            idx = options.index(current)
        except ValueError:
            idx = 0
        new_idx = (idx + direction) % len(options)
        item["set"](options[new_idx])

    # ─── AI Models submenu ──────────────────────────────────────────

    def build_ai_models_submenu_items(self):
        """Build the AI Models sub-menu items list."""
        app = self.app
        from voicecode.providers import detect_providers, get_provider_by_name

        all_provider_names = [p.name for p in detect_providers()]
        items = []
        if all_provider_names:
            items.append({
                "key": "ai_provider",
                "label": "Active Provider",
                "desc": "AI CLI to use for refinement and agent execution",
                "options": all_provider_names,
                "get": lambda: app.ai_provider.name,
                "set": self.set_ai_provider,
            })

        # Custom command for Gemini
        gemini_provider = get_provider_by_name("Gemini")
        if gemini_provider:
            items.append({
                "key": "gemini_command",
                "label": "Gemini CLI Command",
                "desc": "Custom command/path for Gemini CLI",
                "options": None,
                "get": lambda: gemini_provider.command_override or gemini_provider.binary,
                "set": None,
                "editable": True,
                "action": self.start_editing_gemini_command,
            })

        # Gemini --proxy=false toggle
        if gemini_provider:
            items.append({
                "key": "gemini_disable_proxy",
                "label": "Gemini Disable Proxy",
                "desc": "Pass --proxy=false to Gemini CLI",
                "options": ["On", "Off"],
                "get": lambda: "On" if gemini_provider.disable_proxy else "Off",
                "set": self._set_gemini_disable_proxy,
            })

        # Show provider info for all known providers
        for p in detect_providers():
            if p.is_installed():
                ver = p.get_version() or "unknown"
                base_cmd = p._get_base_cmd()[0]
                path = shutil.which(base_cmd) or base_cmd
                items.append({
                    "key": f"_info_{p.name.lower()}",
                    "label": f"{p.name} CLI",
                    "desc": f"{path}",
                    "options": None,
                    "get": lambda v=ver: v,
                    "set": None,
                })
            else:
                items.append({
                    "key": f"_info_{p.name.lower()}",
                    "label": f"{p.name} CLI",
                    "desc": "not installed",
                    "options": None,
                    "get": lambda: "UNAVAILABLE",
                    "set": None,
                })
        return items

    def set_ai_provider(self, name):
        """Switch the active AI provider."""
        from voicecode.providers import get_provider_by_name

        app = self.app
        provider = get_provider_by_name(name)
        if provider and not provider.is_installed():
            self._set_status(
                f"{name} was not found. Available providers are checked on startup."
            )
            return
        if provider:
            app.ai_provider = provider
            persist_setting("ai_provider", name)
            app.runner.clear_session()
            self._set_status(f"AI provider switched to {name}.")

    def _set_gemini_disable_proxy(self, value):
        """Toggle Gemini --proxy=false flag."""
        from voicecode.providers import get_provider_by_name

        gemini_provider = get_provider_by_name("Gemini")
        if gemini_provider:
            enabled = value == "On"
            gemini_provider.disable_proxy = enabled
            persist_setting("gemini_disable_proxy", enabled)
            state = "enabled" if enabled else "disabled"
            self._set_status(f"Gemini --proxy=false {state}.")

    def open_ai_models_submenu(self):
        """Open the AI Models sub-menu."""
        app = self.app
        app.ai_models_submenu_open = True
        app.ai_models_submenu_cursor = 0
        app._settings_scroll_top = 0
        app.ai_models_submenu_items = self.build_ai_models_submenu_items()
        app.show_settings_overlay = True

    def ai_models_submenu_cycle(self, direction):
        """Cycle the current AI Models sub-menu setting's value."""
        app = self.app
        item = app.ai_models_submenu_items[app.ai_models_submenu_cursor]
        if item.get("options") is None:
            return
        options = item["options"]
        current = item["get"]()
        try:
            idx = options.index(current)
        except ValueError:
            idx = 0
        new_idx = (idx + direction) % len(options)
        item["set"](options[new_idx])

    # ─── TTS submenu open/cycle ─────────────────────────────────────

    def open_tts_submenu(self):
        """Open the TTS settings sub-menu."""
        app = self.app
        app.tts_submenu_open = True
        app.tts_submenu_cursor = 0
        app._settings_scroll_top = 0
        app.tts_submenu_items = self.build_tts_submenu_items()
        app.show_settings_overlay = True

    def tts_submenu_cycle(self, direction):
        """Cycle the current TTS sub-menu setting's value."""
        app = self.app
        item = app.tts_submenu_items[app.tts_submenu_cursor]
        if item.get("options") is None:
            return
        options = item["options"]
        current = item["get"]()
        try:
            idx = options.index(current)
        except ValueError:
            idx = 0
        new_idx = (idx + direction) % len(options)
        item["set"](options[new_idx])

    # ─── Test Tools submenu ─────────────────────────────────────────

    def build_test_tools_items(self):
        """Build the Test Tools sub-menu items list."""
        app = self.app
        items = [
            {
                "key": "_action_echo_test",
                "label": "[Enter] Echo / Mic Test",
                "desc": "Record 1s of audio and play it back to test your mic",
                "options": None,
                "get": lambda: "",
                "set": None,
                "action": app.recording_helper.echo_test,
            },
        ]
        if TTS_AVAILABLE:
            items.extend([
                {
                    "key": "_action_test_speech",
                    "label": "[Enter] Play TTS Test Sound",
                    "desc": "Speak a test sentence with the active voice profile",
                    "options": None,
                    "get": lambda: "",
                    "set": None,
                    "action": self.action_test_speech,
                },
                {
                    "key": "tts_volume_gain",
                    "label": "TTS Volume Gain",
                    "desc": "Digital volume boost multiplier",
                    "options": ["1.0", "1.5", "2.0", "2.5", "3.0"],
                    "get": lambda: f"{app.tts_volume_gain:.1f}",
                    "set": self.set_tts_volume_gain,
                },
            ])
        if CAST_AVAILABLE and TTS_AVAILABLE:
            items.append({
                "key": "_action_cast_broadcast_test",
                "label": "[Enter] Chromecast Broadcast Test",
                "desc": "Type a message and broadcast it via TTS to Cast devices",
                "options": None,
                "get": lambda: "",
                "set": None,
                "action": self.start_cast_broadcast_test,
                "editable": True,
            })
        return items

    def open_test_tools_submenu(self):
        """Open the Test Tools sub-menu."""
        app = self.app
        app.test_tools_submenu_open = True
        app.test_tools_submenu_cursor = 0
        app._settings_scroll_top = 0
        app.test_tools_submenu_items = self.build_test_tools_items()
        app.show_settings_overlay = True

    def test_tools_submenu_cycle(self, direction):
        """Cycle the current Test Tools sub-menu setting's value."""
        app = self.app
        item = app.test_tools_submenu_items[app.test_tools_submenu_cursor]
        if item.get("options") is None:
            return
        options = item["options"]
        current = item["get"]()
        try:
            idx = options.index(current)
        except ValueError:
            idx = 0
        new_idx = (idx + direction) % len(options)
        item["set"](options[new_idx])

    # ─── Google Cast submenu ────────────────────────────────────────

    def build_cast_submenu_items(self):
        """Build the Google Cast sub-menu items list."""
        app = self.app
        items = [
            {
                "key": "cast_enabled",
                "label": "Enable Cast Notifications",
                "desc": "Send TTS summary to Cast speakers on agent completion",
                "options": ["ON", "OFF"],
                "get": lambda: "ON" if app.cast_enabled else "OFF",
                "set": self.set_cast_enabled,
            },
        ]
        if app.cast_enabled:
            items += [
                {
                    "key": "cast_volume",
                    "label": "Cast Volume",
                    "desc": "Force device volume before playback (0-100%)",
                    "options": ["20%", "40%", "60%", "80%", "100%"],
                    "get": lambda: f"{int(app.cast_volume * 100)}%",
                    "set": self.set_cast_volume,
                },
                {
                    "key": "cast_mute_local_tts",
                    "label": "Mute Local TTS",
                    "desc": "Play TTS only on Cast speakers, not locally",
                    "options": ["ON", "OFF"],
                    "get": lambda: "ON" if app.cast_mute_local_tts else "OFF",
                    "set": self.set_cast_mute_local_tts,
                },
                {
                    "key": "_action_cast_scan",
                    "label": "[Enter] Scan for Devices",
                    "desc": "Discover Cast devices and speaker groups on your network",
                    "options": None,
                    "get": lambda: "scanning..." if app.cast_scanning else "",
                    "set": None,
                    "action": self.action_cast_scan,
                },
            ]

        # Add a section header and device list if we have discovered devices
        if app.cast_discovered_devices:
            items.append({
                "type": "section",
                "label": f"DEVICES ({len(app.cast_discovered_devices)})",
                "style": "yellow",
            })
            for dev_name in app.cast_discovered_devices:
                items.append({
                    "key": f"_cast_dev_{dev_name}",
                    "label": dev_name,
                    "desc": "Cast-enabled speaker or group",
                    "options": ["ON", "OFF"],
                    "get": self._make_cast_dev_getter(dev_name),
                    "set": self._make_cast_dev_setter(dev_name),
                })

        # Show previously-selected devices that weren't found in latest scan
        missing = [d for d in app.cast_selected_devices
                   if d not in app.cast_discovered_devices]
        if missing:
            items.append({
                "type": "section",
                "label": "SAVED",
                "style": "red",
            })
            for dev_name in missing:
                items.append({
                    "key": f"_cast_dev_{dev_name}",
                    "label": dev_name,
                    "desc": "Previously selected \u2014 not found in latest scan",
                    "options": ["ON", "OFF"],
                    "get": self._make_cast_dev_getter(dev_name),
                    "set": self._make_cast_dev_setter(dev_name),
                })

        return items

    def _make_cast_dev_getter(self, dev_name):
        """Return a lambda that checks whether dev_name is selected."""
        app = self.app
        return lambda: "ON" if dev_name in app.cast_selected_devices else "OFF"

    def _make_cast_dev_setter(self, dev_name):
        """Return a function that toggles dev_name in the selected set."""
        app = self.app

        def _toggle(val):
            if val == "ON" and dev_name not in app.cast_selected_devices:
                app.cast_selected_devices.append(dev_name)
            elif val == "OFF" and dev_name in app.cast_selected_devices:
                app.cast_selected_devices.remove(dev_name)
            persist_setting("cast_selected_devices", app.cast_selected_devices)
            n = len(app.cast_selected_devices)
            self._set_status(
                f"{dev_name} {'selected' if val == 'ON' else 'deselected'} "
                f"({n} device{'s' if n != 1 else ''} total)")

        return _toggle

    def open_cast_submenu(self):
        """Open the Google Cast sub-menu."""
        app = self.app
        app.cast_submenu_open = True
        app.cast_submenu_cursor = 0
        app._settings_scroll_top = 0
        app.cast_submenu_items = self.build_cast_submenu_items()
        app.show_settings_overlay = True

    def cast_submenu_cycle(self, direction):
        """Cycle the current Cast sub-menu setting's value."""
        app = self.app
        selectable = [it for it in app.cast_submenu_items
                      if it.get("type") != "section"]
        if not selectable or app.cast_submenu_cursor >= len(selectable):
            return
        item = selectable[app.cast_submenu_cursor]
        if item.get("options") is None:
            return
        options = item["options"]
        current = item["get"]()
        try:
            idx = options.index(current)
        except ValueError:
            idx = 0
        new_idx = (idx + direction) % len(options)
        item["set"](options[new_idx])

    # ─── Cast setters ───────────────────────────────────────────────

    def set_cast_enabled(self, val):
        app = self.app
        app.cast_enabled = (val == "ON")
        persist_setting("cast_enabled", app.cast_enabled)
        if not app.cast_enabled and app.cast_mute_local_tts:
            app.cast_mute_local_tts = False
            persist_setting("cast_mute_local_tts", False)
        app.cast_submenu_items = self.build_cast_submenu_items()
        state = "enabled" if app.cast_enabled else "disabled"
        self._set_status(f"Google Cast notifications {state}")

    def set_cast_volume(self, val):
        app = self.app
        try:
            app.cast_volume = int(val.rstrip("%")) / 100.0
        except (ValueError, AttributeError):
            app.cast_volume = 0.8
        persist_setting("cast_volume", app.cast_volume)
        self._set_status(f"Cast volume set to {int(app.cast_volume * 100)}%")

    def set_cast_mute_local_tts(self, val):
        app = self.app
        app.cast_mute_local_tts = (val == "ON")
        persist_setting("cast_mute_local_tts", app.cast_mute_local_tts)
        state = "muted" if app.cast_mute_local_tts else "unmuted"
        self._set_status(f"Local TTS {state} (Cast only)")

    def action_cast_scan(self):
        """Scan for Cast devices in a background thread."""
        app = self.app
        if app.cast_scanning:
            return
        app.cast_scanning = True
        # Rebuild to show "scanning..." hint
        app.cast_submenu_items = self.build_cast_submenu_items()

        def _scan():
            discover_cast_devices(ui_queue=app.ui_queue)
            app.cast_scanning = False

        threading.Thread(target=_scan, daemon=True).start()

    # ─── TTS setters ────────────────────────────────────────────────

    def set_tts_enabled(self, val):
        app = self.app
        app.tts_enabled = (val == "ON")
        _engine_mod._tts_enabled = app.tts_enabled
        persist_setting("tts_enabled", app.tts_enabled)
        state = "enabled" if app.tts_enabled else "disabled"
        self._set_status(f"Text-to-speech {state}")

    def set_tts_volume_gain(self, val):
        app = self.app
        try:
            app.tts_volume_gain = float(val)
        except ValueError:
            app.tts_volume_gain = 1.0
        persist_setting("tts_volume_gain", app.tts_volume_gain)
        self._set_status(f"TTS Volume Gain set to {app.tts_volume_gain:.1f}x")

    def set_typewriter_speed(self, val):
        app = self.app
        app._typewriter_chars_per_sec = val
        persist_setting("typewriter_speed", val)
        self._set_status(f"Typewriter speed set to {val} chars/sec")

    # ─── Voice / STT setters ───────────────────────────────────────

    def set_whisper_model(self, val):
        app = self.app
        if val != app.whisper_model:
            app.whisper_model = val
            _whisper_mod._whisper_model = None  # force reload on next use
            persist_setting("whisper_model", val)
            self._set_status(f"Whisper model \u2192 {val} (will load on next recording)")

    def set_vad_threshold(self, val):
        app = self.app
        app.vad_threshold = val
        _constants_mod.VAD_THRESHOLD = val
        persist_setting("vad_threshold", val)

    def set_silence_timeout(self, val):
        app = self.app
        app.silence_timeout = val
        _constants_mod.SILENCE_AFTER_SPEECH_SEC = val
        persist_setting("silence_timeout", val)

    def set_min_speech(self, val):
        app = self.app
        app.min_speech_duration = val
        _constants_mod.MIN_SPEECH_DURATION_SEC = val
        persist_setting("min_speech_duration", val)

    def set_tts_voice(self, val):
        if val in PIPER_VOICES:
            _voices_mod._tts_voice_index = PIPER_VOICES.index(val)
            settings = load_settings()
            settings["tts_voice"] = val
            save_settings(settings)

    # ─── TTS actions ────────────────────────────────────────────────

    def action_download_voices(self):
        def _on_progress(name, i, total):
            self._set_status(f"Downloading voices... {i}/{total}: {name}")

        def _on_done(ok, fail):
            if fail:
                self._set_status(f"Downloaded {ok} voices, {fail} failed.")
                speak_text(f"Downloaded {ok} voices. {fail} failed.")
            else:
                self._set_status(f"All {ok} voices downloaded.")
                speak_text(f"All {ok} voices downloaded successfully.")

        self._set_status("Downloading all voice files...")
        download_all_voices(on_progress=_on_progress, on_done=_on_done)

    def action_test_speech(self):
        curr_voice = get_tts_voice_name()
        if curr_voice == "N/A":
            self._set_status("No voice selected.")
            return
        model_path = get_tts_voice_model()
        if not model_path.exists():
            self._set_status("Voice not downloaded! Use the option below.")
            return
        speak_text("Standard system read-back test active. Hello from the Voice Code BBS.")

    def start_cast_broadcast_test(self):
        """Enter text editing mode for Chromecast broadcast test."""
        app = self.app
        if not app.cast_selected_devices:
            self._set_status("No Cast devices selected. Configure in Google Cast settings.")
            return
        app.settings_editing_text = True
        app.settings_edit_buffer = ""
        app.settings_edit_cursor = 0
        app.show_settings_overlay = True

    def commit_cast_broadcast_test(self):
        """Broadcast the typed text to configured Cast devices via TTS."""
        app = self.app
        text = app.settings_edit_buffer.strip()
        app.settings_editing_text = False
        if not text:
            self._set_status("No text entered, broadcast cancelled.")
            return
        if not app.cast_selected_devices:
            self._set_status("No Cast devices selected.")
            return
        self._set_status(f"Broadcasting to {len(app.cast_selected_devices)} device(s)...")
        cast_tts_to_devices(
            text,
            app.cast_selected_devices,
            ui_queue=app.ui_queue,
            volume=app.cast_volume,
        )

    def action_download_current_voice(self):
        curr_voice = get_tts_voice_name()
        if curr_voice == "N/A":
            self._set_status("No voice selected or available.")
            return

        self._set_status(f"Downloading {curr_voice}...")

        def _on_done(success, err_or_name):
            if success:
                self._set_status(f"Voice {err_or_name} downloaded.")
                speak_text(f"Voice {err_or_name} downloaded successfully.")
            else:
                self._set_status(f"Failed to download voice: {err_or_name}")
                speak_text("Voice download failed.")

        download_single_voice_model(curr_voice, on_done=_on_done)

    def action_clean_voices(self):
        deleted, kept = delete_unused_voices()
        if deleted:
            self._set_status(f"Deleted {deleted} unused voice files, kept {kept}")
            speak_text(f"Deleted {deleted} unused voice files.")
        else:
            self._set_status("No unused voice files to delete.")

    # ─── Text editing ───────────────────────────────────────────────

    def cancel_text_edit(self):
        """Cancel inline text editing."""
        self.app.settings_editing_text = False

    def commit_text_edit(self):
        """Dispatch text edit commit based on which setting is being edited."""
        item = self.selectable_item()
        if not item:
            return
        if item["key"] == "working_dir":
            self.commit_working_dir()
        elif item["key"] == "gemini_command":
            self.commit_gemini_command()
        elif item["key"] == "_action_cast_broadcast_test":
            self.commit_cast_broadcast_test()

    def start_editing_working_dir(self):
        """Enter inline text editing mode for the working directory path."""
        app = self.app
        app.settings_editing_text = True
        app.settings_edit_buffer = app.working_dir
        app.settings_edit_cursor = len(app.settings_edit_buffer)
        app.show_settings_overlay = True

    def update_working_dir_paths(self):
        """Derive prompts/docs paths from working_dir."""
        app = self.app
        if app.working_dir:
            wd = Path(app.working_dir).expanduser()
            app.save_base = wd / "prompts"
            app.history_base = app.save_base / "history"
        else:
            default = Path("~/prompts").expanduser()
            app.save_base = default / "voicecode"
            app.history_base = app.save_base / "history"

    def commit_working_dir(self):
        """Apply the edited working directory path."""
        app = self.app
        new_path = app.settings_edit_buffer.strip()
        app.working_dir = new_path
        self.update_working_dir_paths()
        persist_setting("working_dir", new_path)
        app.browser.scan_history_prompts()
        app.settings_editing_text = False
        if new_path:
            self._set_status(f"Working directory \u2192 {new_path}")
        else:
            self._set_status("Working directory cleared.")

    def start_editing_gemini_command(self):
        """Enter inline text editing mode for the gemini command string."""
        from voicecode.providers import get_provider_by_name

        app = self.app
        app.settings_editing_text = True
        g_prov = get_provider_by_name("Gemini")
        app.settings_edit_buffer = g_prov.command_override or g_prov.binary
        app.settings_edit_cursor = len(app.settings_edit_buffer)
        app.show_settings_overlay = True

    def commit_gemini_command(self):
        """Apply the edited gemini command string."""
        from voicecode.providers import get_provider_by_name

        app = self.app
        new_cmd = app.settings_edit_buffer.strip()
        g_prov = get_provider_by_name("Gemini")
        if g_prov:
            if new_cmd == g_prov.binary or not new_cmd:
                g_prov.command_override = None
                persist_setting("gemini_command", None)
                self._set_status("Gemini command reset to default.")
            else:
                g_prov.command_override = new_cmd
                persist_setting("gemini_command", new_cmd)
                self._set_status(f"Gemini command \u2192 {new_cmd}")
        app.settings_editing_text = False

    # ─── Cursor / selection helpers ─────────────────────────────────

    def selectable_items(self):
        """Return list of selectable (non-section) settings items."""
        return [it for it in self.app.settings_items if it.get("type") != "section"]

    def selectable_item(self):
        """Return the currently selected settings item (skipping sections)."""
        app = self.app
        if app.voice_submenu_open:
            items = app.voice_submenu_items
            cursor = app.voice_submenu_cursor
        elif app.tts_submenu_open:
            items = app.tts_submenu_items
            cursor = app.tts_submenu_cursor
        elif app.test_tools_submenu_open:
            items = app.test_tools_submenu_items
            cursor = app.test_tools_submenu_cursor
        elif app.ai_models_submenu_open:
            items = app.ai_models_submenu_items
            cursor = app.ai_models_submenu_cursor
        elif app.cast_submenu_open:
            items = app.cast_submenu_items
            cursor = app.cast_submenu_cursor
        else:
            items = app.settings_items
            cursor = app.settings_cursor

        selectable = [it for it in items if it.get("type") != "section"]
        if 0 <= cursor < len(selectable):
            return selectable[cursor]
        return None

    def settings_cursor_move(self, direction):
        """Move settings cursor, skipping section headers."""
        app = self.app
        selectable = self.selectable_items()
        if selectable:
            app.settings_cursor = (app.settings_cursor + direction) % len(selectable)

    def settings_cycle(self, direction):
        """Cycle the current setting's value left (-1) or right (+1)."""
        item = self.selectable_item()
        if not item or item.get("options") is None:
            return
        options = item["options"]
        current = item["get"]()
        try:
            idx = options.index(current)
        except ValueError:
            idx = 0
        new_idx = (idx + direction) % len(options)
        item["set"](options[new_idx])

    # ─── Draw ───────────────────────────────────────────────────────

    def draw(self):
        """Draw a BBS-style settings modal overlay on top of the UI."""
        app = self.app
        h, w = app.stdscr.getmaxyx()

        # Determine which items/cursor/title to render
        if app.voice_submenu_open:
            render_items = app.voice_submenu_items
            render_cursor = app.voice_submenu_cursor
            render_title = " VOICE SETTINGS "
            render_footer = " \u2191\u2193 Navigate  \u2190\u2192 Change  Esc Close "
        elif app.tts_submenu_open:
            render_items = app.tts_submenu_items
            render_cursor = app.tts_submenu_cursor
            render_title = " TEXT-TO-SPEECH SETTINGS "
            render_footer = " \u2191\u2193 Navigate  \u2190\u2192 Change  Enter Action  Esc Close "
        elif app.test_tools_submenu_open:
            render_items = app.test_tools_submenu_items
            render_cursor = app.test_tools_submenu_cursor
            render_title = " TEST TOOLS "
            render_footer = " \u2191\u2193 Navigate  \u2190\u2192 Change  Enter Action  Esc Close "
        elif app.ai_models_submenu_open:
            render_items = app.ai_models_submenu_items
            render_cursor = app.ai_models_submenu_cursor
            render_title = " AI MODELS "
            render_footer = " \u2191\u2193 Navigate  \u2190\u2192 Change  Esc Close "
        elif app.cast_submenu_open:
            render_items = app.cast_submenu_items
            render_cursor = app.cast_submenu_cursor
            render_title = " GOOGLE CAST NOTIFICATIONS "
            render_footer = " \u2191\u2193 Navigate  \u2190\u2192 Change  Enter Scan  Esc Close "
        else:
            render_items = app.settings_items
            render_cursor = app.settings_cursor
            render_title = " SETTINGS "
            render_footer = " \u2191\u2193 Navigate  \u2190\u2192 Change  Enter Action  O/Esc Close "

        overlay_w = min(72, w - 6)
        # Count rows: sections take 1 row, regular items take 3 rows
        item_rows = sum(1 if it.get("type") == "section" else 3 for it in render_items)
        overlay_h = min(4 + item_rows + 3, h - 4)
        if overlay_w < 44 or overlay_h < 8:
            return

        # Available rows for content (between title separator and footer)
        content_h = overlay_h - 5  # 3 top (border+title+sep) + 2 bottom (footer+border)

        # Pre-compute virtual row positions for each item and find selected
        item_vrows = []   # (virtual_row_start, height, item_index)
        vrow = 0
        selectable_idx = -1
        selected_vrow_start = 0
        selected_vrow_end = 0
        for i, item in enumerate(render_items):
            if item.get("type") == "section":
                item_vrows.append((vrow, 1, i))
                vrow += 1
            else:
                selectable_idx += 1
                h_item = 3
                item_vrows.append((vrow, h_item, i))
                if selectable_idx == render_cursor:
                    selected_vrow_start = vrow
                    selected_vrow_end = vrow + h_item
                vrow += h_item
        total_vrows = vrow

        # Adjust scroll offset to keep selected item visible
        scroll = app._settings_scroll_top
        if selected_vrow_start < scroll:
            scroll = selected_vrow_start
        if selected_vrow_end > scroll + content_h:
            scroll = selected_vrow_end - content_h
        scroll = max(0, min(scroll, max(0, total_vrows - content_h)))
        app._settings_scroll_top = scroll

        start_y = max(1, (h - overlay_h) // 2)
        start_x = max(2, (w - overlay_w) // 2)

        border_attr = curses.color_pair(CP_HEADER) | curses.A_BOLD
        body_attr = curses.color_pair(CP_HELP) | curses.A_BOLD
        accent_attr = curses.color_pair(CP_HEADER) | curses.A_BOLD
        sel_attr = curses.color_pair(CP_RECORDING) | curses.A_BOLD
        val_attr = curses.color_pair(CP_AGENT) | curses.A_BOLD

        inner_w = overlay_w - 2

        try:
            # Top border
            top = "\u2554" + "\u2550" * inner_w + "\u2557"
            app.stdscr.addnstr(start_y, start_x, top, overlay_w, border_attr)

            # Title bar (yellow background)
            title_attr = curses.color_pair(CP_SETTINGS_TITLE) | curses.A_BOLD
            title_line = "\u2551" + render_title.center(inner_w) + "\u2551"
            app.stdscr.addnstr(start_y + 1, start_x, title_line, overlay_w, title_attr)

            # Title separator
            sep = "\u2560" + "\u2550" * inner_w + "\u2563"
            app.stdscr.addnstr(start_y + 2, start_x, sep, overlay_w, border_attr)

            sect_red_attr = curses.color_pair(CP_SECT_RED) | curses.A_BOLD
            sect_yellow_attr = curses.color_pair(CP_HEADER) | curses.A_BOLD
            submenu_attr = curses.color_pair(CP_SUBMENU) | curses.A_BOLD

            content_top_y = start_y + 3
            content_bot_y = start_y + overlay_h - 2  # exclusive (footer row)
            row = content_top_y
            selectable_idx = -1  # track index among selectable items
            for vrow_start, vrow_h, item_idx in item_vrows:
                item = render_items[item_idx]
                vrow_end = vrow_start + vrow_h

                # Skip items entirely above the scroll viewport
                if vrow_end <= scroll:
                    if item.get("type") != "section":
                        selectable_idx += 1
                    continue

                # Stop if we've gone past the visible area
                if vrow_start - scroll >= content_h:
                    break

                # Compute the screen row for this item
                row = content_top_y + (vrow_start - scroll)

                if row >= content_bot_y:
                    break

                # Section header -- not selectable
                if item.get("type") == "section":
                    if row < content_bot_y:
                        s_attr = sect_red_attr if item.get("style") == "red" else sect_yellow_attr
                        sect_label = f" \u2500\u2500 {item['label']} "
                        sect_padded = sect_label + "\u2500" * max(0, inner_w - len(sect_label))
                        sect_line = "\u2551" + sect_padded[:inner_w] + "\u2551"
                        app.stdscr.addnstr(row, start_x, sect_line, overlay_w, s_attr)
                    continue

                selectable_idx += 1

                is_selected = (selectable_idx == render_cursor)
                is_action = item.get("options") is None
                is_submenu = item.get("submenu", False)
                line_attr = sel_attr if is_selected else (submenu_attr if is_submenu else body_attr)

                # Setting label line
                cursor_ch = ">" if is_selected else " "
                if is_submenu:
                    label = f" {cursor_ch} {item['label']}  \u25b6"
                else:
                    label = f" {cursor_ch} {item['label']}"

                # Row positions for the 3 sub-rows of this item
                r0 = content_top_y + (vrow_start - scroll)      # label
                r1 = r0 + 1                                      # value/desc
                r2 = r0 + 2                                      # blank sep

                is_editable = item.get("editable", False)

                if is_editable:
                    # Editable text field -- show path on the desc line
                    if is_selected and app.settings_editing_text:
                        label = f" {cursor_ch} {item['label']}  [editing]"
                    else:
                        label = f" {cursor_ch} {item['label']}  [Enter to edit]"
                    if r0 < content_bot_y:
                        padded = label + " " * max(0, inner_w - len(label))
                        body_line = "\u2551" + padded[:inner_w] + "\u2551"
                        app.stdscr.addnstr(r0, start_x, body_line, overlay_w, line_attr)

                    # Show the editable path value
                    if r1 < content_bot_y:
                        if is_selected and app.settings_editing_text:
                            buf = app.settings_edit_buffer
                            cur = app.settings_edit_cursor
                            # Scroll the visible window if path is too long
                            max_vis = inner_w - 7
                            if cur > max_vis:
                                vis_start = cur - max_vis + 1
                            else:
                                vis_start = 0
                            vis_text = buf[vis_start:vis_start + max_vis]
                            vis_cursor = cur - vis_start
                            path_line = f"  >> {vis_text}"
                            path_padded = path_line + " " * max(0, inner_w - len(path_line))
                            body_line = "\u2551" + path_padded[:inner_w] + "\u2551"
                            app.stdscr.addnstr(r1, start_x, body_line, overlay_w, val_attr)
                            # Draw cursor character with reverse video
                            cursor_x = start_x + 1 + 5 + vis_cursor  # "║  >> " = 5 chars
                            if cursor_x < start_x + overlay_w - 1:
                                ch_under = buf[cur] if cur < len(buf) else " "
                                app.stdscr.addnstr(
                                    r1, cursor_x, ch_under, 1,
                                    curses.color_pair(CP_AGENT) | curses.A_REVERSE)
                        else:
                            val_text = f"  >> {item['get']()}"
                            val_padded = val_text + " " * max(0, inner_w - len(val_text))
                            body_line = "\u2551" + val_padded[:inner_w] + "\u2551"
                            attr = val_attr if is_selected else body_attr
                            app.stdscr.addnstr(r1, start_x, body_line, overlay_w, attr)

                    # Blank separator
                    if r2 < content_bot_y:
                        blank = "\u2551" + " " * inner_w + "\u2551"
                        app.stdscr.addnstr(r2, start_x, blank, overlay_w, body_attr)
                    continue

                elif is_action:
                    # Action item -- show status hint if get() returns non-empty
                    action_val = item["get"]() if callable(item.get("get")) else ""
                    if action_val:
                        hint = f"  ({action_val})"
                        full = label + hint
                        padded = full + " " * max(0, inner_w - len(full))
                    else:
                        padded = label + " " * max(0, inner_w - len(label))
                    if r0 < content_bot_y:
                        body_line = "\u2551" + padded[:inner_w] + "\u2551"
                        app.stdscr.addnstr(r0, start_x, body_line, overlay_w, line_attr)
                else:
                    current_val = str(item["get"]())
                    # Build value display with < > arrows when selected
                    if is_selected:
                        val_display = f"< {current_val} >"
                    else:
                        val_display = f"  {current_val}  "

                    # Right-align the value
                    space = inner_w - len(label) - len(val_display) - 1
                    full_line = label + " " * max(1, space) + val_display + " "

                    padded = full_line[:inner_w]
                    padded += " " * max(0, inner_w - len(padded))
                    if r0 < content_bot_y:
                        body_line = "\u2551" + padded + "\u2551"
                        app.stdscr.addnstr(r0, start_x, body_line, overlay_w, line_attr)

                        # Overwrite just the value portion in green if selected
                        if is_selected:
                            val_x = start_x + 1 + max(1, inner_w - len(val_display) - 1)
                            app.stdscr.addnstr(r0, val_x, val_display, len(val_display), val_attr)

                # Description line (dimmer)
                if r1 < content_bot_y:
                    desc = f"     {item['desc']}"
                    desc_padded = desc + " " * max(0, inner_w - len(desc))
                    desc_line = "\u2551" + desc_padded[:inner_w] + "\u2551"
                    app.stdscr.addnstr(r1, start_x, desc_line, overlay_w, body_attr)

                # Blank separator line
                if r2 < content_bot_y:
                    blank = "\u2551" + " " * inner_w + "\u2551"
                    app.stdscr.addnstr(r2, start_x, blank, overlay_w, body_attr)

            # Fill remaining rows with blank lines
            last_vrow = item_vrows[-1][0] + item_vrows[-1][1] if item_vrows else 0
            fill_start = content_top_y + max(0, last_vrow - scroll)
            for r in range(max(fill_start, content_top_y), content_bot_y):
                blank = "\u2551" + " " * inner_w + "\u2551"
                app.stdscr.addnstr(r, start_x, blank, overlay_w, body_attr)

            # Footer help line
            footer_padded = render_footer.center(inner_w)
            footer_line = "\u2551" + footer_padded[:inner_w] + "\u2551"
            app.stdscr.addnstr(start_y + overlay_h - 2, start_x, footer_line,
                                overlay_w, accent_attr)

            # Bottom border
            bottom = "\u255a" + "\u2550" * inner_w + "\u255d"
            app.stdscr.addnstr(start_y + overlay_h - 1, start_x, bottom, overlay_w, border_attr)
        except curses.error:
            pass
