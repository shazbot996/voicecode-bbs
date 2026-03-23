"""Conventions document publishing agent."""

from voicecode.publish.base import PublishAgent


class ConventionsAgent(PublishAgent):
    doc_type = "CONVENTIONS"

    # Fixed output path — conventions always live at docs/context/CONVENTIONS.md
    FIXED_DEST_FOLDER = "context/"

    def build_prompt(self, scope: str, dest_folder: str) -> str:
        """Build the conventions prompt, always targeting context/CONVENTIONS.md."""
        return self.prompt_template.format(
            scope=scope,
            dest_folder=self.FIXED_DEST_FOLDER,
        )
