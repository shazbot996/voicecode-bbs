"""Overlay renderers for help, about, escape menu, shortcuts browser, shortcut editor, and document reader."""

import curses
import textwrap
from pathlib import Path

from version import __version__
from voicecode.publish.frontmatter import parse_frontmatter
from voicecode.ui.colors import (
    CP_AGENT,
    CP_DOC_BADGE_CYAN,
    CP_DOC_BADGE_GREEN,
    CP_DOC_BADGE_MAGENTA,
    CP_DOC_BADGE_YELLOW,
    CP_DOC_BODY,
    CP_DOC_DIM,
    CP_DOC_HEADING,
    CP_DOC_LIST_BG,
    CP_DOC_LIST_BORDER,
    CP_DOC_LIST_SEL,
    CP_HEADER,
    CP_HELP,
    CP_PROMPT,
    CP_RECORDING,
    CP_VOICE,
)
from voicecode.data.tools import get_tool_names, get_tool_detail
from voicecode.settings import load_shortcuts


DOC_TYPE_COLORS = {
    "arch": CP_DOC_BADGE_CYAN,
    "adr": CP_DOC_BADGE_CYAN,
    "plan": CP_DOC_BADGE_GREEN,
    "spec": CP_DOC_BADGE_GREEN,
    "glossary": CP_DOC_BADGE_MAGENTA,
    "schema": CP_DOC_BADGE_MAGENTA,
    "constraints": CP_DOC_BADGE_MAGENTA,
    "conventions": CP_DOC_BADGE_MAGENTA,
    "readme": CP_DOC_BADGE_YELLOW,
}


