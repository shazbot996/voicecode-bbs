"""Architecture Decision Record publishing agent."""

from voicecode.publish.base import PublishAgent


class AdrAgent(PublishAgent):
    doc_type = "ADR"
