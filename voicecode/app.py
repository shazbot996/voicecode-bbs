"""BBSApp core — main loop, initialization, UI queue processing."""

import curses
import sys
import os
import time
import queue
import threading
import collections
import datetime
import textwrap
import random
import numpy as np
from pathlib import Path

from version import __version__
from voicecode.constants import (
    AgentState, SAMPLE_RATE, VAD_THRESHOLD,
    SILENCE_AFTER_SPEECH_SEC, MIN_SPEECH_DURATION_SEC,
)
from voicecode.settings import load_settings, save_settings, load_shortcuts, persist_setting
from voicecode.ui.colors import (
    CP_HEADER, CP_PROMPT, CP_DICTATION, CP_STATUS, CP_HELP, CP_RECORDING,
    CP_BANNER, CP_ACCENT, CP_AGENT, CP_XFER, CP_VOICE,
    CP_CTX_GREEN, CP_CTX_YELLOW, CP_CTX_RED,
    CP_TTS, CP_SECT_RED, CP_SUBMENU, CP_SETTINGS_TITLE,
    CP_FAV_EMPTY, CP_FAV_FILLED, CP_PUBLISH, CP_PUBLISH_TITLE,
    init_colors, get_active_theme, set_active_theme,
)
from voicecode.ui.panes import TextPane
from voicecode.ui.drawing import DrawingHelper
from voicecode.ui.overlays import OverlayRenderer
from voicecode.ui.settings_overlay import SettingsOverlay
from voicecode.ui.publish_overlay import PublishOverlay
from voicecode.ui.input import InputHandler
from voicecode.ui.animation import AnimationHelper
from voicecode.agent.runner import RunnerHelper
from voicecode.agent.execution import ExecutionHelper
from voicecode.history.browser import BrowserHelper
from voicecode.history.favorites import FavoritesHelper
from voicecode.audio.capture import RecordingHelper
from voicecode.audio.vad import get_vad_model
from voicecode.stt.whisper import get_whisper_model
from voicecode.tts.voices import TTS_AVAILABLE
from voicecode.providers import detect_providers, get_provider_by_name
from voicecode.providers.claude import ClaudeProvider


