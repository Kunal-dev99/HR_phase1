"""audit_event table, run/timestamp index and append-only trigger (BE-0.6, D-12).

Revision ID: 0001_audit_event
Revises:
Create Date: 2026-10-22

D-01: additive only. D-02: downgrade() drops the triggers, the function, the index and the
table. Once real audit data exists in a shared environment, downgrading this revision needs
a new decision (it destroys audit records).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_audit_event"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FUNCTION = "audit_event_reject_mutation"


def upgrade() -> None:
    op.create_table(
        "audit_event",
        sa.Column(
            "id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("screening_run_id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor_type", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("configuration_version_id", sa.Uuid(), nullable=True),
        sa.Column("reason_code", sa.String(64), nullable=True),
        sa.Column("details_reference", sa.String(512), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_audit_event"),
    )
    op.create_index(
        "ix_audit_event_screening_run_id_timestamp",
        "audit_event",
        ["screening_run_id", "timestamp"],
    )
    op.execute(
        f"""
        CREATE FUNCTION {FUNCTION}() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_event is append-only: % is not allowed', TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER audit_event_no_update_delete
        BEFORE UPDATE OR DELETE ON audit_event
        FOR EACH ROW EXECUTE FUNCTION {FUNCTION}()
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER audit_event_no_truncate
        BEFORE TRUNCATE ON audit_event
        FOR EACH STATEMENT EXECUTE FUNCTION {FUNCTION}()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_event_no_truncate ON audit_event")
    op.execute("DROP TRIGGER IF EXISTS audit_event_no_update_delete ON audit_event")
    op.execute(f"DROP FUNCTION IF EXISTS {FUNCTION}()")
    op.drop_index("ix_audit_event_screening_run_id_timestamp", table_name="audit_event")
    op.drop_table("audit_event")
