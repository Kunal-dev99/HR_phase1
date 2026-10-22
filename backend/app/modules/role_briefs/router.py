"""Role brief HTTP routes (BE-6.6, D-34, D-38).

Mounted under ``/api/v1`` only when ``FEATURE_ROLE_BRIEF=true``. Routes call only
``RoleBriefService``; they never touch repositories or run queries. A missing or
out-of-scope run looks the same (404, D-09).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import Principal, require_permission
from app.modules.requisitions.constants import PERMISSION_SCREENING_RUN_READ
from app.modules.role_briefs import constants as c
from app.modules.role_briefs.schemas import ApproveRoleBriefRequest, RoleBriefResponse
from app.modules.role_briefs.service import (
    RoleBriefConflictError,
    RoleBriefNotFoundError,
    RoleBriefService,
)

router = APIRouter(tags=["role-briefs"])


def get_role_brief_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RoleBriefService:
    return RoleBriefService(session)


ServiceDep = Annotated[RoleBriefService, Depends(get_role_brief_service)]


@router.get(c.ROLE_BRIEF_PATH, response_model=RoleBriefResponse, name="get_role_brief")
async def get_role_brief(
    run_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(PERMISSION_SCREENING_RUN_READ))],
    service: ServiceDep,
) -> RoleBriefResponse:
    try:
        return await service.get_for_run(principal, run_id)
    except RoleBriefNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from None


@router.post(
    c.APPROVE_ROLE_BRIEF_PATH, response_model=RoleBriefResponse, name="approve_role_brief"
)
async def approve_role_brief(
    run_id: uuid.UUID,
    body: ApproveRoleBriefRequest,
    principal: Annotated[
        Principal, Depends(require_permission(c.PERMISSION_ROLE_BRIEF_APPROVE))
    ],
    service: ServiceDep,
) -> RoleBriefResponse:
    try:
        return await service.approve(principal, run_id, body.role_brief_version_id)
    except RoleBriefNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from None
    except RoleBriefConflictError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Role brief cannot be approved"
        ) from None