class BBSApp:
    """The main curses application — three-pane BBS terminal."""

    def __init__(self):
        # Left panes
        self.prompt_pane = TextPane("PROMPT BROWSER", CP_PROMPT)
        self.dictation_pane = TextPane("DICTATION BUFFER", CP_DICTATION)
        self.dictation_pane.MAX_LINES = 500  # smaller cap for dictation fragments

        # Right pane
        self.agent_pane = TextPane("AGENT TERMINAL", CP_AGENT)

        # Retro welcome art shown when panes are empty
        self.prompt_pane.welcome_art = [
            "╔══════════════════════════════════════╗",
            "║       ◆  PROMPT  WORKSHOP  ◆         ║",
            "║   Press SPACE to start dictating...  ║",
            "╚══════════════════════════════════════╝",
            "",
            "  [SPACE] Record   [R] Refine   [D] Direct execute",
            "  [P] Publish   [END] Clear prompt & buffer",
            "",
            "  ←→ to browse history  ↑↓ scroll",
            "  [F] favorites  1-0 load favorites",
            "",
            "  Publish processes your prompt through",
            "  purpose-built agents to create polished",
            "  documents ready for sharing, export, or",
            "  further agent processing by referencing",
            "  directly.",
        ]
        self.dictation_pane.welcome_art = [
            "╔══════════════════════════════════════╗",
            "║      ◆  DICTATION  BUFFER  ◆         ║",
            "║   Voice fragments appear here as     ║",
            "║   you record (SPACE) or type (Enter).║",
            "╚══════════════════════════════════════╝",
            "",
            "  This is your scratchpad for voice input.",
            "  Fragments collect here, then:",
            "",
            "  [R] Refine → merges into the Prompt above",
            "  [D] Direct → sends straight to the Agent",
            "  [U] Undo   → remove last entry",
            "  [C] Clear  → wipe and start over",
            "",
            "                         [Y] Replay TTS ♪",
        ]
        # Load all tips for cycling
        self._all_tips = self._load_all_tips()
        self._tip_index = random.randrange(len(self._all_tips)) if self._all_tips else 0

        self.agent_pane.welcome_art = [
            "╔═══════════════════════════════════════╗",
            "║   GREETINGS PROFESSOR FALKEN.         ║",
            "╚═══════════════════════════════════════╝",
            "",
            "  READY TO RECEIVE TRANSMISSION.",
            "",
            "  Awaiting prompt upload...",
            "  Protocol: ZMODEM-VOICE/1.0",
            "  Connection: LOCAL",
            "",
            "  ── Quick Start ─────────────────",
            "",
            "  SPACE ··· Record voice / Enter ··· Type text",
            "  R     ··· Refine into prompt",
            "  E     ··· Execute prompt",
            "  D     ··· Direct execute",
            "  P     ··· Publish document",
            "  F     ··· Favorites (toggle / add)",
            "  W     ··· New session (clear context)",
            "  O     ··· Options / Settings",
            "  H     ··· Full help screen",
            "  ESC   ··· Main menu",
            "",
            "  ── [T] Tip ─────────────────────",
            "",
        ] + self._get_current_tip()

        self.fragments: list[str] = []
        self.current_prompt: str | None = None
        self.prompt_version = 0

        self.status_msg = f"Welcome to VoiceCode BBS v{__version__}!"
        self.status_color = CP_STATUS
        self.running = True
        self.restart = False
        self.recording = False
        self.refining = False

        # Audio
        self.audio_frames: list[np.ndarray] = []
        self.audio_lock = threading.Lock()

        # Event queue for cross-thread UI updates
        self.ui_queue: queue.Queue = queue.Queue()

        # Working directory & derived paths — from persisted settings
        saved = load_settings()
        self.theme_name = saved.get("theme", "pcboard")
        self.tts_volume_gain = float(saved.get("tts_volume_gain", 1.0))

        # Prompts and docs live under the working directory
        # Default to cwd if not yet configured, and persist so it sticks
        self.working_dir = saved.get("working_dir", "")
        if not self.working_dir:
            self.working_dir = os.getcwd()
            persist_setting("working_dir", self.working_dir)
        self._update_working_dir_paths()
        self.history_prompts: list[Path] = []
        self.favorites_slots: list[str | None] = [None] * 10  # 10 numbered slots (keys 1-9, 0)
        self.browser_index: int = -1
        self.browser_view: str = "active"  # "active" or "favorites"
        self._scan_history_prompts()
        self._load_favorites_slots()

        # Prompt saved state
        self.prompt_saved = True  # no unsaved prompt at start
        self.confirming_new = False  # for [N] save confirmation dialog
        self.confirming_edit_historical = False  # for editing a historical prompt
        self.choosing_fav_slot = False  # for [F] slot selection
        self.confirming_fav_overwrite = False  # for overwrite confirmation
        self._pending_fav_slot: int = -1  # slot index pending overwrite confirm
        self._pending_fav_path: str = ""  # path pending favorites assignment

        # (working_dir already set above via _update_working_dir_paths)

        # Help overlay state
        self.show_help_overlay = False
        self.show_about_overlay = False

        # Escape menu overlay state
        self.show_escape_menu = False
        self.escape_menu_cursor = 0
        self._escape_menu_items = [
            ("Options", "settings"),
            ("Help", "help"),
            ("About", "about"),
            ("Restart", "restart"),
            ("Quit", "quit"),
        ]

        # Shortcuts overlay state (was folder slug)
        self.show_folder_slug = False
        self.folder_slug_cursor = 0
        self.folder_slug_list: list[str] = []
        self.folder_slug_scroll = 0
        self._shortcut_strings: list[str] = load_shortcuts()
        self._shortcut_count = 0  # how many items at the top are shortcuts
        # Browser category: 0=Shortcuts, 1=Project Folders, 2=Documents, 3=Tools
        self._browser_category = 0
        self._browser_categories = ["Shortcuts", "Project Folders", "Documents", "Tools"]
        self._browser_cat_lists: list[list[str]] = [[], [], [], []]

        # Document reader overlay state
        self.show_doc_reader = False
        self.doc_reader_path = ""
        self.doc_reader_title = ""
        self.doc_reader_lines: list[str] = []
        self.doc_reader_scroll = 0
        self.doc_reader_doc_type = ""
        # Document editor state (edit mode within reader)
        self.doc_edit_mode = False
        self.doc_edit_lines: list[str] = []
        self.doc_edit_cursor_row = 0
        self.doc_edit_cursor_col = 0
        self.doc_edit_scroll = 0
        self.doc_edit_save_confirm = False
        self.doc_reader_on_close: object = None  # optional callback when doc reader closes

        # Maintenance overlay state (modal within doc reader)
        self.show_maint_overlay = False
        self.maint_cursor = 0
        self.maint_actions: list[tuple[str, str]] = []  # (action_name, description)

        # Browser delete confirmation state (modal within browser)
        self.show_browser_delete_confirm = False
        self._browser_delete_path = ""  # full path of file to delete
        self._browser_delete_title = ""  # display title (rel path)

        # Document actions overlay state (modal within browser)
        self.show_doc_actions = False
        self.doc_actions_cursor = 0
        self.doc_actions_list: list[tuple[str, str]] = []  # (action_id, label)
        self.doc_actions_path = ""  # full path of selected doc
        self.doc_actions_title = ""  # display title (rel path)
        self.doc_actions_doc_type = ""  # cached doc type

        # Shortcut editor overlay state
        self.show_shortcut_editor = False
        self.shortcut_editor_cursor = 0
        self.shortcut_editor_scroll = 0
        self.shortcut_editing_text = False
        self.shortcut_edit_buffer = ""
        self.shortcut_edit_cursor_pos = 0

        # Mid-recording folder injections: [(audio_seconds, text), ...]
        self._recording_injections: list[tuple[float, str]] = []

        # Direct text entry mode (Enter key in dictation buffer)
        self.typing_mode = False
        self.typing_buffer = ""
        self.typing_cursor = 0

        # Settings overlay state
        self.show_settings_overlay = False
        self.settings_cursor = 0
        self.settings_editing_text = False  # True when inline text editing is active
        self.settings_edit_buffer = ""      # current text being edited
        self.settings_edit_cursor = 0       # cursor position within buffer

        # Sub-menu state
        self.tts_submenu_open = False
        self.tts_submenu_cursor = 0
        self.tts_submenu_items = []
        self.test_tools_submenu_open = False
        self.test_tools_submenu_cursor = 0
        self.voice_submenu_open = False
        self.voice_submenu_cursor = 0
        self.test_tools_submenu_items = []
        self.ai_models_submenu_open = False
        self.ai_models_submenu_cursor = 0
        self.ai_models_submenu_items = []
        self.cast_submenu_open = False
        self.cast_submenu_cursor = 0
        self.cast_submenu_items = []
        self.theme_submenu_open = False
        self.theme_submenu_cursor = 0
        self.theme_submenu_items = []
        self._theme_before_preview = None  # for ESC revert
        self._settings_scroll_top = 0  # vertical scroll offset for settings

        # Publish overlay state
        self.show_publish_overlay = False
        self.publish_step = 0           # 0 = type, 1 = folder
        self.publish_cursor = 0
        self.publish_selected_type = None
        self.publish_selected_folder = None
        self.cast_enabled = saved.get("cast_enabled", False)
        self.cast_volume = float(saved.get("cast_volume", 0.8))
        self.cast_discovered_devices: list[str] = []
        self.cast_selected_devices: list[str] = list(
            saved.get("cast_selected_devices", []))
        self.cast_scanning = False
        self.cast_mute_local_tts = saved.get("cast_mute_local_tts", False)
        self.tts_enabled = saved.get("tts_enabled", True)

        # Voice settings (mutable, persisted)
        self.vad_threshold = saved.get("vad_threshold", VAD_THRESHOLD)
        self.silence_timeout = saved.get("silence_timeout", SILENCE_AFTER_SPEECH_SEC)
        self.min_speech_duration = saved.get("min_speech_duration", MIN_SPEECH_DURATION_SEC)
        self.whisper_model = saved.get("whisper_model", "base.en")

        # AI provider — detect installed CLIs and restore saved choice
        saved_provider = saved.get("ai_provider", "Claude")

        # Apply command overrides from settings
        gemini_cmd = saved.get("gemini_command")
        g_prov = get_provider_by_name("Gemini")
        if gemini_cmd and g_prov:
            g_prov.command_override = gemini_cmd
        if g_prov and saved.get("gemini_disable_proxy", False):
            g_prov.disable_proxy = True

        # Detect available providers after overrides are applied
        self.available_providers = detect_providers()

        self.ai_provider = get_provider_by_name(saved_provider)
        if not self.ai_provider or not self.ai_provider.is_installed():
            # Fallback to first available, or Claude as default
            self.ai_provider = self.available_providers[0] if self.available_providers else ClaudeProvider()

        # Agent state
        self.agent_state = AgentState.IDLE
        self.agent_process = None
        self._agent_cancel = threading.Event()
        self.last_tts_summary = ""
        self._last_history_prompt_path: Path | None = None

        # Session continuity — reuse session_id across prompts
        self.session_id: str | None = None
        self.session_turns = 0
        self.context_tokens_used = 0
        self.context_window_size = 0

        # ZMODEM animation state
        self.xfer_progress = 0.0
        self.xfer_frame = 0
        self.xfer_bytes = 0
        self.xfer_start_time = 0.0
        self.xfer_prompt_text = ""

        # Typewriter state
        self.typewriter_queue: collections.deque = collections.deque()
        self._typewriter_budget = 0.0       # fractional char budget carried across frames
        self._typewriter_last_ts = 0.0      # monotonic timestamp of last _process call
        self._typewriter_line_color = None   # per-line color override (None = default)
        self._typewriter_chars_per_sec = saved.get("typewriter_speed", 200)
        self.agent_first_output = False      # tracks if agent has produced any output
        self.agent_last_activity = 0.0       # time.time() of last output from agent
        self.agent_welcome_shown = False     # True after initial welcome art displayed

        # Pending source pane tracking (yellow border while agent processes)
        self._agent_source_pane = None       # which pane sent the prompt
        self._agent_source_original_color = None  # original color_pair to restore

        # Executed prompt display — persists in prompt browser until new prompt
        self.executed_prompt_text: str | None = None
        self._prompt_pane_original_color: int | None = None

        # ─── Helper objects (composition) ─────────────────────────
        self.drawing = DrawingHelper(self)
        self.overlays = OverlayRenderer(self)
        self.settings_overlay = SettingsOverlay(self)
        self.publish_overlay = PublishOverlay(self)
        self.input_handler = InputHandler(self)
        self.animation = AnimationHelper(self)
        self.runner = RunnerHelper(self)
        self.execution = ExecutionHelper(self)
        self.browser = BrowserHelper(self)
        self.favorites = FavoritesHelper(self)
        self.recording_helper = RecordingHelper(self)

        # Build settings items (delegated to settings_overlay)
        self.settings_overlay.build_settings_items()

    # ─── Tips ──────────────────────────────────────────────────────

    def _load_all_tips(self) -> list[str]:
        """Load all tips from tips.txt."""
        tips_path = Path(__file__).resolve().parent.parent / "tips.txt"
        try:
            text = tips_path.read_text().strip()
            return [t.strip() for t in text.splitlines() if t.strip()]
        except FileNotFoundError:
            return []

    def _get_current_tip(self) -> list[str]:
        """Wrap the current tip for the welcome screen."""
        if not self._all_tips:
            return []
        tip = self._all_tips[self._tip_index % len(self._all_tips)]
        wrapped = textwrap.wrap(tip, width=37)
        return ["  " + line for line in wrapped]

    def _load_random_tip(self) -> list[str]:
        """Load a random tip from tips.txt and wrap it for the welcome screen."""
        if not self._all_tips:
            return []
        tip = random.choice(self._all_tips)
        wrapped = textwrap.wrap(tip, width=37)
        return ["  " + line for line in wrapped]

    def cycle_tip(self):
        """Cycle to the next tip and update the agent welcome art."""
        if not self._all_tips:
            return
        self._tip_index = (self._tip_index + 1) % len(self._all_tips)
        # Find the tip section marker and replace everything after it
        marker = "  ── [T] Tip ─────────────────────"
        art = self.agent_pane.welcome_art
        for i, line in enumerate(art):
            if line == marker:
                # Keep everything up to and including the marker + blank line
                self.agent_pane.welcome_art = art[:i + 2] + self._get_current_tip()
                break

    # ─── Working directory helpers ─────────────────────────────────

    def _update_working_dir_paths(self):
        """Derive prompts/docs paths from working_dir."""
        if self.working_dir:
            wd = Path(self.working_dir).expanduser()
            self.save_base = wd / "prompts"
            self.history_base = self.save_base / "history"
        else:
            default = Path("~/prompts").expanduser()
            self.save_base = default / "voicecode"
            self.history_base = self.save_base / "history"

    def _scan_history_prompts(self):
        self.history_prompts = sorted(self.history_base.glob("[0-9]*_*_prompt.md"))

    def _load_favorites_slots(self):
        """Load 10-slot favorites from settings."""
        saved = load_settings()
        slots = saved.get("favorites_slots", [None] * 10)
        # Ensure exactly 10 slots
        self.favorites_slots = (slots + [None] * 10)[:10]
        # Validate paths still exist
        for i, p in enumerate(self.favorites_slots):
            if p and not Path(p).exists():
                self.favorites_slots[i] = None

    # ─── Main event loop ──────────────────────────────────────────

    def run(self, stdscr):
        """Main event loop."""
        self.stdscr = stdscr
        from voicecode.audio.utils import suppress_stderr
        suppress_stderr()
        init_colors(self.theme_name, TTS_AVAILABLE)
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.timeout(16)  # ~60fps for smooth animations

        # Enable bracketed paste mode so pasted text arrives as a single
        # delimited block instead of individual keystrokes.
        sys.stdout.write("\x1b[?2004h")
        sys.stdout.flush()

        self.drawing.draw_loading("Loading Silero VAD model...")
        get_vad_model()
        self.drawing.draw_loading("Loading Whisper model...")
        get_whisper_model(self.whisper_model)
        self.drawing.draw_loading("Ready!")
        time.sleep(2.0)

        self.browser.load_browser_prompt(80)
        self.browser.set_dictation_info(80)
        self.input_handler.load_persisted_buffer(80)
        self.browser.set_agent_welcome(40)

        try:
            while self.running:
                self.process_ui_queue()
                self.animation.process_typewriter()
                self.drawing.draw()
                self.input_handler.handle_input()
        finally:
            # Disable bracketed paste mode before exiting curses
            sys.stdout.write("\x1b[?2004l")
            sys.stdout.flush()

    # ─── Status bar ───────────────────────────────────────────────

    def set_status(self, msg: str, color: int = None):
        """Set the status bar message."""
        color = color if color is not None else CP_STATUS
        # Recording indicator has highest priority — suppress non-recording
        # alerts while recording is active so the red bar stays visible.
        if self.recording and color != CP_RECORDING:
            return
        self.status_msg = msg
        self.status_color = color

    # ─── Cross-thread UI queue ────────────────────────────────────

    def process_ui_queue(self):
        """Drain the cross-thread UI update queue."""
        left_width = self.stdscr.getmaxyx()[1] * 2 // 5

        while True:
            try:
                msg = self.ui_queue.get_nowait()
            except queue.Empty:
                break

            if msg[0] == "status":
                self.status_msg = msg[1]
                self.status_color = msg[2] if len(msg) > 2 else CP_STATUS

            elif msg[0] == "live_preview":
                # Update or add the live preview lines (shown dimly while recording)
                text = msg[1]
                # Remove previous preview lines
                while self.dictation_pane.lines and self.dictation_pane.lines[-1].startswith("  ◌ "):
                    self.dictation_pane.lines.pop()
                # Wrap the preview text to fit within the pane
                wrap_width = max(1, left_width - 2)
                prefix = "  ◌ "
                wrapped = textwrap.wrap(text, width=max(1, wrap_width - len(prefix)))
                if wrapped:
                    self.dictation_pane.lines.append(f"{prefix}{wrapped[0]}")
                    for continuation in wrapped[1:]:
                        self.dictation_pane.lines.append(f"  ◌  {continuation}")
                else:
                    self.dictation_pane.lines.append(f"{prefix}{text}")
                self.dictation_pane.scroll_to_bottom(
                    self.dictation_pane._last_height if hasattr(self.dictation_pane, '_last_height') else 10)

            elif msg[0] == "remove_live_preview":
                # Remove all live preview lines before adding final fragment
                while self.dictation_pane.lines and self.dictation_pane.lines[-1].startswith("  ◌ "):
                    self.dictation_pane.lines.pop()

            elif msg[0] == "fragment":
                text = msg[1]
                # New dictation clears the executed prompt from the browser
                if self.executed_prompt_text is not None:
                    self.execution.clear_executed_prompt()
                    self.browser.load_browser_prompt(left_width)
                self.fragments.append(text)
                self.input_handler.persist_buffer()
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                self.dictation_pane.add_line(f"[{ts}] {text}", left_width)

            elif msg[0] == "refined":
                self.current_prompt = msg[1]
                self.prompt_version += 1
                self.prompt_saved = False  # track unsaved state
                self.browser_index = -1
                self.browser.load_browser_prompt(left_width)
                # Clear fragments and dictation after refinement
                self.fragments.clear()
                self.input_handler.clear_buffer_file()
                self.dictation_pane.lines.clear()
                self.dictation_pane.scroll_offset = 0
                self.browser.set_dictation_info(left_width)
                self.refining = False

            elif msg[0] == "agent_state":
                self.agent_state = msg[1]
                if msg[1] == AgentState.DONE:
                    self.session_turns += 1
                    # Clear the gold executed-prompt display; the prompt
                    # is already saved in history, so return the prompt
                    # pane to its initial "new prompt" state.
                    if self.executed_prompt_text is not None:
                        self.execution.clear_executed_prompt()
                        self.browser.load_browser_prompt(left_width)

            elif msg[0] == "clear_dictation_buffer":
                # Agent succeeded — now safe to discard the dictation buffer.
                self.fragments.clear()
                self.input_handler.clear_buffer_file()

            elif msg[0] == "session_id":
                self.session_id = msg[1]

            elif msg[0] == "context_usage":
                self.context_tokens_used = msg[1]
                if msg[2]:
                    self.context_window_size = msg[2]

            elif msg[0] == "typewriter_char":
                self.typewriter_queue.append(msg[1])

            elif msg[0] == "typewriter_color":
                self.typewriter_queue.append(("color", msg[1]))

            elif msg[0] == "cast_scan_result":
                self.cast_discovered_devices = msg[1]
                # Rebuild submenu items to show discovered devices
                if self.cast_submenu_open:
                    self.cast_submenu_items = self.settings_overlay.build_cast_submenu_items()
