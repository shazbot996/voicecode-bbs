"""Tests for settings utility functions."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from voicecode.settings import (
    slug_from_text, next_seq,
    load_settings, save_settings,
    load_shortcuts, save_shortcuts,
    persist_setting,
)


# -- slug_from_text (pure) --

class TestSlugFromText:
    def test_simple_text(self):
        assert slug_from_text("Write a Docker compose file") == "write_a_docker_compose_file"

    def test_skips_markdown_headings(self):
        assert slug_from_text("# Title\nActual prompt here") == "actual_prompt_here"

    def test_strips_special_chars(self):
        assert slug_from_text("Hello, world! How's it?") == "hello_world_hows_it"

    def test_respects_max_words(self):
        assert slug_from_text("one two three four five six", max_words=3) == "one_two_three"

    def test_default_max_words_is_five(self):
        result = slug_from_text("a b c d e f g")
        assert result == "a_b_c_d_e"

    def test_empty_text(self):
        assert slug_from_text("") == "prompt"

    def test_only_headings(self):
        result = slug_from_text("# heading\n# another")
        assert result != ""
        assert isinstance(result, str)

    def test_whitespace_only(self):
        assert slug_from_text("   \n   ") == "prompt"

    def test_numbers_preserved(self):
        assert slug_from_text("Add 3 columns") == "add_3_columns"

    def test_multiline_picks_first_non_heading(self):
        text = "# Title\n## Subtitle\nThe real content here"
        assert slug_from_text(text) == "the_real_content_here"


# -- next_seq (filesystem) --

class TestNextSeq:
    def test_empty_directory(self, tmp_path):
        assert next_seq(tmp_path) == 1

    def test_nonexistent_directory(self, tmp_path):
        assert next_seq(tmp_path / "nope") == 1

    def test_sequential_files(self, tmp_path):
        (tmp_path / "001_first.md").touch()
        (tmp_path / "002_second.md").touch()
        assert next_seq(tmp_path) == 3

    def test_gap_in_sequence(self, tmp_path):
        (tmp_path / "001_a.md").touch()
        (tmp_path / "005_b.md").touch()
        assert next_seq(tmp_path) == 6

    def test_ignores_non_numbered_files(self, tmp_path):
        (tmp_path / "readme.md").touch()
        (tmp_path / "003_real.md").touch()
        assert next_seq(tmp_path) == 4


# -- load_settings / save_settings (I/O) --

class TestLoadSettings:
    def test_returns_empty_dict_when_missing(self, tmp_path):
        with patch("voicecode.settings.SETTINGS_FILE", tmp_path / "nope.json"):
            assert load_settings() == {}

    def test_returns_empty_dict_on_bad_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json {{{")
        with patch("voicecode.settings.SETTINGS_FILE", bad):
            assert load_settings() == {}

    def test_loads_valid_json(self, tmp_path):
        f = tmp_path / "settings.json"
        f.write_text('{"key": "value"}')
        with patch("voicecode.settings.SETTINGS_FILE", f):
            assert load_settings() == {"key": "value"}


class TestSaveSettings:
    def test_creates_file(self, tmp_path):
        f = tmp_path / "settings.json"
        with patch("voicecode.settings.SETTINGS_DIR", tmp_path), \
             patch("voicecode.settings.SETTINGS_FILE", f):
            save_settings({"a": 1})
        assert json.loads(f.read_text()) == {"a": 1}

    def test_overwrites_existing(self, tmp_path):
        f = tmp_path / "settings.json"
        f.write_text('{"old": true}')
        with patch("voicecode.settings.SETTINGS_DIR", tmp_path), \
             patch("voicecode.settings.SETTINGS_FILE", f):
            save_settings({"new": True})
        assert json.loads(f.read_text()) == {"new": True}


# -- load_shortcuts / save_shortcuts --

class TestShortcuts:
    def test_load_missing_file(self, tmp_path):
        with patch("voicecode.settings.SHORTCUTS_FILE", tmp_path / "nope.txt"):
            assert load_shortcuts() == []

    def test_round_trip(self, tmp_path):
        f = tmp_path / "shortcuts.txt"
        with patch("voicecode.settings.SETTINGS_DIR", tmp_path), \
             patch("voicecode.settings.SHORTCUTS_FILE", f):
            save_shortcuts(["shortcut one", "shortcut two"])
        with patch("voicecode.settings.SHORTCUTS_FILE", f):
            result = load_shortcuts()
        assert "shortcut one" in result
        assert "shortcut two" in result

    def test_empty_shortcuts_list(self, tmp_path):
        f = tmp_path / "shortcuts.txt"
        with patch("voicecode.settings.SETTINGS_DIR", tmp_path), \
             patch("voicecode.settings.SHORTCUTS_FILE", f):
            save_shortcuts([])
        with patch("voicecode.settings.SHORTCUTS_FILE", f):
            assert load_shortcuts() == []


# -- persist_setting --

class TestPersistSetting:
    def test_updates_single_key(self, tmp_path):
        f = tmp_path / "settings.json"
        f.write_text('{"existing": true}')
        with patch("voicecode.settings.SETTINGS_DIR", tmp_path), \
             patch("voicecode.settings.SETTINGS_FILE", f):
            persist_setting("new_key", 42)
        data = json.loads(f.read_text())
        assert data == {"existing": True, "new_key": 42}

    def test_creates_from_scratch(self, tmp_path):
        f = tmp_path / "settings.json"
        with patch("voicecode.settings.SETTINGS_DIR", tmp_path), \
             patch("voicecode.settings.SETTINGS_FILE", f):
            persist_setting("first", "value")
        data = json.loads(f.read_text())
        assert data == {"first": "value"}
