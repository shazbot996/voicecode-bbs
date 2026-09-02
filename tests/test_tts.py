from voicecode.tts.engine import (extract_tts_summary, clean_spoken_text,
                               extract_fallback_summary, format_error_readout)


class TestExtractTtsSummary:
    def test_extracts_summary(self):
        text = "Some response.\n\n[TTS_SUMMARY]\nThis is the summary.\n[/TTS_SUMMARY]"
        assert extract_tts_summary(text) == "This is the summary."

    def test_strips_whitespace(self):
        text = "[TTS_SUMMARY]   padded text   [/TTS_SUMMARY]"
        assert extract_tts_summary(text) == "padded text"

    def test_returns_empty_when_missing(self):
        assert extract_tts_summary("No summary here.") == ""

    def test_handles_multiline_summary(self):
        text = "[TTS_SUMMARY]\nLine one.\nLine two.\n[/TTS_SUMMARY]"
        result = extract_tts_summary(text)
        assert "Line one." in result
        assert "Line two." in result

    def test_embedded_in_long_response(self):
        text = ("# Header\nLots of markdown...\n" * 50 +
                "[TTS_SUMMARY]Found it.[/TTS_SUMMARY]\n")
        assert extract_tts_summary(text) == "Found it."

    def test_unclosed_tag_returns_empty(self):
        assert extract_tts_summary("[TTS_SUMMARY]no closing tag") == ""

    def test_empty_string(self):
        assert extract_tts_summary("") == ""

    def test_empty_summary_block(self):
        text = "[TTS_SUMMARY]   [/TTS_SUMMARY]"
        assert extract_tts_summary(text) == ""

    def test_last_block_wins(self):
        # The summary is requested at the end of the response, so an earlier
        # block (the agent echoing the instruction back) must not win.
        text = ("Sure, I will end with:\n[TTS_SUMMARY]\nYour summary here.\n"
                "[/TTS_SUMMARY]\n\nDone.\n\n[TTS_SUMMARY]\nThe real one.\n"
                "[/TTS_SUMMARY]\n")
        assert extract_tts_summary(text) == "The real one."

    def test_skips_empty_trailing_block(self):
        text = "[TTS_SUMMARY]Real summary.[/TTS_SUMMARY]\n[TTS_SUMMARY][/TTS_SUMMARY]"
        assert extract_tts_summary(text) == "Real summary."

    def test_ignores_markers_quoted_in_source(self):
        # Tasks about this codebase put the markers in quoted source code.
        text = ("The detector looks for [TTS_SUMMARY] and [/TTS_SUMMARY] in "
                "emit_typewriter().\n\n[TTS_SUMMARY]\nI explained the marker "
                "detection.\n[/TTS_SUMMARY]\n")
        assert extract_tts_summary(text) == "I explained the marker detection."

    def test_none_safe(self):
        assert extract_tts_summary("") == ""


class TestCleanSpokenText:
    def test_strips_markdown_formatting(self):
        raw = "## Header\nThis is **bold** and *italic* with `inline code` and [a link](https://example.com)."
        clean = clean_spoken_text(raw)
        assert "##" not in clean
        assert "**" not in clean
        assert "*" not in clean
        assert "`" not in clean
        assert "https://" not in clean
        assert "Header This is bold and italic with inline code and a link." in clean

    def test_strips_code_blocks(self):
        raw = "Here is the fix:\n```python\ndef foo():\n    return 42\n```\nIt is all done."
        clean = clean_spoken_text(raw)
        assert "def foo" not in clean
        assert clean == "Here is the fix: It is all done."

    def test_strips_ansi_codes(self):
        raw = "\x1b[32mSuccess!\x1b[0m All tests passed."
        clean = clean_spoken_text(raw)
        assert clean == "Success! All tests passed."

    def test_empty_and_whitespace(self):
        assert clean_spoken_text("") == ""
        assert clean_spoken_text("   \n\t  ") == ""


class TestExtractFallbackSummary:
    def test_extracts_from_unclosed_tts_tag(self):
        text = "I analyzed the repo.\n[TTS_SUMMARY]\nI resolved the container issue by updating timeout configs."
        summary = extract_fallback_summary(text)
        assert "I resolved the container issue by updating timeout configs." in summary

    def test_extracts_from_plain_markdown_response(self):
        text = ("# Completed\n"
                "I examined the problem and fixed the audio device configuration. "
                "Tests are now passing cleanly. You can run the workshop now.")
        summary = extract_fallback_summary(text)
        assert "I examined the problem and fixed the audio device configuration." in summary
        assert "Tests are now passing cleanly." in summary

    def test_empty_input(self):
        assert extract_fallback_summary("") == ""


class TestFormatErrorReadout:
    def test_container_timeout(self):
        msg = format_error_readout("Task failed: container timed out after 300s", "Antigravity")
        assert "execution container timed out" in msg

    def test_timeout_waiting_for_response(self):
        msg = format_error_readout("ERROR: timeout waiting for response", "Antigravity")
        assert "execution container timed out" in msg

    def test_exit_code_124_is_timeout(self):
        msg = format_error_readout("", "Antigravity", exit_code=124)
        assert "execution container timed out" in msg

    def test_rate_limit(self):
        msg = format_error_readout("Rate limit exceeded 429", "Antigravity")
        assert "rate limit" in msg or "quota" in msg

    def test_cli_not_found(self):
        msg = format_error_readout("agy: command not found", "Antigravity")
        assert "command line tool was not found" in msg

    def test_memory_limit_137(self):
        msg = format_error_readout("", "Antigravity", exit_code=137)
        assert "memory" in msg

    def test_generic_exit_code(self):
        msg = format_error_readout("", "Antigravity", exit_code=1)
        assert "exit code 1" in msg

    def test_specific_error_message(self):
        msg = format_error_readout("Error: database locked by another process", "Antigravity")
        assert "database locked by another process" in msg
