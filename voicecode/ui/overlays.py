"""Overlay renderers for help, about, escape menu, shortcuts browser, and shortcut editor."""

import curses
from pathlib import Path

from version import __version__
from voicecode.ui.colors import (
    CP_AGENT,
    CP_HEADER,
    CP_HELP,
    CP_RECORDING,
    CP_VOICE,
    CP_XTREE_BG,
    CP_XTREE_BORDER,
    CP_XTREE_SEL,
)
from voicecode.settings import load_shortcuts


class OverlayRenderer:
    """Renders overlay modals. Gets a reference to the app for state access."""

    def __init__(self, app):
        self.app = app

    def draw_help(self):
        """Draw a 90s BBS-style help modal overlay on top of the UI."""
        app = self.app
        h, w = app.stdscr.getmaxyx()

        # Overlay dimensions — leave a border of surrounding UI visible
        overlay_w = min(64, w - 6)
        overlay_h = min(30, h - 4)
        if overlay_w < 40 or overlay_h < 16:
            return

        start_y = max(1, (h - overlay_h) // 2)
        start_x = max(2, (w - overlay_w) // 2)

        border_attr = curses.color_pair(CP_HEADER) | curses.A_BOLD
        text_attr = curses.color_pair(CP_HELP) | curses.A_BOLD
        body_attr = curses.color_pair(CP_HELP)
        accent_attr = curses.color_pair(CP_HEADER) | curses.A_BOLD

        inner_w = overlay_w - 2

        # Content lines for the help overlay
        content = [
            "",
            f"  V O I C E C O D E   B B S   v{__version__}",
            "  Voice-Driven Prompt Workshop",
            "",
            "  ── How It Works ──────────────────",
            "  Dictate speech fragments, refine",
            "  them into polished prompts with AI,",
            "  then execute via AI agent.",
            "",
            "  ── Keyboard Controls ─────────────",
            "  SPACE  Toggle recording on/off",
            "  R      Refine fragments → prompt",
            "  E      Execute current prompt",
            "  D      Direct execute (skip refine)",
            "  F      Assign to favorites slot",
            "  1-0    Quick-load favorites 1-10",
            "  N      New prompt",
            "  U      Undo last dictation entry",
            "  C      Clear dictation buffer",
            "  K      Kill running agent",
            "  W      New session (clear context)",
            "  ←/→    Browse within current view",
            "  ↑/↓    Cycle active/favorites/history",
            "  Home   Return to current prompt",
            "  Enter  Type text into dictation",
            "  Tab    Shortcuts browser",
            "  PgUp/Dn  Scroll agent pane",
            "  [/]    Cycle TTS voice",
            "  P      Replay last TTS summary",
            "  M      Toggle Gemini / Claude",
            "  O      Options / Settings",
            "  H      This help screen",
            "  X      Restart application",
            "  Q      Quit",
            "  ESC    Main menu (Options/About...)",
            "",
            "  Press H, ESC, or Q to close",
        ]

        # Truncate if overlay is too small
        content = content[:overlay_h - 2]

        try:
            # Top border
            top = "╔" + "═" * inner_w + "╗"
            app.stdscr.addnstr(start_y, start_x, top, overlay_w, border_attr)

            # Title bar
            title = " HELP — SYSTEM GUIDE "
            title_line = "║" + title.center(inner_w) + "║"
            app.stdscr.addnstr(start_y + 1, start_x, title_line, overlay_w, accent_attr)

            # Title separator
            sep = "╠" + "═" * inner_w + "╣"
            app.stdscr.addnstr(start_y + 2, start_x, sep, overlay_w, border_attr)

            # Body lines
            for i, line in enumerate(content):
                row = start_y + 3 + i
                if row >= start_y + overlay_h - 1:
                    break
                padded = line + " " * max(0, inner_w - len(line))
                body_line = "║" + padded[:inner_w] + "║"
                app.stdscr.addnstr(row, start_x, body_line, overlay_w, body_attr)

            # Fill remaining rows
            for row in range(start_y + 3 + len(content), start_y + overlay_h - 1):
                if row >= start_y + overlay_h - 1:
                    break
                empty_line = "║" + " " * inner_w + "║"
                app.stdscr.addnstr(row, start_x, empty_line, overlay_w, body_attr)

            # Bottom border
            bottom = "╚" + "═" * inner_w + "╝"
            app.stdscr.addnstr(start_y + overlay_h - 1, start_x, bottom, overlay_w, border_attr)
        except curses.error:
            pass

    def draw_about(self):
        """Draw a BBS-style about / title screen overlay."""
        app = self.app
        h, w = app.stdscr.getmaxyx()

        overlay_w = min(64, w - 6)
        overlay_h = min(26, h - 4)
        if overlay_w < 40 or overlay_h < 16:
            return

        start_y = max(1, (h - overlay_h) // 2)
        start_x = max(2, (w - overlay_w) // 2)

        border_attr = curses.color_pair(CP_HEADER) | curses.A_BOLD
        body_attr = curses.color_pair(CP_HELP)
        accent_attr = curses.color_pair(CP_HEADER) | curses.A_BOLD

        inner_w = overlay_w - 2

        content = [
            "",
            "  ╦  ╦╔═╗╦╔═╗╔═╗╔═╗╔═╗╔╦╗╔═╗",
            "  ╚╗╔╝║ ║║║  ║╣ ║  ║ ║ ║║║╣ ",
            "   ╚╝ ╚═╝╩╚═╝╚═╝╚═╝╚═╝═╩╝╚═╝",
            f"          B  B  S   v{__version__}",
            "",
            "  ── About ─────────────────────",
            "  Voice-driven prompt workshop",
            "  for interacting with AI agents.",
            "  Dictate, refine, and execute",
            "  prompts — all by voice.",
            "",
            "  ── Author ────────────────────",
            "  Charles Schiele",
            "  github.com/shazbot996/voicecode-bbs",
            "",
            "  ── Built With ────────────────",
            "  Python, faster-whisper, Silero VAD",
            "  Piper TTS, curses",
            "",
            "  Press A, ESC, or Q to close",
        ]

        content = content[:overlay_h - 2]

        try:
            top = "╔" + "═" * inner_w + "╗"
            app.stdscr.addnstr(start_y, start_x, top, overlay_w, border_attr)

            title = " ABOUT — VOICECODE BBS "
            title_line = "║" + title.center(inner_w) + "║"
            app.stdscr.addnstr(start_y + 1, start_x, title_line, overlay_w, accent_attr)

            sep = "╠" + "═" * inner_w + "╣"
            app.stdscr.addnstr(start_y + 2, start_x, sep, overlay_w, border_attr)

            for i, line in enumerate(content):
                row = start_y + 3 + i
                if row >= start_y + overlay_h - 1:
                    break
                padded = line + " " * max(0, inner_w - len(line))
                body_line = "║" + padded[:inner_w] + "║"
                app.stdscr.addnstr(row, start_x, body_line, overlay_w, body_attr)

            for row in range(start_y + 3 + len(content), start_y + overlay_h - 1):
                if row >= start_y + overlay_h - 1:
                    break
                empty_line = "║" + " " * inner_w + "║"
                app.stdscr.addnstr(row, start_x, empty_line, overlay_w, body_attr)

            bottom = "╚" + "═" * inner_w + "╝"
            app.stdscr.addnstr(start_y + overlay_h - 1, start_x, bottom, overlay_w, border_attr)
        except curses.error:
            pass

    def draw_escape_menu(self):
        """Draw a centered BBS/DOS-style Escape menu modal."""
        app = self.app
        h, w = app.stdscr.getmaxyx()

        num_items = len(app._escape_menu_items)
        # Box: title bar (3 rows) + items + blank top/bottom padding + bottom border
        overlay_h = num_items + 6  # top border + title + sep + blank + items + blank + bottom
        overlay_w = 36
        if overlay_w > w - 4 or overlay_h > h - 2:
            return

        start_y = max(1, (h - overlay_h) // 2)
        start_x = max(2, (w - overlay_w) // 2)

        border_attr = curses.color_pair(CP_HEADER) | curses.A_BOLD
        body_attr = curses.color_pair(CP_HELP) | curses.A_BOLD
        accent_attr = curses.color_pair(CP_HEADER) | curses.A_BOLD

        sel_attr = curses.color_pair(CP_VOICE) | curses.A_BOLD

        inner_w = overlay_w - 2

        try:
            # Top border
            app.stdscr.addnstr(start_y, start_x,
                               "╔" + "═" * inner_w + "╗", overlay_w, border_attr)
            # Title
            title = " MAIN MENU "
            title_line = "║" + title.center(inner_w) + "║"
            app.stdscr.addnstr(start_y + 1, start_x, title_line, overlay_w, accent_attr)
            # Separator
            app.stdscr.addnstr(start_y + 2, start_x,
                               "╠" + "═" * inner_w + "╣", overlay_w, border_attr)

            # Blank line above items
            app.stdscr.addnstr(start_y + 3, start_x,
                               "║" + " " * inner_w + "║", overlay_w, body_attr)

            # Menu items
            for i, (label, _action) in enumerate(app._escape_menu_items):
                row = start_y + 4 + i
                if i == app.escape_menu_cursor:
                    line = f"  > {label}  "
                    attr = sel_attr
                else:
                    line = f"    {label}  "

                    attr = body_attr
                padded = line + " " * max(0, inner_w - len(line))
                app.stdscr.addnstr(row, start_x,
                                   "║" + padded[:inner_w] + "║", overlay_w, attr)

            # Blank line below items
            blank_row = start_y + 4 + num_items
            app.stdscr.addnstr(blank_row, start_x,
                               "║" + " " * inner_w + "║", overlay_w, body_attr)

            # Bottom border
            app.stdscr.addnstr(blank_row + 1, start_x,
                               "╚" + "═" * inner_w + "╝", overlay_w, border_attr)
        except curses.error:
            pass

    def scan_folder_slugs(self):
        """Build three category lists: shortcuts, project folders, documents."""
        app = self.app
        app._shortcut_strings = load_shortcuts()
        # Category 0: Shortcuts
        app._browser_cat_lists[0] = list(app._shortcut_strings)

        # Category 1: Project Folders
        dirs: list[str] = []
        root = Path(app.working_dir).expanduser() if app.working_dir else None
        if root and root.is_dir():
            try:
                for entry in sorted(root.iterdir()):
                    if entry.is_dir() and not entry.name.startswith("."):
                        rel = entry.name
                        dirs.append(rel + "/")
                        try:
                            for sub in sorted(entry.iterdir()):
                                if sub.is_dir() and not sub.name.startswith("."):
                                    dirs.append(rel + "/" + sub.name + "/")
                        except PermissionError:
                            pass
            except PermissionError:
                pass
        app._browser_cat_lists[1] = dirs

        # Category 2: Documents (all files recursive from {working_dir}/docs/)
        docs: list[str] = []
        if app.working_dir:
            doc_root = Path(app.working_dir).expanduser() / "docs"
            wd_root = Path(app.working_dir).expanduser()
            if doc_root.is_dir():
                try:
                    all_files = [f for f in doc_root.rglob("*")
                                 if f.is_file()
                                 and not any(p.startswith(".") for p in f.relative_to(doc_root).parts)]
                    for doc_file in sorted(all_files, key=lambda f: f.stat().st_mtime, reverse=True):
                        docs.append(str(doc_file.relative_to(wd_root)))
                except (PermissionError, OSError):
                    pass
        app._browser_cat_lists[2] = docs

        # Flat list is the active category's list (for cursor/scroll compat)
        app.folder_slug_list = app._browser_cat_lists[app._browser_category]

    def draw_folder_slug(self):
        """Draw the categorised browser overlay on the agent pane."""
        app = self.app
        h, w = app.stdscr.getmaxyx()

        # Agent pane geometry
        content_height = h - 4
        left_width = w // 2
        right_width = w - left_width
        content_y = 2

        # Overlay is inset from agent pane borders so terminal peeks through
        overlay_x = left_width + 3
        overlay_y = content_y + 2
        overlay_w = right_width - 6
        overlay_h = content_height - 4
        if overlay_w < 20 or overlay_h < 7:
            return

        bg_attr = curses.color_pair(CP_XTREE_BG)
        sel_attr = curses.color_pair(CP_XTREE_SEL) | curses.A_BOLD
        border_attr = curses.color_pair(CP_XTREE_BORDER) | curses.A_BOLD

        inner_w = overlay_w - 2
        inner_h = overlay_h - 6  # border + subtitle + tabs + separator + footer + border

        try:
            # Top border
            top = "╔" + "═" * inner_w + "╗"
            app.stdscr.addnstr(overlay_y, overlay_x, top, overlay_w, border_attr)

            # Subtitle
            subtitle = ' <-- "String Injector"! '
            subtitle_line = "║" + subtitle.center(inner_w) + "║"
            app.stdscr.addnstr(overlay_y + 1, overlay_x, subtitle_line, overlay_w, border_attr)

            # Category tabs row
            cat = app._browser_category
            tabs = ""
            for i, name in enumerate(app._browser_categories):
                count = len(app._browser_cat_lists[i])
                label = f" {name} ({count}) "
                if i == cat:
                    label = f"[{label}]"
                else:
                    label = f" {label} "
                tabs += label
            tabs_padded = tabs.center(inner_w)[:inner_w]
            tabs_line = "║" + tabs_padded + "║"
            # Highlight active tab
            app.stdscr.addnstr(overlay_y + 2, overlay_x, tabs_line, overlay_w, border_attr)

            # Tab separator
            sep = "╠" + "═" * inner_w + "╣"
            app.stdscr.addnstr(overlay_y + 3, overlay_x, sep, overlay_w, border_attr)

            # Scrolling: keep cursor visible
            if app.folder_slug_cursor < app.folder_slug_scroll:
                app.folder_slug_scroll = app.folder_slug_cursor
            elif app.folder_slug_cursor >= app.folder_slug_scroll + inner_h:
                app.folder_slug_scroll = app.folder_slug_cursor - inner_h + 1

            # Icon per category
            cat_icons = {0: "⚡", 1: "📁", 2: "📄"}
            cat_icons_sel = {0: "⚡", 1: "📂", 2: "📄"}
            icon_base = cat_icons.get(cat, "·")
            icon_sel = cat_icons_sel.get(cat, "·")

            # List rows
            # Show hint when Documents tab is active but not configured
            show_not_configured = (cat == 2 and not app.working_dir
                                   and not app.folder_slug_list)
            if show_not_configured:
                hint_lines = [
                    "",
                    "Working directory not configured.",
                    "",
                    "Press O to open Options and set",
                    "the Working Directory path.",
                    "Docs are read from docs/ subfolder.",
                ]
                hint_attr = curses.color_pair(CP_XTREE_BORDER)
                for i in range(inner_h):
                    row_y = overlay_y + 4 + i
                    if i < len(hint_lines):
                        text = hint_lines[i].center(inner_w)[:inner_w]
                    else:
                        text = " " * inner_w
                    line = "║" + text + "║"
                    app.stdscr.addnstr(row_y, overlay_x, line, overlay_w,
                                       hint_attr if i < len(hint_lines) else bg_attr)
            else:
                for i in range(inner_h):
                    row_y = overlay_y + 4 + i
                    idx = app.folder_slug_scroll + i
                    if idx < len(app.folder_slug_list):
                        entry = app.folder_slug_list[idx]
                        is_sel = (idx == app.folder_slug_cursor)
                        icon = icon_sel if is_sel else icon_base
                        text = f" {icon} {entry}"
                        # +1 for double-width emoji
                        display_w = len(text) + 1
                        padded = text[:inner_w] + " " * max(0, inner_w - display_w)
                        line = "║" + padded + "║"
                        attr = sel_attr if is_sel else bg_attr
                        app.stdscr.addnstr(row_y, overlay_x, line, overlay_w, attr)
                    else:
                        blank = "║" + " " * inner_w + "║"
                        app.stdscr.addnstr(row_y, overlay_x, blank, overlay_w, bg_attr)

            # Footer
            edit_hint = "  E Edit" if cat == 0 else ""
            footer_text = f" ←→ Tab  ↑↓ Select  Enter Insert{edit_hint}  Tab/Esc Close "
            footer_padded = footer_text.center(inner_w)
            footer_line = "║" + footer_padded[:inner_w] + "║"
            app.stdscr.addnstr(overlay_y + overlay_h - 2, overlay_x,
                               footer_line, overlay_w, border_attr)

            # Bottom border
            bottom = "╚" + "═" * inner_w + "╝"
            app.stdscr.addnstr(overlay_y + overlay_h - 1, overlay_x,
                               bottom, overlay_w, border_attr)
        except curses.error:
            pass

    def open_shortcut_editor(self):
        """Open the shortcut editor overlay."""
        app = self.app
        app._shortcut_strings = load_shortcuts()
        app.show_shortcut_editor = True
        app.shortcut_editor_cursor = 0
        app.shortcut_editor_scroll = 0
        app.shortcut_editing_text = False

    def draw_shortcut_editor(self):
        """Draw the shortcut editor overlay."""
        app = self.app
        h, w = app.stdscr.getmaxyx()

        overlay_w = min(68, w - 6)
        # +1 for the [Add New] row
        num_entries = len(app._shortcut_strings) + 1
        overlay_h = min(4 + num_entries + 2, h - 4)
        if overlay_w < 40 or overlay_h < 6:
            return

        start_y = max(1, (h - overlay_h) // 2)
        start_x = max(2, (w - overlay_w) // 2)

        border_attr = curses.color_pair(CP_HEADER) | curses.A_BOLD
        body_attr = curses.color_pair(CP_HELP)
        accent_attr = curses.color_pair(CP_HEADER) | curses.A_BOLD
        sel_attr = curses.color_pair(CP_RECORDING) | curses.A_BOLD
        val_attr = curses.color_pair(CP_AGENT) | curses.A_BOLD

        inner_w = overlay_w - 2
        inner_h = overlay_h - 5  # borders + title + separator + footer

        try:
            # Top border
            top = "╔" + "═" * inner_w + "╗"
            app.stdscr.addnstr(start_y, start_x, top, overlay_w, border_attr)

            # Title bar
            title = " EDIT SHORTCUTS "
            title_line = "║" + title.center(inner_w) + "║"
            app.stdscr.addnstr(start_y + 1, start_x, title_line, overlay_w, accent_attr)

            # Title separator
            sep = "╠" + "═" * inner_w + "╣"
            app.stdscr.addnstr(start_y + 2, start_x, sep, overlay_w, border_attr)

            # Scrolling
            if app.shortcut_editor_cursor < app.shortcut_editor_scroll:
                app.shortcut_editor_scroll = app.shortcut_editor_cursor
            elif app.shortcut_editor_cursor >= app.shortcut_editor_scroll + inner_h:
                app.shortcut_editor_scroll = app.shortcut_editor_cursor - inner_h + 1

            # List rows
            for i in range(inner_h):
                row_y = start_y + 3 + i
                idx = app.shortcut_editor_scroll + i
                is_sel = (idx == app.shortcut_editor_cursor)
                line_attr = sel_attr if is_sel else body_attr

                if idx < len(app._shortcut_strings):
                    entry = app._shortcut_strings[idx]
                    cursor = ">" if is_sel else " "

                    if is_sel and app.shortcut_editing_text:
                        # Inline editing mode
                        buf = app.shortcut_edit_buffer
                        cur = app.shortcut_edit_cursor_pos
                        max_vis = inner_w - 7
                        vis_start = max(0, cur - max_vis + 1) if cur > max_vis else 0
                        vis_text = buf[vis_start:vis_start + max_vis]
                        vis_cur = cur - vis_start
                        text = f" {cursor} {vis_text}"
                        padded = text + " " * max(0, inner_w - len(text))
                        line = "║" + padded[:inner_w] + "║"
                        app.stdscr.addnstr(row_y, start_x, line, overlay_w, val_attr)
                        # Draw cursor
                        cursor_x = start_x + 1 + 4 + vis_cur
                        if cursor_x < start_x + overlay_w - 1:
                            ch_under = buf[cur] if cur < len(buf) else " "
                            app.stdscr.addnstr(
                                row_y, cursor_x, ch_under, 1,
                                curses.color_pair(CP_AGENT) | curses.A_REVERSE)
                    else:
                        text = f" {cursor} {entry}"
                        padded = text + " " * max(0, inner_w - len(text))
                        line = "║" + padded[:inner_w] + "║"
                        app.stdscr.addnstr(row_y, start_x, line, overlay_w, line_attr)
                elif idx == len(app._shortcut_strings):
                    # [Add New] row
                    cursor = ">" if is_sel else " "
                    if is_sel and app.shortcut_editing_text:
                        buf = app.shortcut_edit_buffer

                        cur = app.shortcut_edit_cursor_pos
                        max_vis = inner_w - 7
                        vis_start = max(0, cur - max_vis + 1) if cur > max_vis else 0
                        vis_text = buf[vis_start:vis_start + max_vis]
                        vis_cur = cur - vis_start
                        text = f" {cursor} {vis_text}"
                        padded = text + " " * max(0, inner_w - len(text))
                        line = "║" + padded[:inner_w] + "║"
                        app.stdscr.addnstr(row_y, start_x, line, overlay_w, val_attr)
                        cursor_x = start_x + 1 + 4 + vis_cur
                        if cursor_x < start_x + overlay_w - 1:
                            ch_under = buf[cur] if cur < len(buf) else " "
                            app.stdscr.addnstr(
                                row_y, cursor_x, ch_under, 1,
                                curses.color_pair(CP_AGENT) | curses.A_REVERSE)
                    else:
                        text = f" {cursor} [Add New Shortcut]"
                        padded = text + " " * max(0, inner_w - len(text))
                        line = "║" + padded[:inner_w] + "║"
                        app.stdscr.addnstr(row_y, start_x, line, overlay_w, line_attr)
                else:
                    blank = "║" + " " * inner_w + "║"
                    app.stdscr.addnstr(row_y, start_x, blank, overlay_w, body_attr)

            # Footer
            if app.shortcut_editing_text:
                footer_text = " Enter Save  Esc Cancel "
            else:
                footer_text = " Enter Edit  Del Remove  Esc Close "
            footer_padded = footer_text.center(inner_w)
            footer_line = "║" + footer_padded[:inner_w] + "║"
            app.stdscr.addnstr(start_y + overlay_h - 2, start_x, footer_line,
                               overlay_w, accent_attr)

            # Bottom border
            bottom = "╚" + "═" * inner_w + "╝"
            app.stdscr.addnstr(start_y + overlay_h - 1, start_x, bottom,
                               overlay_w, border_attr)
        except curses.error:
            pass
