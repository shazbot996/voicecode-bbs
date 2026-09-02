"""Tests for the Antigravity (`agy`) CLI provider.

Event fixtures are taken from real `agy --output-format stream-json` output
so these tests pin actual CLI behavior rather than an assumed schema.
"""

import os
from unittest.mock import patch

from voicecode.providers.antigravity import AntigravityProvider, _FALLBACK_MODELS
from voicecode.providers.base import DEFAULT_CONTEXT_WINDOW, MODE_BUILD, MODE_PLAN


# ─── Command building ───────────────────────────────────────────────

class TestBuildRefineCmd:
    def test_basic(self, antigravity):
        cmd = antigravity.build_refine_cmd("hello")
        assert cmd[0] == "agy"
        assert "--dangerously-skip-permissions" in cmd
        assert "--print-timeout" in cmd
        assert cmd[cmd.index("--print-timeout") + 1] == "1h"
        assert cmd[-1] == "--print=hello"

    def test_no_stream_json(self, antigravity):
        # Refinement wants plain text on stdout.
        assert "stream-json" not in antigravity.build_refine_cmd("hi")

    def test_workspace_dir_added(self, antigravity):
        antigravity.set_workspace_dir("/tmp/work")
        cmd = antigravity.build_refine_cmd("hi")
        assert "--add-dir" in cmd
        assert cmd[cmd.index("--add-dir") + 1] == "/tmp/work"

    def test_workspace_dir_expanded(self, antigravity):
        antigravity.set_workspace_dir("~/proj")
        cmd = antigravity.build_refine_cmd("hi")
        assert cmd[cmd.index("--add-dir") + 1] == os.path.expanduser("~/proj")

    def test_workspace_dir_omitted_when_unset(self, antigravity):
        antigravity.set_workspace_dir("")
        assert "--add-dir" not in antigravity.build_refine_cmd("hi")


class TestBuildExecuteCmd:
    def test_stream_json(self, antigravity):
        cmd = antigravity.build_execute_cmd("do it")
        assert cmd[cmd.index("--output-format") + 1] == "stream-json"

    def test_print_timeout_added(self, antigravity):
        cmd = antigravity.build_execute_cmd("do it")
        assert "--print-timeout" in cmd
        assert cmd[cmd.index("--print-timeout") + 1] == "1h"

    def test_print_timeout_not_duplicated_with_override(self, antigravity):
        antigravity.command_override = "agy --print-timeout 30m"
        cmd = antigravity.build_execute_cmd("do it")
        assert cmd.count("--print-timeout") == 1
        assert cmd[cmd.index("--print-timeout") + 1] == "30m"

    def test_prompt_is_fused_and_last(self, antigravity):
        """Regression test for the Go-flag quirk.

        A bare `--print` swallows the next token, so the prompt must be one
        fused argv element in final position.
        """
        cmd = antigravity.build_execute_cmd("do it", "sess-1")
        assert cmd[-1] == "--print=do it"
        assert "--print" not in cmd          # never the bare flag
        assert "do it" not in cmd            # never a standalone value

    def test_multiline_prompt_stays_one_arg(self, antigravity):
        cmd = antigravity.build_execute_cmd("line one\nline two")
        assert cmd[-1] == "--print=line one\nline two"
        assert len([a for a in cmd if a.startswith("--print=")]) == 1

    def test_conversation_when_session_id(self, antigravity):
        cmd = antigravity.build_execute_cmd("go", "abc-123")
        assert cmd[cmd.index("--conversation") + 1] == "abc-123"

    def test_no_conversation_without_session_id(self, antigravity):
        assert "--conversation" not in antigravity.build_execute_cmd("go")
        assert "--resume" not in antigravity.build_execute_cmd("go", "abc")

    def test_build_mode(self, antigravity):
        cmd = antigravity.build_execute_cmd("go", None, MODE_BUILD)
        assert cmd[cmd.index("--mode") + 1] == "accept-edits"

    def test_plan_mode(self, antigravity):
        cmd = antigravity.build_execute_cmd("go", None, MODE_PLAN)
        assert cmd[cmd.index("--mode") + 1] == "plan"
        # Verified: skip-permissions does NOT defeat plan mode on `agy`,
        # so it is kept in both modes (unlike Claude).
        assert "--dangerously-skip-permissions" in cmd

    def test_model_flag(self, antigravity):
        antigravity.set_model("gemini-3.1-pro-high")
        cmd = antigravity.build_execute_cmd("go")
        assert cmd[cmd.index("--model") + 1] == "gemini-3.1-pro-high"

    def test_no_model_flag_when_default(self, antigravity):
        antigravity.set_model(None)
        assert "--model" not in antigravity.build_execute_cmd("go")


# ─── Model discovery ────────────────────────────────────────────────

