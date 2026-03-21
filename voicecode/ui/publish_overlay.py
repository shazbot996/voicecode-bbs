"""Publish overlay — document type and destination folder selection."""

import curses

from voicecode.ui.colors import (
    CP_PUBLISH, CP_PUBLISH_TITLE, CP_ACCENT, CP_VOICE, CP_AGENT,
)


# Document types available for publishing
DOC_TYPES = [
    "BRIEF",
    "ARCH",
    "SPEC",
    "PLAN",
    "SCHEMA",
    "ADR",
    "CONVENTIONS",
    "CONSTRAINTS",
    "GLOSSARY",
    "RUNBOOK",
    "WORKFLOW",
    "CHANGELOG",
    "README",
]

# Destination folders (no changelog/ — those should be automatic)
DEST_FOLDERS = [
    "context/",
    "decisions/",
    "plans/",
    "specs/",
    "runbooks/",
]

# Reference tree shown in the tutorial section
REFERENCE_TREE = [
    "docs/",
    "  context/          — what Claude reads every session (or on demand)",
    "    BRIEF.md",
    "    ARCH.md",
    "    CONVENTIONS.md",
    "    CONSTRAINTS.md",
    "    GLOSSARY.md",
    "    SCHEMA.md",
    "  decisions/        — ADRs, numbered sequentially",
    "    0001-use-gcp-tree-architecture.md",
    "    0002-typescript-react-frontend.md",
    "  plans/            — active and archived plans",
    "    active/",
    "    archive/",
    "  specs/            — feature specs",
    "    active/",
    "    archive/",
    "  runbooks/         — operational docs",
    "  changelog/        — or just CHANGELOG.md at root",
]


