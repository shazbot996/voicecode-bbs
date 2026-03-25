"""Maintenance agent registry."""

_MAINT_REGISTRY: dict = {}


def _init_registry():
    from voicecode.publish.maintenance.reconcile import ReconcileAgent
    from voicecode.publish.maintenance.refresh import RefreshAgent
    from voicecode.publish.maintenance.coverage import CoverageAgent
    _MAINT_REGISTRY["RECONCILE"] = ReconcileAgent()
    _MAINT_REGISTRY["REFRESH"] = RefreshAgent()
    _MAINT_REGISTRY["COVERAGE"] = CoverageAgent()


def get_maintenance_agent(action_name: str):
    if not _MAINT_REGISTRY:
        _init_registry()
    return _MAINT_REGISTRY.get(action_name)


def get_available_actions(doc_type: str) -> list[tuple[str, str]]:
    """Return (action_name, description) pairs applicable to doc_type."""
    if not _MAINT_REGISTRY:
        _init_registry()
    result = []
    for name, agent in _MAINT_REGISTRY.items():
        types = agent.applicable_types
        if not types or doc_type.lower() in [t.lower() for t in types]:
            result.append((name, agent.description))
    return result
