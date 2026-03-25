---
type: plan
title: "VoiceCode Smoke Test Suite"
spec_reference: "Conversation-driven — smoke tests for regression safety"
scope: "Add pytest-based test infrastructure and phased test coverage for all testable modules"
date: 2026-03-24
---

## 1. Goal

Introduce a lightweight smoke test suite for VoiceCode that can be run quickly against code changes to catch regressions in core logic. The suite targets the ~25% of the codebase that is pure or near-pure (provider parsers, settings utilities, TTS extraction, publish prompt building, TextPane state logic) without requiring curses, audio hardware, or running CLI subprocesses. A `make test` target provides the single entry point.

## 2. Context & Prior Art

### Current state

- **No test infrastructure exists** — no `tests/` directory, no pytest config, no test dependencies.
- **No `pyproject.toml` or `setup.py`** — the project is a plain package run via `python voicecode_bbs.py`.
- **Makefile** (`Makefile`) has targets for `init`, `voicecode`, `clean` but nothing for tests.
- **`requirements.txt`** lists runtime deps only (faster-whisper, sounddevice, numpy, silero-vad, torch, piper-tts, pathvalidate, pychromecast).

### Key modules and their testability

| Module | Key functions | Pure? | Notes |
|--------|--------------|-------|-------|
| `voicecode/providers/claude.py` | 7 `parse_*` methods, `build_*_cmd` | Yes | Dict in → value out |
| `voicecode/providers/gemini.py` | 6 `parse_*` methods, `build_*_cmd`, `get_env` | Yes | Dict in → value out |
| `voicecode/providers/base.py` | `_get_base_cmd`, `is_installed`, `get_version` | Mostly | `is_installed` calls `shutil.which` |
| `voicecode/providers/__init__.py` | `detect_providers`, `get_provider_by_name` | No | `detect_providers` calls `is_installed` |
| `voicecode/settings.py` | `slug_from_text`, `next_seq`, `load_settings`, `save_settings`, `load_shortcuts`, `save_shortcuts` | Mixed | Slug/seq are pure; I/O functions need tmp dirs |
| `voicecode/tts/engine.py:16-21` | `extract_tts_summary` | Yes | Regex extraction |
| `voicecode/publish/base.py` | `PublishAgent.build_prompt`, `prompt_path` | Yes (with template I/O) | Template loading hits disk |
| `voicecode/publish/constraints.py` | `ConstraintsAgent.build_prompt` | Yes | Overrides `dest_folder` |
| `voicecode/ui/panes.py` | `TextPane` — `set_text`, `add_line`, `add_char_to_last_line`, `_trim_lines`, scroll methods | Yes (state mutation only) | No curses dependency except `draw()` |
| `voicecode/agent/refine.py` | `_load_refine_prompts`, `refine_with_llm` | No | File I/O + subprocess |
| `voicecode/constants.py` | `AgentState` | Yes | Trivial string constants |

### Patterns to follow

- The project uses a flat helper-per-concern layout (`voicecode/providers/`, `voicecode/agent/`, `voicecode/ui/`, etc.) — tests should mirror this.
- All providers inherit from `CLIProvider` (`providers/base.py:8`) with the same abstract interface — tests can be parametrized across providers.
- `PublishAgent` subclasses (`publish/arch.py` through `publish/conventions.py`) all follow the same 7-line pattern — a single parametrized test covers all of them.

## 3. Implementation Steps

### Phase 1: Infrastructure

#### Step 1.1 — Add test dependencies

**What:** Add `pytest` to a dev/test requirements file.
**Where:** New file `requirements-dev.txt`.
**How:**
```
pytest>=8.0
```
Keep it minimal — `unittest.mock` is in the stdlib, no extra mocking library needed. Do not add `pytest-cov` yet; coverage is a Phase 2+ concern.
**Why:** Separates test deps from runtime deps, keeping the main `requirements.txt` unchanged.

#### Step 1.2 — Create pytest configuration

