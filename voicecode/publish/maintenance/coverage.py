"""Coverage Check maintenance agent — finds gaps in document coverage."""

from voicecode.publish.maintenance.base import MaintenanceAgent


class CoverageAgent(MaintenanceAgent):
    action_name = "COVERAGE"
    description = "Coverage — find gaps"

    @property
    def applicable_types(self) -> list[str]:
        return ["glossary", "schema", "constraints", "conventions", "arch"]

    @property
    def excluded_types(self) -> list[str]:
        return ["root-context"]
