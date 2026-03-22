"""Feature spec publishing agent."""

from voicecode.publish.base import PublishAgent


class SpecAgent(PublishAgent):
    doc_type = "SPEC"