**What:** Add a minimal `pytest.ini` (or `[tool.pytest.ini_options]` section — but since there is no `pyproject.toml`, use a standalone file).
**Where:** `pytest.ini` at project root.
**How:**
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_functions = test_*
```
**Why:** Tells pytest where to find tests. Keeps discovery simple.

#### Step 1.3 — Create test directory and conftest

**What:** Create `tests/` directory with a `conftest.py` providing shared fixtures.
**Where:** `tests/conftest.py`.
**How:**
```python
"""Shared fixtures for VoiceCode smoke tests."""

import pytest
from voicecode.providers.claude import ClaudeProvider
from voicecode.providers.gemini import GeminiProvider


@pytest.fixture
def claude():
    return ClaudeProvider()


@pytest.fixture
def gemini():
    return GeminiProvider()
```
**Why:** Provider instances are used across many test files. Central fixtures avoid duplication.

#### Step 1.4 — Add `make test` target

**What:** Add a `test` target to the Makefile.
**Where:** `Makefile`, after the `voicecode` target.
**How:** Add the following target and update the `.PHONY` line:
```makefile
test: ## Run the smoke test suite
	. $(VENV)/bin/activate && python -m pytest -q
```
Update the `.PHONY` line to include `test`.
**Why:** Single command to run all tests, consistent with the existing `make voicecode` pattern. Uses `python -m pytest` so the virtualenv's pytest is used and `voicecode` is on `sys.path`.

---

### Phase 2: Provider Parser Tests

These are the highest-value tests — pure functions that parse JSON events from Claude and Gemini CLIs. If a CLI output format changes, these break first.

#### Step 2.1 — Claude provider parser tests

**What:** Test all 7 parse methods and 2 command builders on `ClaudeProvider`.
**Where:** `tests/test_providers_claude.py`.
**How:** Each method gets positive and negative cases. Use `pytest.mark.parametrize` for multi-case methods. Example structure:

```python
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
        assert total == 1800  # 1000 + 500 + 200 + 100
        assert window == 200000

    def test_returns_none_for_non_result(self, cp):
        assert cp.parse_context_usage({"type": "assistant"}) is None


# -- is_result_event --

class TestIsResultEvent:
    def test_extracts_result_text(self, cp):
        event = {"type": "result", "result": "Done."}
        assert cp.is_result_event(event) == "Done."

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
```

**Why:** These parsers are the primary integration surface with external CLIs. A format change in Claude CLI output is the most likely regression source.

#### Step 2.2 — Gemini provider parser tests

**What:** Test all parse methods, command builders, and `get_env` on `GeminiProvider`.
**Where:** `tests/test_providers_gemini.py`.
**How:** Same pattern as Claude tests. Key differences to test:

```python
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
        # Gemini messages also carry session fields — must ignore them
        event = {"type": "message", "role": "assistant", "session_id": "ignore-me"}
        assert gp.parse_init_event(event) is None

    def test_accepts_sessionId_variant(self, gp):
        event = {"type": "init", "sessionId": "gem-456"}
        assert gp.parse_init_event(event) == "gem-456"


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


# -- parse_thinking_event --

class TestParseThinkingEvent:
    def test_extracts_thinking(self, gp):
        event = {"type": "message", "role": "assistant",
                 "thinking": "Analyzing the code..."}
        assert gp.parse_thinking_event(event) == "Analyzing the code..."

    def test_returns_none_without_thinking(self, gp):
        event = {"type": "message", "role": "assistant", "content": "Done"}
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

    def test_returns_none_for_wrong_type(self, gp):
        assert gp.parse_tool_result_event({"type": "message"}) is None


# -- parse_context_usage --

class TestParseContextUsage:
    def test_extracts_stats(self, gp):
        event = {"type": "result", "stats": {"total_tokens": 5000}}
        total, window = gp.parse_context_usage(event)
        assert total == 5000
        assert window == 1_000_000  # Hard-coded Gemini context window

    def test_returns_none_for_zero_tokens(self, gp):
        event = {"type": "result", "stats": {"total_tokens": 0}}
        assert gp.parse_context_usage(event) is None


# -- is_result_event --

class TestIsResultEvent:
    def test_extracts_result(self, gp):
        event = {"type": "result", "response": "All done."}
        assert gp.is_result_event(event) == "All done."

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
```

**Why:** Gemini event format differs from Claude — separate tests ensure both providers parse correctly.

#### Step 2.3 — Provider base class and registry tests

**What:** Test `CLIProvider._get_base_cmd`, `command_override`, and `get_provider_by_name`.
**Where:** `tests/test_providers_base.py`.
**How:**
```python
"""Tests for provider base class and registry."""

