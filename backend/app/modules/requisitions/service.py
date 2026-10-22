"""Requisitions services: snapshots, eligibility, run creation and ingestion.

Services hold the business rules and orchestration. They reach the database only through
repositories, and the HR System only through ``integrations`` services.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.requisitions import constants as c
from app.modules.requisitions.repository import (
    DbSnapshotStore,
    SnapshotRepository,
    SnapshotStore,
    compute_payload_hash,
)
from app.modules.requisitions.schemas import SnapshotCapture, SnapshotRead

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
