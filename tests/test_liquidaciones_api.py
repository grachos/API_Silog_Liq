"""Integration tests for the /api/v1/liquidaciones endpoint and /health."""
from unittest.mock import AsyncMock, patch
import pytest
from app.services.cache import cache
from tests.conftest import SAMPLE_CSV_VALID


@pytest.mark.asyncio
async def test_health_check_endpoint(app_client):
    """GET /health returns status ok without exposing sensitive info."""
    resp = await app_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_get_liquidaciones_e2e(app_client):
    """Tests complete liquidaciones query with mock Silogtran response."""
    await cache.clear()
    auth_headers = {"Authorization": "Bearer test_permanent_consumer_token_123"}

    # Mock fetch_manifest_report to return valid sample CSV
    with patch(
        "app.services.silogtran_client.SilogtranClient.fetch_manifest_report",
        new=AsyncMock(return_value=SAMPLE_CSV_VALID.encode("utf-8"))
    ) as mock_fetch:
        # First query (Cache Miss)
        resp1 = await app_client.get(
            "/api/v1/liquidaciones?fecha_inicio=2026-01-01&fecha_fin=2026-01-31&page=1&page_size=10",
            headers=auth_headers
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["success"] is True
        assert len(data1["data"]) == 2
        assert data1["meta"]["from_cache"] is False
        assert data1["meta"]["total_registros"] == 2
        assert data1["data"][0]["numero_manifiesto"] == "M-2026-000123"
        assert data1["data"][0]["valor_flete"] == 1500000.5
        assert mock_fetch.call_count == 1

        # Second query (Cache Hit - instant response, mock_fetch should NOT be called again)
        resp2 = await app_client.get(
            "/api/v1/liquidaciones?fecha_inicio=2026-01-01&fecha_fin=2026-01-31&page=1&page_size=10",
            headers=auth_headers
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["success"] is True
        assert data2["meta"]["from_cache"] is True
        assert mock_fetch.call_count == 1  # Still 1, served from cache!

        # Third query with force_refresh=true (Bypasses cache, calls mock_fetch again)
        resp3 = await app_client.get(
            "/api/v1/liquidaciones?fecha_inicio=2026-01-01&fecha_fin=2026-01-31&force_refresh=true",
            headers=auth_headers
        )
        assert resp3.status_code == 200
        data3 = resp3.json()
        assert data3["meta"]["from_cache"] is False
        assert mock_fetch.call_count == 2


@pytest.mark.asyncio
async def test_get_liquidaciones_pagination(app_client):
    """Validates page and page_size pagination behavior."""
    await cache.clear()
    auth_headers = {"Authorization": "Bearer test_permanent_consumer_token_123"}

    with patch(
        "app.services.silogtran_client.SilogtranClient.fetch_manifest_report",
        new=AsyncMock(return_value=SAMPLE_CSV_VALID.encode("utf-8"))
    ):
        # Request page 1 with page_size=1
        resp_p1 = await app_client.get(
            "/api/v1/liquidaciones?fecha_inicio=2026-01-01&fecha_fin=2026-01-31&page=1&page_size=1",
            headers=auth_headers
        )
        assert resp_p1.status_code == 200
        data_p1 = resp_p1.json()
        assert len(data_p1["data"]) == 1
        assert data_p1["meta"]["total_registros"] == 2
        assert data_p1["meta"]["page"] == 1
        assert data_p1["meta"]["total_pages"] == 2
        assert data_p1["data"][0]["numero_manifiesto"] == "M-2026-000123"

        # Request page 2 with page_size=1
        resp_p2 = await app_client.get(
            "/api/v1/liquidaciones?fecha_inicio=2026-01-01&fecha_fin=2026-01-31&page=2&page_size=1",
            headers=auth_headers
        )
        assert resp_p2.status_code == 200
        data_p2 = resp_p2.json()
        assert len(data_p2["data"]) == 1
        assert data_p2["data"][0]["numero_manifiesto"] == "M-2026-000124"
