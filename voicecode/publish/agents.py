"""AGENTS root context document publishing agent."""

from voicecode.publish.base import PublishAgent


class AgentsAgent(PublishAgent):
    doc_type = "AGENTS"

    # Fixed output path — AGENTS.md always lives at the project root
    FIXED_DEST_FOLDER = ""

    def build_prompt(self, scope: str, dest_folder: str) -> str:
        """Build the AGENTS context prompt, always targeting the project root."""
        return self.prompt_template.format(
            scope=scope,
            dest_folder=self.FIXED_DEST_FOLDER,
        )
