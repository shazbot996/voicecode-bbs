"""Tests for TextPane state logic (no curses dependency except draw)."""

import pytest
from voicecode.ui.panes import TextPane


@pytest.fixture
def pane():
    return TextPane("Test", color_pair=1)


# -- set_text --

class TestSetText:
    def test_basic_text(self, pane):
        pane.set_text("Hello world", width=80)
        assert pane.lines == ["Hello world"]

    def test_wraps_long_lines(self, pane):
        pane.set_text("a " * 50, width=20)
        assert all(len(line) <= 18 for line in pane.lines)

    def test_preserves_blank_lines(self, pane):
        pane.set_text("Line one\n\nLine three", width=80)
        assert pane.lines[1] == ""

    def test_multiple_paragraphs(self, pane):
        pane.set_text("First\nSecond\nThird", width=80)
        assert len(pane.lines) == 3

    def test_clears_previous_content(self, pane):
        pane.set_text("old content", width=80)
        pane.set_text("new content", width=80)
        assert pane.lines == ["new content"]


# -- add_char_to_last_line --

class TestAddCharToLastLine:
    def test_appends_character(self, pane):
        pane.add_char_to_last_line("H", width=80)
        pane.add_char_to_last_line("i", width=80)
        assert pane.lines == ["Hi"]

    def test_newline_starts_new_line(self, pane):
        pane.add_char_to_last_line("A", width=80)
        pane.add_char_to_last_line("\n", width=80)
        pane.add_char_to_last_line("B", width=80)
        assert pane.lines == ["A", "B"]

    def test_wraps_at_width(self, pane):
        # width=5 means content width is max(1, 5-3) = 2
        for ch in "ABCDE":
            pane.add_char_to_last_line(ch, width=5)
        assert len(pane.lines) > 1

    def test_empty_pane_creates_first_line(self, pane):
        assert pane.lines == []
        pane.add_char_to_last_line("X", width=80)
        assert pane.lines == ["X"]

    def test_consecutive_newlines(self, pane):
        pane.add_char_to_last_line("A", width=80)
        pane.add_char_to_last_line("\n", width=80)
        pane.add_char_to_last_line("\n", width=80)
        pane.add_char_to_last_line("B", width=80)
        assert pane.lines == ["A", "", "B"]


# -- add_line --

class TestAddLine:
    def test_adds_line(self, pane):
        pane.add_line("Hello", width=80)
        assert "Hello" in pane.lines

    def test_wraps_long_line(self, pane):
        pane.add_line("word " * 30, width=40)
        assert len(pane.lines) > 1


# -- _trim_lines --

class TestTrimLines:
    def test_trims_at_max(self, pane):
        pane.lines = [f"line {i}" for i in range(TextPane.MAX_LINES + 100)]
        pane._trim_lines()
        assert len(pane.lines) == TextPane.MAX_LINES

    def test_no_trim_under_max(self, pane):
        pane.lines = ["a"] * 10
        pane._trim_lines()
        assert len(pane.lines) == 10

    def test_adjusts_scroll_offset(self, pane):
        pane.lines = [f"line {i}" for i in range(TextPane.MAX_LINES + 50)]
        pane.scroll_offset = 100
        pane._trim_lines()
        assert pane.scroll_offset == 50

    def test_scroll_offset_floors_at_zero(self, pane):
        pane.lines = [f"line {i}" for i in range(TextPane.MAX_LINES + 10)]
        pane.scroll_offset = 5
        pane._trim_lines()
        assert pane.scroll_offset == 0

    def test_shifts_line_colors(self, pane):
        overflow = 10
        pane.lines = ["x"] * (TextPane.MAX_LINES + overflow)
        pane.line_colors = {5: 2, TextPane.MAX_LINES + 5: 3}
        pane._trim_lines()
        # line 5 was trimmed away (index < overflow)
        assert all(k >= 0 for k in pane.line_colors)
        # The high index should have been shifted down
        assert (TextPane.MAX_LINES + 5 - overflow) in pane.line_colors


# -- scrolling --

class TestScrolling:
    def test_scroll_up_disables_auto(self, pane):
        pane.auto_scroll = True
        pane.scroll_offset = 5
        pane.scroll_up()
        assert pane.scroll_offset == 4
        assert pane.auto_scroll is False

    def test_scroll_up_floors_at_zero(self, pane):
        pane.scroll_offset = 0
        pane.scroll_up()
        assert pane.scroll_offset == 0

    def test_scroll_down_reenables_auto_at_bottom(self, pane):
        pane.lines = ["x"] * 20
        pane.auto_scroll = False
        pane.scroll_offset = 9
        pane.scroll_down(visible_height=10, amount=1)
        assert pane.auto_scroll is True

    def test_scroll_down_caps_at_max(self, pane):
        pane.lines = ["x"] * 20
        pane.scroll_offset = 10
        pane.scroll_down(visible_height=10, amount=100)
        assert pane.scroll_offset == 10

    def test_scroll_to_bottom(self, pane):
        pane.lines = ["x"] * 30
        pane.scroll_to_bottom(visible_height=10)
        assert pane.scroll_offset == 20
        assert pane.auto_scroll is True

    def test_is_scrollable_false(self, pane):
        pane.lines = ["x"] * 5
        pane._last_height = 10
        assert pane.is_scrollable is False

    def test_is_scrollable_true(self, pane):
        pane.lines = ["x"] * 15
        pane._last_height = 10
        assert pane.is_scrollable is True