from unittest.mock import patch
from voicecode.providers.base import CLIProvider
from voicecode.providers.claude import ClaudeProvider
from voicecode.providers import get_provider_by_name


class TestGetBaseCmd:
    def test_default_binary(self):
        p = ClaudeProvider()
        assert p._get_base_cmd() == ["claude"]

    def test_command_override(self):
        p = ClaudeProvider()
        p.command_override = "/usr/local/bin/claude --model opus"
        assert p._get_base_cmd() == ["/usr/local/bin/claude", "--model", "opus"]


class TestIsInstalled:
    def test_found(self):
        p = ClaudeProvider()
        with patch("shutil.which", return_value="/usr/bin/claude"):
            assert p.is_installed() is True

    def test_not_found(self):
        p = ClaudeProvider()
        with patch("shutil.which", return_value=None):
            assert p.is_installed() is False


class TestGetProviderByName:
    def test_case_insensitive_lookup(self):
        assert get_provider_by_name("claude") is not None
        assert get_provider_by_name("Claude") is not None
        assert get_provider_by_name("CLAUDE") is not None

    def test_unknown_returns_none(self):
        assert get_provider_by_name("openai") is None
```

---

### Phase 3: Settings & Utility Tests

#### Step 3.1 — Pure settings functions

**What:** Test `slug_from_text` and `next_seq`.
**Where:** `tests/test_settings.py`.
**How:**

```python
"""Tests for settings utility functions."""

import pytest
from pathlib import Path
from voicecode.settings import slug_from_text, next_seq


class TestSlugFromText:
    def test_simple_text(self):
        assert slug_from_text("Write a Docker compose file") == "write_a_docker_compose"

    def test_skips_markdown_headings(self):
        assert slug_from_text("# Title\nActual prompt here") == "actual_prompt_here"

    def test_strips_special_chars(self):
        assert slug_from_text("Hello, world! How's it?") == "hello_world_hows_it"

    def test_respects_max_words(self):
        assert slug_from_text("one two three four five six", max_words=3) == "one_two_three"

    def test_empty_text(self):
        assert slug_from_text("") == "prompt"

    def test_only_headings(self):
        # All lines are comments — falls through to else branch
        result = slug_from_text("# heading\n# another")
        assert result != ""

    def test_whitespace_only(self):
        assert slug_from_text("   \n   ") == "prompt"

    def test_unicode_stripped(self):
        assert slug_from_text("café résumé") == "caf_rsum"


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
```

#### Step 3.2 — Settings I/O functions

**What:** Test `load_settings`, `save_settings`, `load_shortcuts`, `save_shortcuts`, `persist_setting` using temp directories.
**Where:** `tests/test_settings_io.py`.
**How:** Patch `SETTINGS_DIR` and `SETTINGS_FILE` to point at `tmp_path`:

```python
"""Tests for settings I/O (load/save with filesystem)."""

import json
from unittest.mock import patch
from voicecode.settings import load_settings, save_settings, load_shortcuts, save_shortcuts, persist_setting


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
            assert load_shortcuts() == ["shortcut one", "shortcut two"]


class TestPersistSetting:
    def test_updates_single_key(self, tmp_path):
        f = tmp_path / "settings.json"
        f.write_text('{"existing": true}')
        with patch("voicecode.settings.SETTINGS_DIR", tmp_path), \
             patch("voicecode.settings.SETTINGS_FILE", f):
            persist_setting("new_key", 42)
        data = json.loads(f.read_text())
        assert data == {"existing": True, "new_key": 42}
```

---

### Phase 4: TTS & Publish Tests

#### Step 4.1 — TTS summary extraction

**What:** Test `extract_tts_summary` (pure regex function).
**Where:** `tests/test_tts.py`.
**How:**

```python
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
```

#### Step 4.2 — Publish agent tests

**What:** Test `PublishAgent.prompt_path`, `build_prompt`, and subclass overrides.
**Where:** `tests/test_publish.py`.
**How:**

```python
"""Tests for publish agent prompt building."""

