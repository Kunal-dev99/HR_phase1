"""Snapshot store: canonical hashing, tamper detection and reuse (BE-1.5, D-05)."""

import hashlib
import json
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.requisitions.constants import (
    PAYLOAD_REFERENCE_PREFIX,
    REQUISITION_INGESTION_SCHEMA_VERSION,
)
from app.modules.requisitions.models import Requisition
from app.modules.requisitions.repository import (
    DbSnapshotStore,
    SnapshotIntegrityError,
    SnapshotRepository,
    canonical_json,
    compute_payload_hash,
)
from app.modules.requisitions.service import SnapshotService

PAYLOAD = {
    "title": "Data Engineer — Zürich",
    "external_requisition_id": "REQ-SNAP-1",
    "nested": {"b": 2, "a": [3, 1.5, None, True]},
    "status": "open",
}


async def _requisition(session: AsyncSession) -> uuid.UUID:
    req = Requisition(
        hr_system_key="mock",
        external_requisition_id=f"REQ-SNAP-{uuid.uuid4().hex[:8]}",
        source_status="open",
        business_unit_key="bu-1",
        last_synced_at=datetime.now(UTC),
    )
    session.add(req)
    await session.flush()
    return req.id


async def test_hash_is_canonical_and_verified(db_session: AsyncSession) -> None:
    expected_bytes = json.dumps(
        PAYLOAD, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    assert canonical_json(PAYLOAD) == expected_bytes
    assert b'"nested":{"a":[3,1.5,null,true],"b":2}' in expected_bytes
    assert "Zürich".encode() in expected_bytes  # UTF-8, not \\u escapes
    expected_hash = "sha256:" + hashlib.sha256(expected_bytes).hexdigest()

    # Key order and whitespace in the input do not change the hash.
    reordered = json.loads(json.dumps(dict(reversed(list(PAYLOAD.items()))), indent=2))
    assert compute_payload_hash(reordered) == expected_hash
    assert compute_payload_hash({**PAYLOAD, "status": "closed"}) != expected_hash
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})

    store = DbSnapshotStore(db_session)
    reference, payload_hash = await store.put(reordered)
    assert payload_hash == expected_hash
    assert reference.startswith(PAYLOAD_REFERENCE_PREFIX)
    uuid.UUID(reference.removeprefix(PAYLOAD_REFERENCE_PREFIX))

    # get() recomputes the hash on read and returns the same content.
    assert await store.get(reference, payload_hash) == PAYLOAD
    with pytest.raises(SnapshotIntegrityError):
        await store.get(reference, "sha256:" + "0" * 64)
    for bad in ("s3://bucket/key", PAYLOAD_REFERENCE_PREFIX + "not-a-uuid"):
        with pytest.raises(SnapshotIntegrityError):
            await store.get(bad, payload_hash)
    with pytest.raises(SnapshotIntegrityError, match="missing"):
        await store.get(f"{PAYLOAD_REFERENCE_PREFIX}{uuid.uuid4()}", payload_hash)

    # A captured snapshot records the hash, reference and ingestion schema version.
    capture = await SnapshotService.for_session(db_session).capture(
        requisition_id=await _requisition(db_session), payload=PAYLOAD, external_version="v1"
    )
    assert capture.reused is False
    assert capture.snapshot.payload_hash == expected_hash
    assert capture.snapshot.schema_version == REQUISITION_INGESTION_SCHEMA_VERSION == "1"
    assert capture.snapshot.external_version == "v1"


@pytest.mark.pg_only
async def test_tampered_payload_raises(db_session: AsyncSession) -> None:
    service = SnapshotService.for_session(db_session)
    capture = await service.capture(
        requisition_id=await _requisition(db_session), payload=PAYLOAD, external_version=None
    )
    assert await service.load_payload(capture.snapshot) == PAYLOAD

    reference = capture.snapshot.payload_reference
    payload_id = uuid.UUID(reference.removeprefix(PAYLOAD_REFERENCE_PREFIX))
    await db_session.execute(
        text(
            "UPDATE requisition_snapshot_payload "
            "SET payload = jsonb_set(payload, '{status}', '\"closed\"') WHERE id = :id"
        ),
        {"id": payload_id},
    )
    with pytest.raises(SnapshotIntegrityError, match="hash mismatch"):
        await service.load_payload(capture.snapshot)


async def test_identical_payload_reuses_snapshot(db_session: AsyncSession) -> None:
    service = SnapshotService.for_session(db_session)
    snapshots = SnapshotRepository(db_session)
    requisition_id = await _requisition(db_session)

    first = await service.capture(
        requisition_id=requisition_id, payload=PAYLOAD, external_version="v1"
    )
    same = await service.capture(
        requisition_id=requisition_id,
        payload=json.loads(json.dumps(PAYLOAD, sort_keys=True)),  # same content, new object
        external_version="v1",
    )
    assert first.reused is False
    assert same.reused is True
    assert same.snapshot.id == first.snapshot.id
    assert await snapshots.count_for_requisition(requisition_id) == 1
    payload_rows = await db_session.scalar(
        text("SELECT count(*) FROM requisition_snapshot_payload WHERE payload_hash = :h"),
        {"h": first.snapshot.payload_hash},
    )
    assert payload_rows == 1

    changed = await service.capture(
        requisition_id=requisition_id,
        payload={**PAYLOAD, "status": "on_hold"},
        external_version="v2",
    )
    assert changed.reused is False
    assert changed.snapshot.id != first.snapshot.id
    assert await snapshots.count_for_requisition(requisition_id) == 2

    # Reuse compares with the *latest* snapshot only: going back to the first content
    # creates a new snapshot rather than silently re-pinning an older one.
    back = await service.capture(
        requisition_id=requisition_id, payload=PAYLOAD, external_version="v1"
    )
    assert back.reused is False
    assert await snapshots.count_for_requisition(requisition_id) == 3
