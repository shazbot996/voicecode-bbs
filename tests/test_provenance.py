"""Tests for prompt-artifact provenance and lineage tracking."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from voicecode.publish.frontmatter import (
    extract_prompt_metadata,
    strip_prompt_metadata,
    strip_frontmatter,
    parse_frontmatter,
)
from voicecode.agent.execution import ExecutionHelper
from voicecode.agent.runner import RunnerHelper
from voicecode.history.browser import BrowserHelper


def test_extract_prompt_metadata_comments():
    text = (
        "# Prompt Version: 1\n"
        "# Executed: 2026-09-08 14:00:00\n"
        "# Artifacts: docs/specs/auth-SPEC.md, docs/plans/auth-PLAN.md\n\n"
        "Create an auth specification for OAuth2 login.\n"
    )
    meta = extract_prompt_metadata(text)
    assert meta["version"] == "1"
    assert meta["executed"] == "2026-09-08 14:00:00"
    assert meta["artifacts"] == ["docs/specs/auth-SPEC.md", "docs/plans/auth-PLAN.md"]


def test_extract_prompt_metadata_frontmatter():
    text = (
        "---\n"
        "type: spec\n"
        "prompt: 042_auth_spec_prompt.md\n"
        "artifacts:\n"
        "  - docs/specs/auth-SPEC.md\n"
        "  - docs/plans/auth-PLAN.md\n"
        "---\n\n"
        "# Auth Spec Title\nContent here.\n"
    )
    meta = extract_prompt_metadata(text)
    assert meta["type"] == "spec"
    assert meta["prompt"] == "042_auth_spec_prompt.md"
    assert meta["artifacts"] == ["docs/specs/auth-SPEC.md", "docs/plans/auth-PLAN.md"]


def test_strip_prompt_metadata():
    text = (
        "# Prompt Version: 2\n"
        "# Artifacts: docs/specs/auth-SPEC.md\n\n"
        "---\n"
        "type: spec\n"
        "---\n\n"
        "Refined prompt body here.\n"
    )
    clean = strip_prompt_metadata(text)
    assert clean == "Refined prompt body here."


def test_strip_frontmatter():
    text = (
        "---\n"
        "type: architecture\n"
        "title: System Architecture\n"
        "---\n\n"
        "# System Architecture\n\nMain content."
    )
    assert strip_frontmatter(text) == "# System Architecture\n\nMain content."


def test_save_to_history_and_record_prompt_artifacts(tmp_path):
    mock_app = MagicMock()
    mock_app.history_base = tmp_path
    mock_app.prompt_version = 1
    mock_app.history_prompts = []

    exec_helper = ExecutionHelper(mock_app)

    # 1. Save prompt
    prompt_file = exec_helper.save_to_history("Write a spec for database sharding.")
    assert prompt_file is not None
    assert prompt_file.exists()
    content = prompt_file.read_text()
    assert "Write a spec for database sharding." in content
    assert "# Executed:" in content

    # 2. Record artifacts after run
    artifacts = ["docs/specs/sharding-SPEC.md", "docs/schema/sharding-SCHEMA.md"]
    updated_file = exec_helper.record_prompt_artifacts(prompt_file, artifacts)
    assert updated_file is not None
    updated_content = updated_file.read_text()
    assert "# Artifacts: docs/specs/sharding-SPEC.md, docs/schema/sharding-SCHEMA.md" in updated_content

    # 3. Save response with artifacts
    resp_file = exec_helper.save_response_to_history("Successfully created spec.", artifacts=artifacts)
    assert resp_file is not None
    resp_content = resp_file.read_text()
    assert "# Artifacts: docs/specs/sharding-SPEC.md, docs/schema/sharding-SCHEMA.md" in resp_content
    assert "Successfully created spec." in resp_content


def test_runner_normalize_artifact_path(tmp_path):
    mock_app = MagicMock()
    mock_app.working_dir = str(tmp_path)
    mock_app.ai_provider.resolved_workspace_dir.return_value = str(tmp_path)
    runner = RunnerHelper(mock_app)

    abs_target = str(tmp_path / "docs" / "specs" / "test-SPEC.md")
    norm = runner._normalize_artifact_path(abs_target)
    assert norm == os.path.join("docs", "specs", "test-SPEC.md")

    rel_target = "docs/specs/test-SPEC.md"
    assert runner._normalize_artifact_path(rel_target) == rel_target


def test_browser_extract_artifacts_and_load(tmp_path):
    mock_app = MagicMock()
    mock_app.history_base = tmp_path
    mock_app.browser_view = "active"
    mock_app.browser_index = 0
    mock_app._doc_prompt_cache = {"docs/specs/linked-SPEC.md": "001_test_prompt.md"}
    mock_app._doc_type_cache = {"docs/specs/test-SPEC.md": "spec", "docs/specs/linked-SPEC.md": "spec"}
    mock_app.prompt_pane = MagicMock()

    prompt_path = tmp_path / "001_test_prompt.md"
    prompt_path.write_text(
        "# Prompt Version: 1\n"
        "# Artifacts: docs/specs/test-SPEC.md\n\n"
        "Generate a spec document."
    )
    response_path = tmp_path / "001_test_response.md"
    response_path.write_text("Spec has been generated.")

    mock_app.history_prompts = [prompt_path]
    browser = BrowserHelper(mock_app)

    # Test artifact extraction
    arts = browser.extract_prompt_artifacts(prompt_path)
    assert "docs/specs/test-SPEC.md" in arts
    assert "docs/specs/linked-SPEC.md" in arts

    # Test loading browser prompt
    browser.load_browser_prompt(width=80)
    assert "2 artifacts" in mock_app.prompt_pane.title
    set_text_call = mock_app.prompt_pane.set_text.call_args[0][0]
    assert "ARTIFACTS / GENERATED FILES (2)" in set_text_call
    assert "▸ docs/specs/test-SPEC.md  [SPEC]" in set_text_call
    assert "▸ docs/specs/linked-SPEC.md  [SPEC]" in set_text_call


def test_browser_get_active_prompt_text_strips_metadata(tmp_path):
    mock_app = MagicMock()
    mock_app.history_base = tmp_path
    mock_app.browser_view = "active"
    mock_app.browser_index = 0

    prompt_path = tmp_path / "001_test_prompt.md"
    prompt_path.write_text(
        "# Executed: 2026-09-08 14:00:00\n"
        "# Artifacts: docs/specs/test-SPEC.md\n\n"
        "---\n"
        "type: spec\n"
        "---\n\n"
        "Active prompt body."
    )
    mock_app.history_prompts = [prompt_path]
    browser = BrowserHelper(mock_app)

    active_text = browser.get_active_prompt_text()
    assert active_text == "Active prompt body."


def test_scan_folder_slugs_builds_doc_prompt_cache(tmp_path):
    from voicecode.ui.overlays import OverlayRenderer

    docs_dir = tmp_path / "docs" / "specs"
    docs_dir.mkdir(parents=True)
    spec_doc = docs_dir / "auth-SPEC.md"
    spec_doc.write_text(
        "---\n"
        "type: spec\n"
        "prompt: 005_auth_flow_prompt.md\n"
        "---\n\n"
        "# Auth Spec Content"
    )

    history_dir = tmp_path / "history"
    history_dir.mkdir(parents=True)
    history_prompt = history_dir / "005_auth_flow_prompt.md"
    history_prompt.write_text(
        "# Executed: 2026-09-08 15:00:00\n"
        "# Artifacts: docs/specs/auth-SPEC.md\n\n"
        "Prompt body"
    )

    mock_app = MagicMock()
    mock_app.working_dir = str(tmp_path)
    mock_app.docs_folder = str(tmp_path / "docs")
    mock_app.history_base = history_dir
    mock_app.history_prompts = [history_prompt]
    mock_app.tools_data = []

    overlays = OverlayRenderer(mock_app)
    overlays.scan_folder_slugs()

    assert "docs/specs/auth-SPEC.md" in mock_app._doc_prompt_cache
    assert mock_app._doc_prompt_cache["docs/specs/auth-SPEC.md"] == "005_auth_flow_prompt.md"
    assert mock_app._doc_type_cache["docs/specs/auth-SPEC.md"] == "spec"


def test_open_doc_actions_includes_origin_prompt(tmp_path):
    from voicecode.ui.input import InputHandler

    mock_app = MagicMock()
    mock_app._doc_type_cache = {"docs/specs/auth-SPEC.md": "spec"}
    mock_app._doc_prompt_cache = {"docs/specs/auth-SPEC.md": "005_auth_flow_prompt.md"}

    inp = InputHandler(mock_app)
    inp._open_doc_actions(str(tmp_path / "docs" / "specs" / "auth-SPEC.md"), "docs/specs/auth-SPEC.md")

    action_ids = [action[0] for action in mock_app.doc_actions_list]
    assert "VIEW" in action_ids
    assert "RECONCILE" in action_ids
    assert "REFRESH" in action_ids
    assert "ORIGIN_PROMPT" in action_ids
    origin_action = next(a for a in mock_app.doc_actions_list if a[0] == "ORIGIN_PROMPT")
    assert "005_auth_flow_prompt.md" in origin_action[1]

