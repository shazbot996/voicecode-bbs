"""ZMODEM animation and typewriter effect."""

import curses
import random
import time
import collections

from voicecode.constants import ZMODEM_FRAMES
from voicecode.ui.colors import *


class AnimationHelper:
    def __init__(self, app):
        self.app = app

    def draw_agent_xfer(self, y, x, height, width):
        """Draw the ZMODEM-style transfer animation in the right pane."""
        app = self.app
        border_attr = curses.color_pair(CP_XFER) | curses.A_BOLD
        content_attr = curses.color_pair(CP_XFER)
        green_attr = curses.color_pair(CP_AGENT) | curses.A_BOLD

        # Draw border
        title = " FILE TRANSFER "
        top = "╔══" + title + "═" * max(0, width - 3 - len(title) - 1) + "╗"
        try:
            app.stdscr.addnstr(y, x, top, width, border_attr)
        except curses.error:
            pass

        for i in range(1, height - 1):
            try:
                app.stdscr.addstr(y + i, x, "║", border_attr)
                app.stdscr.addstr(y + i, x + 1, " " * max(0, width - 2), content_attr)
                app.stdscr.addnstr(y + i, x + width - 1, "║", 1, border_attr)
            except curses.error:
                pass

        bottom = "╚" + "═" * max(0, width - 2) + "╝"
        try:
            app.stdscr.addnstr(y + height - 1, x, bottom, width, border_attr)
        except curses.error:
            pass

        # Content
        inner_w = width - 4
        cx = x + 2
        elapsed = time.time() - app.xfer_start_time
        app.xfer_progress = min(0.99, elapsed / 3.0)  # ~3 sec animation

        lines_content = [
            ("Protocol", "ZMODEM-VOICE/1.0"),
            ("Filename", "prompt_upload.md"),
            ("   Bytes", f"{app.xfer_bytes:,}"),
            ("     BPS", f"{random.randint(28800, 115200):,}"),
            ("  Errors", "0"),
            ("  Status", ZMODEM_FRAMES[app.xfer_frame % len(ZMODEM_FRAMES)]),
        ]

        # Update animation frame
        app.xfer_frame = int(elapsed * 4)

        row = y + 2
        # ASCII art modem
        modem_art = [
            "   ┌──────────────────┐",
            "   │ ≈≈≈ SENDING ≈≈≈  │",
            "   │ ◄══════════════► │",
            "   └──────────────────┘",
        ]
        for line in modem_art:
            try:
                app.stdscr.addnstr(row, cx, line[:inner_w], inner_w, green_attr)
            except curses.error:
                pass
            row += 1

        row += 1
        for label, val in lines_content:
            try:
                text = f"  {label}: {val}"
                app.stdscr.addnstr(row, cx, text[:inner_w], inner_w, content_attr)
            except curses.error:
                pass
            row += 1

        # Progress bar
        row += 1
        bar_w = min(inner_w - 12, 30)
        filled = int(app.xfer_progress * bar_w)
        bar = "█" * filled + "░" * (bar_w - filled)
        pct = f" {int(app.xfer_progress * 100):3d}%"
        try:
            app.stdscr.addnstr(row, cx, f"  [{bar}]{pct}", inner_w, green_attr)
        except curses.error:
            pass

        # Spinning chars
        row += 2
        spinners = "|/-\\"
        spin_ch = spinners[int(elapsed * 8) % len(spinners)]
        try:
            app.stdscr.addnstr(row, cx, f"  {spin_ch} Transmitting...", inner_w, content_attr)
        except curses.error:
            pass

    def process_typewriter(self):
        """Process queued characters for the typewriter effect.

        Uses a time-based budget so characters emit at a steady rate
        (~_typewriter_chars_per_sec) regardless of how bursty the input
        stream is.  This prevents the "long pause then dump" glitch.
        """
        app = self.app
        if not app.typewriter_queue:
            app._typewriter_last_ts = 0.0
            return

        now = time.monotonic()
        if app._typewriter_last_ts == 0.0:
            # First call with data — seed the timestamp, grant a small
            # initial budget so the very first chars appear immediately.
            app._typewriter_last_ts = now
            app._typewriter_budget = 2.0
        else:
            elapsed = now - app._typewriter_last_ts
            app._typewriter_last_ts = now
            app._typewriter_budget += elapsed * app._typewriter_chars_per_sec
            # Cap budget so a long idle period doesn't cause a huge dump
            if app._typewriter_budget > 120:
                app._typewriter_budget = 120

        right_width = app.stdscr.getmaxyx()[1] - app.stdscr.getmaxyx()[1] // 2
        chars_this_frame = 0

        while app.typewriter_queue and app._typewriter_budget >= 1.0:
            ch = app.typewriter_queue.popleft()

            # Handle color-change sentinel tuples (free — don't cost budget)
            if isinstance(ch, tuple) and ch[0] == "color":
                app._typewriter_line_color = ch[1]  # None to reset
                # Tag current last line with the new color
                if app._typewriter_line_color is not None and app.agent_pane.lines:
                    idx = len(app.agent_pane.lines) - 1
                    app.agent_pane.line_colors[idx] = app._typewriter_line_color
                continue

            prev_count = len(app.agent_pane.lines)
            app.agent_pane.add_char_to_last_line(ch, right_width)
            # Tag any newly created lines with the current override color
            if app._typewriter_line_color is not None:
                for idx in range(prev_count, len(app.agent_pane.lines)):
                    app.agent_pane.line_colors[idx] = app._typewriter_line_color
            app._typewriter_budget -= 1.0
            chars_this_frame += 1
