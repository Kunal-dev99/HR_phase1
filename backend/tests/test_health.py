from httpx import ASGITransport, AsyncClient

from app.core.settings import Settings
from app.main import create_app

URL = "postgresql+asyncpg://u:p@localhost:5432/hr_phase1_p1req_copy"


async def test_healthz_ok() -> None:
    app = create_app(Settings(_env_file=None, DATABASE_URL=URL))  # type: ignore[call-arg]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
