"""Refresh maintenance agent — updates document to match current code."""

from voicecode.publish.maintenance.base import MaintenanceAgent


class RefreshAgent(MaintenanceAgent):
    action_name = "REFRESH"
    description = "Refresh — update in-place"
