"""Screening-run API (BE-2.3, BE-2.4, D-08, D-09, D-11)."""

from httpx import AsyncClient

from tests.conftest import dev_headers

URL = "/api/v1/screening-runs"


async def test_post_returns_202_with_run_id_and_status_url(screening_client: AsyncClient) -> None:
    response = await screening_client.post(
        URL,
        json={"external_requisition_id": "  REQ-OPEN-1  "},
        headers={**dev_headers(), "X-Correlation-ID": "corr-api-0001"},
    )
    assert response.status_code == 202
    body = response.json()
    assert set(body) == {"run_id", "status", "status_url", "correlation_id"}
    assert body["status"] == "created"
    assert body["status_url"] == f"{URL}/{body['run_id']}"
    assert response.headers["Location"] == body["status_url"]
    assert body["correlation_id"] == "corr-api-0001"
    assert response.headers["X-Correlation-ID"] == "corr-api-0001"

    extra = await screening_client.post(
        URL, json={"external_requisition_id": "REQ-OPEN-1", "x": 1}, headers=dev_headers()
    )
    assert extra.status_code == 422


async def test_post_without_principal_401(screening_client: AsyncClient) -> None:
    response = await screening_client.post(URL, json={"external_requisition_id": "REQ-OPEN-1"})
    assert response.status_code == 401


async def test_post_without_permission_403(screening_client: AsyncClient) -> None:
    response = await screening_client.post(
        URL,
        json={"external_requisition_id": "REQ-OPEN-1"},
        headers=dev_headers(permissions="screening_run:read"),
    )
    assert response.status_code == 403


async def _post_open(client: AsyncClient) -> str:
    response = await client.post(
        URL, json={"external_requisition_id": "REQ-OPEN-1"}, headers=dev_headers()
    )
    assert response.status_code == 202
    return str(response.json()["status_url"])


async def test_get_returns_state_and_phase_status(screening_client: AsyncClient) -> None:
    status_url = await _post_open(screening_client)
    response = await screening_client.get(status_url, headers=dev_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "role_brief_draft"
    assert body["phases"] == {"phase_1": "in_progress"}
    assert body["completion_reason"] is None
    requisition = body["requisition"]
    assert requisition["external_requisition_id"] == "REQ-OPEN-1"
    assert requisition["hr_system_key"] == "mock"
    assert requisition["payload_hash"].startswith("sha256:")
    assert requisition["snapshot_id"] and requisition["captured_at"]
    assert "payload" not in requisition and "payload" not in body


async def test_get_other_business_unit_404(screening_client: AsyncClient) -> None:
    status_url = await _post_open(screening_client)
    response = await screening_client.get(
        status_url, headers=dev_headers(business_units="bu-other", principal_id="other-1")
    )
    assert response.status_code == 404


async def test_get_without_permission_403(screening_client: AsyncClient) -> None:
    status_url = await _post_open(screening_client)
    response = await screening_client.get(
        status_url, headers=dev_headers(permissions="screening_run:create")
    )
    assert response.status_code == 403
