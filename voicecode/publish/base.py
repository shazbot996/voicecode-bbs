"""Base class for publishing agents."""

from pathlib import Path

# Directory containing prompt template files (one per agent)
PROMPTS_DIR = Path(__file__).parent / "prompts"


class PublishAgent:
    """Base class for all document-publishing agents.

    Each subclass sets ``doc_type`` (e.g. "ARCH").  The prompt template is
    loaded at runtime from ``prompts/<DOC_TYPE>.md`` so it can be edited
    both on disk and through the in-app editor.

    Templates receive two format placeholders:
      - {scope}       — the user's prompt describing what to focus on
      - {dest_folder} — the destination folder within docs/
    """

    # Subclasses must set this
    doc_type: str = ""

    @property
    def prompt_path(self) -> Path:
        """Return the path to this agent's prompt template file."""
        return PROMPTS_DIR / f"{self.doc_type}.md"

    @property
    def prompt_template(self) -> str:
        """Load the prompt template from disk each time it is needed."""
        return self.prompt_path.read_text(encoding="utf-8")

    def build_prompt(self, scope: str, dest_folder: str) -> str:
        """Build the full agent prompt from user scope and destination."""
        return self.prompt_template.format(
            scope=scope,
            dest_folder=dest_folder,
        )
