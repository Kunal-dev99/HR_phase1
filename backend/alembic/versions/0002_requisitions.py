"""requisition, snapshots, screening_run and integration_attempt (BE-1.2, D-05, D-09, D-10).

Revision ID: 0002_requisitions
Revises: 0001_audit_event
Create Date: 2026-10-22

D-01: additive only (five new tables and their indexes). ``status`` has no DB CHECK so
later states stay additive (D-10). D-02: downgrade() drops the five tables in reverse FK
order. Audit rows that reference runs stay in ``audit_event`` (no FK by design, D-12).
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_requisitions"
down_revision: str | None = "0001_audit_event"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOW = sa.text("clock_timestamp()")


def _id() -> sa.Column[Any]:
    return sa.Column(
        "id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )


def _ts(name: str, *, nullable: bool = False, default: bool = False) -> sa.Column[Any]:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=nullable,
        server_default=_NOW if default else None,
    )


def upgrade() -> None:
    op.create_table(
        "requisition",
        _id(),
        sa.Column("hr_system_key", sa.String(64), nullable=False),
        sa.Column("external_requisition_id", sa.String(128), nullable=False),
        sa.Column("external_version", sa.String(128), nullable=True),
        sa.Column("source_status", sa.String(64), nullable=False),
        sa.Column("business_unit_key", sa.String(64), nullable=False),
        _ts("last_source_modified_at", nullable=True),
        _ts("last_synced_at"),
        _ts("created_at", default=True),
        _ts("updated_at", default=True),
        sa.PrimaryKeyConstraint("id", name="pk_requisition"),
        sa.UniqueConstraint(
            "hr_system_key",
            "external_requisition_id",
            name="uq_requisition_hr_system_key_external_requisition_id",
        ),
    )

    # Restricted payload store behind SnapshotStore (D-05). No FK: payload_reference is an
    # opaque pointer so object storage can replace this table later.
    op.create_table(
        "requisition_snapshot_payload",
        _id(),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("payload_hash", sa.String(80), nullable=False),
        _ts("created_at", default=True),
        sa.PrimaryKeyConstraint("id", name="pk_requisition_snapshot_payload"),
    )

    op.create_table(
        "requisition_snapshot",
        _id(),
        sa.Column("requisition_id", sa.Uuid(), nullable=False),
        sa.Column("external_version", sa.String(128), nullable=True),
        sa.Column("payload_reference", sa.String(512), nullable=False),
        sa.Column("payload_hash", sa.String(80), nullable=False),
        _ts("captured_at", default=True),
        sa.Column("schema_version", sa.String(16), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_requisition_snapshot"),
        sa.ForeignKeyConstraint(
            ["requisition_id"],
            ["requisition.id"],
            name="fk_requisition_snapshot_requisition_id_requisition",
        ),
    )
    op.create_index(
        "ix_requisition_snapshot_requisition_id_captured_at",
        "requisition_snapshot",
        ["requisition_id", "captured_at"],
    )

    op.create_table(
        "screening_run",
        _id(),
        sa.Column("requisition_id", sa.Uuid(), nullable=True),
        sa.Column("requisition_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("role_brief_version_id", sa.Uuid(), nullable=True),
        sa.Column("role_configuration_version_id", sa.Uuid(), nullable=True),
        sa.Column("hr_system_key", sa.String(64), nullable=False),
        sa.Column("external_requisition_id", sa.String(128), nullable=False),
        sa.Column("business_unit_key", sa.String(64), nullable=True),
        sa.Column(
            "scope_business_units",
            postgresql.ARRAY(sa.String(64)),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("status_details", postgresql.JSONB(), nullable=True),
        sa.Column("started_by", sa.String(128), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        _ts("started_at", default=True),
        _ts("completed_at", nullable=True),
        sa.Column("completion_reason", sa.String(64), nullable=True),
        _ts("created_at", default=True),
        sa.PrimaryKeyConstraint("id", name="pk_screening_run"),
        sa.ForeignKeyConstraint(
            ["requisition_id"],
            ["requisition.id"],
            name="fk_screening_run_requisition_id_requisition",
        ),
        sa.ForeignKeyConstraint(
            ["requisition_snapshot_id"],
            ["requisition_snapshot.id"],
            name="fk_screening_run_requisition_snapshot_id_requisition_snapshot",
        ),
    )
    op.create_index(
        "ix_screening_run_requisition_id_status_started_at",
        "screening_run",
        ["requisition_id", "status", "started_at"],
    )

    op.create_table(
        "integration_attempt",
        _id(),
        sa.Column("screening_run_id", sa.Uuid(), nullable=False),
        sa.Column("integration_name", sa.String(64), nullable=False),
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("request_reference", sa.String(512), nullable=True),
        sa.Column("response_reference", sa.String(512), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        _ts("started_at"),
        _ts("completed_at", nullable=True),
        _ts("next_retry_at", nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_integration_attempt"),
        sa.ForeignKeyConstraint(
            ["screening_run_id"],
            ["screening_run.id"],
            name="fk_integration_attempt_screening_run_id_screening_run",
        ),
    )
    op.create_index(
        "ix_integration_attempt_run_id_name_outcome",
        "integration_attempt",
        ["screening_run_id", "integration_name", "outcome"],
    )


def downgrade() -> None:
    # Reverse FK order. Dropping a table drops its indexes and constraints with it.
    op.drop_table("integration_attempt")
    op.drop_table("screening_run")
    op.drop_table("requisition_snapshot")
    op.drop_table("requisition_snapshot_payload")
    op.drop_table("requisition")