import pytest
from unittest.mock import patch, PropertyMock
from voicecode.publish.base import PublishAgent, PROMPTS_DIR
from voicecode.publish.arch import ArchAgent
from voicecode.publish.spec import SpecAgent
from voicecode.publish.plan import PlanAgent
from voicecode.publish.constraints import ConstraintsAgent
from voicecode.publish.glossary import GlossaryAgent


class TestPublishAgentPromptPath:
    @pytest.mark.parametrize("agent_cls,expected_name", [
        (ArchAgent, "ARCH.md"),
        (SpecAgent, "SPEC.md"),
        (PlanAgent, "PLAN.md"),
    ])
    def test_prompt_path_matches_doc_type(self, agent_cls, expected_name):
        agent = agent_cls()
        assert agent.prompt_path == PROMPTS_DIR / expected_name


class TestBuildPrompt:
    def test_formats_scope_and_dest(self):
        agent = ArchAgent()
        template = "Scope: {scope}\nDest: {dest_folder}"
        with patch.object(type(agent), "prompt_template",
                          new_callable=PropertyMock, return_value=template):
            result = agent.build_prompt("my scope", "docs/arch/")
        assert "my scope" in result
        assert "docs/arch/" in result

    def test_constraints_overrides_dest(self):
        agent = ConstraintsAgent()
        template = "Scope: {scope}\nDest: {dest_folder}"
        with patch.object(type(agent), "prompt_template",
                          new_callable=PropertyMock, return_value=template):
            result = agent.build_prompt("my scope", "ignored/")
        assert "context/" in result
        assert "ignored/" not in result
```

---

### Phase 5: TextPane Logic Tests

#### Step 5.1 — TextPane state management (no curses)

**What:** Test `TextPane` wrapping, scrolling, trimming — everything except `draw()`.
**Where:** `tests/test_panes.py`.
**How:** Instantiate `TextPane` directly (it only imports `curses` for `draw()`, and the constructor doesn't call curses):

```python
"""Tests for TextPane state logic (no curses dependency except draw)."""

from voicecode.ui.panes import TextPane


@pytest.fixture
def pane():
    return TextPane("Test", color_pair=1)


class TestSetText:
    def test_basic_text(self, pane):
        pane.set_text("Hello world", width=80)
        assert pane.lines == ["Hello world"]

    def test_wraps_long_lines(self, pane):
        pane.set_text("a " * 50, width=20)
        assert all(len(line) <= 18 for line in pane.lines)  # width - 2

    def test_preserves_blank_lines(self, pane):
        pane.set_text("Line one\n\nLine three", width=80)
        assert pane.lines[1] == ""


class TestAddCharToLastLine:
    def test_appends_character(self, pane):
        pane.add_char_to_last_line("H", width=80)
        pane.add_char_to_last_line("i", width=80)
        assert pane.lines == ["Hi"]

    def test_newline_starts_new_line(self, pane):
        pane.add_char_to_last_line("A", width=80)
        pane.add_char_to_last_line("\n", width=80)
        pane.add_char_to_last_line("B", width=80)
        assert pane.lines == ["A", "B"]

    def test_wraps_at_width(self, pane):
        # width=5, so content width is 5-3=2 chars before wrap
        for ch in "ABCDE":
            pane.add_char_to_last_line(ch, width=5)
        assert len(pane.lines) > 1


class TestTrimLines:
    def test_trims_at_max(self, pane):
        pane.lines = [f"line {i}" for i in range(TextPane.MAX_LINES + 100)]
        pane._trim_lines()
        assert len(pane.lines) == TextPane.MAX_LINES

    def test_adjusts_scroll_offset(self, pane):
        pane.lines = [f"line {i}" for i in range(TextPane.MAX_LINES + 50)]
        pane.scroll_offset = 100
        pane._trim_lines()
        assert pane.scroll_offset == 50  # shifted by overflow (100 - 50)

    def test_shifts_line_colors(self, pane):
        pane.lines = ["x"] * (TextPane.MAX_LINES + 10)
        pane.line_colors = {5: 2, TextPane.MAX_LINES + 5: 3}
        pane._trim_lines()
        # line 5 was trimmed away; MAX_LINES+5 shifted to MAX_LINES+5-10
        assert 5 not in pane.line_colors


