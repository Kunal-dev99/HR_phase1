"""``audit_event`` ORM model (Data Model §4.18 + ``details``, D-12).

Rows are append-only: the repository only inserts, and on PostgreSQL a database trigger
rejects UPDATE, DELETE and TRUNCATE (app level only on SQLite, D-26). ``screening_run_id``
is indexed but deliberately has no foreign key.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, JSONType, UTCDateTime, utc_now
from app.modules.audit import constants as c


class AuditEvent(Base):
    __tablename__ = c.TABLE_NAME
    __table_args__ = (
        Index("ix_audit_event_screening_run_id_timestamp", "screening_run_id", "timestamp"),
    )
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    screening_run_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(c.ENTITY_TYPE_MAX), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(c.ENTITY_ID_MAX), nullable=False)
    event_type: Mapped[str] = mapped_column(String(c.EVENT_TYPE_MAX), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(c.ACTOR_TYPE_MAX), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(c.ACTOR_ID_MAX), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utc_now)
    correlation_id: Mapped[str] = mapped_column(String(c.CORRELATION_ID_MAX), nullable=False)
    configuration_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(c.REASON_CODE_MAX), nullable=True)
    details_reference: Mapped[str | None] = mapped_column(
        String(c.DETAILS_REFERENCE_MAX), nullable=True
    )
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
