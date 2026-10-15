"""Tests for per-month report caching and background Silogtran session renewal."""
import time
from datetime import date
from unittest.mock import AsyncMock, patch
import httpx
import pytest
from app.core.config import settings
from app.services import liquidaciones_service
from app.services.liquidaciones_service import month_chunks, month_ttl
from app.services.silogtran_client import SilogtranClient
from tests.conftest import HTML_REPORT_PAGE, HTML_LOGIN_PAGE, SAMPLE_CSV_VALID

FETCH = "app.services.silogtran_client.SilogtranClient.fetch_manifest_report"


def test_month_chunks_cover_whole_months_across_years():
    assert month_chunks(date(2025, 12, 10), date(2026, 2, 5)) == [
        (date(2025, 12, 1), date(2025, 12, 31)),
        (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 2, 28)),
    ]


def test_closed_months_are_cached_longer_than_current_month():
    with patch.object(liquidaciones_service, "local_today", return_value=date(2026, 2, 10)):
        assert month_ttl(date(2026, 1, 31)) == settings.CACHE_CLOSED_MONTH_TTL_SECONDS
        assert month_ttl(date(2026, 2, 28)) == settings.CACHE_TTL_SECONDS


@pytest.mark.asyncio
async def test_partial_ranges_in_same_month_reuse_one_fetch():
    with patch(FETCH, new=AsyncMock(return_value=SAMPLE_CSV_VALID.encode("utf-8"))) as mock_fetch:
        first, first_cached, _ = await liquidaciones_service.get_liquidaciones("2026-01-01", "2026-01-15")
        second, second_cached, _ = await liquidaciones_service.get_liquidaciones("2026-01-16", "2026-01-31")

    mock_fetch.assert_awaited_once_with("2026-01-01", "2026-01-31")
    assert [i.numero_manifiesto for i in first] == ["M-2026-000123"]
    assert [i.numero_manifiesto for i in second] == ["M-2026-000124"]
    assert first_cached is False
    assert second_cached is True


@pytest.mark.asyncio
async def test_multi_month_range_fetches_each_month_once():
    with patch(FETCH, new=AsyncMock(return_value=SAMPLE_CSV_VALID.encode("utf-8"))) as mock_fetch:
        items, from_cache, _ = await liquidaciones_service.get_liquidaciones("2025-12-10", "2026-02-05")
        _, again_cached, _ = await liquidaciones_service.get_liquidaciones("2025-12-01", "2026-02-28")

    assert [c.args for c in mock_fetch.await_args_list] == [
        ("2025-12-01", "2025-12-31"),
        ("2026-01-01", "2026-01-31"),
        ("2026-02-01", "2026-02-28"),
    ]
    # Only January has rows in the sample CSV, and both fall inside the range
    assert len(items) == 2
    assert from_cache is False
    assert again_cached is True


@pytest.mark.asyncio
async def test_force_refresh_refetches_cached_months():
    with patch(FETCH, new=AsyncMock(return_value=SAMPLE_CSV_VALID.encode("utf-8"))) as mock_fetch:
        await liquidaciones_service.get_liquidaciones("2026-01-01", "2026-01-31")
        _, from_cache, _ = await liquidaciones_service.get_liquidaciones("2026-01-01", "2026-01-31", force_refresh=True)

    assert mock_fetch.await_count == 2
    assert from_cache is False


def _client_returning(html: str) -> SilogtranClient:
    def handler(request: httpx.Request):
        return httpx.Response(200, text=html)

    silogtran = SilogtranClient(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    silogtran._is_authenticated = True
    silogtran._authenticated_at = time.time() - 600
    return silogtran


@pytest.mark.asyncio
async def test_keepalive_logs_in_when_there_is_no_session():
    silogtran = SilogtranClient(client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(404))))
    with patch.object(silogtran, "ensure_authenticated", new=AsyncMock()) as mock_login:
        await silogtran.keep_session_alive()
    mock_login.assert_awaited_once()


@pytest.mark.asyncio
async def test_keepalive_extends_a_live_session_without_logging_in():
    silogtran = _client_returning(HTML_REPORT_PAGE)
    before = silogtran._authenticated_at
    with patch.object(silogtran, "ensure_authenticated", new=AsyncMock()) as mock_login:
        await silogtran.keep_session_alive()
    mock_login.assert_not_awaited()
    assert silogtran._authenticated_at > before


@pytest.mark.asyncio
async def test_keepalive_relogs_in_when_silogtran_returns_login_page():
    silogtran = _client_returning(HTML_LOGIN_PAGE.replace("<title>Silogtran - Login</title>", "<title>Iniciar sesión</title>"))
    with patch.object(silogtran, "ensure_authenticated", new=AsyncMock()) as mock_login:
        await silogtran.keep_session_alive()
    mock_login.assert_awaited_once()
    assert silogtran._is_authenticated is False  # invalidated before the mocked re-login


@pytest.mark.asyncio
async def test_keepalive_skips_while_a_report_request_is_running():
    silogtran = _client_returning(HTML_REPORT_PAGE)
    before = silogtran._authenticated_at
    async with silogtran._request_lock:
        await silogtran.keep_session_alive()
    assert silogtran._authenticated_at == before
