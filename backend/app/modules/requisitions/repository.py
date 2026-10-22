"""Requisitions repositories: all database access for the module (BE-1.3).

Row scoping (D-04, D-09) lives here: ``ScreeningRunRepository.get_for_principal`` builds its
filter from the authenticated principal only. ``get_for_workflow`` is the one unscoped read;
services may use it for background work, routers never import it.

Repositories flush but never commit; the caller owns the unit of work.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Protocol

from sqlalchemy import ColumnElement, and_, func, or_, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import utc_now
from app.core.security import Principal
from app.modules.requisitions import constants as c
from app.modules.requisitions.constants import RunStatus
from app.modules.requisitions.models import (
    Requisition,
    RequisitionSnapshot,
    RequisitionSnapshotPayload,
    ScreeningRun,
)
from app.modules.requisitions.schemas import RequisitionUpsert

_REFRESH = {"populate_existing": True}

# Columns an upsert may overwrite: source fields only, never id or created_at.
_SOURCE_FIELDS = (
    "external_version",
    "source_status",
    "business_unit_key",
    "last_source_modified_at",
)


class RequisitionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, data: RequisitionUpsert) -> Requisition:
        """``INSERT … ON CONFLICT (hr_system_key, external_requisition_id) DO UPDATE``.

        The dialect's own ``insert`` is used (PostgreSQL or SQLite, D-28); timestamps come
        from the app clock.
        """
        values = data.model_dump()
        now = utc_now()
        dialect = self._session.get_bind().dialect.name
        insert_fn = sqlite.insert if dialect == "sqlite" else postgresql.insert
        insert = insert_fn(Requisition).values(**values, last_synced_at=now)
        stmt = insert.on_conflict_do_update(
            index_elements=[Requisition.hr_system_key, Requisition.external_requisition_id],
            set_={
                **{name: insert.excluded[name] for name in _SOURCE_FIELDS},
                "last_synced_at": now,
                "updated_at": now,
            },
        ).returning(Requisition)
        result = await self._session.scalars(stmt, execution_options=_REFRESH)
        requisition: Requisition = result.one()
        return requisition

    async def get(self, requisition_id: uuid.UUID) -> Requisition | None:
        return await self._session.get(Requisition, requisition_id)

    async def get_by_external_id(
        self, hr_system_key: str, external_requisition_id: str
    ) -> Requisition | None:
        result = await self._session.scalars(
            select(Requisition).where(
                Requisition.hr_system_key == hr_system_key,
                Requisition.external_requisition_id == external_requisition_id,
            )
        )
        return result.one_or_none()


class SnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        requisition_id: uuid.UUID,
        external_version: str | None,
        payload_reference: str,
        payload_hash: str,
        schema_version: str,
    ) -> RequisitionSnapshot:
        snapshot = RequisitionSnapshot(
            requisition_id=requisition_id,
            external_version=external_version,
            payload_reference=payload_reference,
            payload_hash=payload_hash,
            schema_version=schema_version,
        )
        self._session.add(snapshot)
        await self._session.flush()
        return snapshot

    async def get(self, snapshot_id: uuid.UUID) -> RequisitionSnapshot | None:
        return await self._session.get(RequisitionSnapshot, snapshot_id)

    async def latest_for_requisition(self, requisition_id: uuid.UUID) -> RequisitionSnapshot | None:
        result = await self._session.scalars(
            select(RequisitionSnapshot)
            .where(RequisitionSnapshot.requisition_id == requisition_id)
            .order_by(RequisitionSnapshot.captured_at.desc(), RequisitionSnapshot.id.desc())
            .limit(1)
        )
        return result.one_or_none()

    async def count_for_requisition(self, requisition_id: uuid.UUID) -> int:
        result = await self._session.scalar(
            select(func.count())
            .select_from(RequisitionSnapshot)
            .where(RequisitionSnapshot.requisition_id == requisition_id)
        )
        return int(result or 0)


def principal_scope_filter(principal: Principal) -> ColumnElement[bool]:
    """D-09 visibility rule, derived from the principal only (never a request parameter).

    A run is visible when its business unit is one of the principal's, or when it has no
    business unit yet and the principal started it. ``*`` is honoured only when explicitly
    granted, and it matches resolved runs only: unresolved runs stay with their starter.
    """
    own_unresolved = and_(
        ScreeningRun.business_unit_key.is_(None), ScreeningRun.started_by == principal.id
    )
    if c.WILDCARD_BUSINESS_UNIT in principal.business_units:
        return or_(ScreeningRun.business_unit_key.is_not(None), own_unresolved)
    units = sorted(principal.business_units)
    if not units:
        return own_unresolved
    return or_(ScreeningRun.business_unit_key.in_(units), own_unresolved)


class ScreeningRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        hr_system_key: str,
        external_requisition_id: str,
        started_by: str,
        scope_business_units: list[str],
        correlation_id: str,
    ) -> ScreeningRun:
        run = ScreeningRun(
            hr_system_key=hr_system_key,
            external_requisition_id=external_requisition_id,
            started_by=started_by,
            scope_business_units=scope_business_units,
            correlation_id=correlation_id,
            status=RunStatus.CREATED.value,
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def get_for_principal(
        self, run_id: uuid.UUID, principal: Principal
    ) -> ScreeningRun | None:
        """Scoped read: ``None`` when the run is missing *or* out of scope (D-09)."""
        result = await self._session.scalars(
            select(ScreeningRun).where(
                ScreeningRun.id == run_id, principal_scope_filter(principal)
            ),
            execution_options=_REFRESH,
        )
        return result.one_or_none()

    async def get_for_workflow(self, run_id: uuid.UUID) -> ScreeningRun | None:
        """Unscoped read for background workflow services only. Never used by routers."""
        result = await self._session.scalars(
            select(ScreeningRun).where(ScreeningRun.id == run_id), execution_options=_REFRESH
        )
        return result.one_or_none()

    async def list_ids_in_status(self, status: RunStatus) -> list[uuid.UUID]:
        """Unscoped, for startup recovery only (D-06). Oldest first."""
        result = await self._session.scalars(
            select(ScreeningRun.id)
            .where(ScreeningRun.status == status.value)
            .order_by(ScreeningRun.started_at)
        )
        return list(result.all())

    async def claim_for_ingestion(self, run_id: uuid.UUID) -> ScreeningRun | None:
        """Single-winner claim: ``UPDATE … WHERE status='created' RETURNING`` (D-06)."""
        return await self.transition(
            run_id,
            expected_status=RunStatus.CREATED,
            new_status=RunStatus.INGESTING_REQUISITION,
        )

    async def transition(
        self,
        run_id: uuid.UUID,
        *,
        expected_status: RunStatus,
        new_status: RunStatus,
        requisition_id: uuid.UUID | None = None,
        requisition_snapshot_id: uuid.UUID | None = None,
        business_unit_key: str | None = None,
        role_brief_version_id: uuid.UUID | None = None,
        completion_reason: str | None = None,
        status_details: dict[str, Any] | None = None,
        completed: bool = False,
    ) -> ScreeningRun | None:
        """Conditional status change. Returns ``None`` if the run is not in ``expected_status``.

        Only the fields passed are written; ``None`` never clears an existing value.
        """
        values: dict[str, Any] = {"status": new_status.value}
        optional = {
            "requisition_id": requisition_id,
            "requisition_snapshot_id": requisition_snapshot_id,
            "business_unit_key": business_unit_key,
            "role_brief_version_id": role_brief_version_id,
            "completion_reason": completion_reason,
            "status_details": status_details,
        }
        values.update({k: v for k, v in optional.items() if v is not None})
        if completed:
            values["completed_at"] = utc_now()
        stmt = (
            update(ScreeningRun)
            .where(ScreeningRun.id == run_id, ScreeningRun.status == expected_status.value)
            .values(**values)
            .returning(ScreeningRun)
        )
        result = await self._session.scalars(stmt, execution_options=_REFRESH)
        return result.one_or_none()


# --- Snapshot payload store (BE-1.5, D-05) ----------------------------------------------


class SnapshotIntegrityError(RuntimeError):
    """A stored payload does not match its recorded hash, or the reference is unusable."""


def canonical_json(payload: dict[str, Any]) -> bytes:
    """Canonical JSON: sorted keys, compact separators, UTF-8, no NaN/Infinity (D-05)."""
    if not isinstance(payload, dict):
        raise TypeError("snapshot payloads must be JSON objects")
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def compute_payload_hash(payload: dict[str, Any]) -> str:
    return c.PAYLOAD_HASH_PREFIX + hashlib.sha256(canonical_json(payload)).hexdigest()


class SnapshotStore(Protocol):
    """Where snapshot payloads live. Object storage can implement this later (D-05)."""

    async def put(self, payload: dict[str, Any]) -> tuple[str, str]:
        """Store ``payload``; return ``(payload_reference, payload_hash)``."""
        ...

    async def get(self, reference: str, expected_hash: str) -> dict[str, Any]:
        """Return the payload after re-verifying its hash; raise on any mismatch."""
        ...


class DbSnapshotStore:
    """``requisition_snapshot_payload`` table, written in the caller's transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def put(self, payload: dict[str, Any]) -> tuple[str, str]:
        canonical = canonical_json(payload)
        payload_hash = c.PAYLOAD_HASH_PREFIX + hashlib.sha256(canonical).hexdigest()
        row = RequisitionSnapshotPayload(payload=json.loads(canonical), payload_hash=payload_hash)
        self._session.add(row)
        await self._session.flush()
        return f"{c.PAYLOAD_REFERENCE_PREFIX}{row.id}", payload_hash

    async def get(self, reference: str, expected_hash: str) -> dict[str, Any]:
        if not reference.startswith(c.PAYLOAD_REFERENCE_PREFIX):
            raise SnapshotIntegrityError("unsupported payload reference")
        try:
            payload_id = uuid.UUID(reference.removeprefix(c.PAYLOAD_REFERENCE_PREFIX))
        except ValueError:
            raise SnapshotIntegrityError("malformed payload reference") from None
        result = await self._session.scalars(
            select(RequisitionSnapshotPayload).where(RequisitionSnapshotPayload.id == payload_id),
            execution_options=_REFRESH,
        )
        row = result.one_or_none()
        if row is None:
            raise SnapshotIntegrityError("snapshot payload is missing")
        actual = compute_payload_hash(row.payload)
        if actual != expected_hash or actual != row.payload_hash:
            raise SnapshotIntegrityError("snapshot payload hash mismatch")
        return row.payload
