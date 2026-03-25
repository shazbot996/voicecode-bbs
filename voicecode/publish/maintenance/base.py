"""Base class for document maintenance agents."""

from pathlib import Path

MAINT_PROMPTS_DIR = Path(__file__).parent / "prompts"


class MaintenanceAgent:
    """Base class for maintenance actions on published documents.

    Each subclass sets ``action_name`` (e.g. "RECONCILE").  The prompt
    template is loaded at runtime from ``prompts/<ACTION_NAME>.md``.

    Templates receive three placeholders:
      - {doc_path}    — path to the document being maintained
      - {doc_content} — full text of the document
      - {doc_type}    — the document's front matter type value
    """

    action_name: str = ""
    description: str = ""  # Short label shown in overlay

    @property
    def prompt_path(self) -> Path:
        return MAINT_PROMPTS_DIR / f"{self.action_name}.md"

    @property
    def prompt_template(self) -> str:
        return self.prompt_path.read_text(encoding="utf-8")

    def build_prompt(self, doc_path: str, doc_content: str, doc_type: str) -> str:
        return self.prompt_template.format(
            doc_path=doc_path,
            doc_content=doc_content,
            doc_type=doc_type,
        )

    @property
    def applicable_types(self) -> list[str]:
        """Document types this action applies to. Empty list = all types."""
        return []

    @property
    def excluded_types(self) -> list[str]:
        """Document types this action should never apply to."""
        return []
