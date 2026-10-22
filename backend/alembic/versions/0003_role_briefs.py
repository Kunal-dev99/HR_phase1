"""role_brief_version (BE-6.4, D-37).

Revision ID: 0003_role_briefs
Revises: 0002_requisitions
Create Date: 2026-10-22

D-01: additive only (one new table, its unique constraint and one index). No FK is added
on the existing ``screening_run.role_brief_version_id`` (D-37). D-02: downgrade() drops
only the index and the table. Dialect-aware like 0002 (D-27, D-28): JSONB and server
defaults on PostgreSQL; JSON and app-side defaults on SQLite.
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_role_briefs"
down_revision: str | None = "0002_requisitions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "role_brief_version"
INDEX = "ix_role_brief_version_screening_run_id"


def _is_postgresql() -> bool:
    return bool(op.get_context().dialect.name == "postgresql")


def _json() -> Any:
    return postgresql.JSONB() if _is_postgresql() else sa.JSON()


def upgrade() -> None:
    pg = _is_postgresql()
    op.create_table(
        TABLE,
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()") if pg else None,
        ),
        sa.Column("requisition_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("structured_role_data", _json(), nullable=False),
        sa.Column("explicit_source_facts", _json(), nullable=False),
        sa.Column("ai_inferences", _json(), nullable=False),
        sa.Column("ambiguities", _json(), nullable=False),
        sa.Column("source_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.String(16), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()") if pg else None,
        ),
        sa.Column("screening_run_id", sa.Uuid(), nullable=False),
        sa.Column("source_payload_hash", sa.String(80), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("model_provider", sa.String(64), nullable=False),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_role_brief_version"),
        sa.ForeignKeyConstraint(
            ["requisition_id"],
            ["requisition.id"],
            name="fk_role_brief_version_requisition_id_requisition",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["requisition_snapshot.id"],
            name="fk_role_brief_version_source_snapshot_id_requisition_snapshot",
        ),
        sa.ForeignKeyConstraint(
            ["screening_run_id"],
            ["screening_run.id"],
            name="fk_role_brief_version_screening_run_id_screening_run",
        ),
        sa.UniqueConstraint(
            "requisition_id",
            "version_number",
            name="uq_role_brief_version_requisition_id_version_number",
        ),
    )
    op.create_index(INDEX, TABLE, ["screening_run_id"])


def downgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_table(TABLE)
