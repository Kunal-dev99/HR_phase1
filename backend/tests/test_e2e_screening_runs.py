"""End-to-end acceptance over HTTP with RUN_EXECUTOR=inline (BE-2.5, D-18 trimmed)."""

from httpx import AsyncClient

from tests.conftest import dev_headers

URL = "/api/v1/screening-runs"


async def _run(client: AsyncClient, external_id: str) -> dict[str, object]:
    post = await client.post(
        URL, json={"external_requisition_id": external_id}, headers=dev_headers()
    )
    assert post.status_code == 202
    get = await client.get(post.json()["status_url"], headers=dev_headers())
    assert get.status_code == 200
    body: dict[str, object] = get.json()
    return body


async def test_open_requisition_reaches_role_brief_draft(screening_client: AsyncClient) -> None:
    body = await _run(screening_client, "REQ-OPEN-1")
    assert body["status"] == "role_brief_draft"


async def test_closed_requisition_is_blocked(screening_client: AsyncClient) -> None:
    body = await _run(screening_client, "REQ-CLOSED-1")
    assert body["status"] == "blocked"
    assert body["completion_reason"] == "requisition_not_eligible_status"
    assert body["phases"] == {"phase_1": "blocked"}
