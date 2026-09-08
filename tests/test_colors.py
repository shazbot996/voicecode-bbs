"""Tests for themes, color initialization, and TTS styling."""

import curses
from unittest.mock import patch, MagicMock

import pytest
from voicecode.ui.themes import THEMES, ROLE_TO_PAIR, validate_theme, get_theme_dict
from voicecode.ui.colors import CP_TTS, init_colors, set_active_theme, get_active_theme


class TestThemes:
    def test_all_themes_have_required_roles(self):
        for name, theme in THEMES.items():
            missing = validate_theme(theme)
            assert not missing, f"Theme {name} is missing roles: {missing}"

    def test_tts_in_role_to_pair(self):
        assert "tts" in ROLE_TO_PAIR
        assert ROLE_TO_PAIR["tts"] == CP_TTS

    def test_pcboard_tts_is_white(self):
        theme = get_theme_dict("pcboard")
        assert theme["tts"]["fg"] == curses.COLOR_WHITE


class TestColorInit:
    @patch("curses.init_pair")
    @patch("curses.use_default_colors")
    @patch("curses.start_color")
    def test_init_colors_sets_cp_tts_to_white(self, mock_start, mock_use_def, mock_init_pair):
        # Even if tts_available is False, CP_TTS must be initialized from theme["tts"] (white)
        init_colors("pcboard", tts_available=False)
        assert get_active_theme() == "pcboard"

        # Check all init_pair calls
        tts_calls = [call for call in mock_init_pair.call_args_list if call[0][0] == CP_TTS]
        assert len(tts_calls) >= 1
        # In pcboard theme, tts fg is COLOR_WHITE (7)
        for call in tts_calls:
            fg_arg = call[0][1]
            assert fg_arg == curses.COLOR_WHITE

    @patch("curses.init_pair")
    @patch("curses.use_default_colors")
    @patch("curses.start_color")
    def test_set_active_theme_sets_cp_tts_to_white(self, mock_start, mock_use_def, mock_init_pair):
        set_active_theme("pcboard", tts_available=False)
        assert get_active_theme() == "pcboard"

        tts_calls = [call for call in mock_init_pair.call_args_list if call[0][0] == CP_TTS]
        assert len(tts_calls) >= 1
        for call in tts_calls:
            assert call[0][1] == curses.COLOR_WHITE
