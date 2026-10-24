"""What clients see when PostgreSQL is unreachable: a stable 503, never a 500 or a leak."""

import httpx
import pytest

from app.db.session import create_engine, create_session_factory
from app.main import create_app


@pytest.mark.parametrize(
    "database_url",
    [
        # Nothing listening on the port: ConnectionRefusedError.
        "postgresql+asyncpg://knowledge:knowledge@127.0.0.1:1/knowledge",
        # Host does not resolve, as when the `db` container is stopped: socket.gaierror.
        "postgresql+asyncpg://knowledge:knowledge@db-host-that-does-not-exist.invalid:5432/knowledge",
    ],
    ids=["connection-refused", "unknown-host"],
)
async def test_database_outage_returns_stable_503(settings, services, database_url):
    broken_settings = settings.model_copy(update={"database_url": database_url, "db_pool_timeout_s": 2})
    broken = create_engine(broken_settings)
    services.engine = broken
    services.session_factory = create_session_factory(broken)
    app = create_app(settings, services)

    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            listing = await client.get("/documents")
            ask = await client.post("/ask", json={"question": "How do refunds work?"})
            ready = await client.get("/ready")
    finally:
        await broken.dispose()

    for response in (listing, ask):
        assert response.status_code == 503, response.text
        assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
        assert "127.0.0.1" not in response.text and ".invalid" not in response.text
    assert ready.status_code == 503
    assert ready.json()["checks"]["database"].startswith("error")
