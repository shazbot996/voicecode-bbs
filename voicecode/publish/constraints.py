"""Constraints document publishing agent."""

from voicecode.publish.base import PublishAgent


class ConstraintsAgent(PublishAgent):
    doc_type = "CONSTRAINTS"

    # Fixed output path — constraints always live at docs/context/CONSTRAINTS.md
    FIXED_DEST_FOLDER = "context/"

    def build_prompt(self, scope: str, dest_folder: str) -> str:
        """Build the constraints prompt, always targeting context/CONSTRAINTS.md."""
        return self.prompt_template.format(
            scope=scope,
            dest_folder=self.FIXED_DEST_FOLDER,
        )
