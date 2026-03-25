"""Drift Check maintenance agent — checks root context files against codebase."""

from voicecode.publish.maintenance.base import MaintenanceAgent


class CtxDriftAgent(MaintenanceAgent):
    action_name = "CTX_DRIFT"
    description = "Drift check — find stale sections"

    @property
    def applicable_types(self) -> list[str]:
        return ["root-context"]
