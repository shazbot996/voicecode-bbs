"""Tests for provider base class and registry."""

from unittest.mock import patch
from voicecode.providers.base import CLIProvider
from voicecode.providers.claude import ClaudeProvider
from voicecode.providers.gemini import GeminiProvider
from voicecode.providers import get_provider_by_name


class TestGetBaseCmd:
    def test_default_binary(self):
        p = ClaudeProvider()
        assert p._get_base_cmd() == ["claude"]

    def test_gemini_binary(self):
        p = GeminiProvider()
        assert p._get_base_cmd() == ["gemini"]

    def test_command_override(self):
        p = ClaudeProvider()
        p.command_override = "/usr/local/bin/claude --model opus"
        assert p._get_base_cmd() == ["/usr/local/bin/claude", "--model", "opus"]

    def test_command_override_cleared(self):
        p = ClaudeProvider()
        p.command_override = "/custom/path"
        p.command_override = None
        assert p._get_base_cmd() == ["claude"]


class TestIsInstalled:
    def test_found(self):
        p = ClaudeProvider()
        with patch("shutil.which", return_value="/usr/bin/claude"):
            assert p.is_installed() is True

    def test_not_found(self):
        p = ClaudeProvider()
        with patch("shutil.which", return_value=None):
            assert p.is_installed() is False


class TestGetVersion:
    def test_returns_version_string(self):
        p = ClaudeProvider()
        mock_result = type("Result", (), {"returncode": 0, "stdout": "1.2.3\n"})()
        with patch("subprocess.run", return_value=mock_result):
            assert p.get_version() == "1.2.3"

    def test_returns_none_on_failure(self):
        p = ClaudeProvider()
        mock_result = type("Result", (), {"returncode": 1, "stdout": ""})()
        with patch("subprocess.run", return_value=mock_result):
            assert p.get_version() is None

    def test_returns_none_on_exception(self):
        p = ClaudeProvider()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert p.get_version() is None


class TestGetProviderByName:
    def test_case_insensitive_lookup(self):
        assert get_provider_by_name("claude") is not None
        assert get_provider_by_name("Claude") is not None
        assert get_provider_by_name("CLAUDE") is not None

    def test_gemini_lookup(self):
        assert get_provider_by_name("gemini") is not None

    def test_unknown_returns_none(self):
        assert get_provider_by_name("openai") is None

    def test_returns_correct_type(self):
        assert isinstance(get_provider_by_name("claude"), ClaudeProvider)
        assert isinstance(get_provider_by_name("gemini"), GeminiProvider)
