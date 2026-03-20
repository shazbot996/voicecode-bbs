"""Input handling — keyboard dispatch, paste handling, modal key routing."""

import curses
import datetime
import json
import textwrap

from voicecode.constants import AgentState, SAMPLE_RATE
from voicecode.ui.colors import CP_STATUS, CP_VOICE
from voicecode.tts.voices import TTS_AVAILABLE, get_tts_voice_name, get_tts_voice_model, cycle_tts_voice
from voicecode.tts.engine import speak_text, stop_speaking
from voicecode.settings import load_shortcuts, save_shortcuts
from voicecode.providers import get_provider_by_name


class InputHandler:
    """Handles all keyboard input for the BBS app.

    Gets a reference to the app for state access and method dispatch.
    """

    def __init__(self, app):
        self.app = app

    def read_paste_content(self) -> str:
        """Read characters until the bracketed-paste end sequence ESC[201~."""
        app = self.app
        buf: list[int] = []
        # Switch to short blocking reads so we drain the paste quickly
        app.stdscr.timeout(50)
        max_chars = 10_000  # safety cap
        try:
            while len(buf) < max_chars:
                c = app.stdscr.getch()
                if c == -1:
                    # Small gap — if we already have content, assume paste ended
                    # without a proper close bracket (unsupported terminal)
                    if buf:
                        break
                    continue
                buf.append(c)
                # Check for paste-end: ESC [ 2 0 1 ~ (27 91 50 48 49 126)
                if (len(buf) >= 6
                        and buf[-6:] == [27, 91, 50, 48, 49, 126]):
                    buf = buf[:-6]
                    break
        finally:
            app.stdscr.timeout(16)  # restore normal timeout
        return "".join(chr(c) for c in buf if 0 < c < 0x110000)

    def inject_paste(self, text: str):
        """Inject pasted text into the active text field, dictation buffer, or recording stream."""
        app = self.app
        text = text.strip()
        if not text:
            return

        # If a modal text field is active, insert there instead of dictation
        if app.shortcut_editing_text:
            # Collapse to single line for text field
            flat = " ".join(text.splitlines())
            b = app.shortcut_edit_buffer
            c = app.shortcut_edit_cursor_pos
            app.shortcut_edit_buffer = b[:c] + flat + b[c:]
            app.shortcut_edit_cursor_pos += len(flat)
            app.set_status("Pasted into editor")
            return
        if app.typing_mode:
            flat = " ".join(text.splitlines())
            b = app.typing_buffer
            c = app.typing_cursor
            app.typing_buffer = b[:c] + flat + b[c:]
            app.typing_cursor += len(flat)
            app.set_status("Pasted into text entry")
            return
        if app.settings_editing_text:
            flat = " ".join(text.splitlines())
            b = app.settings_edit_buffer
            c = app.settings_edit_cursor
            app.settings_edit_buffer = b[:c] + flat + b[c:]
            app.settings_edit_cursor += len(flat)
            app.set_status("Pasted into editor")
            return

        # Collapse to single line for dictation (newlines -> spaces)
        text = " ".join(text.splitlines())

        truncated = text[:40] + ("\u2026" if len(text) > 40 else "")
        if app.recording:
            # Same injection path as shortcut/folder slug injection
            with app.audio_lock:
                audio_secs = (sum(len(f) for f in app.audio_frames)
                              / SAMPLE_RATE) if app.audio_frames else 0.0
            app._recording_injections.append((audio_secs, text))
            preview = app._live_preview_text
            combined = f"{preview} {text}" if preview else text
            app.ui_queue.put(("live_preview", combined))
            app.set_status(f"Pasted: {truncated}")
        else:
            left_width = app.stdscr.getmaxyx()[1] * 2 // 5
            app.fragments.append(text)
            self.persist_buffer()
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            app.dictation_pane.add_line(f"[{ts}] {text}", left_width)
            app.set_status(f"Pasted: {truncated}")

    # Buffer persistence helpers

    def active_buffer_path(self):
        """Return the path for the active buffer persistence file."""
        return self.app.save_base / "active_buffer.json"

    def persist_buffer(self):
        """Save current fragments to disk for crash recovery."""
        app = self.app
        path = self.active_buffer_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = [{"text": f} for f in app.fragments]
            path.write_text(json.dumps(data), encoding="utf-8")
        except OSError:
            pass

    def clear_buffer_file(self):
        """Remove the persisted buffer file."""
        try:
            self.active_buffer_path().unlink(missing_ok=True)
        except OSError:
            pass

    def load_persisted_buffer(self, width: int):
        """Restore fragments from a previous session if present."""
        app = self.app
        path = self.active_buffer_path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for entry in data:
                text = entry["text"]
                app.fragments.append(text)
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                app.dictation_pane.add_line(f"[{ts}] {text}", width)
        except (OSError, json.JSONDecodeError, KeyError):
            pass

    def rebuild_dictation_pane(self):
        """Rebuild dictation pane lines from current fragments list."""
        app = self.app
        left_width = app.stdscr.getmaxyx()[1] // 2
        app.dictation_pane.lines.clear()
        app.dictation_pane.scroll_offset = 0
        if app.fragments:
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            for frag in app.fragments:
                app.dictation_pane.add_line(f"[{ts}] {frag}", left_width)
        else:
            app.browser.set_dictation_info(left_width)

    def handle_input(self):
        """Main input dispatcher — routes keys to the correct handler."""
        app = self.app
        try:
            ch = app.stdscr.getch()
        except curses.error:
            return

        if ch == -1:
            return

        # Handle help overlay dismiss (before anything else)
        if app.show_help_overlay:
            if ch in (ord("h"), ord("H"), ord("q"), ord("Q"), 27):
                app.show_help_overlay = False
                # Consume any follow-up byte from ESC sequence
                if ch == 27:
                    app.stdscr.nodelay(True)
                    app.stdscr.getch()
            return

        # Handle about overlay dismiss
        if app.show_about_overlay:
            if ch in (ord("a"), ord("A"), ord("q"), ord("Q"), 27):
                app.show_about_overlay = False
                if ch == 27:
                    app.stdscr.nodelay(True)
                    app.stdscr.getch()
            return

        # Handle escape menu overlay
        if app.show_escape_menu:
            if ch == curses.KEY_UP:
                app.escape_menu_cursor = (app.escape_menu_cursor - 1) % len(app._escape_menu_items)
            elif ch == curses.KEY_DOWN:
                app.escape_menu_cursor = (app.escape_menu_cursor + 1) % len(app._escape_menu_items)
            elif ch in (10, 13, curses.KEY_ENTER):
                _label, action = app._escape_menu_items[app.escape_menu_cursor]
                app.show_escape_menu = False
                if action == "settings":
                    app.show_settings_overlay = True
                    app.settings_cursor = 0
                    app._settings_scroll_top = 0
                    app.tts_submenu_open = False
                    app.test_tools_submenu_open = False
                    app.voice_submenu_open = False
                    app.ai_models_submenu_open = False
                elif action == "help":
                    app.show_help_overlay = True
                elif action == "about":
                    app.show_about_overlay = True
                elif action == "restart":
                    app.runner.kill_agent(sync=True)
                    app.restart = True
                    app.running = False
                elif action == "quit":
                    app.runner.kill_agent(sync=True)
                    app.running = False
            elif ch == 27:
                app.show_escape_menu = False
                app.stdscr.nodelay(True)
                app.stdscr.getch()
            elif ch in (ord("q"), ord("Q")):
                app.show_escape_menu = False
            return

        # Handle folder slug overlay
        if app.show_folder_slug:
            if ch == curses.KEY_UP:
                if app.folder_slug_cursor > 0:
                    app.folder_slug_cursor -= 1
                return
            elif ch == curses.KEY_DOWN:
                if app.folder_slug_cursor < len(app.folder_slug_list) - 1:
                    app.folder_slug_cursor += 1
                return
            elif ch == curses.KEY_LEFT:
                # Switch to previous category
                app._browser_category = (app._browser_category - 1) % len(app._browser_categories)
                app.folder_slug_list = app._browser_cat_lists[app._browser_category]
                app.folder_slug_cursor = 0
                app.folder_slug_scroll = 0
                return
            elif ch == curses.KEY_RIGHT:
                # Switch to next category
                app._browser_category = (app._browser_category + 1) % len(app._browser_categories)
                app.folder_slug_list = app._browser_cat_lists[app._browser_category]
                app.folder_slug_cursor = 0
                app.folder_slug_scroll = 0
                return
            elif ch in (10, 13, curses.KEY_ENTER):
                if app.folder_slug_list:
                    slug = app.folder_slug_list[app.folder_slug_cursor]
                    if app.recording:
                        # Inject into the ongoing recording stream — will be
                        # merged into the final transcript at the right position.
                        with app.audio_lock:
                            audio_secs = (sum(len(f) for f in app.audio_frames)
                                          / SAMPLE_RATE) if app.audio_frames else 0.0
                        app._recording_injections.append((audio_secs, slug))
                        # Update live preview to show slug inline
                        preview = app._live_preview_text
                        combined = f"{preview} {slug}" if preview else slug
                        app.ui_queue.put(("live_preview", combined))
                        app.set_status(f"Injected: {slug}")
                    else:
                        left_width = app.stdscr.getmaxyx()[1] * 2 // 5
                        app.fragments.append(slug)
                        self.persist_buffer()
                        ts = datetime.datetime.now().strftime("%H:%M:%S")
                        app.dictation_pane.add_line(f"[{ts}] {slug}", left_width)
                        app.set_status(f"Inserted: {slug}")
                return
            elif ch in (ord("e"), ord("E")):
                # Only allow editing in the Shortcuts category
                if app._browser_category == 0:
                    app.show_folder_slug = False
                    app.overlays.open_shortcut_editor()
                return
            elif ch == 9:  # Tab closes shortcuts browser
                app.show_folder_slug = False
                return
            elif ch == 27:
                app.show_folder_slug = False
                app.stdscr.nodelay(True)
                app.stdscr.getch()
                return
            # Other keys (including SPACE) fall through to main handler

        # Handle shortcut editor overlay
        if app.show_shortcut_editor:
            if app.shortcut_editing_text:
                if ch in (10, 13, curses.KEY_ENTER):
                    # Save the edited/new shortcut
                    text = app.shortcut_edit_buffer.strip()
                    if text:
                        idx = app.shortcut_editor_cursor
                        if idx < len(app._shortcut_strings):
                            app._shortcut_strings[idx] = text
                        else:
                            app._shortcut_strings.append(text)
                            app.shortcut_editor_cursor = len(app._shortcut_strings)
                        save_shortcuts(app._shortcut_strings)
                    app.shortcut_editing_text = False
                elif ch == 27:
                    app.stdscr.nodelay(True)
                    next_ch = app.stdscr.getch()
                    if next_ch == 91:  # '[' -- CSI sequence
                        csi = []
                        while True:
                            c = app.stdscr.getch()
                            if c == -1:
                                break
                            csi.append(c)
                            if 64 <= c <= 126:
                                break
                        if csi == [50, 48, 48, 126]:  # "200~" -- bracketed paste
                            pasted = self.read_paste_content()
                            self.inject_paste(pasted)
                        # else: ignore unknown CSI sequence
                    else:
                        # Pure ESC -- cancel editing
                        app.shortcut_editing_text = False
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    if app.shortcut_edit_cursor_pos > 0:
                        b = app.shortcut_edit_buffer
                        c = app.shortcut_edit_cursor_pos
                        app.shortcut_edit_buffer = b[:c-1] + b[c:]
                        app.shortcut_edit_cursor_pos -= 1
                elif ch == curses.KEY_DC:
                    b = app.shortcut_edit_buffer
                    c = app.shortcut_edit_cursor_pos
                    if c < len(b):
                        app.shortcut_edit_buffer = b[:c] + b[c+1:]
                elif ch == curses.KEY_LEFT:
                    app.shortcut_edit_cursor_pos = max(0, app.shortcut_edit_cursor_pos - 1)
                elif ch == curses.KEY_RIGHT:
                    app.shortcut_edit_cursor_pos = min(
                        len(app.shortcut_edit_buffer), app.shortcut_edit_cursor_pos + 1)
                elif ch == curses.KEY_HOME or ch == 1:  # Ctrl+A
                    app.shortcut_edit_cursor_pos = 0
                elif ch == curses.KEY_END or ch == 5:  # Ctrl+E
                    app.shortcut_edit_cursor_pos = len(app.shortcut_edit_buffer)
                elif 32 <= ch <= 126:
                    b = app.shortcut_edit_buffer
                    c = app.shortcut_edit_cursor_pos
                    app.shortcut_edit_buffer = b[:c] + chr(ch) + b[c:]
                    app.shortcut_edit_cursor_pos += 1
                return

            if ch == 27:
                app.show_shortcut_editor = False
                app.overlays.scan_folder_slugs()  # refresh to reflect edits
                app.show_folder_slug = True  # return to folder menu
                app.stdscr.nodelay(True)
                app.stdscr.getch()
            elif ch == curses.KEY_UP:
                if app.shortcut_editor_cursor > 0:
                    app.shortcut_editor_cursor -= 1
            elif ch == curses.KEY_DOWN:
                if app.shortcut_editor_cursor < len(app._shortcut_strings):
                    app.shortcut_editor_cursor += 1
            elif ch in (10, 13, curses.KEY_ENTER):
                idx = app.shortcut_editor_cursor
                if idx < len(app._shortcut_strings):
                    app.shortcut_edit_buffer = app._shortcut_strings[idx]
                else:
                    app.shortcut_edit_buffer = ""
                app.shortcut_edit_cursor_pos = len(app.shortcut_edit_buffer)
                app.shortcut_editing_text = True
            elif ch in (curses.KEY_DC, 330):  # Delete key
                idx = app.shortcut_editor_cursor
                if idx < len(app._shortcut_strings):
                    del app._shortcut_strings[idx]
                    save_shortcuts(app._shortcut_strings)
                    if app.shortcut_editor_cursor > len(app._shortcut_strings):
                        app.shortcut_editor_cursor = len(app._shortcut_strings)
            return

        # Handle settings overlay navigation
        if app.show_settings_overlay:
            # Inline text editing mode (e.g. prompt library path)
            if app.settings_editing_text:
                if ch in (10, 13, curses.KEY_ENTER):
                    app.settings_overlay.commit_text_edit()
                elif ch == 27:
                    app.stdscr.nodelay(True)
                    next_ch = app.stdscr.getch()
                    if next_ch == 91:  # '[' -- CSI sequence
                        csi = []
                        while True:
                            c = app.stdscr.getch()
                            if c == -1:
                                break
                            csi.append(c)
                            if 64 <= c <= 126:
                                break
                        if csi == [50, 48, 48, 126]:  # "200~" -- bracketed paste
                            pasted = self.read_paste_content()
                            self.inject_paste(pasted)
                        # else: ignore unknown CSI sequence
                    else:
                        # Pure ESC -- cancel editing
                        app.settings_overlay.cancel_text_edit()
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    if app.settings_edit_cursor > 0:
                        b = app.settings_edit_buffer
                        c = app.settings_edit_cursor
                        app.settings_edit_buffer = b[:c-1] + b[c:]
                        app.settings_edit_cursor -= 1
                elif ch == curses.KEY_DC:  # Delete key
                    b = app.settings_edit_buffer
                    c = app.settings_edit_cursor
                    if c < len(b):
                        app.settings_edit_buffer = b[:c] + b[c+1:]
                elif ch == curses.KEY_LEFT:
                    app.settings_edit_cursor = max(0, app.settings_edit_cursor - 1)
                elif ch == curses.KEY_RIGHT:
                    app.settings_edit_cursor = min(
                        len(app.settings_edit_buffer), app.settings_edit_cursor + 1)
                elif ch == curses.KEY_HOME or ch == 1:  # Ctrl+A
                    app.settings_edit_cursor = 0
                elif ch == curses.KEY_END or ch == 5:  # Ctrl+E
                    app.settings_edit_cursor = len(app.settings_edit_buffer)
                elif 32 <= ch <= 126:  # printable ASCII
                    b = app.settings_edit_buffer
                    c = app.settings_edit_cursor
                    app.settings_edit_buffer = b[:c] + chr(ch) + b[c:]
                    app.settings_edit_cursor += 1
                return

            # Voice sub-menu navigation
            if app.voice_submenu_open:
                if ch in (27,):
                    app.voice_submenu_open = False
                    app.stdscr.nodelay(True)
                    app.stdscr.getch()
                elif ch in (ord("q"), ord("Q")):
                    app.voice_submenu_open = False
                elif ch == curses.KEY_UP:
                    app.voice_submenu_cursor = (app.voice_submenu_cursor - 1) % len(app.voice_submenu_items)
                elif ch == curses.KEY_DOWN:
                    app.voice_submenu_cursor = (app.voice_submenu_cursor + 1) % len(app.voice_submenu_items)
                elif ch == curses.KEY_LEFT:
                    app.settings_overlay.voice_submenu_cycle(-1)
                elif ch == curses.KEY_RIGHT:
                    app.settings_overlay.voice_submenu_cycle(1)
                return

            # TTS sub-menu navigation
            if app.tts_submenu_open:
                if ch in (27,):
                    app.tts_submenu_open = False
                    app.stdscr.nodelay(True)
                    app.stdscr.getch()
                elif ch in (ord("q"), ord("Q")):
                    app.tts_submenu_open = False
                elif ch == curses.KEY_UP:
                    app.tts_submenu_cursor = (app.tts_submenu_cursor - 1) % len(app.tts_submenu_items)
                elif ch == curses.KEY_DOWN:
                    app.tts_submenu_cursor = (app.tts_submenu_cursor + 1) % len(app.tts_submenu_items)
                elif ch == curses.KEY_LEFT:
                    app.settings_overlay.tts_submenu_cycle(-1)
                elif ch == curses.KEY_RIGHT:
                    app.settings_overlay.tts_submenu_cycle(1)
                elif ch in (10, 13, curses.KEY_ENTER):
                    item = app.tts_submenu_items[app.tts_submenu_cursor]
                    if item.get("action"):
                        item["action"]()
                return

            # AI Models sub-menu navigation
            if app.ai_models_submenu_open:
                if ch in (27,):
                    app.ai_models_submenu_open = False
                    app.stdscr.nodelay(True)
                    app.stdscr.getch()
                elif ch in (ord("q"), ord("Q")):
                    app.ai_models_submenu_open = False
                elif ch == curses.KEY_UP:
                    selectable = [i for i, it in enumerate(app.ai_models_submenu_items)
                                 if it.get("options") is not None or it.get("action") is not None]
                    if selectable:
                        cur_pos = selectable.index(app.ai_models_submenu_cursor) if app.ai_models_submenu_cursor in selectable else 0
                        app.ai_models_submenu_cursor = selectable[(cur_pos - 1) % len(selectable)]
                    else:
                        app.ai_models_submenu_cursor = (app.ai_models_submenu_cursor - 1) % len(app.ai_models_submenu_items)
                elif ch == curses.KEY_DOWN:
                    selectable = [i for i, it in enumerate(app.ai_models_submenu_items)
                                 if it.get("options") is not None or it.get("action") is not None]
                    if selectable:
                        cur_pos = selectable.index(app.ai_models_submenu_cursor) if app.ai_models_submenu_cursor in selectable else 0
                        app.ai_models_submenu_cursor = selectable[(cur_pos + 1) % len(selectable)]
                    else:
                        app.ai_models_submenu_cursor = (app.ai_models_submenu_cursor + 1) % len(app.ai_models_submenu_items)
                elif ch == curses.KEY_LEFT:
                    app.settings_overlay.ai_models_submenu_cycle(-1)
                elif ch == curses.KEY_RIGHT:
                    app.settings_overlay.ai_models_submenu_cycle(1)
                elif ch in (10, 13, curses.KEY_ENTER):
                    item = app.ai_models_submenu_items[app.ai_models_submenu_cursor]
                    if item.get("action"):
                        if item.get("editable"):
                            item["action"]()  # will set settings_editing_text = True
                        else:
                            app.show_settings_overlay = False
                            item["action"]()
                return

            # Test Tools sub-menu navigation
            if app.test_tools_submenu_open:
                if ch in (27,):
                    app.test_tools_submenu_open = False
                    app.stdscr.nodelay(True)
                    app.stdscr.getch()
                elif ch in (ord("q"), ord("Q")):
                    app.test_tools_submenu_open = False
                elif ch == curses.KEY_UP:
                    app.test_tools_submenu_cursor = (app.test_tools_submenu_cursor - 1) % len(app.test_tools_submenu_items)
                elif ch == curses.KEY_DOWN:
                    app.test_tools_submenu_cursor = (app.test_tools_submenu_cursor + 1) % len(app.test_tools_submenu_items)
                elif ch == curses.KEY_LEFT:
                    app.settings_overlay.test_tools_submenu_cycle(-1)
                elif ch == curses.KEY_RIGHT:
                    app.settings_overlay.test_tools_submenu_cycle(1)
                elif ch in (10, 13, curses.KEY_ENTER):
                    item = app.test_tools_submenu_items[app.test_tools_submenu_cursor]
                    if item.get("action"):
                        item["action"]()
                return

            # Google Cast sub-menu navigation
            if app.cast_submenu_open:
                selectable_count = sum(
                    1 for it in app.cast_submenu_items
                    if it.get("type") != "section")
                if ch in (27,):
                    app.cast_submenu_open = False
                    app.stdscr.nodelay(True)
                    app.stdscr.getch()
                elif ch in (ord("q"), ord("Q")):
                    app.cast_submenu_open = False
                elif ch == curses.KEY_UP:
                    if selectable_count:
                        app.cast_submenu_cursor = (
                            app.cast_submenu_cursor - 1) % selectable_count
                elif ch == curses.KEY_DOWN:
                    if selectable_count:
                        app.cast_submenu_cursor = (
                            app.cast_submenu_cursor + 1) % selectable_count
                elif ch == curses.KEY_LEFT:
                    app.settings_overlay.cast_submenu_cycle(-1)
                elif ch == curses.KEY_RIGHT:
                    app.settings_overlay.cast_submenu_cycle(1)
                elif ch in (10, 13, curses.KEY_ENTER):
                    sel = [it for it in app.cast_submenu_items
                           if it.get("type") != "section"]
                    if 0 <= app.cast_submenu_cursor < len(sel):
                        item = sel[app.cast_submenu_cursor]
                        if item.get("action"):
                            item["action"]()
                return

            if ch in (ord("o"), ord("O"), ord("q"), ord("Q"), 27):
                app.show_settings_overlay = False
                app.tts_submenu_open = False
                app.test_tools_submenu_open = False
                app.voice_submenu_open = False
                app.ai_models_submenu_open = False
                app.cast_submenu_open = False
                if ch == 27:
                    app.stdscr.nodelay(True)
                    app.stdscr.getch()
            elif ch == curses.KEY_UP:
                app.settings_overlay.settings_cursor_move(-1)
            elif ch == curses.KEY_DOWN:
                app.settings_overlay.settings_cursor_move(1)
            elif ch == curses.KEY_LEFT:
                app.settings_overlay.settings_cycle(-1)
            elif ch == curses.KEY_RIGHT:
                app.settings_overlay.settings_cycle(1)
            elif ch in (10, 13, curses.KEY_ENTER):
                item = app.settings_overlay.selectable_item()
                if item and item.get("action"):
                    if item.get("editable"):
                        item["action"]()  # keep modal open for editing
                    elif item.get("submenu"):
                        item["action"]()  # submenu openers keep modal open
                    else:
                        # Non-submenu, non-editable action: close modal then run
                        # but check if we're in a submenu first
                        if any([app.voice_submenu_open, app.tts_submenu_open,
                                app.test_tools_submenu_open, app.ai_models_submenu_open]):
                            item["action"]()  # just run it, don't close main modal
                        else:
                            app.show_settings_overlay = False
                            item["action"]()
            return

        # Handle confirmation dialog for [N]ew prompt
        if app.confirming_new:
            if ch == ord("y") or ch == ord("Y"):
                app.confirming_new = False
                app.execution.save_prompt()
                app.execution.do_new_prompt()
            elif ch == ord("n") or ch == ord("N"):
                app.confirming_new = False
                app.execution.do_new_prompt()
            else:
                # Any other key cancels
                app.confirming_new = False
                app.set_status("New prompt cancelled.")
            return

        # Handle confirmation dialog for editing a historical prompt
        if app.confirming_edit_historical:
            if ch == ord("y") or ch == ord("Y"):
                app.confirming_edit_historical = False
                app.execution.copy_historical_to_current()
            else:
                # Any other key cancels
                app.confirming_edit_historical = False
                app.set_status("Edit cancelled.")
            return

        # Handle favorites slot selection
        if app.choosing_fav_slot:
            app.choosing_fav_slot = False
            slot_idx = app.favorites.key_to_fav_slot(ch)
            if slot_idx >= 0:
                app.favorites.assign_to_fav_slot(slot_idx)
            else:
                app.set_status("Favorites assignment cancelled.")
            return

        # Handle favorites overwrite confirmation
        if app.confirming_fav_overwrite:
            app.confirming_fav_overwrite = False
            if ch == ord("y") or ch == ord("Y"):
                app.favorites.do_assign_fav_slot(app._pending_fav_slot)
            else:
                app._pending_fav_slot = -1
                app.set_status("Favorites assignment cancelled.")
            return

        # Handle direct text entry mode in dictation buffer
        if app.typing_mode:
            if ch in (10, 13, curses.KEY_ENTER):
                # Submit the typed text as a fragment
                text = app.typing_buffer.strip()
                if text:
                    left_width = app.stdscr.getmaxyx()[1] // 2
                    app.fragments.append(text)
                    self.persist_buffer()
                    ts = datetime.datetime.now().strftime("%H:%M:%S")
                    app.dictation_pane.add_line(f"[{ts}] {text}", left_width)
                    app.set_status("Text entry added.")
                else:
                    app.set_status("Empty entry discarded.")
                app.typing_mode = False
                app.typing_buffer = ""
                app.typing_cursor = 0
            elif ch == 27:
                # ESC -- could be cancel or start of a CSI sequence (e.g. paste)
                # Check for CSI before cancelling so paste doesn't lose the buffer
                app.stdscr.nodelay(True)
                next_ch = app.stdscr.getch()
                if next_ch == 91:  # '[' -- CSI sequence (could be paste)
                    csi = []
                    while True:
                        c = app.stdscr.getch()
                        if c == -1:
                            break
                        csi.append(c)
                        if 64 <= c <= 126:
                            break
                    if csi == [50, 48, 48, 126]:  # bracketed paste
                        pasted = self.read_paste_content()
                        flat = " ".join(pasted.strip().splitlines())
                        b = app.typing_buffer
                        c = app.typing_cursor
                        app.typing_buffer = b[:c] + flat + b[c:]
                        app.typing_cursor += len(flat)
                        app.set_status("Pasted into text entry")
                    # else: unknown CSI sequence in typing mode -- ignore
                else:
                    # Plain ESC -- cancel typing mode
                    app.typing_mode = False
                    app.typing_buffer = ""
                    app.typing_cursor = 0
                    app.set_status("Text entry cancelled.")
            elif ch == curses.KEY_LEFT:
                if app.typing_cursor > 0:
                    app.typing_cursor -= 1
            elif ch == curses.KEY_RIGHT:
                if app.typing_cursor < len(app.typing_buffer):
                    app.typing_cursor += 1
            elif ch == curses.KEY_HOME:
                app.typing_cursor = 0
            elif ch == curses.KEY_END:
                app.typing_cursor = len(app.typing_buffer)
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                if app.typing_cursor > 0:
                    b = app.typing_buffer
                    app.typing_buffer = b[:app.typing_cursor - 1] + b[app.typing_cursor:]
                    app.typing_cursor -= 1
            elif ch in (curses.KEY_DC, 330):
                if app.typing_cursor < len(app.typing_buffer):
                    b = app.typing_buffer
                    app.typing_buffer = b[:app.typing_cursor] + b[app.typing_cursor + 1:]
            elif 32 <= ch <= 126:
                b = app.typing_buffer
                app.typing_buffer = b[:app.typing_cursor] + chr(ch) + b[app.typing_cursor:]
                app.typing_cursor += 1
            return

        if ch == ord("q") or ch == ord("Q"):
            app.runner.kill_agent(sync=True)
            app.running = False

        elif ch == ord("x") or ch == ord("X"):
            app.runner.kill_agent(sync=True)
            app.restart = True
            app.running = False

        elif ch == ord("k") or ch == ord("K"):
            if app.agent_state in (AgentState.DOWNLOADING, AgentState.RECEIVING):
                app.runner.kill_agent()

        elif ch == ord("w") or ch == ord("W"):
            if app.agent_state in (AgentState.IDLE, AgentState.DONE):
                app.runner.clear_session()

        elif ch == ord(" "):
            if app.recording:
                app.recording_helper.stop_recording()
            elif not app.refining:
                app.recording_helper.start_recording()

        elif ch == ord("r") or ch == ord("R"):
            if not app.refining and not app.recording:
                if app.browser_index >= 0:
                    app.execution.confirm_edit_historical()
                else:
                    app.execution.start_refine()

        elif ch == ord("d") or ch == ord("D"):
            if not app.refining and not app.recording:
                app.execution.execute_raw()

        elif ch == ord("s") or ch == ord("S"):
            if not app.refining and not app.recording:
                app.execution.save_prompt()

        elif ch == ord("f") or ch == ord("F"):
            if not app.refining and not app.recording:
                if app.browser_view == "favorites" and app.browser_index >= 0:
                    app.favorites.remove_from_favorites()
                else:
                    app.favorites.add_to_favorites(None)

        elif ch == ord("e") or ch == ord("E"):
            if app.agent_state in (AgentState.IDLE, AgentState.DONE):
                app.execution.execute_prompt()

        elif ch == ord("n") or ch == ord("N"):
            if not app.refining and not app.recording:
                app.execution.new_prompt()

        elif ch == ord("u") or ch == ord("U"):
            if app.fragments:
                removed = app.fragments.pop()
                self.persist_buffer()
                self.rebuild_dictation_pane()
                preview = removed[:40] + "\u2026" if len(removed) > 40 else removed
                app.set_status(f"Undid: {preview}")
            else:
                app.set_status("Nothing to undo.")

        elif ch == ord("c") or ch == ord("C"):
            app.fragments.clear()
            self.clear_buffer_file()
            app.dictation_pane.lines.clear()
            app.dictation_pane.scroll_offset = 0
            app.browser.set_dictation_info(app.stdscr.getmaxyx()[1] // 2)
            app.set_status("Dictation buffer cleared.")

        elif ch == ord("p") or ch == ord("P"):
            if app.last_tts_summary:
                stop_speaking()
                speak_text(app.last_tts_summary, on_done=lambda: app.ui_queue.put(
                    ("status", "Ready for next prompt.", CP_STATUS)))
                app.set_status("Replaying summary...", CP_STATUS)
            else:
                app.set_status("No summary to replay.")

        elif ch == curses.KEY_LEFT:
            if app.browser_view == "active":
                app.browser.scan_history_prompts()
            prompt_list = app.browser.current_browser_list()
            if not prompt_list:
                view_name = "favorite" if app.browser_view == "favorites" else "history"
                app.set_status(f"No {view_name} prompts to browse.")
            elif app.browser_index == -1:
                app.browser_index = len(prompt_list) - 1
                app.browser.load_browser_prompt(app.stdscr.getmaxyx()[1] // 2)
            elif app.browser_index > 0:
                app.browser_index -= 1
                app.browser.load_browser_prompt(app.stdscr.getmaxyx()[1] // 2)
            else:
                app.set_status("Already at oldest prompt.")

        elif ch == curses.KEY_RIGHT:
            prompt_list = app.browser.current_browser_list()
            if app.browser_index == -1:
                app.set_status("Already at current session.")
            elif app.browser_index < len(prompt_list) - 1:
                app.browser_index += 1
                app.browser.load_browser_prompt(app.stdscr.getmaxyx()[1] // 2)
            else:
                app.browser_index = -1
                app.browser.load_browser_prompt(app.stdscr.getmaxyx()[1] // 2)

        elif ch == curses.KEY_UP:
            # Toggle between active and favorites (up)
            if app.prompt_pane.scroll_offset == 0:
                if app.browser_view == "active":
                    app.favorites.load_favorites_slots()
                    app.browser_view = "favorites"
                else:
                    app.browser_view = "active"
                app.browser_index = -1
                app.browser.load_browser_prompt(app.stdscr.getmaxyx()[1] // 2)
                h = app.stdscr.getmaxyx()[0]
                content_height = h - 4
                visible = content_height // 2 - 2
                max_off = max(0, len(app.prompt_pane.lines) - visible)
                app.prompt_pane.scroll_offset = max_off
                view_names = {"active": "active prompts", "favorites": "favorites"}
                count = len(app.browser.current_browser_list())
                app.set_status(f"Switched to {view_names[app.browser_view]}. ({count} entries)")
            else:
                app.prompt_pane.scroll_up(2)

        elif ch == curses.KEY_DOWN:
            # Toggle between active and favorites (down)
            h = app.stdscr.getmaxyx()[0]
            content_height = h - 4
            visible = content_height // 2 - 2
            max_off = max(0, len(app.prompt_pane.lines) - visible)
            if app.prompt_pane.scroll_offset >= max_off:
                if app.browser_view == "active":
                    app.favorites.load_favorites_slots()
                    app.browser_view = "favorites"
                else:
                    app.browser_view = "active"
                app.browser_index = -1
                app.browser.load_browser_prompt(app.stdscr.getmaxyx()[1] // 2)
                view_names = {"active": "active prompts", "favorites": "favorites"}
                count = len(app.browser.current_browser_list())
                app.set_status(f"Switched to {view_names[app.browser_view]}. ({count} entries)")
            else:
                app.prompt_pane.scroll_down(visible, 2)

        elif ch == curses.KEY_END:
            if not app.refining and not app.recording:
                app.execution.new_prompt()

        elif ch == curses.KEY_HOME:
            # Return to current prompt editor
            app.browser_view = "active"
            app.browser_index = -1
            app.browser.load_browser_prompt(app.stdscr.getmaxyx()[1] // 2)
            app.set_status("Returned to current prompt.")

        elif ch == curses.KEY_PPAGE:
            if app.prompt_pane.is_scrollable:
                app.prompt_pane.scroll_up(5)
            else:
                app.agent_pane.scroll_up(5)

        elif ch == curses.KEY_NPAGE:
            h = app.stdscr.getmaxyx()[0]
            content_height = h - 4
            visible = content_height // 2 - 2
            if app.prompt_pane.is_scrollable:
                app.prompt_pane.scroll_down(visible, 5)
            else:
                app.agent_pane.scroll_down(content_height - 2, 5)

        elif ch == ord("["):
            name = cycle_tts_voice(-1)
            app.set_status(f"Voice: {name}", CP_VOICE)
            model_path = get_tts_voice_model()
            if not model_path or not model_path.exists():
                app.set_status(f"Voice {name} not downloaded!", CP_VOICE)
            else:
                speak_text(f"Voice changed to {name.replace('-', ' ').replace('_', ' ')}")

        elif ch == ord("]"):
            name = cycle_tts_voice(1)
            app.set_status(f"Voice: {name}", CP_VOICE)
            model_path = get_tts_voice_model()
            if not model_path or not model_path.exists():
                app.set_status(f"Voice {name} not downloaded!", CP_VOICE)
            else:
                speak_text(f"Voice changed to {name.replace('-', ' ').replace('_', ' ')}")

        elif ord("0") <= ch <= ord("9"):
            # Number keys 1-9, 0 -> quick-load favorites slots
            if not app.recording and not app.refining:
                app.favorites.quick_load_favorite(ch)

        elif ch in (10, 13, curses.KEY_ENTER):
            # Enter starts direct text entry in dictation buffer
            if not app.recording and not app.refining:
                app.typing_mode = True
                app.typing_buffer = ""
                app.typing_cursor = 0
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                app.set_status(f"[{ts}] Type text, Enter to submit, ESC to cancel")

        elif ch == 9:  # Tab
            # Tab opens shortcuts browser (allowed during recording for injection)
            if (not app.refining
                    and app.agent_state in (AgentState.IDLE, AgentState.DONE)
                    and (app.working_dir or app._shortcut_strings)):
                app.overlays.scan_folder_slugs()
                # Pick first non-empty category, or stay on current
                has_any = any(app._browser_cat_lists)
                if has_any:
                    # If current category is empty, jump to first non-empty
                    if not app._browser_cat_lists[app._browser_category]:
                        for i, lst in enumerate(app._browser_cat_lists):
                            if lst:
                                app._browser_category = i
                                break
                    app.folder_slug_list = app._browser_cat_lists[app._browser_category]
                    app.show_folder_slug = True
                    app.folder_slug_cursor = 0
                    app.folder_slug_scroll = 0
                else:
                    app.set_status("No shortcuts, folders, or documents found.")
            elif (not app.working_dir and not app._shortcut_strings):
                app.set_status("Set working directory or add shortcuts in ESC \u2192 Options.")

        elif ch == ord("h") or ch == ord("H"):
            app.show_help_overlay = True

        elif ch == ord("o") or ch == ord("O"):
            app.show_settings_overlay = True
            app.settings_cursor = 0
            app.tts_submenu_open = False
            app.test_tools_submenu_open = False
            app.voice_submenu_open = False
            app.ai_models_submenu_open = False

        elif ch == ord("t") or ch == ord("T"):
            app.cycle_tip()
            app.set_status("Tip cycled.")

        elif ch == ord("m") or ch == ord("M"):
            # Toggle AI provider between Gemini and Claude
            gemini = get_provider_by_name("Gemini")
            claude = get_provider_by_name("Claude")
            if (gemini and gemini.is_installed()
                    and claude and claude.is_installed()):
                if app.ai_provider.name == "Claude":
                    app.settings_overlay.set_ai_provider("Gemini")
                else:
                    app.settings_overlay.set_ai_provider("Claude")
            else:
                app.set_status("Both Gemini and Claude must be installed to toggle.")

        elif ch == 27:
            # ESC key -- could be menu, arrow key, or bracketed paste start
            app.stdscr.nodelay(True)
            next_ch = app.stdscr.getch()
            if next_ch == -1:
                # Pure ESC press -- open menu
                app.show_escape_menu = True
                app.escape_menu_cursor = 0
            elif next_ch == 91:  # '[' -- CSI sequence
                # Read remaining CSI params to check for paste start "200~"
                csi = []
                while True:
                    c = app.stdscr.getch()
                    if c == -1:
                        break
                    csi.append(c)
                    # CSI terminates at 0x40-0x7E (letters, ~, etc.)
                    if 64 <= c <= 126:
                        break
                if csi == [50, 48, 48, 126]:  # "200~" -- bracketed paste start
                    pasted = self.read_paste_content()
                    self.inject_paste(pasted)
                # Otherwise it was a normal escape sequence (arrow key etc.)
                # which curses already handled via KEY_UP/DOWN/etc.
