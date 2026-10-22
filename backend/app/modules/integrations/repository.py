"""Integration-attempt repository. Flushes within the caller's transaction; never commits."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integrations.models import IntegrationAttempt
from app.modules.integrations.schemas import IntegrationAttemptCreate


class IntegrationAttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, data: IntegrationAttemptCreate) -> IntegrationAttempt:
        attempt = IntegrationAttempt(**data.model_dump(mode="python"))
        self._session.add(attempt)
        await self._session.flush()
        return attempt

    async def list_for_run(self, screening_run_id: uuid.UUID) -> Sequence[IntegrationAttempt]:
        result = await self._session.scalars(
            select(IntegrationAttempt)
            .where(IntegrationAttempt.screening_run_id == screening_run_id)
            .order_by(IntegrationAttempt.started_at, IntegrationAttempt.id)
        )
        return result.all()
