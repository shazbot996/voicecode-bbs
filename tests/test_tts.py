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
