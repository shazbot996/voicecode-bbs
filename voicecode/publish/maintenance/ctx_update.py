"""Update maintenance agent — regenerates root context files from codebase."""

from voicecode.publish.maintenance.base import MaintenanceAgent


class CtxUpdateAgent(MaintenanceAgent):
    action_name = "CTX_UPDATE"
    description = "Update — regenerate from codebase"

    @property
    def applicable_types(self) -> list[str]:
        return ["root-context"]
