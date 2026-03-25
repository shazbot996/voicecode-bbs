"""Reconcile maintenance agent — checks document drift against codebase."""

from voicecode.publish.maintenance.base import MaintenanceAgent


class ReconcileAgent(MaintenanceAgent):
    action_name = "RECONCILE"
    description = "Reconcile — check drift"