class TestListModels:
    def test_parses_tab_separated_output(self, antigravity):
        stdout = ("Fetching available models...\n"
                  "gemini-3.7-flash-high\tGemini 3.7 Flash (High)\n"
                  "gemini-3.1-pro-low\tGemini 3.1 Pro (Low)\n")
        result = type("R", (), {"returncode": 0, "stdout": stdout})()
        with patch("subprocess.run", return_value=result):
            models = antigravity.list_models()
        assert models[0] == (None, "Default")
        assert ("gemini-3.7-flash-high", "Gemini 3.7 Flash (High)") in models
        # The preamble line has no tab and must be skipped.
        assert all(mid is None or "Fetching" not in mid for mid, _ in models)

    def test_result_is_cached(self, antigravity):
        result = type("R", (), {"returncode": 0, "stdout": "a\tA\nb\tB\n"})()
        with patch("subprocess.run", return_value=result) as m:
            antigravity.list_models()
            antigravity.list_models()
        assert m.call_count == 1

    def test_falls_back_when_cli_missing(self, antigravity):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert antigravity.list_models() == _FALLBACK_MODELS

    def test_falls_back_on_empty_output(self, antigravity):
        result = type("R", (), {"returncode": 0, "stdout": ""})()
        with patch("subprocess.run", return_value=result):
            assert antigravity.list_models() == _FALLBACK_MODELS


# ─── Event parsing ──────────────────────────────────────────────────

INIT = {"event": "init", "conversation_id": "5a17-abc",
        "init": {"cwd": "/tmp", "permission_mode": "always-proceed"}}

TEXT = {"event": "step_update", "step_update": {
    "step_index": 3, "state": "ACTIVE", "step_type": "agent_response",
    "text_delta": "The contents are:"}}

TOOL_ACTIVE = {"event": "step_update", "step_update": {
    "step_index": 2, "state": "ACTIVE", "step_type": "tool",
    "tool_name": "view_file",
    "tool_info": {"name": "view_file",
                  "parameters": {"AbsolutePath": "/tmp/probe.txt"}}}}

TOOL_DONE = {"event": "step_update", "step_update": {
    "step_index": 2, "state": "DONE", "step_type": "tool",
    "tool_name": "view_file",
    "tool_info": {"name": "view_file",
                  "parameters": {"AbsolutePath": "/tmp/probe.txt"},
                  "output": "2 lines, 16 bytes"}}}

RESULT = {"event": "result", "result": {
    "conversation_id": "5a17-abc", "status": "SUCCESS", "response": "all done",
    "duration_seconds": 5.48, "num_turns": 1,
    "usage": {"input_tokens": 17744, "output_tokens": 345,
              "thinking_tokens": 271, "cache_read_tokens": 7260,
              "total_tokens": 18089}}}


class TestParseInitEvent:
    def test_reads_top_level_conversation_id(self, antigravity):
        assert antigravity.parse_init_event(INIT) == "5a17-abc"

    def test_reads_nested_init_conversation_id(self, antigravity):
        ev = {"event": "init", "init": {"conversation_id": "nested-123"}}
        assert antigravity.parse_init_event(ev) == "nested-123"

    def test_reads_result_conversation_id(self, antigravity):
        assert antigravity.parse_init_event(RESULT) == "5a17-abc"

    def test_ignores_text_events(self, antigravity):
        assert antigravity.parse_init_event(TEXT) is None

    def test_missing_id(self, antigravity):
        assert antigravity.parse_init_event({"event": "init", "init": {}}) is None


class TestParseTextEvent:
    def test_returns_delta(self, antigravity):
        assert antigravity.parse_text_event(TEXT) == ("The contents are:", [])

    def test_empty_delta_ignored(self, antigravity):
        ev = {"event": "step_update", "step_update": {
            "step_type": "agent_response", "state": "DONE", "text_delta": ""}}
        assert antigravity.parse_text_event(ev) is None

    def test_tool_rendered_on_active(self, antigravity):
        text, tools = antigravity.parse_text_event(TOOL_ACTIVE)
        assert text == ""
        assert tools == [("view_file", {"AbsolutePath": "/tmp/probe.txt"})]

    def test_tool_not_rendered_twice(self, antigravity):
        """Tool steps fire ACTIVE then DONE; only ACTIVE may render."""
        assert antigravity.parse_text_event(TOOL_DONE) is None

    def test_ignores_non_step_events(self, antigravity):
        assert antigravity.parse_text_event(INIT) is None
        assert antigravity.parse_text_event(RESULT) is None


class TestParseThinkingEvent:
    def test_always_none(self, antigravity):
        # stream-json carries thinking_tokens counters but no thinking text.
        for ev in (INIT, TEXT, TOOL_ACTIVE, RESULT):
            assert antigravity.parse_thinking_event(ev) is None


