"""RequisitionRepository.upsert updates source fields only (BE-1.3)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.requisitions.repository import RequisitionRepository
from app.modules.requisitions.schemas import RequisitionUpsert


async def test_upsert_inserts_then_updates_source_fields_only(db_session: AsyncSession) -> None:
    repo = RequisitionRepository(db_session)
    first = await repo.upsert(
        RequisitionUpsert(
            hr_system_key="mock",
            external_requisition_id="REQ-UPSERT-1",
            external_version="v1",
            source_status="open",
            business_unit_key="bu-1",
        )
    )
    first_id, created_at, synced_at = first.id, first.created_at, first.last_synced_at

    second = await repo.upsert(
        RequisitionUpsert(
            hr_system_key="mock",
            external_requisition_id="REQ-UPSERT-1",
            external_version="v2",
            source_status="closed",
            business_unit_key="bu-1",
        )
    )
    assert second.id == first_id
    assert second.created_at == created_at
    assert second.external_version == "v2"
    assert second.source_status == "closed"
    assert second.last_synced_at > synced_at
    assert second.updated_at > created_at
