"""Base class for publishing agents."""


class PublishAgent:
    """Base class for all document-publishing agents.

    Each subclass defines a system prompt template that receives:
      - scope: the user's prompt describing what to focus on
        (e.g. "the voicecode/ui/ folder", "the whole repo", "the API layer")
      - dest_folder: the destination folder within docs/
        (e.g. "context/", "decisions/")

    The agent builds a full prompt string that gets sent through the
    normal agent execution pipeline (provider → CLI → streaming output).
    """

    # Subclasses must set this
    doc_type: str = ""
    prompt_template: str = ""

    def build_prompt(self, scope: str, dest_folder: str) -> str:
        """Build the full agent prompt from user scope and destination."""
        return self.prompt_template.format(
            scope=scope,
            dest_folder=dest_folder,
        )
