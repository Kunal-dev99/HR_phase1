"""Schema checks for 0002_requisitions (BE-1.2)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.requisitions.models import Requisition


def _requisition(external_id: str, hr_system_key: str = "mock") -> Requisition:
    return Requisition(
        hr_system_key=hr_system_key,
        external_requisition_id=external_id,
        source_status="open",
        business_unit_key="bu-1",
        last_synced_at=datetime.now(UTC),
    )


@pytest.mark.pg_only
async def test_requisition_unique_external_id(db_session: AsyncSession) -> None:
    db_session.add(_requisition("REQ-UNIQUE-1"))
    await db_session.flush()

    # Same external ID in another HR System is a different requisition.
    db_session.add(_requisition("REQ-UNIQUE-1", hr_system_key="other-hr"))
    await db_session.flush()

    unique_name = "uq_requisition_hr_system_key_external_requisition_id"
    with pytest.raises(IntegrityError, match=unique_name):
        async with db_session.begin_nested():
            db_session.add(_requisition("REQ-UNIQUE-1"))
            await db_session.flush()


@pytest.mark.pg_only
async def test_screening_run_status_has_no_check_constraint(db_session: AsyncSession) -> None:
    """D-10: status is validated by the application enum only, so new states stay additive."""
    rows = await db_session.execute(
        text(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'screening_run'::regclass AND contype = 'c'"
        )
    )
    assert rows.all() == []
