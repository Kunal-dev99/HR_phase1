"""Audit service. ``record`` joins the caller's unit of work (D-12).

Callers build ``AuditService`` over the same session as their own repositories, so the
audit row commits or rolls back together with the state change it describes.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.correlation import get_correlation_id
from app.modules.audit.constants import ActorType
from app.modules.audit.repository import AuditRepository
from app.modules.audit.schemas import AuditEventCreate, AuditEventRead, DetailValue


class MissingCorrelationIdError(ValueError):
    """An audit event needs a correlation ID; none was given and none is in context."""


class AuditService:
    def __init__(self, repository: AuditRepository) -> None:
        self._repository = repository

    @classmethod
    def for_session(cls, session: AsyncSession) -> AuditService:
        return cls(AuditRepository(session))

    async def record(
        self,
        *,
        screening_run_id: uuid.UUID,
        entity_type: str,
        entity_id: str,
        event_type: str,
        actor_type: ActorType,
        actor_id: str | None = None,
        correlation_id: str | None = None,
        configuration_version_id: uuid.UUID | None = None,
        reason_code: str | None = None,
        details_reference: str | None = None,
        details: dict[str, DetailValue] | None = None,
    ) -> AuditEventRead:
        resolved_correlation_id = correlation_id or get_correlation_id()
        if not resolved_correlation_id:
            raise MissingCorrelationIdError("audit events must carry a correlation_id")
        data = AuditEventCreate(
            screening_run_id=screening_run_id,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            correlation_id=resolved_correlation_id,
            configuration_version_id=configuration_version_id,
            reason_code=reason_code,
            details_reference=details_reference,
            details=details,
        )
        event = await self._repository.add(data)
        return AuditEventRead.model_validate(event)

    async def list_for_run(self, screening_run_id: uuid.UUID) -> list[AuditEventRead]:
        events = await self._repository.list_for_run(screening_run_id)
        return [AuditEventRead.model_validate(e) for e in events]
