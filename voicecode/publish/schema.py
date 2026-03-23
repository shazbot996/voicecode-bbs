"""Schema document publishing agent."""

from voicecode.publish.base import PublishAgent


class SchemaAgent(PublishAgent):
    doc_type = "SCHEMA"

    # Fixed output path — schema always lives at docs/context/SCHEMA.md
    FIXED_DEST_FOLDER = "context/"

    def build_prompt(self, scope: str, dest_folder: str) -> str:
        """Build the schema prompt, always targeting context/SCHEMA.md."""
        return self.prompt_template.format(
            scope=scope,
            dest_folder=self.FIXED_DEST_FOLDER,
        )
