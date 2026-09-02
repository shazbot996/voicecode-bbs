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


def test_speak_summary_saves_and_speaks():
    from unittest.mock import MagicMock, patch
    from voicecode.agent.runner import RunnerHelper

    mock_app = MagicMock()
    mock_app.cast_enabled = False
    runner = RunnerHelper(mock_app)

    with patch("voicecode.agent.runner.speak_text") as mock_speak, \
         patch("voicecode.agent.runner.stop_speaking") as mock_stop:
        runner.speak_summary("The test summary", is_error=False)

        assert mock_app.last_tts_summary == "The test summary"
        mock_app.execution.save_response_to_history.assert_called_once_with("The test summary", is_error=False)
        mock_stop.assert_called_once()
        mock_speak.assert_called_once()


def test_emit_typewriter_sets_tts_summary_emitted_and_color():
    import queue
    from unittest.mock import MagicMock
    from voicecode.agent.runner import RunnerHelper
    from voicecode.ui.colors import CP_TTS

    mock_app = MagicMock()
    mock_app.ui_queue = queue.Queue()
    mock_app._tts_detect_buf = ""
    mock_app._tts_in_summary = False
    mock_app._tts_summary_emitted = False

    runner = RunnerHelper(mock_app)
    runner.emit_typewriter("Hello [TTS_SUMMARY]this is summary[/TTS_SUMMARY] goodbye")

    assert mock_app._tts_summary_emitted is True

    items = []
    while not mock_app.ui_queue.empty():
        items.append(mock_app.ui_queue.get())

    # Check color switched to CP_TTS and back to None
    assert ("typewriter_color", CP_TTS) in items
    assert ("typewriter_color", None) in items


def test_emit_readback_summary_emits_white_text_when_not_already_streamed():
    import queue
    from unittest.mock import MagicMock
    from voicecode.agent.runner import RunnerHelper
    from voicecode.ui.colors import CP_TTS

    mock_app = MagicMock()
    mock_app.ui_queue = queue.Queue()
    mock_app._tts_detect_buf = ""
    mock_app._tts_in_summary = False
    mock_app._tts_summary_emitted = False

    runner = RunnerHelper(mock_app)
    runner.emit_readback_summary("Final readback summary text.")

    assert mock_app._tts_summary_emitted is True

    items = []
    while not mock_app.ui_queue.empty():
        items.append(mock_app.ui_queue.get())

    # Should set color to CP_TTS, stream characters, and reset to None
    assert ("typewriter_color", CP_TTS) in items
    chars = "".join([val for kind, val in items if kind == "typewriter_char"])
    assert "Final readback summary text." in chars
    assert ("typewriter_color", None) in items


def test_emit_readback_summary_skips_when_already_streamed():
    import queue
    from unittest.mock import MagicMock
    from voicecode.agent.runner import RunnerHelper

    mock_app = MagicMock()
    mock_app.ui_queue = queue.Queue()
    mock_app._tts_detect_buf = ""
    mock_app._tts_in_summary = False
    mock_app._tts_summary_emitted = True

    runner = RunnerHelper(mock_app)
    runner.emit_readback_summary("Already emitted summary.")

    assert mock_app.ui_queue.empty()

