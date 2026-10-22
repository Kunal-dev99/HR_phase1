"""``integration_attempt`` ORM model (Data Model §4.17).

Records that an external call happened and how it ended. It never holds a request or
response body; ``request_reference`` / ``response_reference`` are pointers only.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.integrations import constants as c


class IntegrationAttempt(Base):
    __tablename__ = c.INTEGRATION_ATTEMPT_TABLE
    __table_args__ = (
        Index(
            "ix_integration_attempt_run_id_name_outcome",
            "screening_run_id",
            "integration_name",
            "outcome",
        ),
    )
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    screening_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("screening_run.id"), nullable=False
    )
    integration_name: Mapped[str] = mapped_column(String(c.INTEGRATION_NAME_MAX), nullable=False)
    operation: Mapped[str] = mapped_column(String(c.OPERATION_MAX), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(c.CORRELATION_ID_MAX), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(c.IDEMPOTENCY_KEY_MAX))
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    request_reference: Mapped[str | None] = mapped_column(String(c.REFERENCE_MAX))
    response_reference: Mapped[str | None] = mapped_column(String(c.REFERENCE_MAX))
    http_status: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(c.OUTCOME_MAX), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(c.ERROR_CODE_MAX))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
