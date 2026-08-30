"""Tests for TTS utility functions."""

from voicecode.tts.engine import extract_tts_summary


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
