"""Glossary document publishing agent."""

from voicecode.publish.base import PublishAgent


class GlossaryAgent(PublishAgent):
    doc_type = "GLOSSARY"

    # Fixed output path — the glossary is always docs/context/GLOSSARY.md
    FIXED_DEST_FOLDER = "context/"

    def build_prompt(self, scope: str, dest_folder: str) -> str:
        """Build the glossary prompt, always targeting context/GLOSSARY.md."""
        return self.prompt_template.format(
            scope=scope,
            dest_folder=self.FIXED_DEST_FOLDER,
        )