class TestScrolling:
    def test_scroll_up_disables_auto(self, pane):
        pane.auto_scroll = True
        pane.scroll_offset = 5
        pane.scroll_up()
        assert pane.scroll_offset == 4
        assert pane.auto_scroll is False

    def test_scroll_down_reenables_auto_at_bottom(self, pane):
        pane.lines = ["x"] * 20
        pane.auto_scroll = False
        pane.scroll_offset = 9
        pane.scroll_down(visible_height=10, amount=1)
        assert pane.auto_scroll is True

    def test_scroll_to_bottom(self, pane):
        pane.lines = ["x"] * 30
        pane.scroll_to_bottom(visible_height=10)
        assert pane.scroll_offset == 20
        assert pane.auto_scroll is True

    def test_is_scrollable(self, pane):
        pane.lines = ["x"] * 5
        pane._last_height = 10
        assert pane.is_scrollable is False
        pane.lines = ["x"] * 15
        assert pane.is_scrollable is True
```

**Why:** TextPane is used for all three panes (prompt, dictation, agent). Wrapping and trimming bugs affect the core display.

---

### Phase 6: Agent Refine Tests

#### Step 6.1 — Refine prompt loading and subprocess mocking

**What:** Test `_load_refine_prompts` and `refine_with_llm` with mocked subprocess.
**Where:** `tests/test_agent_refine.py`.
**How:**

```python
"""Tests for agent prompt refinement."""

from unittest.mock import patch, MagicMock
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


class TestRefineWithLlm:
    def test_success(self, tmp_path):
        template = tmp_path / "REFINE.md"
        template.write_text("Refine these: {fragments}")
        provider = ClaudeProvider()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Refined prompt text"
        with patch("voicecode.agent.refine.REFINE_PROMPT_PATH", template), \
             patch("subprocess.run", return_value=mock_result):
            result = refine_with_llm(["fragment one"], None, provider=provider)
        assert result == "Refined prompt text"

    def test_cli_not_found(self, tmp_path):
        template = tmp_path / "REFINE.md"
        template.write_text("Refine: {fragments}")
        provider = ClaudeProvider()
        with patch("voicecode.agent.refine.REFINE_PROMPT_PATH", template), \
             patch("subprocess.run", side_effect=FileNotFoundError):
            result = refine_with_llm(["frag"], None, provider=provider)
        assert "[Error:" in result
        assert "not found" in result

    def test_timeout(self, tmp_path):
        import subprocess
        template = tmp_path / "REFINE.md"
        template.write_text("Refine: {fragments}")
        provider = ClaudeProvider()
        with patch("voicecode.agent.refine.REFINE_PROMPT_PATH", template), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 120)):
            result = refine_with_llm(["frag"], None, provider=provider)
        assert "timed out" in result
