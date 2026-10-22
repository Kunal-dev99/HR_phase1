"""``role_brief_version`` ORM model (Data Model §4.4 plus the D-37 additions).

Immutable once written: the repository's conditional approve is the only update path.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, JSONType, UTCDateTime, utc_now
from app.modules.role_briefs import constants as c


class RoleBriefVersion(Base):
    __tablename__ = c.ROLE_BRIEF_VERSION_TABLE
    __table_args__ = (
        UniqueConstraint("requisition_id", "version_number"),
        Index("ix_role_brief_version_screening_run_id", "screening_run_id"),
    )
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    requisition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("requisition.id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(c.STATUS_MAX), nullable=False)
    structured_role_data: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    explicit_source_facts: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, nullable=False)
    ai_inferences: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, nullable=False)
    ambiguities: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, nullable=False)
    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("requisition_snapshot.id"), nullable=False
    )
    schema_version: Mapped[str] = mapped_column(String(c.SCHEMA_VERSION_MAX), nullable=False)
    created_by: Mapped[str] = mapped_column(String(c.CREATED_BY_MAX), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(c.APPROVED_BY_MAX))
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utc_now)
    # D-37 additions.
    screening_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("screening_run.id"), nullable=False
    )
    source_payload_hash: Mapped[str] = mapped_column(String(c.PAYLOAD_HASH_MAX), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(c.PROMPT_VERSION_MAX), nullable=False)
    model_provider: Mapped[str] = mapped_column(String(c.MODEL_PROVIDER_MAX), nullable=False)
    model_name: Mapped[str] = mapped_column(String(c.MODEL_NAME_MAX), nullable=False)
