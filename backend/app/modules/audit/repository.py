"""Audit repository: insert and read only. There is no update or delete path (D-12)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditEvent
from app.modules.audit.schemas import AuditEventCreate


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, data: AuditEventCreate) -> AuditEvent:
        """Insert within the caller's transaction. Flushes; never commits."""
        event = AuditEvent(**data.model_dump(mode="python"))
        self._session.add(event)
        await self._session.flush()
        return event

    async def list_for_run(self, screening_run_id: uuid.UUID) -> Sequence[AuditEvent]:
        result = await self._session.execute(
            select(AuditEvent)
            .where(AuditEvent.screening_run_id == screening_run_id)
            .order_by(AuditEvent.timestamp, AuditEvent.id)
        )
        return result.scalars().all()