class TestParseToolResultEvent:
    def test_extracts_output_on_done(self, antigravity):
        assert antigravity.parse_tool_result_event(TOOL_DONE) == "2 lines, 16 bytes"

    def test_none_on_active(self, antigravity):
        assert antigravity.parse_tool_result_event(TOOL_ACTIVE) is None

    def test_none_when_output_absent(self, antigravity):
        # write_to_file emits a DONE step with no output field.
        ev = {"event": "step_update", "step_update": {
            "state": "DONE", "step_type": "tool", "tool_name": "write_to_file",
            "tool_info": {"parameters": {"TargetFile": "/tmp/x"}}}}
        assert antigravity.parse_tool_result_event(ev) is None

    def test_truncates_long_output(self, antigravity):
        long_out = "x" * 500
        ev = {"event": "step_update", "step_update": {
            "state": "DONE", "step_type": "tool", "tool_name": "run_command",
            "tool_info": {"output": long_out}}}
        preview = antigravity.parse_tool_result_event(ev)
        assert preview.startswith("x" * 200)
        assert preview.endswith("... (500 chars)")

    def test_flattens_newlines(self, antigravity):
        ev = {"event": "step_update", "step_update": {
            "state": "DONE", "step_type": "tool", "tool_name": "list_dir",
            "tool_info": {"output": "a\nb\nc"}}}
        assert antigravity.parse_tool_result_event(ev) == "a b c"


class TestParseContextUsage:
    def test_from_result_event(self, antigravity):
        used, window = antigravity.parse_context_usage(RESULT)
        assert used == 17744 + 7260
        assert window == DEFAULT_CONTEXT_WINDOW

    def test_from_agent_response_step(self, antigravity):
        ev = {"event": "step_update", "step_update": {
            "step_type": "agent_response", "state": "DONE",
            "usage": {"input_tokens": 5400, "cache_read_tokens": 7260}}}
        assert antigravity.parse_context_usage(ev) == (12660, DEFAULT_CONTEXT_WINDOW)

    def test_none_without_usage(self, antigravity):
        assert antigravity.parse_context_usage(TEXT) is None
        assert antigravity.parse_context_usage(INIT) is None

    def test_none_when_zero(self, antigravity):
        ev = {"event": "result", "result": {
            "usage": {"input_tokens": 0, "cache_read_tokens": 0}}}
        assert antigravity.parse_context_usage(ev) is None


class TestIsResultEvent:
    def test_returns_response(self, antigravity):
        assert antigravity.is_result_event(RESULT) == "all done"

    def test_empty_string_when_response_missing(self, antigravity):
        """Must be "" not None so run_agent() falls back to streamed deltas."""
        ev = {"event": "result", "result": {"status": "SUCCESS"}}
        assert antigravity.is_result_event(ev) == ""

    def test_terminates_on_non_success(self, antigravity):
        ev = {"event": "result", "result": {"status": "ERROR", "response": "nope"}}
        assert antigravity.is_result_event(ev) == "nope"

    def test_none_for_other_events(self, antigravity):
        assert antigravity.is_result_event(TEXT) is None
        assert antigravity.is_result_event(INIT) is None


class TestParseErrorEvent:
    def test_top_level_error_string(self, antigravity):
        ev = {"event": "error", "error": "Container timed out"}
        assert antigravity.parse_error_event(ev) == "Container timed out"

    def test_top_level_error_dict(self, antigravity):
        ev = {"event": "error", "error": {"message": "Resource exhausted", "code": 429}}
        assert antigravity.parse_error_event(ev) == "Resource exhausted"

    def test_step_error_state(self, antigravity):
        ev = {"event": "step_update", "step_update": {"step_type": "tool", "state": "ERROR", "error": "Execution failed"}}
        assert antigravity.parse_error_event(ev) == "Execution failed"

    def test_result_error_status(self, antigravity):
        ev = {"event": "result", "result": {"status": "ERROR", "error": "Task timeout expired"}}
        assert antigravity.parse_error_event(ev) == "Task timeout expired"

    def test_none_for_normal_event(self, antigravity):
        assert antigravity.parse_error_event(TEXT) is None
        assert antigravity.parse_error_event(INIT) is None
        assert antigravity.parse_error_event(RESULT) is None


class TestGetEnv:
    def test_proxy_vars_survive(self, antigravity):
        """Inverse of the deleted Gemini test_strips_proxy_when_disabled."""
        with patch.dict(os.environ, {"HTTPS_PROXY": "http://proxy:8080"}):
            assert antigravity.get_env()["HTTPS_PROXY"] == "http://proxy:8080"

    def test_is_a_copy(self, antigravity):
        env = antigravity.get_env()
        env["VOICECODE_TEST_ONLY"] = "1"
        assert "VOICECODE_TEST_ONLY" not in os.environ
