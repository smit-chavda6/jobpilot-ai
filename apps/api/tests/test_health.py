import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.main import app


@pytest.mark.asyncio
async def test_healthz_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data
        assert "X-Request-ID" in response.headers


@pytest.mark.asyncio
async def test_readyz_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/readyz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"


@pytest.mark.asyncio
async def test_error_envelope_format_on_404():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/non_existent_route")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "HTTP_404"
        assert "request_id" in data["error"]
