"""Role brief repository: all database access for ``role_brief_version`` (BE-6.5).

Versions are immutable (D-37): ``approve`` is a conditional
``UPDATE … WHERE status='awaiting_review' RETURNING`` and the only update path. Nothing is
ever deleted. Row scoping is applied by loading the run through
``ScreeningRunRepository.get_for_principal`` first (D-09); a brief is only read by the ID
pinned on a run the principal can see. Flushes but never commits.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utc_now
from app.modules.role_briefs.constants import RoleBriefStatus
from app.modules.role_briefs.models import RoleBriefVersion
from app.modules.role_briefs.schemas import RoleBriefCreate

_REFRESH = {"populate_existing": True}


class RoleBriefRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, data: RoleBriefCreate) -> RoleBriefVersion:
        values = data.model_dump(mode="json")
        row = RoleBriefVersion(
            **{
                **values,
                "requisition_id": data.requisition_id,
                "screening_run_id": data.screening_run_id,
                "source_snapshot_id": data.source_snapshot_id,
            }
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, role_brief_version_id: uuid.UUID) -> RoleBriefVersion | None:
        result = await self._session.scalars(
            select(RoleBriefVersion).where(RoleBriefVersion.id == role_brief_version_id),
            execution_options=_REFRESH,
        )
        return result.one_or_none()

    async def next_version_number(self, requisition_id: uuid.UUID) -> int:
        current = await self._session.scalar(
            select(func.max(RoleBriefVersion.version_number)).where(
                RoleBriefVersion.requisition_id == requisition_id
            )
        )
        return int(current or 0) + 1

    async def approve(
        self, role_brief_version_id: uuid.UUID, approved_by: str
    ) -> RoleBriefVersion | None:
        """``awaiting_review -> approved``. ``None`` if the version is not awaiting review."""
        stmt = (
            update(RoleBriefVersion)
            .where(
                RoleBriefVersion.id == role_brief_version_id,
                RoleBriefVersion.status == RoleBriefStatus.AWAITING_REVIEW.value,
            )
            .values(
                status=RoleBriefStatus.APPROVED.value,
                approved_by=approved_by,
                approved_at=utc_now(),
            )
            .returning(RoleBriefVersion)
        )
        result = await self._session.scalars(stmt, execution_options=_REFRESH)
        return result.one_or_none()
