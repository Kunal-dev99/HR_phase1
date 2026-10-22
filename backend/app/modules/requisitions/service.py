"""Requisitions services: snapshots, eligibility, run creation and ingestion.

Services hold the business rules and orchestration. They reach the database only through
repositories, and the HR System only through ``integrations`` services.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integrations.schemas import HRRequisitionPayload
from app.modules.requisitions import constants as c
from app.modules.requisitions.constants import CompletionReason
from app.modules.requisitions.repository import (
    DbSnapshotStore,
    SnapshotRepository,
    SnapshotStore,
    compute_payload_hash,
)
from app.modules.requisitions.schemas import EligibilityResult, SnapshotCapture, SnapshotRead

# --- Snapshots (BE-1.5, D-05) -------------------------------------------------------------


class SnapshotService:
    def __init__(self, snapshots: SnapshotRepository, store: SnapshotStore) -> None:
        self._snapshots = snapshots
        self._store = store

    @classmethod
    def for_session(cls, session: AsyncSession) -> SnapshotService:
        return cls(SnapshotRepository(session), DbSnapshotStore(session))

    async def capture(
        self,
        *,
        requisition_id: uuid.UUID,
        payload: dict[str, Any],
        external_version: str | None,
    ) -> SnapshotCapture:
        """Pin ``payload`` as a snapshot, reusing the latest one if the hash is unchanged."""
        payload_hash = compute_payload_hash(payload)
        latest = await self._snapshots.latest_for_requisition(requisition_id)
        if latest is not None and latest.payload_hash == payload_hash:
            return SnapshotCapture(snapshot=SnapshotRead.model_validate(latest), reused=True)

        reference, stored_hash = await self._store.put(payload)
        if stored_hash != payload_hash:  # the store must hash exactly what we hashed
            raise RuntimeError("snapshot store returned an unexpected payload hash")
        snapshot = await self._snapshots.add(
            requisition_id=requisition_id,
            external_version=external_version,
            payload_reference=reference,
            payload_hash=payload_hash,
            schema_version=c.REQUISITION_INGESTION_SCHEMA_VERSION,
        )
        return SnapshotCapture(snapshot=SnapshotRead.model_validate(snapshot), reused=False)

    async def load_payload(self, snapshot: SnapshotRead) -> dict[str, Any]:
        """Return the snapshot payload; raises ``SnapshotIntegrityError`` if it was altered."""
        return await self._store.get(snapshot.payload_reference, snapshot.payload_hash)


# --- Eligibility (BE-1.6, D-07) -----------------------------------------------------------


def _normalise_status(value: str) -> str:
    return value.strip().casefold()


def check_eligibility(
    payload: HRRequisitionPayload, eligible_statuses: Collection[str]
) -> EligibilityResult:
    """Pure eligibility check, rules version ``ELIGIBILITY_RULES_VERSION``.

    Eligible when the source status is in ``eligible_statuses`` (compared trimmed and
    case-insensitively) and every field in ``ELIGIBILITY_REQUIRED_FIELDS`` is non-blank.
    A disallowed status is reported first. The payload is never modified and no default is
    ever filled in: a missing field is reported, not invented.
    """
    allowed = {_normalise_status(s) for s in eligible_statuses}
    missing = tuple(
        name
        for name in c.ELIGIBILITY_REQUIRED_FIELDS
        if not isinstance(value := getattr(payload, name), str) or not value.strip()
    )
    if _normalise_status(payload.status) not in allowed:
        reason: CompletionReason | None = CompletionReason.REQUISITION_NOT_ELIGIBLE_STATUS
    elif missing:
        reason = CompletionReason.REQUISITION_INCOMPLETE
    else:
        reason = None
    return EligibilityResult(
        eligible=reason is None,
        reason_code=reason,
        missing_fields=missing,
        rules_version=c.ELIGIBILITY_RULES_VERSION,
    )
