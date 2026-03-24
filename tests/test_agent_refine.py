"""Tests for agent prompt refinement."""

import subprocess
from unittest.mock import patch, MagicMock

import pytest
from voicecode.agent.refine import _load_refine_prompts, refine_with_llm
from voicecode.providers.claude import ClaudeProvider


class TestLoadRefinePrompts:
    def test_splits_on_separator(self, tmp_path):
        template = tmp_path / "REFINE.md"
        template.write_text("Initial prompt\n===MODIFY===\nModify prompt")
        with patch("voicecode.agent.refine.REFINE_PROMPT_PATH", template):
            initial, modify = _load_refine_prompts()
        assert initial == "Initial prompt"
        assert modify == "Modify prompt"

    def test_no_separator_uses_same_for_both(self, tmp_path):
        template = tmp_path / "REFINE.md"
        template.write_text("Only one section")
        with patch("voicecode.agent.refine.REFINE_PROMPT_PATH", template):
            initial, modify = _load_refine_prompts()
        assert initial == "Only one section"
        assert modify == "Only one section"

    def test_multiple_separators_splits_on_first(self, tmp_path):
        template = tmp_path / "REFINE.md"
        template.write_text("Part A\n===MODIFY===\nPart B\n===MODIFY===\nPart C")
        with patch("voicecode.agent.refine.REFINE_PROMPT_PATH", template):
            initial, modify = _load_refine_prompts()
        assert initial == "Part A"
        assert "Part B" in modify
        assert "Part C" in modify


class TestRefineWithLlm:
    def _mock_template(self, tmp_path):
        template = tmp_path / "REFINE.md"
        template.write_text("Refine these: {fragments}\n===MODIFY===\n"
                            "Current: {current_prompt}\nNew: {fragments}")
        return template

    def test_success_initial(self, tmp_path):
        template = self._mock_template(tmp_path)
        provider = ClaudeProvider()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Refined prompt text"
        with patch("voicecode.agent.refine.REFINE_PROMPT_PATH", template), \
             patch("subprocess.run", return_value=mock_result):
            result = refine_with_llm(["fragment one"], None, provider=provider)
        assert result == "Refined prompt text"

    def test_success_modify(self, tmp_path):
        template = self._mock_template(tmp_path)
        provider = ClaudeProvider()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Modified prompt"
        with patch("voicecode.agent.refine.REFINE_PROMPT_PATH", template), \
             patch("subprocess.run", return_value=mock_result) as mock_run:
            result = refine_with_llm(["frag"], "existing prompt", provider=provider)
        assert result == "Modified prompt"
        # Verify the modify template was used (contains current_prompt)
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        prompt_text = cmd[-1]  # -p <prompt>
        assert "existing prompt" in prompt_text

    def test_cli_not_found(self, tmp_path):
        template = self._mock_template(tmp_path)
        provider = ClaudeProvider()
        with patch("voicecode.agent.refine.REFINE_PROMPT_PATH", template), \
             patch("subprocess.run", side_effect=FileNotFoundError):
            result = refine_with_llm(["frag"], None, provider=provider)
        assert "[Error:" in result
        assert "not found" in result

    def test_timeout(self, tmp_path):
        template = self._mock_template(tmp_path)
        provider = ClaudeProvider()
        with patch("voicecode.agent.refine.REFINE_PROMPT_PATH", template), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 120)):
            result = refine_with_llm(["frag"], None, provider=provider)
        assert "timed out" in result

    def test_nonzero_returncode(self, tmp_path):
        template = self._mock_template(tmp_path)
        provider = ClaudeProvider()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "some error"
        with patch("voicecode.agent.refine.REFINE_PROMPT_PATH", template), \
             patch("subprocess.run", return_value=mock_result):
            result = refine_with_llm(["frag"], None, provider=provider)
        assert "[Error:" in result

    def test_status_callback_called(self, tmp_path):
        template = self._mock_template(tmp_path)
        provider = ClaudeProvider()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "done"
        callback = MagicMock()
        with patch("voicecode.agent.refine.REFINE_PROMPT_PATH", template), \
             patch("subprocess.run", return_value=mock_result):
            refine_with_llm(["frag"], None, status_callback=callback, provider=provider)
        callback.assert_called_once()
