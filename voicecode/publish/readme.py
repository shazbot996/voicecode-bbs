"""README document publishing agent."""

from voicecode.publish.base import PublishAgent


class ReadmeAgent(PublishAgent):
    doc_type = "README"

    # Fixed output path — the README always lives at the project root
    FIXED_DEST_FOLDER = ""

    def build_prompt(self, scope: str, dest_folder: str) -> str:
        """Build the README prompt, always targeting the project root."""
        return self.prompt_template.format(
            scope=scope,
            dest_folder=self.FIXED_DEST_FOLDER,
        )
