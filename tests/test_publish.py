"""Tests for publish agent prompt building."""

import pytest
from unittest.mock import patch, PropertyMock
from voicecode.publish.base import PublishAgent, PROMPTS_DIR
from voicecode.publish.agents import AgentsAgent
from voicecode.publish.arch import ArchAgent
from voicecode.publish.spec import SpecAgent
from voicecode.publish.plan import PlanAgent
from voicecode.publish.constraints import ConstraintsAgent
from voicecode.publish.glossary import GlossaryAgent
from voicecode.publish.conventions import ConventionsAgent
from voicecode.publish.schema import SchemaAgent
from voicecode.publish.readme import ReadmeAgent
from voicecode.ui.publish_overlay import get_publish_agent, IMPLEMENTED_TYPES


class TestPublishAgentPromptPath:
    @pytest.mark.parametrize("agent_cls,expected_name", [
        (AgentsAgent, "AGENTS.md"),
        (ArchAgent, "ARCH.md"),
        (SpecAgent, "SPEC.md"),
        (PlanAgent, "PLAN.md"),
        (ConstraintsAgent, "CONSTRAINTS.md"),
        (GlossaryAgent, "GLOSSARY.md"),
        (ConventionsAgent, "CONVENTIONS.md"),
        (SchemaAgent, "SCHEMA.md"),
        (ReadmeAgent, "README.md"),
    ])
    def test_prompt_path_matches_doc_type(self, agent_cls, expected_name):
        agent = agent_cls()
        assert agent.prompt_path == PROMPTS_DIR / expected_name

    def test_all_agents_have_doc_type(self):
        for cls in [AgentsAgent, ArchAgent, SpecAgent, PlanAgent, ConstraintsAgent,
                    GlossaryAgent, ConventionsAgent, SchemaAgent, ReadmeAgent]:
            assert cls().doc_type != ""


class TestBuildPrompt:
    def test_formats_scope_and_dest(self):
        agent = ArchAgent()
        template = "Scope: {scope}\nDest: {dest_folder}"
        with patch.object(type(agent), "prompt_template",
                          new_callable=PropertyMock, return_value=template):
            result = agent.build_prompt("my scope", "docs/arch/")
        assert "my scope" in result
        assert "docs/arch/" in result

    def test_agents_overrides_dest(self):
        agent = AgentsAgent()
        template = "Scope: {scope}\nDest: {dest_folder}"
        with patch.object(type(agent), "prompt_template",
                          new_callable=PropertyMock, return_value=template):
            result = agent.build_prompt("my scope", "ignored/")
        assert "Scope: my scope" in result
        assert "Dest: " in result
        assert "ignored/" not in result

    def test_readme_overrides_dest(self):
        agent = ReadmeAgent()
        template = "Scope: {scope}\nDest: {dest_folder}"
        with patch.object(type(agent), "prompt_template",
                          new_callable=PropertyMock, return_value=template):
            result = agent.build_prompt("my scope", "ignored/")
        assert "Scope: my scope" in result
        assert "Dest: " in result
        assert "ignored/" not in result

    def test_constraints_overrides_dest(self):
        agent = ConstraintsAgent()
        template = "Scope: {scope}\nDest: {dest_folder}"
        with patch.object(type(agent), "prompt_template",
                          new_callable=PropertyMock, return_value=template):
            result = agent.build_prompt("my scope", "ignored/")
        assert "context/" in result
        assert "ignored/" not in result

    def test_glossary_overrides_dest(self):
        agent = GlossaryAgent()
        template = "Scope: {scope}\nDest: {dest_folder}"
        with patch.object(type(agent), "prompt_template",
                          new_callable=PropertyMock, return_value=template):
            result = agent.build_prompt("my scope", "ignored/")
        assert "context/" in result

    def test_agents_prompt_template_loads(self):
        agent = AgentsAgent()
        content = agent.prompt_template
        assert "{scope}" in content
        assert "AGENTS.md" in content
        assert "CLAUDE.md" in content

    def test_get_publish_agent_registry(self):
        for doc_type in IMPLEMENTED_TYPES:
            agent = get_publish_agent(doc_type)
            assert agent is not None
            assert agent.doc_type == doc_type
