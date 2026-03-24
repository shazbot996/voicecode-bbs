"""Tests for GeminiProvider event parsing and command building."""

import os
from unittest.mock import patch

import pytest
from voicecode.providers.gemini import GeminiProvider


@pytest.fixture
def gp():
    return GeminiProvider()


# -- parse_init_event --

class TestParseInitEvent:
    def test_extracts_session_id(self, gp):
        event = {"type": "init", "session_id": "gem-abc"}
        assert gp.parse_init_event(event) == "gem-abc"

    def test_returns_none_for_message_type(self, gp):
        event = {"type": "message", "role": "assistant", "session_id": "ignore-me"}
        assert gp.parse_init_event(event) is None

    def test_accepts_sessionId_variant(self, gp):
        event = {"type": "init", "sessionId": "gem-456"}
        assert gp.parse_init_event(event) == "gem-456"

    def test_accepts_session_variant(self, gp):
        event = {"type": "init", "session": "gem-789"}
        assert gp.parse_init_event(event) == "gem-789"

    def test_returns_none_for_no_session(self, gp):
        event = {"type": "init"}
        assert gp.parse_init_event(event) is None


# -- parse_text_event --

class TestParseTextEvent:
    def test_extracts_assistant_text(self, gp):
        event = {"type": "message", "role": "assistant", "content": "Hello"}
        text, tools = gp.parse_text_event(event)
        assert text == "Hello"
        assert tools == []

    def test_extracts_tool_use_event(self, gp):
        event = {"type": "tool_use", "tool_name": "Edit",
                 "parameters": {"path": "/tmp/x"}}
        text, tools = gp.parse_text_event(event)
        assert text == ""
        assert tools == [("Edit", {"path": "/tmp/x"})]

    def test_ignores_user_message(self, gp):
        event = {"type": "message", "role": "user", "content": "hi"}
        assert gp.parse_text_event(event) is None

    def test_returns_none_for_empty_content(self, gp):
        event = {"type": "message", "role": "assistant", "content": ""}
        assert gp.parse_text_event(event) is None

    def test_ignores_non_message_type(self, gp):
        event = {"type": "result", "content": "something"}
        assert gp.parse_text_event(event) is None


# -- parse_thinking_event --

class TestParseThinkingEvent:
    def test_extracts_thinking(self, gp):
        event = {"type": "message", "role": "assistant",
                 "thinking": "Analyzing the code..."}
        assert gp.parse_thinking_event(event) == "Analyzing the code..."

    def test_returns_none_without_thinking(self, gp):
        event = {"type": "message", "role": "assistant", "content": "Done"}
        assert gp.parse_thinking_event(event) is None

    def test_returns_none_for_non_assistant(self, gp):
        event = {"type": "message", "role": "user", "thinking": "ignore"}
        assert gp.parse_thinking_event(event) is None

    def test_empty_thinking_returns_none(self, gp):
        event = {"type": "message", "role": "assistant", "thinking": ""}
        assert gp.parse_thinking_event(event) is None


# -- parse_tool_result_event --

class TestParseToolResultEvent:
    def test_extracts_output(self, gp):
        event = {"type": "tool_result", "output": "file contents"}
        assert "file contents" in gp.parse_tool_result_event(event)

    def test_extracts_error(self, gp):
        event = {"type": "tool_result", "output": "",
                 "error": {"type": "not_found", "message": "No such file"}}
        result = gp.parse_tool_result_event(event)
        assert "ERROR" in result
        assert "not_found" in result

    def test_truncates_long_output(self, gp):
        event = {"type": "tool_result", "output": "y" * 500}
        result = gp.parse_tool_result_event(event)
        assert len(result) < 500

    def test_returns_none_for_wrong_type(self, gp):
        assert gp.parse_tool_result_event({"type": "message"}) is None

    def test_returns_none_for_empty_output(self, gp):
        event = {"type": "tool_result", "output": ""}
        assert gp.parse_tool_result_event(event) is None


# -- parse_context_usage --

class TestParseContextUsage:
    def test_extracts_stats(self, gp):
        event = {"type": "result", "stats": {"total_tokens": 5000}}
        total, window = gp.parse_context_usage(event)
        assert total == 5000
        assert window == 1_000_000

    def test_returns_none_for_zero_tokens(self, gp):
        event = {"type": "result", "stats": {"total_tokens": 0}}
        assert gp.parse_context_usage(event) is None

    def test_returns_none_for_non_result(self, gp):
        assert gp.parse_context_usage({"type": "message"}) is None


# -- is_result_event --

class TestIsResultEvent:
    def test_extracts_response(self, gp):
        event = {"type": "result", "response": "All done."}
        assert gp.is_result_event(event) == "All done."

    def test_falls_back_to_result_field(self, gp):
        event = {"type": "result", "result": "Fallback text"}
        assert gp.is_result_event(event) == "Fallback text"

    def test_returns_none_for_non_result(self, gp):
        assert gp.is_result_event({"type": "message"}) is None


# -- build_execute_cmd --

class TestBuildExecuteCmd:
    def test_basic_cmd(self, gp):
        cmd = gp.build_execute_cmd("test prompt")
        assert cmd[0] == "gemini"
        assert "--yolo" in cmd
        assert "-o" in cmd
        assert "stream-json" in cmd
        assert cmd[-2:] == ["-p", "test prompt"]

    def test_with_session(self, gp):
        cmd = gp.build_execute_cmd("test", session_id="s1")
        assert "--resume" in cmd
        assert "s1" in cmd

    def test_without_session(self, gp):
        cmd = gp.build_execute_cmd("test")
        assert "--resume" not in cmd


# -- build_refine_cmd --

class TestBuildRefineCmd:
    def test_basic_cmd(self, gp):
        cmd = gp.build_refine_cmd("refine this")
        assert cmd[0] == "gemini"
        assert "--yolo" in cmd
        assert cmd[-2:] == ["-p", "refine this"]


# -- get_env --

class TestGetEnv:
    def test_strips_gemini_api_key(self, gp):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "secret"}):
            env = gp.get_env()
            assert "GEMINI_API_KEY" not in env

    def test_strips_proxy_when_disabled(self):
        gp = GeminiProvider()
        gp.disable_proxy = True
        with patch.dict(os.environ, {"HTTPS_PROXY": "http://proxy:8080"}):
            env = gp.get_env()
            assert "HTTPS_PROXY" not in env

    def test_keeps_proxy_by_default(self, gp):
        with patch.dict(os.environ, {"HTTPS_PROXY": "http://proxy:8080"}):
            env = gp.get_env()
            assert env.get("HTTPS_PROXY") == "http://proxy:8080"

    def test_disable_proxy_flag_in_cmd(self):
        gp = GeminiProvider()
        gp.disable_proxy = True
        cmd = gp.build_execute_cmd("test")
        assert "--proxy=false" in cmd
