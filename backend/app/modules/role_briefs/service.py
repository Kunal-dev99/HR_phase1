"""Role brief services: generation, reading and approval (BE-6.5, BE-6.6).

Generation (D-32): chained after ingestion in the same executor dispatch, in a fresh
session. The run stays in ``role_brief_draft`` during the AI call, and no transaction is
open across it. The result commits in one unit of work: the version insert plus the
conditional run transition and their audit events (D-12). Deterministic code alone decides
the run state; the AI output is schema-validated (gateway) and citation-checked (D-36)
here. Any AI failure blocks the run (D-33) and stores no version.

Cross-module access goes through the requisitions repository and ``SnapshotService``
(D-39); ``requisitions`` never imports this module.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Iterable, Iterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.core.settings import Settings
from app.modules.audit.constants import ActorType
from app.modules.audit.schemas import DetailValue
from app.modules.audit.service import AuditService
from app.modules.integrations.adapters.ai_model.base import (
    AIModelAdapter,
    AIModelError,
    AIOutputInvalid,
    AIRequest,
    AIUnavailable,
)
from app.modules.integrations.constants import OPERATION_ROLE_BRIEF_GENERATE, AIErrorCode
from app.modules.integrations.service import AIGatewayService
from app.modules.requisitions import constants as rc
from app.modules.requisitions import events as run_events
from app.modules.requisitions.constants import CompletionReason, RunStatus
from app.modules.requisitions.models import ScreeningRun
from app.modules.requisitions.repository import ScreeningRunRepository, SnapshotRepository
from app.modules.requisitions.schemas import SnapshotRead
from app.modules.requisitions.service import (
    PermissionDeniedError,
    RunHandler,
    SessionScope,
    SnapshotService,
)
from app.modules.role_briefs import constants as c
from app.modules.role_briefs import events
from app.modules.role_briefs.constants import Basis, RoleBriefStatus, Severity
from app.modules.role_briefs.models import RoleBriefVersion
from app.modules.role_briefs.repository import RoleBriefRepository
from app.modules.role_briefs.schemas import (
    STRUCTURED_FIELDS,
    BriefItem,
    RoleBriefCreate,
    RoleBriefOutputV1,
    RoleBriefResponse,
    RoleStructuredData,
    SourceRef,
)

logger = logging.getLogger("app.role_briefs")

__all__ = [
    "PermissionDeniedError",
    "RoleBriefConflictError",
    "RoleBriefNotFoundError",
    "RoleBriefService",
    "build_role_brief_handler",
]


class RoleBriefNotFoundError(LookupError):
    """The run is missing, out of scope, or has no brief (404)."""


class RoleBriefConflictError(RuntimeError):
    """The run or the brief is not in a state that allows the action (409)."""


# --- Deterministic checks (D-36) ----------------------------------------------------------

_SEGMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d{1,3})\])?$")


def _normalise(text: str) -> str:
    return " ".join(text.split()).casefold()


def resolve_path(payload: dict[str, Any], path: str) -> str | None:
    """Resolve ``a.b[2]`` in the snapshot payload to a string, or ``None``."""
    current: Any = payload
    for segment in path.split("."):
        match = _SEGMENT.fullmatch(segment)
        if match is None or not isinstance(current, dict):
            return None
        current = current.get(match.group(1))
        if match.group(2) is not None:
            index = int(match.group(2))
            if not isinstance(current, list) or index >= len(current):
                return None
            current = current[index]
    return current if isinstance(current, str) else None


def _citation_verified(payload: dict[str, Any], ref: SourceRef) -> bool:
    value = resolve_path(payload, ref.path)
    return value is not None and _normalise(ref.quote) in _normalise(value)


def _all_refs(output: RoleBriefOutputV1) -> Iterator[SourceRef]:
    for item in _structured_items(output):
        yield from item.source_refs
    for fact in output.explicit_source_facts:
        yield from fact.source_refs
    for inference in output.ai_inferences:
        yield from inference.source_refs


def _structured_items(output: RoleStructuredData) -> Iterator[BriefItem]:
    yield output.role_title
    yield output.role_purpose
    yield output.seniority
    for items in (
        output.responsibilities,
        output.required_capabilities,
        output.preferred_capabilities,
        output.location_constraints,
        output.employment_constraints,
    ):
        yield from items


def check_brief(output: RoleBriefOutputV1, payload: dict[str, Any]) -> AIErrorCode | None:
    """Return the first failing D-36 rule, or ``None`` when the brief may be stored."""
    if not all(_citation_verified(payload, ref) for ref in _all_refs(output)):
        return AIErrorCode.CITATION_UNVERIFIED
    mandatory: Iterable[BriefItem] = (*output.responsibilities, *output.required_capabilities)
    if any(item.basis is not Basis.SOURCE_FACT or not item.source_refs for item in mandatory):
        return AIErrorCode.UNCITED_REQUIREMENT
    if any(not fact.source_refs for fact in output.explicit_source_facts):
        return AIErrorCode.UNCITED_REQUIREMENT
    return None


def build_user_content(payload: dict[str, Any]) -> str:
    """The snapshot as JSON inside a labelled block (D-35).

    ``<`` and ``>`` are escaped as JSON unicode escapes, so the content cannot close the
    block; the JSON still decodes to exactly the snapshot.
    """
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1)
    encoded = encoded.replace("<", "\\u003c").replace(">", "\\u003e")
    return f"{c.USER_CONTENT_PREFIX}{encoded}{c.USER_CONTENT_SUFFIX}"


# --- Service ------------------------------------------------------------------------------


def _to_response(row: RoleBriefVersion) -> RoleBriefResponse:
    return RoleBriefResponse(
        role_brief_version_id=row.id,
        screening_run_id=row.screening_run_id,
        requisition_id=row.requisition_id,
        version_number=row.version_number,
        status=RoleBriefStatus(row.status),
        structured_role_data=RoleStructuredData.model_validate(row.structured_role_data),
        explicit_source_facts=row.explicit_source_facts,  # type: ignore[arg-type]
        ai_inferences=row.ai_inferences,  # type: ignore[arg-type]
        ambiguities=row.ambiguities,  # type: ignore[arg-type]
        schema_version=row.schema_version,
        prompt_version=row.prompt_version,
        model_provider=row.model_provider,
        model_name=row.model_name,
        source_snapshot_id=row.source_snapshot_id,
        source_payload_hash=row.source_payload_hash,
        created_by=row.created_by,
        created_at=row.created_at,
        approved_by=row.approved_by,
        approved_at=row.approved_at,
    )


class RoleBriefService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        gateway: AIGatewayService | None = None,
        model: str | None = None,
    ) -> None:
        self._session = session
        self._gateway = gateway
        self._model = model
        self._runs = ScreeningRunRepository(session)
        self._snapshot_rows = SnapshotRepository(session)
        self._snapshots = SnapshotService.for_session(session)
        self._briefs = RoleBriefRepository(session)
        self._audit = AuditService.for_session(session)

    # -- generation (background) --------------------------------------------------------

    async def generate(self, run_id: uuid.UUID) -> uuid.UUID | None:
        """Generate the run's brief. Returns the version ID, or ``None`` (no-op/blocked)."""
        if self._gateway is None or not self._model:
            raise RuntimeError("generate() needs an AI gateway and a model")
        try:
            loaded = await self._load_for_generation(run_id)
        finally:
            await self._session.commit()  # read-only unit: nothing is held across the AI call
        if loaded is None:
            return None
        run, snapshot, payload = loaded

        request = AIRequest(
            system_prompt=c.ROLE_BRIEF_SYSTEM_PROMPT,
            user_content=build_user_content(payload),
            json_schema=RoleBriefOutputV1.model_json_schema(),
            model=self._model,
            max_output_tokens=c.ROLE_BRIEF_MAX_OUTPUT_TOKENS,
            routing_key=run.external_requisition_id,
        )
        try:
            try:
                result = await self._gateway.generate_structured(
                    request,
                    RoleBriefOutputV1,
                    screening_run_id=run.id,
                    correlation_id=run.correlation_id,
                    operation=OPERATION_ROLE_BRIEF_GENERATE,
                )
                failure = check_brief(result.output, payload)
                if failure is not None:
                    raise AIOutputInvalid(failure)
            except AIModelError as exc:
                await self._block(run, exc)
                await self._session.commit()
                return None
            version_id = await self._store(
                run, snapshot, result.output, result.provider, result.model
            )
        except BaseException:
            await self._session.rollback()
            raise
        if version_id is None:
            await self._session.rollback()  # lost a race: no row, no transition
            return None
        await self._session.commit()
        return version_id

    async def _load_for_generation(
        self, run_id: uuid.UUID
    ) -> tuple[ScreeningRun, SnapshotRead, dict[str, Any]] | None:
        run = await self._runs.get_for_workflow(run_id)
        if (
            run is None
            or run.status != RunStatus.ROLE_BRIEF_DRAFT
            or run.role_brief_version_id is not None
            or run.requisition_snapshot_id is None
        ):
            return None
        snapshot_row = await self._snapshot_rows.get(run.requisition_snapshot_id)
        if snapshot_row is None:
            return None
        snapshot = SnapshotRead.model_validate(snapshot_row)
        payload = await self._snapshots.load_payload(snapshot)  # hash-verified
        return run, snapshot, payload

    async def _store(
        self,
        run: ScreeningRun,
        snapshot: SnapshotRead,
        output: RoleBriefOutputV1,
        provider: str,
        model: str,
    ) -> uuid.UUID | None:
        structured = RoleStructuredData.model_validate(
            output.model_dump(include=set(STRUCTURED_FIELDS))
        )
        row = await self._briefs.add(
            RoleBriefCreate(
                requisition_id=snapshot.requisition_id,
                screening_run_id=run.id,
                version_number=await self._briefs.next_version_number(snapshot.requisition_id),
                status=RoleBriefStatus.AWAITING_REVIEW,
                structured_role_data=structured,
                explicit_source_facts=output.explicit_source_facts,
                ai_inferences=output.ai_inferences,
                ambiguities=output.ambiguities,
                source_snapshot_id=snapshot.id,
                source_payload_hash=snapshot.payload_hash,
                schema_version=c.ROLE_BRIEF_SCHEMA_VERSION,
                prompt_version=c.ROLE_BRIEF_PROMPT_VERSION,
                model_provider=provider,
                model_name=model[: c.MODEL_NAME_MAX],
                created_by=f"{c.CREATED_BY_PREFIX}{provider}/{model}"[: c.CREATED_BY_MAX],
            )
        )
        updated = await self._runs.transition(
            run.id,
            expected_status=RunStatus.ROLE_BRIEF_DRAFT,
            new_status=RunStatus.AWAITING_ROLE_APPROVAL,
            role_brief_version_id=row.id,
        )
        if updated is None:
            return None
        await self._record(
            run,
            entity_type=c.ENTITY_ROLE_BRIEF_VERSION,
            entity_id=str(row.id),
            event_type=events.ROLE_BRIEF_CREATED,
            actor_type=ActorType.SYSTEM,
            actor_id=c.GENERATOR_ACTOR_ID,
            details={
                "role_brief_version_id": str(row.id),
                "version_number": row.version_number,
                "schema_version": row.schema_version,
                "prompt_version": row.prompt_version,
                "model_provider": row.model_provider,
                "model_name": row.model_name,
                "explicit_source_facts": len(output.explicit_source_facts),
                "ai_inferences": len(output.ai_inferences),
                "ambiguities": len(output.ambiguities),
            },
        )
        await self._record_transition(
            run,
            RunStatus.ROLE_BRIEF_DRAFT,
            RunStatus.AWAITING_ROLE_APPROVAL,
            reason_code="role_brief_created",
            actor_type=ActorType.SYSTEM,
            actor_id=c.GENERATOR_ACTOR_ID,
        )
        logger.info(
            "role brief created",
            extra={
                "event": "role_brief_created",
                "screening_run_id": str(run.id),
                "correlation_id": run.correlation_id,
            },
        )
        return row.id

    async def _block(self, run: ScreeningRun, error: AIModelError) -> None:
        reason = (
            CompletionReason.ROLE_BRIEF_AI_UNAVAILABLE
            if isinstance(error, AIUnavailable)
            else CompletionReason.ROLE_BRIEF_OUTPUT_INVALID
        )
        updated = await self._runs.transition(
            run.id,
            expected_status=RunStatus.ROLE_BRIEF_DRAFT,
            new_status=RunStatus.BLOCKED,
            completion_reason=reason.value,
            status_details={"error_code": error.error_code.value, "retryable": True},
            completed=True,
        )
        if updated is None:
            return  # moved on meanwhile; the attempt row still records the call
        await self._record_transition(
            run,
            RunStatus.ROLE_BRIEF_DRAFT,
            RunStatus.BLOCKED,
            reason_code=reason.value,
            actor_type=ActorType.SYSTEM,
            actor_id=c.GENERATOR_ACTOR_ID,
            extra={"error_code": error.error_code.value},
        )
        logger.info(
            "role brief generation failed",
            extra={
                "event": "role_brief_failed",
                "screening_run_id": str(run.id),
                "correlation_id": run.correlation_id,
                "error_code": error.error_code.value,
            },
        )

    # -- reading and approval (HTTP) ----------------------------------------------------

    async def get_for_run(self, principal: Principal, run_id: uuid.UUID) -> RoleBriefResponse:
        if not principal.has_permission(rc.PERMISSION_SCREENING_RUN_READ):
            raise PermissionDeniedError(rc.PERMISSION_SCREENING_RUN_READ)
        run = await self._runs.get_for_principal(run_id, principal)  # D-09 scope
        if run is None or run.role_brief_version_id is None:
            raise RoleBriefNotFoundError("role brief not found")
        row = await self._briefs.get(run.role_brief_version_id)
        if row is None or row.screening_run_id != run.id:
            raise RoleBriefNotFoundError("role brief not found")
        return _to_response(row)

    async def approve(
        self, principal: Principal, run_id: uuid.UUID, role_brief_version_id: uuid.UUID
    ) -> RoleBriefResponse:
        """Approve the run's current brief and move the run to ``role_configuration``.

        Joins the caller's unit of work (the request transaction).
        """
        if not principal.has_permission(c.PERMISSION_ROLE_BRIEF_APPROVE):
            raise PermissionDeniedError(c.PERMISSION_ROLE_BRIEF_APPROVE)
        run = await self._runs.get_for_principal(run_id, principal)  # D-09 scope
        if run is None:
            raise RoleBriefNotFoundError("run not found")
        if (
            run.status != RunStatus.AWAITING_ROLE_APPROVAL
            or run.role_brief_version_id != role_brief_version_id
        ):
            raise RoleBriefConflictError("role brief cannot be approved in this state")
        row = await self._briefs.approve(role_brief_version_id, principal.id)
        if row is None:
            raise RoleBriefConflictError("role brief is not awaiting review")
        updated = await self._runs.transition(
            run.id,
            expected_status=RunStatus.AWAITING_ROLE_APPROVAL,
            new_status=RunStatus.ROLE_CONFIGURATION,
        )
        if updated is None:
            raise RoleBriefConflictError("run is no longer awaiting role approval")
        material = sum(1 for a in row.ambiguities if a.get("severity") == Severity.MATERIAL)
        await self._record(
            run,
            entity_type=c.ENTITY_ROLE_BRIEF_VERSION,
            entity_id=str(row.id),
            event_type=events.ROLE_BRIEF_APPROVED,
            actor_type=ActorType.USER,
            actor_id=principal.id,
            details={
                "role_brief_version_id": str(row.id),
                "version_number": row.version_number,
                "material_ambiguities": material,
                "ambiguities": len(row.ambiguities),
            },
        )
        await self._record_transition(
            run,
            RunStatus.AWAITING_ROLE_APPROVAL,
            RunStatus.ROLE_CONFIGURATION,
            reason_code="role_brief_approved",
            actor_type=ActorType.USER,
            actor_id=principal.id,
        )
        return _to_response(row)

    # -- audit helpers ------------------------------------------------------------------

    async def _record_transition(
        self,
        run: ScreeningRun,
        old: RunStatus,
        new: RunStatus,
        *,
        reason_code: str,
        actor_type: ActorType,
        actor_id: str,
        extra: dict[str, DetailValue] | None = None,
    ) -> None:
        await self._record(
            run,
            entity_type=rc.ENTITY_SCREENING_RUN,
            entity_id=str(run.id),
            event_type=run_events.RUN_STATUS_CHANGED,
            actor_type=actor_type,
            actor_id=actor_id,
            reason_code=reason_code,
            details={"from_status": old.value, "to_status": new.value, **(extra or {})},
        )

    async def _record(
        self,
        run: ScreeningRun,
        *,
        entity_type: str,
        entity_id: str,
        event_type: str,
        actor_type: ActorType,
        actor_id: str,
        details: dict[str, DetailValue],
        reason_code: str | None = None,
    ) -> None:
        await self._audit.record(
            screening_run_id=run.id,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            correlation_id=run.correlation_id,
            reason_code=reason_code,
            details=details,
        )


# --- Executor wiring (BE-6.6, D-32) -------------------------------------------------------


def build_role_brief_handler(
    settings: Settings, gateway_adapter: AIModelAdapter, session_scope: SessionScope
) -> RunHandler:
    """Each call generates the run's brief in its own session from ``session_scope``."""

    async def _generate(run_id: uuid.UUID) -> None:
        async with session_scope() as session:
            gateway = AIGatewayService.for_session(
                session, gateway_adapter, timeout_seconds=settings.AI_TIMEOUT_SECONDS
            )
            await RoleBriefService(session, gateway=gateway, model=settings.AI_MODEL).generate(
                run_id
            )

    return _generate
