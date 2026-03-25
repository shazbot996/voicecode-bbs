"""Maintenance agent registry."""

_MAINT_REGISTRY: dict = {}


def _init_registry():
    from voicecode.publish.maintenance.reconcile import ReconcileAgent
    from voicecode.publish.maintenance.refresh import RefreshAgent
    from voicecode.publish.maintenance.coverage import CoverageAgent
    from voicecode.publish.maintenance.ctx_update import CtxUpdateAgent
    from voicecode.publish.maintenance.ctx_drift import CtxDriftAgent
    _MAINT_REGISTRY["RECONCILE"] = ReconcileAgent()
    _MAINT_REGISTRY["REFRESH"] = RefreshAgent()
    _MAINT_REGISTRY["COVERAGE"] = CoverageAgent()
    _MAINT_REGISTRY["CTX_UPDATE"] = CtxUpdateAgent()
    _MAINT_REGISTRY["CTX_DRIFT"] = CtxDriftAgent()


def get_maintenance_agent(action_name: str):
    if not _MAINT_REGISTRY:
        _init_registry()
    return _MAINT_REGISTRY.get(action_name)


def get_available_actions(doc_type: str) -> list[tuple[str, str]]:
    """Return (action_name, description) pairs applicable to doc_type."""
    if not _MAINT_REGISTRY:
        _init_registry()
    result = []
    dt_lower = doc_type.lower()
    for name, agent in _MAINT_REGISTRY.items():
        # Check exclusions first
        if dt_lower in [t.lower() for t in agent.excluded_types]:
            continue
        types = agent.applicable_types
        if not types or dt_lower in [t.lower() for t in types]:
            result.append((name, agent.description))
    return result
