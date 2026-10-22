"""Screening-run HTTP routes (BE-2.3, BE-2.4, D-08, D-11).

Mounted only when ``FEATURE_SCREENING_RUNS=true``. Routes call only ``ScreeningRunService``
and the run executor; they never touch repositories or run queries.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.correlation import get_correlation_id, new_correlation_id
from app.core.db import get_session
from app.core.security import Principal, require_permission
from app.modules.requisitions import constants as c
from app.modules.requisitions.schemas import (
    ScreeningRunAccepted,
    ScreeningRunCreateRequest,
    ScreeningRunStatusResponse,
)
from app.modules.requisitions.service import RunExecutor, ScreeningRunService

router = APIRouter(prefix=c.SCREENING_RUNS_PATH, tags=["screening-runs"])


def get_screening_run_service(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> ScreeningRunService:
    return ScreeningRunService.for_session(session, hr_system_key=request.app.state.hr_system_key)


def get_run_executor(request: Request) -> RunExecutor:
    executor: RunExecutor = request.app.state.run_executor
    return executor


ServiceDep = Annotated[ScreeningRunService, Depends(get_screening_run_service)]


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=ScreeningRunAccepted)
async def create_screening_run(
    body: ScreeningRunCreateRequest,
    request: Request,
    response: Response,
    principal: Annotated[
        Principal, Depends(require_permission(c.PERMISSION_SCREENING_RUN_CREATE))
    ],
    service: ServiceDep,
    executor: Annotated[RunExecutor, Depends(get_run_executor)],
) -> ScreeningRunAccepted:
    correlation_id = get_correlation_id() or new_correlation_id()
    run = await service.start(principal, body.external_requisition_id, correlation_id, executor)
    status_url = str(request.url_for("get_screening_run", run_id=str(run.id)).path)
    response.headers["Location"] = status_url
    return ScreeningRunAccepted(
        run_id=run.id,
        status=run.status,
        status_url=status_url,
        correlation_id=run.correlation_id,
    )


@router.get("/{run_id}", response_model=ScreeningRunStatusResponse, name="get_screening_run")
async def get_screening_run(
    run_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(c.PERMISSION_SCREENING_RUN_READ))],
    service: ServiceDep,
) -> ScreeningRunStatusResponse:
    result = await service.get_status(principal, run_id)
    if result is None:  # missing or out of scope look the same (D-09)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return result
