"""Main render loop and drawing functions for VoiceCode BBS."""

import curses
import time
import datetime
import os

from version import __version__
from voicecode.constants import AgentState, BANNER
from voicecode.ui.colors import (
    CP_HEADER, CP_PROMPT, CP_DICTATION, CP_STATUS, CP_HELP,
    CP_RECORDING, CP_BANNER, CP_ACCENT, CP_AGENT, CP_XFER,
    CP_VOICE, CP_CTX_GREEN, CP_CTX_YELLOW, CP_CTX_RED,
    CP_FAV_EMPTY, CP_FAV_FILLED,
)
from voicecode.tts.voices import TTS_AVAILABLE, get_tts_voice_name


class DrawingHelper:
    """Handles all drawing/rendering for the BBS app.

    Receives a reference to the app instance for state access.
    """

    def __init__(self, app):
        self.app = app

    def draw_loading(self, msg: str):
        """Draw loading screen with banner."""
        app = self.app
        app.stdscr.clear()
        h, w = app.stdscr.getmaxyx()
        lines = BANNER.strip().split("\n")
        max_line_w = max(len(l) for l in lines)
        start_y = max(0, (h - len(lines) - 4) // 2)
        block_x = max(0, (w - max_line_w) // 2)
        for i, line in enumerate(lines):
            try:
                cp = CP_BANNER if i < 7 else CP_ACCENT
                app.stdscr.addstr(start_y + i, block_x, line[:w-1],
                                  curses.color_pair(cp) | curses.A_BOLD)
            except curses.error:
                pass
        msg_x = max(0, (w - len(msg)) // 2)
        try:
            app.stdscr.addstr(start_y + len(lines) + 2, msg_x, msg,
                              curses.color_pair(CP_STATUS) | curses.A_BOLD)
        except curses.error:
            pass
        app.stdscr.refresh()

    def draw_bar(self, y: int, text: str, color: int):
        """Draw a full-width status/help bar."""
        app = self.app
        w = app.stdscr.getmaxyx()[1]
        padded = text + " " * max(0, w - len(text))
        try:
            app.stdscr.addnstr(y, 0, padded, w - 1,
                               curses.color_pair(color) | curses.A_BOLD)
        except curses.error:
            pass

    def draw(self):
        """Main render function -- draws the three-pane layout and overlays."""
        app = self.app
        app.stdscr.erase()
        h, w = app.stdscr.getmaxyx()

        if h < 12 or w < 60:
            try:
                app.stdscr.addstr(0, 0, "Terminal too small! Need 60x12 minimum.")
            except curses.error:
                pass
            app.stdscr.refresh()
            return

        # -- Header bar --
        header = f" VOICECODE BBS v{__version__}"
        now = datetime.datetime.now().strftime("%H:%M:%S")
        sysop = f"SysOp: {os.getenv('USER', '?')}"
        voice_tag = f"Voice: {get_tts_voice_name()}"
        model_tag = f"Model: {app.ai_provider.name}"
        right = f"{model_tag}  {voice_tag}  {sysop}  {now} "
        header_line = header + " " * max(0, w - len(header) - len(right)) + right
        try:
            app.stdscr.addnstr(0, 0, header_line, w,
                               curses.color_pair(CP_HEADER) | curses.A_BOLD)
        except curses.error:
            pass

        # -- Divider --
        prompt_list = app.browser.current_browser_list()
        if app.browser_index >= 0:
            bar_label = "Favorites" if app.browser_view == "favorites" else "History"
            browse_info = f"{bar_label}: {app.browser_index + 1}/{len(prompt_list)}"
        else:
            browse_info = f"Session v{app.prompt_version}"
        node_info = (f" {browse_info} \u2502 "
                     f"Favs: {app.favorites.favorites_slot_count()}/10 \u2502 "
                     f"History: {len(app.history_prompts)} \u2502 "
                     f"Frags: {len(app.fragments)} \u2502 Agent: {app.agent_state.upper()} ")
        divider = "\u2500" * 2 + node_info + "\u2500" * max(0, w - 2 - len(node_info))
        try:
            app.stdscr.addnstr(1, 0, divider, w - 1,
                               curses.color_pair(CP_ACCENT))
        except curses.error:
            pass

        # -- Three-pane layout --
        # content_height = everything between divider and help/status bars
        content_height = h - 4  # header + divider + help + status
        left_width = w // 2
        right_width = w - left_width
        prompt_height = content_height // 2
        dictation_height = content_height - prompt_height

        content_y = 2

        # Top-left: Prompt browser
        app.prompt_pane.draw(app.stdscr, content_y, 0,
                             prompt_height, left_width)

        # -- Favorites indicator on left border of Prompt Browser --
        fav_labels = ["F", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]
        fav_start_y = content_y + 1  # first content row inside pane
        for fi, flabel in enumerate(fav_labels):
            fy = fav_start_y + fi
            if fy >= content_y + prompt_height - 1:  # don't overwrite bottom border
                break
            if fi == 0:
                # "F" label in the pane's border color
                attr = curses.color_pair(app.prompt_pane.color_pair) | curses.A_BOLD
            else:
                slot_idx = fi - 1  # slots 0-9
                has_data = app.favorites_slots[slot_idx] is not None
                if has_data:
                    attr = curses.color_pair(CP_FAV_FILLED) | curses.A_BOLD
                else:
                    attr = curses.color_pair(CP_FAV_EMPTY)
            try:
                app.stdscr.addstr(fy, 0, flabel, attr)
            except curses.error:
                pass

        # -- Prompt pane bottom border: browse/view hints --
        prompt_bottom_y = content_y + prompt_height - 1
        hint_attr = curses.color_pair(app.prompt_pane.color_pair) | curses.A_BOLD
        home_hint = " [Home]Current "
        browse_hint = " [\u2190\u2192]Browse [\u2191\u2193]View "
        bh_x = left_width - len(browse_hint) - 1
        try:
            if bh_x > 1:
                app.stdscr.addstr(prompt_bottom_y, bh_x, browse_hint, hint_attr)
            if len(home_hint) + 1 < bh_x:
                app.stdscr.addstr(prompt_bottom_y, 1, home_hint, hint_attr)
        except curses.error:
            pass

        # Bottom-left: Dictation buffer
        app.dictation_pane.draw(app.stdscr, content_y + prompt_height, 0,
                                dictation_height, left_width)

        # -- Typing mode input line (overlays last content line of dictation pane) --
        if app.typing_mode:
            type_y = content_y + prompt_height + dictation_height - 2  # just above bottom border
            type_x = 1
            type_w = left_width - 2
            if type_w > 4 and type_y > content_y + prompt_height:
                prefix = "\u25b8 "
                avail = type_w - len(prefix)
                buf = app.typing_buffer
                cur = app.typing_cursor
                # Scroll the buffer if cursor is past visible area
                scroll = max(0, cur - avail + 1)
                visible = buf[scroll:scroll + avail]
                cursor_pos_in_vis = cur - scroll
                padded = prefix + visible + " " * max(0, avail - len(visible))
                entry_attr = curses.color_pair(CP_VOICE) | curses.A_BOLD
                try:
                    app.stdscr.addnstr(type_y, type_x, padded, type_w, entry_attr)
                    # Draw cursor
                    cx = type_x + len(prefix) + cursor_pos_in_vis
                    if cx < type_x + type_w:
                        ch_under = buf[cur] if cur < len(buf) else " "
                        app.stdscr.addstr(type_y, cx, ch_under,
                                          entry_attr | curses.A_REVERSE)
                except curses.error:
                    pass

        # Right: Agent terminal (full height)
        if app.agent_state == AgentState.DOWNLOADING:
            app.animation.draw_agent_xfer(content_y, left_width, content_height, right_width)
        else:
            app.agent_pane.draw(app.stdscr, content_y, left_width,
                                content_height, right_width)

        # Yellow spinner in agent pane header while agent is active
        if app.agent_state in (AgentState.DOWNLOADING, AgentState.RECEIVING):
            spin_chars = "|/-\\"
            spin_ch = spin_chars[int(time.time() * 4) % len(spin_chars)]
            # Place spinner right after the title text in the header
            title_text = " AGENT TERMINAL " if app.agent_state != AgentState.DOWNLOADING else " FILE TRANSFER "
            spin_x = left_width + 3 + len(title_text)
            if spin_x < left_width + right_width - 2:
                try:
                    app.stdscr.addstr(
                        content_y, spin_x, spin_ch,
                        curses.color_pair(CP_XFER) | curses.A_BOLD)
                except curses.error:
                    pass
            # Show activity indicator while agent is receiving and typewriter is idle
            if (app.agent_state == AgentState.RECEIVING
                    and not app.typewriter_queue):
                now_t = time.time()
                last_act = app.agent_last_activity
                spinners = "\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f"

                if not app.agent_first_output:
                    # Still waiting for first output
                    elapsed = now_t - app.xfer_start_time - 3.0
                    spin = spinners[int(max(0, elapsed) * 6) % len(spinners)]
                    dots = "." * (int(max(0, elapsed) * 2) % 4)
                    thinking_text = f" {spin} Agent processing{dots}"
                elif last_act > 0:
                    # Had output before, now idle -- show time since last activity
                    idle_secs = now_t - last_act
                    if idle_secs >= 1.0:
                        spin = spinners[int(idle_secs * 4) % len(spinners)]
                        idle_int = int(idle_secs)
                        thinking_text = f" {spin} Working... {idle_int}s since last output"
                        if idle_secs >= 60:
                            thinking_text += "  [K to kill]"
                    else:
                        thinking_text = None
                else:
                    thinking_text = None

                if thinking_text:
                    think_y = content_y + 1 + len(app.agent_pane.lines)
                    if think_y < content_y + content_height - 1:
                        try:
                            app.stdscr.addnstr(
                                think_y, left_width + 1, thinking_text,
                                right_width - 2,
                                curses.color_pair(CP_XFER) | curses.A_BOLD)
                        except curses.error:
                            pass

        # -- Agent terminal bottom border: context meter + session info --
        agent_bottom_y = content_y + content_height - 1
        if app.context_window_size > 0:
            ratio = min(1.0, app.context_tokens_used / app.context_window_size)
            if ratio < 0.5:
                ctx_cp = CP_CTX_GREEN
            elif ratio < 0.8:
                ctx_cp = CP_CTX_YELLOW
            else:
                ctx_cp = CP_CTX_RED
            pct = int(ratio * 100)
            ctx_label = f" CTX:{pct}% "
        else:
            ctx_cp = CP_CTX_GREEN
            ctx_label = ""

        # Session info tag (includes active provider name)
        provider_tag = app.ai_provider.name
        if app.session_id:
            sess_label = f" {provider_tag}: {app.session_turns} turn{'s' if app.session_turns != 1 else ''} "
        else:
            sess_label = f" {provider_tag} (no session) "
        hint_label = " [W]New session "

        # Draw colored bottom border for agent pane
        bar_inner_w = right_width - 2  # inside corner chars
        info_text = sess_label + ctx_label
        # Pad bar to fill, then overlay info on the right
        if bar_inner_w > 0:
            ctx_attr = curses.color_pair(ctx_cp) | curses.A_BOLD
            # Build the bottom border with session/context info
            bar = "\u2550" * max(0, bar_inner_w - len(info_text) - len(hint_label))
            full_bar = "\u255a" + hint_label + bar + info_text + "\u255d"
            try:
                app.stdscr.addnstr(agent_bottom_y, left_width, full_bar,
                                   right_width, ctx_attr)
            except curses.error:
                pass

        # -- Arrow key control indicator (yellow, top-right of active pane) --
        arrow_label = " [\u2190\u2192] "
        arrow_attr = curses.color_pair(CP_XFER) | curses.A_BOLD
        if app.show_folder_slug:
            # Shortcuts browser open: agent terminal has arrow key control
            arrow_x = left_width + right_width - len(arrow_label) - 1
            try:
                app.stdscr.addstr(content_y, arrow_x, arrow_label, arrow_attr)
            except curses.error:
                pass
        else:
            # Normal mode: prompt browser has arrow key control
            arrow_x = left_width - len(arrow_label) - 1
            if arrow_x > 4:
                try:
                    app.stdscr.addstr(content_y, arrow_x, arrow_label, arrow_attr)
                except curses.error:
                    pass

        # -- Favorites hint on prompt pane top border (drawn after arrow to take priority) --
        if app.browser_view == "favorites" and app.browser_index >= 0:
            fav_hint = " [F] Remove "
            fav_x = left_width - len(fav_hint) - 1
            if fav_x > 4:
                try:
                    app.stdscr.addstr(content_y, fav_x, fav_hint,
                                      curses.color_pair(CP_RECORDING) | curses.A_BOLD)
                except curses.error:
                    pass
        elif app.browser_index >= 0 or app.current_prompt or app.executed_prompt_text:
            fav_hint = " [F] \u2605 Fav slot "
            fav_x = left_width - len(fav_hint) - 1
            if fav_x > 4:
                try:
                    app.stdscr.addstr(content_y, fav_x, fav_hint,
                                      curses.color_pair(CP_RECORDING) | curses.A_BOLD)
                except curses.error:
                    pass

        # -- Data-flow hotkey hints (drawn after panes so they overlay borders) --
        hint_attr = curses.color_pair(CP_VOICE) | curses.A_BOLD
        # R: bottom border of Prompt Browser -- dictation ^ refines into prompt
        r_label = "=^R^="
        r_y = content_y + prompt_height - 1  # bottom border of prompt pane
        r_x = max(1, (left_width - len(r_label)) // 2)
        try:
            app.stdscr.addstr(r_y, r_x, r_label, hint_attr)
        except curses.error:
            pass
        # E: right edge of Prompt Browser -- prompt > executes in agent
        e_label = "E>"
        e_y = content_y + prompt_height // 2
        try:
            app.stdscr.addstr(e_y, left_width - 1, e_label, hint_attr)
        except curses.error:
            pass
        # D: right edge of Dictation Buffer -- dictation > direct to agent
        d_label = "D>"
        d_y = content_y + prompt_height + dictation_height // 2
        try:
            app.stdscr.addstr(d_y, left_width - 1, d_label, hint_attr)
        except curses.error:
            pass

        # -- Help bar --
        help_y = h - 2
        if app.typing_mode:
            help_text = " TYPING \u25b8 [Enter] Submit  [ESC] Cancel  \u2014 Type text directly into dictation buffer"
            self.draw_bar(help_y, help_text, CP_VOICE)
        elif app.recording:
            help_text = " [SPC] Stop recording"
            self.draw_bar(help_y, help_text, CP_HELP)
        elif app.confirming_new:
            help_text = " \u2588\u2588 UNSAVED PROMPT \u2014 [Y] Save first  [N] Discard  [other] Cancel \u2588\u2588"
            self.draw_bar(help_y, help_text, CP_RECORDING)
        elif app.confirming_edit_historical:
            help_text = " \u2588\u2588 EDIT HISTORICAL PROMPT? \u2014 [Y] Copy as new working prompt  [other] Cancel \u2588\u2588"
            self.draw_bar(help_y, help_text, CP_RECORDING)
        elif app.choosing_fav_slot:
            help_text = " \u2588\u2588 CHOOSE FAVORITES SLOT \u2014 [1-9, 0] to assign  [ESC/other] Cancel \u2588\u2588"
            self.draw_bar(help_y, help_text, CP_RECORDING)
        elif app.confirming_fav_overwrite:
            slot_num = app._pending_fav_slot + 1
            help_text = f" \u2588\u2588 SLOT {slot_num} OCCUPIED \u2014 [Y] Overwrite  [other] Cancel \u2588\u2588"
            self.draw_bar(help_y, help_text, CP_RECORDING)
        elif app.agent_state in (AgentState.DOWNLOADING, AgentState.RECEIVING):
            help_text = " \u25cc Agent working... [K] to kill"
            self.draw_bar(help_y, help_text, CP_STATUS)
        else:
            voice_label = "[V]oice" if TTS_AVAILABLE else ""
            keys = " [Q]uit [X]Restart | [N]ew [U]ndo [C]lear [K]ill [W]NewSess [M]odel [Tab]Shortcuts"
            self.draw_bar(help_y, keys, CP_HELP)
            # Draw [V]oice in red, right-justified
            w = app.stdscr.getmaxyx()[1]
            vx = w - len(voice_label) - 1
            if TTS_AVAILABLE and vx > len(keys):
                try:
                    app.stdscr.addnstr(help_y, vx, voice_label, w - vx - 1,
                                       curses.color_pair(CP_CTX_RED) | curses.A_BOLD)
                except curses.error:
                    pass

        # -- Status bar --
        self.draw_bar(h - 1, f" {app.status_msg}", app.status_color)

        # -- Overlays (drawn last so they're on top) --
        if app.show_help_overlay:
            app.overlays.draw_help()
        if app.show_about_overlay:
            app.overlays.draw_about()
        if app.show_settings_overlay:
            app.settings_overlay.draw()
        if app.show_folder_slug:
            app.overlays.draw_folder_slug()
        if app.show_shortcut_editor:
            app.overlays.draw_shortcut_editor()
        if app.show_escape_menu:
            app.overlays.draw_escape_menu()

        app.stdscr.refresh()