class PublishOverlay:
    """Near-full-screen modal for the Publish workflow.

    Two-step selection:
      Step 0 — pick a document type
      Step 1 — pick a destination folder
    """

    def __init__(self, app):
        self.app = app

    # ── state helpers ────────────────────────────────────────────

    def open(self):
        app = self.app
        app.show_publish_overlay = True
        app.publish_step = 0
        app.publish_cursor = 0
        app.publish_selected_type = None
        app.publish_selected_folder = None

    def close(self):
        self.app.show_publish_overlay = False

    def go_back(self):
        """Go back one step, or close if at step 0."""
        app = self.app
        if app.publish_step == 0:
            self.close()
        else:
            app.publish_step = 0
            app.publish_cursor = DOC_TYPES.index(app.publish_selected_type) if app.publish_selected_type in DOC_TYPES else 0

    def select(self):
        """Confirm the current selection and advance."""
        app = self.app
        if app.publish_step == 0:
            app.publish_selected_type = DOC_TYPES[app.publish_cursor]
            app.publish_step = 1
            app.publish_cursor = 0
        else:
            app.publish_selected_folder = DEST_FOLDERS[app.publish_cursor]
            # Both selections made — for now just report and close
            app.set_status(
                f"Publish: {app.publish_selected_type} → docs/{app.publish_selected_folder}  (generation not yet implemented)")
            self.close()

    def cursor_move(self, direction: int):
        app = self.app
        items = DOC_TYPES if app.publish_step == 0 else DEST_FOLDERS
        app.publish_cursor = max(0, min(len(items) - 1, app.publish_cursor + direction))

    # ── drawing ──────────────────────────────────────────────────

    def draw(self):
        app = self.app
        h, w = app.stdscr.getmaxyx()

        # Modal dimensions — near full screen with margin
        margin_x = 2
        margin_top = 3
        margin_bot = 2
        box_x = margin_x
        box_y = margin_top
        box_w = w - margin_x * 2
        box_h = h - margin_top - margin_bot

        if box_w < 40 or box_h < 16:
            return

        purple = curses.color_pair(CP_PUBLISH) | curses.A_BOLD
        title_attr = curses.color_pair(CP_PUBLISH_TITLE) | curses.A_BOLD
        dim = curses.color_pair(CP_ACCENT)
        bright = curses.color_pair(CP_AGENT) | curses.A_BOLD
        sel_attr = curses.A_REVERSE | curses.A_BOLD | curses.color_pair(CP_PUBLISH)

        # Clear background
        blank = " " * box_w
        for y in range(box_y, box_y + box_h):
            try:
                app.stdscr.addnstr(y, box_x, blank, box_w)
            except curses.error:
                pass

        # Top border + title
        title = " PUBLISH DOCUMENT "
        border_top = "╔" + "═" * (box_w - 2) + "╗"
        try:
            app.stdscr.addnstr(box_y, box_x, border_top, box_w, purple)
            tx = box_x + (box_w - len(title)) // 2
            app.stdscr.addstr(box_y, tx, title, title_attr)
        except curses.error:
            pass

        # Side borders
        for y in range(box_y + 1, box_y + box_h - 1):
            try:
                app.stdscr.addstr(y, box_x, "║", purple)
                app.stdscr.addstr(y, box_x + box_w - 1, "║", purple)
            except curses.error:
                pass

        # Bottom border
        step_label = " Step 1: Document Type " if app.publish_step == 0 else " Step 2: Destination Folder "
        help_text = " [↑↓]Select [Enter]Confirm [ESC]Back "
        border_bot = "╚" + "═" * (box_w - 2) + "╝"
        try:
            app.stdscr.addnstr(box_y + box_h - 1, box_x, border_bot, box_w, purple)
            # Step label on left
            app.stdscr.addstr(box_y + box_h - 1, box_x + 2, step_label, title_attr)
            # Help on right
            hx = box_x + box_w - len(help_text) - 2
            if hx > box_x + len(step_label) + 4:
                app.stdscr.addstr(box_y + box_h - 1, hx, help_text, purple)
        except curses.error:
            pass

        # Content area
        inner_x = box_x + 2
        inner_w = box_w - 4
        cy = box_y + 2  # current y for content

        # ── Left column: reference tree  |  Right column: selection list ──
        # Use a two-column layout: reference on left, selection on right
        divider_x = box_x + box_w // 2
        left_w = divider_x - inner_x - 1
        right_x = divider_x + 2
        right_w = box_x + box_w - 2 - right_x

        # Draw vertical divider
        for y in range(box_y + 1, box_y + box_h - 1):
            try:
                app.stdscr.addstr(y, divider_x, "│", purple)
            except curses.error:
                pass

        # ── LEFT: Reference tree ──
        ref_y = cy
        ref_title = "Docs Folder Structure"
        try:
            app.stdscr.addnstr(ref_y, inner_x, ref_title, left_w, purple)
        except curses.error:
            pass
        ref_y += 1
        try:
            app.stdscr.addnstr(ref_y, inner_x, "─" * min(len(ref_title), left_w), left_w, purple)
        except curses.error:
            pass
        ref_y += 1

        for line in REFERENCE_TREE:
            if ref_y >= box_y + box_h - 2:
                break
            try:
                app.stdscr.addnstr(ref_y, inner_x, line[:left_w], left_w, dim)
            except curses.error:
                pass
            ref_y += 1

        # Supported types label below tree
        ref_y += 1
        if ref_y < box_y + box_h - 3:
            types_label = "Supported Types"
            try:
                app.stdscr.addnstr(ref_y, inner_x, types_label, left_w, purple)
            except curses.error:
                pass
            ref_y += 1
            try:
                app.stdscr.addnstr(ref_y, inner_x, "─" * min(len(types_label), left_w), left_w, purple)
            except curses.error:
                pass
            ref_y += 1
            # List types in compact rows
            type_line = ", ".join(DOC_TYPES)
            # Wrap to fit
            while type_line and ref_y < box_y + box_h - 2:
                chunk = type_line[:left_w]
                # Try to break at comma
                if len(type_line) > left_w:
                    last_comma = chunk.rfind(",")
                    if last_comma > 0:
                        chunk = type_line[:last_comma + 1]
                try:
                    app.stdscr.addnstr(ref_y, inner_x, chunk, left_w, dim)
                except curses.error:
                    pass
                type_line = type_line[len(chunk):].lstrip()
                ref_y += 1

        # ── RIGHT: Selection list ──
        sel_y = cy
        if app.publish_step == 0:
            sel_title = "Select Document Type"
            items = DOC_TYPES
        else:
            sel_title = f"Destination for {app.publish_selected_type}"
            items = DEST_FOLDERS

        try:
            app.stdscr.addnstr(sel_y, right_x, sel_title, right_w, purple)
        except curses.error:
            pass
        sel_y += 1
        try:
            app.stdscr.addnstr(sel_y, right_x, "─" * min(len(sel_title), right_w), right_w, purple)
        except curses.error:
            pass
        sel_y += 1

        # Calculate scroll so selected item is visible
        visible_rows = box_y + box_h - 2 - sel_y
        scroll = 0
        if app.publish_cursor >= visible_rows:
            scroll = app.publish_cursor - visible_rows + 1

        for i, item in enumerate(items):
            if i < scroll:
                continue
            if sel_y >= box_y + box_h - 2:
                break
            label = f"  {item}  "
            if i == app.publish_cursor:
                attr = sel_attr
                label = f"▸ {item}"
            else:
                attr = bright if app.publish_step == 0 else curses.color_pair(CP_VOICE) | curses.A_BOLD
                label = f"  {item}"
            try:
                app.stdscr.addnstr(sel_y, right_x, label[:right_w], right_w, attr)
            except curses.error:
                pass
            sel_y += 1

        # If step 1 (folder), show a note about the selected type
        if app.publish_step == 1:
            sel_y += 1
            if sel_y < box_y + box_h - 2:
                note = f"Type: {app.publish_selected_type}"
                try:
                    app.stdscr.addnstr(sel_y, right_x, note, right_w, dim)
                except curses.error:
                    pass