```

---

## 4. Data Model / Schema Changes

No new data models, classes, enums, or configuration fields are introduced. The test suite only adds:

- `requirements-dev.txt` — new file (test dependency declaration)
- `pytest.ini` — new file (test runner configuration)
- `tests/` — new directory tree (test code only)

No changes to existing schemas, settings format, or module interfaces.

## 5. Integration Points

### Makefile

The only integration with the existing system is the `make test` target added to `Makefile`. This follows the existing `make voicecode` pattern — activate the virtualenv, run a command. The test target uses `python -m pytest -q` for quiet output by default.

### CI (future)

The test suite is designed to run without audio hardware, curses terminals, or CLI installations. This means it can run in CI environments (GitHub Actions, etc.) with only `pip install -r requirements-dev.txt` as setup. No additional integration work is needed for Phase 1-6 tests.

### No UI changes

No overlays, keyboard shortcuts, or display changes.

## 6. Edge Cases & Risks

### Import side effects

`voicecode/tts/engine.py` imports `numpy`, `sounddevice` (via `safe_sd_play`), and `piper-tts` (via `voices.py`) at module level. On machines without audio hardware or these packages, importing the module may fail.

**Mitigation:** The `test_tts.py` file only tests `extract_tts_summary`, which is a pure regex function. If imports fail, isolate the function or add a `pytest.importorskip` guard. Alternatively, ensure the test virtualenv has the runtime requirements installed (which it should, since `make init` installs them).

### `constants.py` path resolution

`SETTINGS_DIR` and `SETTINGS_FILE` in `constants.py` are computed at import time relative to the package directory. Tests that exercise settings I/O must patch these constants to point at temp directories, or the real settings file on disk could be modified.

**Mitigation:** All settings I/O tests in Step 3.2 patch `SETTINGS_DIR` and `SETTINGS_FILE` to `tmp_path`.

### Provider singleton state

`providers/__init__.py` creates singleton `_PROVIDERS` at import time. If a test modifies `command_override` on a provider instance, it persists across tests.

**Mitigation:** Tests that modify provider state should restore it in a fixture teardown, or create fresh instances.

### `curses` import in `ui/panes.py`

`TextPane` imports `curses` at the module level (line 3). This import will succeed on Linux terminals but may fail in constrained CI environments.

**Mitigation:** Standard Linux CI runners (Ubuntu) include the `curses` module in Python's stdlib. This is only a risk on Windows CI, which is not a target environment.

### Thread safety

None of the tested functions involve threading. The test suite avoids testing threaded code paths (agent runner loop, TTS playback, audio capture) which eliminates race conditions in tests.

## 7. Verification

### Running the suite

After implementing all phases:

```bash
make test
```

Expected output:
```
..................................................  [100%]
50+ passed in <1s
```

### Per-phase verification

| Phase | Verify with | Expected |
|-------|------------|----------|
| 1 (Infrastructure) | `make test` with an empty `tests/test_smoke.py` containing one trivial test | pytest discovers and runs it |
| 2 (Provider parsers) | `python -m pytest tests/test_providers_claude.py tests/test_providers_gemini.py tests/test_providers_base.py -v` | All pass, ~30 tests |
| 3 (Settings) | `python -m pytest tests/test_settings.py tests/test_settings_io.py -v` | All pass, ~15 tests |
| 4 (TTS & Publish) | `python -m pytest tests/test_tts.py tests/test_publish.py -v` | All pass, ~10 tests |
| 5 (TextPane) | `python -m pytest tests/test_panes.py -v` | All pass, ~12 tests |
| 6 (Refine) | `python -m pytest tests/test_agent_refine.py -v` | All pass, ~5 tests |

### Acceptance criteria

1. `make test` runs all tests and exits 0 with no failures.
2. Tests complete in under 2 seconds (no network, no model loading, no subprocess waits).
3. Tests do not modify any files outside of `tmp_path` fixtures.
4. Tests do not require Claude CLI, Gemini CLI, or audio hardware to be present.
5. Every provider parse method has at least one positive and one negative test case.
6. `slug_from_text` edge cases (empty, headings-only, special chars) are covered.
7. TextPane wrapping and trimming logic has boundary-condition tests.

## 8. Open Questions

### Q1: Should tests install runtime deps or just test deps?

The test suite imports `voicecode` modules, which transitively import `numpy`, `torch`, `sounddevice`, etc. The simplest approach is to run tests inside the existing virtualenv created by `make init`. If a lighter test-only venv is desired (faster CI), some modules would need conditional imports or `pytest.importorskip` guards.

**Recommendation:** Use the existing venv. Add `pytest` to it via `pip install -r requirements-dev.txt` as a post-init step, or add a `make test-init` target.

### Q2: Should we add `pytest-cov` for coverage reporting?

Not in Phase 1. Coverage is useful once the test suite is established and the team wants to track progress. It can be added later by appending `pytest-cov` to `requirements-dev.txt` and adding `--cov=voicecode --cov-report=term-missing` to the pytest invocation.

### Q3: TextPane `import curses` — will it break in CI?

On standard Ubuntu CI runners, `curses` is part of the Python stdlib and imports fine even without a terminal. The `draw()` method would fail (no `stdscr`), but we don't test `draw()`. If this becomes an issue, the import can be made conditional in `panes.py` or the test can mock it.

**Recommendation:** Try it as-is first. Only fix if it actually fails in CI.