class OverlayRenderer:
    """Renders overlay modals. Gets a reference to the app for state access."""

    def __init__(self, app):
        self.app = app

    def draw_help(self):
        """Draw a 90s BBS-style help modal overlay on top of the UI."""
        app = self.app
        h, w = app.stdscr.getmaxyx()

        # Two-column layout — wider overlay to fit all content
        overlay_w = min(100, w - 4)
        overlay_h = min(30, h - 4)
        if overlay_w < 40 or overlay_h < 16:
            return

        start_y = max(1, (h - overlay_h) // 2)
        start_x = max(2, (w - overlay_w) // 2)

        border_attr = curses.color_pair(CP_HEADER) | curses.A_BOLD
        body_attr = curses.color_pair(CP_HELP)
        accent_attr = curses.color_pair(CP_HEADER) | curses.A_BOLD

        inner_w = overlay_w - 2
        col_w = inner_w // 2

        # Left column content
        left_col = [
            f" V O I C E C O D E  B B S  v{__version__}",
            " Voice-Driven Prompt Workshop",
            "",
            " ── How It Works ──────────────",
            " Dictate speech fragments, refine",
            " them into prompts with AI, then",
            " execute via AI agent.",
            "",
            " ── Recording & Input ─────────",
            " SPACE  Toggle voice recording",
            " Enter  Type text into dictation",
            " U      Undo last dictation entry",
            " C      Clear dictation buffer",
            "",
            " ── Prompt Actions ────────────",
            " R      Refine fragments → prompt",
            " E      Execute current prompt",
            " D      Direct execute (skip refine)",
            " S      Save prompt to history",
            " N      New prompt",
            " K      Kill running agent",
            " W      New session (clear context)",
        ]

        # Right column content
        right_col = [
            " ── History & Favorites ───────",
            " ←/→    Browse prompt history",
            " Home   Return to current prompt",
            " F      Toggle favorites / add fav",
            " 1-0    Quick-load favorites 1-10",
            "",
            " ── Navigation & Scrolling ────",
            " ↑/↓      Scroll prompt pane",
            " PgUp/Dn  Scroll agent output",
            " End      Jump to bottom of output",
            " Tab      Shortcuts/docs browser",
            "",
            " ── Voice & AI ────────────────",
            " [/]    Cycle TTS voice",
            " Y      Replay last TTS summary",
            " M      Toggle Gemini / Claude",
            " P      Publish document",
            "",
            " ── System ────────────────────",
            " O      Options / Settings",
            " T      Cycle tip text",
            " H      This help screen",
            " ESC    Main menu",
            " X      Restart application",
            " Q      Quit",
        ]

        # Pad columns to same length
        max_rows = max(len(left_col), len(right_col))
        while len(left_col) < max_rows:
            left_col.append("")
        while len(right_col) < max_rows:
            right_col.append("")

        # Adjust overlay height to fit content (title rows + body + bottom border)
        body_rows = min(max_rows, overlay_h - 4)

        try:
            # Top border
            top = "╔" + "═" * inner_w + "╗"
            app.stdscr.addnstr(start_y, start_x, top, overlay_w, border_attr)

            # Title bar
            title = " HELP — SYSTEM GUIDE "
            title_line = "║" + title.center(inner_w) + "║"
            app.stdscr.addnstr(start_y + 1, start_x, title_line, overlay_w, accent_attr)

            # Title separator with column divider
            sep = "╠" + "═" * col_w + "╤" + "═" * (inner_w - col_w - 1) + "╣"
            app.stdscr.addnstr(start_y + 2, start_x, sep, overlay_w, border_attr)

            # Body lines — two columns side by side
            for i in range(body_rows):
                row = start_y + 3 + i
                ltext = left_col[i] if i < len(left_col) else ""
                rtext = right_col[i] if i < len(right_col) else ""
                right_w = inner_w - col_w - 1
                lpad = ltext + " " * max(0, col_w - len(ltext))
                rpad = rtext + " " * max(0, right_w - len(rtext))
                body_line = "║" + lpad[:col_w] + "│" + rpad[:right_w] + "║"
                app.stdscr.addnstr(row, start_x, body_line, overlay_w, body_attr)

            # Footer row
            footer_row = start_y + 3 + body_rows
            footer_text = " Press H, ESC, or Q to close "
            right_w = inner_w - col_w - 1
            footer_inner = footer_text.center(inner_w)
            # Footer separator
            fsep = "╠" + "═" * col_w + "╧" + "═" * (inner_w - col_w - 1) + "╣"
            app.stdscr.addnstr(footer_row, start_x, fsep, overlay_w, border_attr)
            footer_line = "║" + footer_inner + "║"
            app.stdscr.addnstr(footer_row + 1, start_x, footer_line, overlay_w, accent_attr)

            # Bottom border
            bottom = "╚" + "═" * inner_w + "╝"
            app.stdscr.addnstr(footer_row + 2, start_x, bottom, overlay_w, border_attr)
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

        # Build front matter type cache for document badges
        app._doc_type_cache = {}
        if app.working_dir:
            wd_root = Path(app.working_dir).expanduser()
            for rel_path in docs:
                try:
                    full = wd_root / rel_path
                    head = full.read_text(encoding="utf-8")[:512]
                    fm = parse_frontmatter(head)
                    if fm.get("type"):
                        app._doc_type_cache[rel_path] = fm["type"]
                except (OSError, UnicodeDecodeError):
                    pass

        # Category 3: Tools (provider-aware library)
        app._browser_cat_lists[3] = get_tool_names(app.ai_provider.name)

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

        cat = app._browser_category
        bg_attr = curses.color_pair(CP_DOC_LIST_BG)
        sel_attr = curses.color_pair(CP_DOC_LIST_SEL) | curses.A_BOLD
        border_attr = curses.color_pair(CP_DOC_LIST_BORDER) | curses.A_BOLD

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
                hint_attr = curses.color_pair(CP_DOC_LIST_BORDER)
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
                        attr = sel_attr if is_sel else bg_attr
                        if cat == 2:
                            # Table layout: fixed-width type column + path
                            type_col_w = 13  # fits "[CONSTRAINTS]"
                            doc_type = app._doc_type_cache.get(entry, "") if hasattr(app, '_doc_type_cache') else ""
                            if doc_type:
                                badge = f"[{doc_type.upper()}]"
                            else:
                                badge = ""
                            badge_padded = badge.ljust(type_col_w)
                            text = f" {badge_padded} {entry}"
                            display_w = len(text)
                            padded = text[:inner_w] + " " * max(0, inner_w - display_w)
                            line = "║" + padded + "║"
                            app.stdscr.addnstr(row_y, overlay_x, line, overlay_w, attr)
                            # Overlay badge with type color
                            if badge and not is_sel:
                                badge_x = overlay_x + 1 + 1  # after ║ + space
                                badge_cp = DOC_TYPE_COLORS.get(doc_type, CP_HEADER)
                                badge_attr = curses.color_pair(badge_cp) | curses.A_BOLD
                                try:
                                    app.stdscr.addstr(row_y, badge_x, badge_padded, badge_attr)
                                except curses.error:
                                    pass
                        else:
                            text = f" {entry}"
                            display_w = len(text)
                            padded = text[:inner_w] + " " * max(0, inner_w - display_w)
                            line = "║" + padded + "║"
                            app.stdscr.addnstr(row_y, overlay_x, line, overlay_w, attr)
                    else:
                        blank = "║" + " " * inner_w + "║"
                        app.stdscr.addnstr(row_y, overlay_x, blank, overlay_w, bg_attr)

            # Footer
            if cat == 0:
                extra_hint = "  E Edit"
            elif cat in (2, 3):
                extra_hint = "  Enter View"
            else:
                extra_hint = ""
            footer_text = f" ←→ Tab  ↑↓ Select  Ins Inject{extra_hint}  Tab/Esc Close "
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

    # ─── Document Reader ──────────────────────────────────────────

    def open_doc_reader(self, full_path: str, display_title: str, on_close=None):
        """Open the document reader overlay for the given file."""
        app = self.app
        app.doc_reader_path = full_path
        app.doc_reader_title = display_title
        app.doc_reader_scroll = 0
        app.doc_reader_on_close = on_close
        try:
            content = Path(full_path).read_text(encoding="utf-8")
        except Exception as e:
            content = f"[Error reading file: {e}]"
        # Pre-wrap lines will happen at draw time based on available width
        app.doc_reader_lines = content.splitlines()
        fm = parse_frontmatter(content)
        app.doc_reader_doc_type = fm.get("type", "")
        app.show_doc_reader = True

    def open_tool_detail(self, index: int):
        """Open the document reader with tool detail content."""
        app = self.app
        title, lines = get_tool_detail(index, app.ai_provider.name)
        app.doc_reader_path = ""
        app.doc_reader_title = title
        app.doc_reader_scroll = 0
        app.doc_reader_on_close = None
        app.doc_reader_lines = lines
        app.doc_reader_doc_type = ""
        app.doc_edit_mode = False
        app.show_doc_reader = True

    def draw_doc_reader(self):
        """Draw a near-full-screen markdown document reader/editor overlay."""
        app = self.app
        h, w = app.stdscr.getmaxyx()

        # Near full-screen with margins
        margin_x = 2
        margin_top = 2
        margin_bot = 2
        box_x = margin_x
        box_y = margin_top
        box_w = w - margin_x * 2
        box_h = h - margin_top - margin_bot

        if box_w < 40 or box_h < 10:
            return

        type_cp = DOC_TYPE_COLORS.get(app.doc_reader_doc_type, CP_HEADER)
        border_attr = curses.color_pair(type_cp) | curses.A_BOLD
        title_attr = curses.color_pair(type_cp) | curses.A_BOLD
        body_attr = curses.color_pair(CP_DOC_BODY) | curses.A_BOLD
        heading_attr = curses.color_pair(CP_DOC_HEADING) | curses.A_BOLD
        dim_attr = curses.color_pair(CP_DOC_DIM)

        inner_w = box_w - 2
        content_w = inner_w - 2  # 1 char padding each side
        visible_h = box_h - 4  # top border + title + sep + bottom border

        if app.doc_edit_mode:
            self._draw_doc_editor(app, box_x, box_y, box_w, box_h, inner_w, content_w,
                                  visible_h, border_attr, title_attr, body_attr,
                                  heading_attr, dim_attr)
        else:
            self._draw_doc_viewer(app, box_x, box_y, box_w, box_h, inner_w, content_w,
                                  visible_h, border_attr, title_attr, body_attr,
                                  heading_attr, dim_attr)

    def _draw_doc_viewer(self, app, box_x, box_y, box_w, box_h, inner_w, content_w,
                         visible_h, border_attr, title_attr, body_attr, heading_attr, dim_attr):
        """Draw read-only document viewer."""
        # Word-wrap source lines to fit content width
        wrapped: list[tuple[str, int]] = []  # (line_text, style: 0=normal, 1=heading, 2=dim)
        for raw_line in app.doc_reader_lines:
            stripped = raw_line.rstrip()
            if stripped.startswith("#"):
                for wl in textwrap.wrap(stripped, width=content_w) or [stripped]:
                    wrapped.append((wl, 1))
            elif stripped.startswith("---") or stripped.startswith("```"):
                wrapped.append((stripped[:content_w], 2))
            elif stripped == "":
                wrapped.append(("", 0))
            else:
                for wl in textwrap.wrap(stripped, width=content_w) or [stripped]:
                    wrapped.append((wl, 0))

        max_scroll = max(0, len(wrapped) - visible_h)
        app.doc_reader_scroll = max(0, min(app.doc_reader_scroll, max_scroll))

        try:
            # Top border
            top = "╔" + "═" * inner_w + "╗"
            app.stdscr.addnstr(box_y, box_x, top, box_w, border_attr)

            # Title bar
            if app.doc_reader_doc_type:
                badge = app.doc_reader_doc_type.upper()
                title = f" [{badge}] {app.doc_reader_title} "
            else:
                title = f" {app.doc_reader_title} "
            if len(title) > inner_w - 4:
                title = title[:inner_w - 7] + "… "
            title_line = "║" + title.center(inner_w) + "║"
            app.stdscr.addnstr(box_y + 1, box_x, title_line, box_w, title_attr)

            # Separator
            sep = "╠" + "═" * inner_w + "╣"
            app.stdscr.addnstr(box_y + 2, box_x, sep, box_w, border_attr)

            # Content lines
            for i in range(visible_h):
                row_y = box_y + 3 + i
                line_idx = app.doc_reader_scroll + i
                if line_idx < len(wrapped):
                    text, style = wrapped[line_idx]
                    if style == 1:
                        attr = heading_attr
                    elif style == 2:
                        attr = dim_attr
                    else:
                        attr = body_attr
                    padded = " " + text + " " * max(0, inner_w - 1 - len(text))
                    line = "║" + padded[:inner_w] + "║"
                    app.stdscr.addnstr(row_y, box_x, line, box_w, attr)
                else:
                    blank = "║" + " " * inner_w + "║"
                    app.stdscr.addnstr(row_y, box_x, blank, box_w, body_attr)

            # Bottom border with scroll info and help
            pct = int(app.doc_reader_scroll / max_scroll * 100) if max_scroll > 0 else 100
            scroll_info = f" {pct}% "
            if app.doc_reader_path:
                help_text = " [↑↓/PgUp/PgDn]Scroll [M]Maintain [Enter]Edit [Ins]Inject [ESC/Q]Close "
            else:
                help_text = " [↑↓/PgUp/PgDn]Scroll [Ins]Inject [ESC/Q]Close "
            border_bot = "╚" + "═" * inner_w + "╝"
            app.stdscr.addnstr(box_y + box_h - 1, box_x, border_bot, box_w, border_attr)
            app.stdscr.addstr(box_y + box_h - 1, box_x + 2, scroll_info, border_attr)
            hx = box_x + box_w - len(help_text) - 2
            if hx > box_x + len(scroll_info) + 4:
                app.stdscr.addstr(box_y + box_h - 1, hx, help_text, border_attr)

            # Scroll indicator bar on right border
            if max_scroll > 0 and visible_h > 2:
                pos = app.doc_reader_scroll / max_scroll
                indicator_y = box_y + 3 + int(pos * (visible_h - 1))
                app.stdscr.addstr(indicator_y, box_x + box_w - 1, "█", border_attr)

        except curses.error:
            pass

    @staticmethod
    def _wrap_edit_lines(lines, content_w):
        """Build a visual-line map by wrapping logical lines to *content_w*.

        Returns a list of tuples ``(logical_idx, start_col, text)`` where each
        entry represents one screen row.
        """
        vlines: list[tuple[int, int, str]] = []
        w = max(content_w, 1)
        for li, raw in enumerate(lines):
            if len(raw) == 0:
                vlines.append((li, 0, ""))
            else:
                for off in range(0, len(raw), w):
                    vlines.append((li, off, raw[off:off + w]))
        return vlines

    def _draw_doc_editor(self, app, box_x, box_y, box_w, box_h, inner_w, content_w,
                         visible_h, border_attr, title_attr, body_attr, heading_attr, dim_attr):
        """Draw editable document editor with cursor and word wrap."""
        edit_border = curses.color_pair(CP_RECORDING) | curses.A_BOLD
        lines = app.doc_edit_lines
        total_lines = len(lines)

        # Build wrapped visual lines
        vlines = self._wrap_edit_lines(lines, content_w)
        total_vlines = len(vlines)

        # Find which visual row the cursor sits on
        cursor_vrow = 0
        for vi, (li, start_col, _text) in enumerate(vlines):
            if li == app.doc_edit_cursor_row:
                if start_col + content_w > app.doc_edit_cursor_col >= start_col:
                    cursor_vrow = vi
                    break
                # If cursor is exactly at end-of-chunk boundary, stay on this row
                if app.doc_edit_cursor_col == start_col:
                    cursor_vrow = vi
                    break
            elif li > app.doc_edit_cursor_row:
                # Past the cursor line — use the last visual row of cursor line
                cursor_vrow = max(vi - 1, 0)
                break
        else:
            # Cursor is on/past the last logical line
            cursor_vrow = max(total_vlines - 1, 0)

        # Auto-scroll to keep cursor visible (using visual rows)
        if cursor_vrow < app.doc_edit_scroll:
            app.doc_edit_scroll = cursor_vrow
        elif cursor_vrow >= app.doc_edit_scroll + visible_h:
            app.doc_edit_scroll = cursor_vrow - visible_h + 1
        app.doc_edit_scroll = max(0, min(app.doc_edit_scroll, max(0, total_vlines - visible_h)))

        try:
            # Top border (red in edit mode)
            top = "╔" + "═" * inner_w + "╗"
            app.stdscr.addnstr(box_y, box_x, top, box_w, edit_border)

            # Title bar — show EDIT indicator
            title = f" EDITING: {app.doc_reader_title} "
            if len(title) > inner_w - 4:
                title = title[:inner_w - 7] + "… "
            title_line = "║" + title.center(inner_w) + "║"
            app.stdscr.addnstr(box_y + 1, box_x, title_line, box_w, edit_border)

            # Separator
            sep = "╠" + "═" * inner_w + "╣"
            app.stdscr.addnstr(box_y + 2, box_x, sep, box_w, edit_border)

            # Content lines with cursor
            for i in range(visible_h):
                row_y = box_y + 3 + i
                vi = app.doc_edit_scroll + i

                # Left border
                app.stdscr.addstr(row_y, box_x, "║", edit_border)

                if vi < total_vlines:
                    li, start_col, segment = vlines[vi]
                    raw_full = lines[li]
                    # Determine style based on logical line content
                    stripped = raw_full.rstrip()
                    if stripped.startswith("#"):
                        attr = heading_attr
                    elif stripped.startswith("---") or stripped.startswith("```"):
                        attr = dim_attr
                    else:
                        attr = body_attr

                    # Pad for display (1 char left pad)
                    display = segment[:content_w]
                    padded = " " + display + " " * max(0, content_w - len(display)) + " "
                    app.stdscr.addnstr(row_y, box_x + 1, padded[:inner_w], inner_w, attr)

                    # Draw cursor if on this visual line
                    if vi == cursor_vrow:
                        vis_col = app.doc_edit_cursor_col - start_col
                        cursor_screen_col = box_x + 2 + vis_col
                        if 0 <= vis_col and cursor_screen_col < box_x + box_w - 1:
                            char_under = segment[vis_col] if vis_col < len(segment) else " "
                            app.stdscr.addstr(row_y, cursor_screen_col, char_under,
                                              curses.A_REVERSE | curses.A_BOLD)
                else:
                    blank = " " * inner_w
                    app.stdscr.addnstr(row_y, box_x + 1, blank, inner_w, body_attr)

                # Right border
                app.stdscr.addstr(row_y, box_x + box_w - 1, "║", edit_border)

            # Bottom border
            line_info = f" Ln {app.doc_edit_cursor_row + 1}/{total_lines} Col {app.doc_edit_cursor_col + 1} "
            help_text = " [ESC]Save/Discard "
            border_bot = "╚" + "═" * inner_w + "╝"
            app.stdscr.addnstr(box_y + box_h - 1, box_x, border_bot, box_w, edit_border)
            app.stdscr.addstr(box_y + box_h - 1, box_x + 2, line_info, edit_border)
            hx = box_x + box_w - len(help_text) - 2
            if hx > box_x + len(line_info) + 4:
                app.stdscr.addstr(box_y + box_h - 1, hx, help_text, edit_border)

            # Scroll indicator
            max_scroll = max(0, total_vlines - visible_h)
            if max_scroll > 0 and visible_h > 2:
                pos = app.doc_edit_scroll / max_scroll
                indicator_y = box_y + 3 + int(pos * (visible_h - 1))
                app.stdscr.addstr(indicator_y, box_x + box_w - 1, "█", edit_border)

            # Save confirmation dialog
            if app.doc_edit_save_confirm:
                self._draw_save_confirm(app, box_x, box_y, box_w, box_h)

        except curses.error:
            pass

    def _draw_save_confirm(self, app, box_x, box_y, box_w, box_h):
        """Draw the save/discard confirmation dialog centered on the editor."""
        dialog_w = 42
        dialog_h = 5
        dx = box_x + (box_w - dialog_w) // 2
        dy = box_y + (box_h - dialog_h) // 2

        border_attr = curses.color_pair(CP_HEADER) | curses.A_BOLD
        text_attr = curses.color_pair(CP_PROMPT) | curses.A_BOLD
        key_attr = curses.color_pair(CP_AGENT) | curses.A_BOLD

        try:
            # Dialog box
            app.stdscr.addnstr(dy, dx, "╔" + "═" * (dialog_w - 2) + "╗", dialog_w, border_attr)
            for i in range(1, dialog_h - 1):
                app.stdscr.addstr(dy + i, dx, "║", border_attr)
                app.stdscr.addnstr(dy + i, dx + 1, " " * (dialog_w - 2), dialog_w - 2, text_attr)
                app.stdscr.addstr(dy + i, dx + dialog_w - 1, "║", border_attr)
            app.stdscr.addnstr(dy + dialog_h - 1, dx, "╚" + "═" * (dialog_w - 2) + "╝", dialog_w, border_attr)

            # Dialog content
            msg = "Save changes?"
            app.stdscr.addstr(dy + 1, dx + (dialog_w - len(msg)) // 2, msg, text_attr)
            options = "[Y]es  [N]o  [ESC]Cancel"
            app.stdscr.addstr(dy + 3, dx + (dialog_w - len(options)) // 2, options, key_attr)
        except curses.error:
            pass
