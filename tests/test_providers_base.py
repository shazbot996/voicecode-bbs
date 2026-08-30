"""Tests for provider base class and registry."""

from unittest.mock import patch
from voicecode.providers.base import CLIProvider
from voicecode.providers.claude import ClaudeProvider
from voicecode.providers.antigravity import AntigravityProvider
from voicecode.providers import get_provider_by_name


class TestGetBaseCmd:
    def test_default_binary(self):
        p = ClaudeProvider()
        assert p._get_base_cmd() == ["claude"]

    def test_antigravity_binary(self):
        p = AntigravityProvider()
        assert p._get_base_cmd() == ["agy"]

    def test_command_override_respects_quoting(self):
        p = ClaudeProvider()
        p.command_override = '"/opt/my tools/claude" --effort high'
        assert p._get_base_cmd() == ["/opt/my tools/claude", "--effort", "high"]

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

    def test_antigravity_lookup(self):
        assert get_provider_by_name("antigravity") is not None

    def test_unknown_returns_none(self):
        assert get_provider_by_name("openai") is None

    def test_returns_correct_type(self):
        assert isinstance(get_provider_by_name("claude"), ClaudeProvider)
        assert isinstance(get_provider_by_name("antigravity"), AntigravityProvider)


class TestVersionUsesBinaryOnly:
    def test_extra_flags_not_passed_to_version(self):
        p = ClaudeProvider()
        p.command_override = "claude --effort high"
        mock_result = type("Result", (), {"returncode": 0, "stdout": "1.2.3\n"})()
        with patch("subprocess.run", return_value=mock_result) as m:
            assert p.get_version() == "1.2.3"
        assert m.call_args[0][0] == ["claude", "--version"]


class TestModelLabel:
    def test_label_for_selected_model(self):
        p = ClaudeProvider()
        p.set_model("opus")
        assert p.model_label() == "Opus 5"

    def test_label_defaults_when_unset(self):
        p = ClaudeProvider()
        p.set_model(None)
        assert p.model_label() == "Default"

    def test_unknown_model_falls_back_to_id(self):
        p = ClaudeProvider()
        p.set_model("some-future-model")
        assert p.model_label() == "some-future-model"
