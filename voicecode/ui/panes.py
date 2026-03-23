"""Scrollable text pane widget for curses UI."""

import curses
import textwrap


class TextPane:
    """A scrollable text region within a curses window."""

    MAX_LINES = 2000  # trim oldest lines when exceeded

    def __init__(self, title: str, color_pair: int):
        self.title = title
        self.lines: list[str] = []
        self.line_colors: dict[int, int] = {}  # line index -> color pair override
        self.scroll_offset = 0
        self.color_pair = color_pair
        self.welcome_art: list[str] = []  # shown centered when lines is empty
        self.auto_scroll = True  # auto-follow new content (disabled by manual scroll)

    def set_text(self, text: str, width: int):
        self.lines = []
        for paragraph in text.split("\n"):
            if not paragraph.strip():
                self.lines.append("")
            else:
                wrapped = textwrap.wrap(paragraph, width=max(1, width - 2))
                self.lines.extend(wrapped if wrapped else [""])

    def add_line(self, text: str, width: int):
        wrapped = textwrap.wrap(text, width=max(1, width - 2))
        self.lines.extend(wrapped if wrapped else [text])
        self._trim_lines()
        if self.auto_scroll:
            self.scroll_to_bottom(self._last_height if hasattr(self, '_last_height') else 10)

    def _trim_lines(self):
        """Trim oldest lines when buffer exceeds MAX_LINES."""
        overflow = len(self.lines) - self.MAX_LINES
        if overflow > 0:
            self.lines = self.lines[overflow:]
            self.scroll_offset = max(0, self.scroll_offset - overflow)
            # Shift line_colors indices
            if self.line_colors:
                self.line_colors = {
                    k - overflow: v for k, v in self.line_colors.items()
                    if k >= overflow
                }

    def add_char_to_last_line(self, ch: str, width: int):
        """Append a character, wrapping if needed. For typewriter effect."""
        if not self.lines:
            self.lines.append("")
        if ch == "\n":
            self.lines.append("")
        else:
            last = self.lines[-1]
            if len(last) >= max(1, width - 3):
                self.lines.append(ch)
            else:
                self.lines[-1] = last + ch
        self._trim_lines()
        if self.auto_scroll:
            self.scroll_to_bottom(self._last_height if hasattr(self, '_last_height') else 10)

    @property
    def is_scrollable(self) -> bool:
        """True if content exceeds visible area."""
        vh = self._last_height if hasattr(self, '_last_height') else 10
        return len(self.lines) > vh

    def scroll_to_bottom(self, visible_height: int):
        max_offset = max(0, len(self.lines) - visible_height)
        self.scroll_offset = max_offset
        self.auto_scroll = True

    def scroll_up(self, amount=1):
        self.scroll_offset = max(0, self.scroll_offset - amount)
        self.auto_scroll = False

    def scroll_down(self, visible_height: int, amount=1):
        max_offset = max(0, len(self.lines) - visible_height)
        self.scroll_offset = min(max_offset, self.scroll_offset + amount)
        # Re-enable auto-scroll when user reaches the bottom
        if self.scroll_offset >= max_offset:
            self.auto_scroll = True

    def draw(self, win, y: int, x: int, height: int, width: int):
        if height < 3 or width < 5:
            return
        self._last_height = height - 2

        border_attr = curses.color_pair(self.color_pair) | curses.A_BOLD
        title_str = f" {self.title} "
        # Truncate title if too long
        max_title = width - 6
        if len(title_str) > max_title:
            title_str = title_str[:max_title - 1] + "…"

        top = "╔══" + title_str + "═" * max(0, width - 3 - len(title_str) - 1) + "╗"

        try:
            win.addnstr(y, x, top, width, border_attr)
        except curses.error:
            pass

        visible_height = height - 2
        content_width = width - 2  # inside the ║ borders

        # Use welcome art left-justified in pane when no content
        if not self.lines and self.welcome_art:
            art_lines = self.welcome_art
            for i in range(visible_height):
                try:
                    win.addstr(y + 1 + i, x, "║", border_attr)
                    if i < len(art_lines):
                        art_line = art_lines[i]
                        art_line = art_line[:content_width - 1]
                        padding = " " * max(0, content_width - 1 - len(art_line))
                        win.addstr(y + 1 + i, x + 1, " " + art_line + padding,
                                   curses.color_pair(self.color_pair) | curses.A_BOLD)
                    else:
                        win.addstr(y + 1 + i, x + 1, " " * max(0, content_width),
                                   curses.color_pair(self.color_pair) | curses.A_BOLD)
                    win.addnstr(y + 1 + i, x + width - 1, "║", 1, border_attr)
                except curses.error:
                    pass
        else:
            visible_lines = self.lines[self.scroll_offset:self.scroll_offset + visible_height]
            for i in range(visible_height):
                try:
                    win.addstr(y + 1 + i, x, "║", border_attr)
                    if i < len(visible_lines):
                        line = visible_lines[i][:content_width - 1]
                        padding = " " * max(0, content_width - 1 - len(line))
                        line_idx = self.scroll_offset + i
                        line_cp = self.line_colors.get(line_idx, self.color_pair)
                        win.addstr(y + 1 + i, x + 1, " " + line + padding,
                                   curses.color_pair(line_cp) | curses.A_BOLD)

                    else:
                        win.addstr(y + 1 + i, x + 1, " " * max(0, content_width),
                                   curses.color_pair(self.color_pair))
                    win.addnstr(y + 1 + i, x + width - 1, "║", 1, border_attr)
                except curses.error:
                    pass

        bottom = "╚" + "═" * max(0, width - 2) + "╝"
        try:
            win.addnstr(y + height - 1, x, bottom, width, border_attr)
        except curses.error:
            pass

        # Scroll indicator
        if len(self.lines) > visible_height and visible_height > 0:
            total = len(self.lines)
            pos = self.scroll_offset / max(1, total - visible_height)
            indicator_y = y + 1 + int(pos * max(0, visible_height - 1))
            try:
                win.addstr(indicator_y, x + width - 1, "█", border_attr)
            except curses.error:
                pass
