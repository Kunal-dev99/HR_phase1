"""Audit event types emitted by the requisitions module (D-12)."""

from __future__ import annotations

SCREENING_RUN_CREATED = "ScreeningRunCreated"
RUN_STATUS_CHANGED = "RunStatusChanged"
REQUISITION_FETCHED = "RequisitionFetched"
REQUISITION_SNAPSHOT_CAPTURED = "RequisitionSnapshotCaptured"

__all__ = [
    "REQUISITION_FETCHED",
    "REQUISITION_SNAPSHOT_CAPTURED",
    "RUN_STATUS_CHANGED",
    "SCREENING_RUN_CREATED",
]
