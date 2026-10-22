"""Eligibility rules v1 (BE-1.6, D-07)."""

import os
from unittest import mock

from app.core.settings import Settings
from app.modules.integrations.adapters.hr_system.mock import MockHRSystemAdapter
from app.modules.integrations.schemas import HRRequisitionPayload
from app.modules.requisitions.constants import (
    DEFAULT_ELIGIBLE_SOURCE_STATUSES,
    ELIGIBILITY_REQUIRED_FIELDS,
    ELIGIBILITY_RULES_VERSION,
    CompletionReason,
)
from app.modules.requisitions.service import check_eligibility

URL = "postgresql+asyncpg://u:p@localhost:5432/hr_phase1_p1req_copy"
OPEN = ("open",)


def _payload(**fields: object) -> HRRequisitionPayload:
    base: dict[str, object] = {
        "external_requisition_id": "REQ-E-1",
        "status": "open",
        "business_unit": "bu-1",
        "title": "Analyst",
        "description": "Analyse things.",
    }
    base.update(fields)
    return HRRequisitionPayload.model_validate({k: v for k, v in base.items() if v is not ...})


def test_default_setting_is_open_only() -> None:
    settings = Settings(_env_file=None, DATABASE_URL=URL)  # type: ignore[call-arg]
    assert settings.REQUISITION_ELIGIBLE_SOURCE_STATUSES == ("open",)
    assert settings.REQUISITION_ELIGIBLE_SOURCE_STATUSES == DEFAULT_ELIGIBLE_SOURCE_STATUSES
    env = {"REQUISITION_ELIGIBLE_SOURCE_STATUSES": '["open","on_hold"]'}
    with mock.patch.dict(os.environ, env):
        configured = Settings(_env_file=None, DATABASE_URL=URL)  # type: ignore[call-arg]
    assert configured.REQUISITION_ELIGIBLE_SOURCE_STATUSES == ("open", "on_hold")
    assert ELIGIBILITY_REQUIRED_FIELDS == ("title", "description")


async def test_open_complete_eligible() -> None:
    result = check_eligibility(await MockHRSystemAdapter().get_requisition("REQ-OPEN-1"), OPEN)
    assert result.eligible is True
    assert result.reason_code is None
    assert result.missing_fields == ()
    assert result.rules_version == ELIGIBILITY_RULES_VERSION == "1"

    # Status comparison ignores case and surrounding whitespace only.
    assert check_eligibility(_payload(status=" OPEN "), OPEN).eligible is True
    # Optional System Design §5 inputs are not required at ingestion (D-07).
    minimal = _payload()
    assert minimal.responsibilities is None and minimal.location is None
    assert check_eligibility(minimal, OPEN).eligible is True


async def test_closed_not_eligible() -> None:
    closed = await MockHRSystemAdapter().get_requisition("REQ-CLOSED-1")
    result = check_eligibility(closed, OPEN)
    assert result.eligible is False
    assert result.reason_code is CompletionReason.REQUISITION_NOT_ELIGIBLE_STATUS
    assert result.missing_fields == ()

    for status in ("on_hold", "draft", "opened", "cancelled"):
        assert (
            check_eligibility(_payload(status=status), OPEN).reason_code
            is CompletionReason.REQUISITION_NOT_ELIGIBLE_STATUS
        ), status

    # The setting decides: the same requisition is eligible if "closed" is configured,
    # and an empty configuration makes nothing eligible (fail closed).
    assert check_eligibility(closed, ("open", "closed")).eligible is True
    assert check_eligibility(_payload(), ()).eligible is False

    # A disallowed status wins over missing fields, which are still reported.
    both = check_eligibility(_payload(status="closed", description=None), OPEN)
    assert both.reason_code is CompletionReason.REQUISITION_NOT_ELIGIBLE_STATUS
    assert both.missing_fields == ("description",)


async def test_missing_title_or_description_incomplete() -> None:
    incomplete = await MockHRSystemAdapter().get_requisition("REQ-INCOMPLETE-1")
    before = incomplete.model_dump()
    result = check_eligibility(incomplete, OPEN)
    assert result.eligible is False
    assert result.reason_code is CompletionReason.REQUISITION_INCOMPLETE
    assert result.missing_fields == ("description",)
    # Nothing was filled in on the payload.
    assert incomplete.model_dump() == before
    assert incomplete.description is None

    cases = {
        "title missing": (_payload(title=...), ("title",)),
        "title blank": (_payload(title="   "), ("title",)),
        "description empty": (_payload(description=""), ("description",)),
        "both missing": (_payload(title=None, description="\n\t"), ("title", "description")),
    }
    for label, (payload, expected) in cases.items():
        outcome = check_eligibility(payload, OPEN)
        assert outcome.reason_code is CompletionReason.REQUISITION_INCOMPLETE, label
        assert outcome.missing_fields == expected, label
