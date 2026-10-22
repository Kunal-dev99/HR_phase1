"""Requisitions ORM models (Data Model §4.1-4.3 with the D-05, D-09 and D-10 additions).

``status`` and ``completion_reason`` are plain strings validated by the application enums
in ``constants.py``; there is no DB CHECK, so new states stay additive (D-10).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, JSONType, StringList, UTCDateTime, utc_now
from app.modules.requisitions import constants as c


class Requisition(Base):
    """The hiring request as last retrieved from the HR System (§4.1 + business_unit_key)."""

    __tablename__ = c.REQUISITION_TABLE
    __table_args__ = (UniqueConstraint("hr_system_key", "external_requisition_id"),)
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    hr_system_key: Mapped[str] = mapped_column(String(c.HR_SYSTEM_KEY_MAX), nullable=False)
    external_requisition_id: Mapped[str] = mapped_column(
        String(c.EXTERNAL_REQUISITION_ID_MAX), nullable=False
    )
    external_version: Mapped[str | None] = mapped_column(String(c.EXTERNAL_VERSION_MAX))
    source_status: Mapped[str] = mapped_column(String(c.SOURCE_STATUS_MAX), nullable=False)
    business_unit_key: Mapped[str] = mapped_column(String(c.BUSINESS_UNIT_KEY_MAX), nullable=False)
    last_source_modified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_synced_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utc_now)


class RequisitionSnapshot(Base):
    """A versioned, hash-verified snapshot of what the HR System returned (§4.2, D-05)."""

    __tablename__ = c.SNAPSHOT_TABLE
    __table_args__ = (
        Index(
            "ix_requisition_snapshot_requisition_id_captured_at",
            "requisition_id",
            "captured_at",
        ),
    )
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    requisition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{c.REQUISITION_TABLE}.id"), nullable=False
    )
    external_version: Mapped[str | None] = mapped_column(String(c.EXTERNAL_VERSION_MAX))
    payload_reference: Mapped[str] = mapped_column(String(c.PAYLOAD_REFERENCE_MAX), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(c.PAYLOAD_HASH_MAX), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utc_now)
    schema_version: Mapped[str] = mapped_column(String(c.SCHEMA_VERSION_MAX), nullable=False)


class RequisitionSnapshotPayload(Base):
    """Restricted payload store behind ``SnapshotStore`` (D-05). Never exposed by the API."""

    __tablename__ = c.SNAPSHOT_PAYLOAD_TABLE
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(c.PAYLOAD_HASH_MAX), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utc_now)


class ScreeningRun(Base):
    """One execution of the screening workflow (§4.3 with the D-10 deviations)."""

    __tablename__ = c.SCREENING_RUN_TABLE
    __table_args__ = (
        Index(
            "ix_screening_run_requisition_id_status_started_at",
            "requisition_id",
            "status",
            "started_at",
        ),
    )
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Nullable (D-10): set during ingestion; a not-found run never gets them.
    requisition_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey(f"{c.REQUISITION_TABLE}.id")
    )
    requisition_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey(f"{c.SNAPSHOT_TABLE}.id")
    )
    # The target tables belong to later features; no FK yet (added with those tables).
    role_brief_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    role_configuration_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    hr_system_key: Mapped[str] = mapped_column(String(c.HR_SYSTEM_KEY_MAX), nullable=False)
    external_requisition_id: Mapped[str] = mapped_column(
        String(c.EXTERNAL_REQUISITION_ID_MAX), nullable=False
    )
    business_unit_key: Mapped[str | None] = mapped_column(String(c.BUSINESS_UNIT_KEY_MAX))
    # The starter's business-unit scope at creation, so background ingestion can apply the
    # D-09 rule without a live principal. Never read from a request parameter.
    scope_business_units: Mapped[list[str]] = mapped_column(
        StringList(c.BUSINESS_UNIT_KEY_MAX),
        nullable=False,
        default=list,
    )
    status: Mapped[str] = mapped_column(String(c.STATUS_MAX), nullable=False)
    status_details: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    started_by: Mapped[str | None] = mapped_column(String(c.STARTED_BY_MAX))
    correlation_id: Mapped[str] = mapped_column(String(c.CORRELATION_ID_MAX), nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completion_reason: Mapped[str | None] = mapped_column(String(c.COMPLETION_REASON_MAX))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utc_now)
