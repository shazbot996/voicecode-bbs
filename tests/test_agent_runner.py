"""Tests for agent runner helper and sanitization logic."""

import pytest

from voicecode.agent.runner import sanitize_text


def test_sanitize_text_none_and_empty():
    assert sanitize_text(None) is None
    assert sanitize_text("") == ""


def test_sanitize_text_strips_ansi_escapes():
    # Standard colors and styles
    text_with_ansi = "Hello \x1b[31;1mWorld\x1b[0m!"
    assert sanitize_text(text_with_ansi) == "Hello World!"


def test_sanitize_text_strips_osc_sequences():
    # Terminal title sets, BEL- and ST-terminated
    assert sanitize_text("\x1b]0;my title\x07done") == "done"
    assert sanitize_text("\x1b]0;my title\x1b\\done") == "done"


def test_sanitize_text_strips_carriage_returns():
    # Progress bars and sequential updates
    text_with_cr = "Processing... \rDone!\r"
    assert sanitize_text(text_with_cr) == "Processing... Done!"


def test_sanitize_text_strips_control_characters():
    # Control codes like bell, backspace, etc.
    text_with_ctrl = "A\x07B\x08C\x1fD"
    assert sanitize_text(text_with_ctrl) == "ABCD"


def test_sanitize_text_expands_tabs_to_spaces():
    # curses advances a raw tab to the next 8-column stop, overshooting the
    # pane border; the pane wraps by character count, so tabs must become
    # real characters.
    assert "\t" not in sanitize_text("a\tb")
    assert sanitize_text("a\tb") == "a    b"


def test_sanitize_text_preserves_newlines():
    assert sanitize_text("Line 1\nLine 2") == "Line 1\nLine 2"


def test_sanitize_text_preserves_printable_characters():
    text = "Hello, World! @#$%^&*()_+ 12345"
    assert sanitize_text(text) == text


def test_sanitize_text_preserves_box_drawing():
    # The transmission banners the runner emits must survive sanitization.
    text = "═══ INCOMING TRANSMISSION ═══"
    assert sanitize_text(text) == text


def test_sanitize_text_handles_pty_shell_output():
    """`agy` runs shell commands on a PTY: CRLF line ends, tab indents.

    This is the exact shape of run_command tool output that painted over
    the left-hand panes.
    """
    raw = ('On branch master\r\nChanges not staged for commit:\r\n'
           '\tmodified:   a.txt\r\n')
    clean = sanitize_text(raw)
    assert "\r" not in clean
    assert "\t" not in clean
    assert clean == ("On branch master\nChanges not staged for commit:\n"
                     "    modified:   a.txt\n")


def test_sanitize_text_leaves_no_control_chars_at_all():
    raw = "\x1b[2J\x1b[H\rcol0\ttab\x00nul\x0bvt\n"
    clean = sanitize_text(raw)
    assert all(ch == "\n" or ch.isprintable() for ch in clean)
