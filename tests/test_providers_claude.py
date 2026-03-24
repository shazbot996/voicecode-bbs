"""Tests for ClaudeProvider event parsing and command building."""

import pytest
from voicecode.providers.claude import ClaudeProvider


@pytest.fixture
def cp():
    return ClaudeProvider()


# -- parse_init_event --

class TestParseInitEvent:
    def test_extracts_session_id(self, cp):
        event = {"type": "system", "subtype": "init", "session_id": "abc-123"}
        assert cp.parse_init_event(event) == "abc-123"

    def test_returns_none_for_wrong_type(self, cp):
        assert cp.parse_init_event({"type": "assistant"}) is None

    def test_returns_none_for_missing_session_id(self, cp):
        assert cp.parse_init_event({"type": "system", "subtype": "init"}) is None

    def test_returns_none_for_wrong_subtype(self, cp):
        assert cp.parse_init_event({"type": "system", "subtype": "other"}) is None


# -- parse_text_event --

class TestParseTextEvent:
    def test_extracts_text(self, cp):
        event = {"type": "assistant", "message": {
            "content": [{"type": "text", "text": "Hello world"}]}}
        text, tools = cp.parse_text_event(event)
        assert text == "Hello world"
        assert tools == []

    def test_extracts_tool_use(self, cp):
        event = {"type": "assistant", "message": {
            "content": [{"type": "tool_use", "name": "Read", "input": {"path": "/tmp"}}]}}
        text, tools = cp.parse_text_event(event)
        assert text == ""
        assert tools == [("Read", {"path": "/tmp"})]

    def test_mixed_text_and_tools(self, cp):
        event = {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Let me read that."},
            {"type": "tool_use", "name": "Read", "input": {}}
        ]}}
        text, tools = cp.parse_text_event(event)
        assert text == "Let me read that."
        assert len(tools) == 1

    def test_returns_none_for_non_assistant(self, cp):
        assert cp.parse_text_event({"type": "user"}) is None

    def test_returns_none_for_empty_content(self, cp):
        event = {"type": "assistant", "message": {"content": []}}
        assert cp.parse_text_event(event) is None

    def test_multiple_text_blocks_concatenated(self, cp):
        event = {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Hello "},
            {"type": "text", "text": "world"},
        ]}}
        text, tools = cp.parse_text_event(event)
        assert text == "Hello world"


# -- parse_thinking_event --

class TestParseThinkingEvent:
    def test_extracts_thinking(self, cp):
        event = {"type": "assistant", "message": {
            "content": [{"type": "thinking", "thinking": "Let me consider..."}]}}
        assert cp.parse_thinking_event(event) == "Let me consider..."

    def test_returns_none_when_no_thinking(self, cp):
        event = {"type": "assistant", "message": {
            "content": [{"type": "text", "text": "Hello"}]}}
        assert cp.parse_thinking_event(event) is None

    def test_returns_none_for_non_assistant(self, cp):
        assert cp.parse_thinking_event({"type": "user"}) is None

    def test_empty_thinking_returns_none(self, cp):
        event = {"type": "assistant", "message": {
            "content": [{"type": "thinking", "thinking": ""}]}}
        assert cp.parse_thinking_event(event) is None


# -- parse_tool_result_event --

class TestParseToolResultEvent:
    def test_extracts_text_result(self, cp):
        event = {"type": "user", "content": [
            {"type": "tool_result", "content": "file contents here"}]}
        result = cp.parse_tool_result_event(event)
        assert "file contents here" in result

    def test_truncates_long_results(self, cp):
        event = {"type": "user", "content": [
            {"type": "tool_result", "content": "x" * 500}]}
        result = cp.parse_tool_result_event(event)
        assert len(result) < 500
        assert "500 chars" in result

    def test_handles_list_content(self, cp):
        event = {"type": "user", "content": [
            {"type": "tool_result", "content": [
                {"type": "text", "text": "line one"},
                {"type": "text", "text": "line two"}
            ]}]}
        result = cp.parse_tool_result_event(event)
        assert "line one" in result

    def test_returns_none_for_non_user(self, cp):
        assert cp.parse_tool_result_event({"type": "assistant"}) is None

    def test_returns_none_for_empty_results(self, cp):
        event = {"type": "user", "content": [
            {"type": "tool_result", "content": ""}]}
        assert cp.parse_tool_result_event(event) is None


# -- parse_context_usage --

class TestParseContextUsage:
    def test_extracts_usage(self, cp):
        event = {"type": "result", "modelUsage": {
            "claude-sonnet-4-6": {
                "contextWindow": 200000,
                "inputTokens": 1000,
                "outputTokens": 500,
                "cacheReadInputTokens": 200,
                "cacheCreationInputTokens": 100
            }}}
        total, window = cp.parse_context_usage(event)
        assert total == 1800
        assert window == 200000

    def test_returns_none_for_non_result(self, cp):
        assert cp.parse_context_usage({"type": "assistant"}) is None

    def test_returns_none_for_empty_model_usage(self, cp):
        event = {"type": "result", "modelUsage": {}}
        assert cp.parse_context_usage(event) is None


# -- is_result_event --

class TestIsResultEvent:
    def test_extracts_result_text(self, cp):
        event = {"type": "result", "result": "Done."}
        assert cp.is_result_event(event) == "Done."

    def test_returns_empty_string_for_missing_result(self, cp):
        event = {"type": "result"}
        assert cp.is_result_event(event) == ""

    def test_returns_none_for_non_result(self, cp):
        assert cp.is_result_event({"type": "assistant"}) is None


# -- build_refine_cmd --

class TestBuildRefineCmd:
    def test_basic_cmd(self, cp):
        cmd = cp.build_refine_cmd("test prompt")
        assert cmd[0] == "claude"
        assert "--print" in cmd
        assert cmd[-2:] == ["-p", "test prompt"]


# -- build_execute_cmd --

class TestBuildExecuteCmd:
    def test_basic_cmd(self, cp):
        cmd = cp.build_execute_cmd("run this")
        assert "--output-format" in cmd
        assert "stream-json" in cmd
        assert "--dangerously-skip-permissions" in cmd
        assert cmd[-2:] == ["-p", "run this"]

    def test_with_session_id(self, cp):
        cmd = cp.build_execute_cmd("run this", session_id="sess-42")
        assert "--resume" in cmd
        assert "sess-42" in cmd

    def test_without_session_id(self, cp):
        cmd = cp.build_execute_cmd("run this")
        assert "--resume" not in cmd

    def test_command_override(self):
        cp = ClaudeProvider()
        cp.command_override = "/usr/local/bin/claude --model opus"
        cmd = cp.build_execute_cmd("test")
        assert cmd[0] == "/usr/local/bin/claude"
        assert "--model" in cmd
