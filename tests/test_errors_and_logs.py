"""Tests for error formatting, HTTP status codes, Silogtran timeouts, and log secret masking."""
import io
import logging
from unittest.mock import AsyncMock, patch
import pytest
from app.core.exceptions import SilogtranError, SilogtranTimeoutError
from app.core.logging import SecretMaskingFilter, StructuredFormatter
from app.services.cache import cache


@pytest.mark.asyncio
async def test_silogtran_timeout_response(app_client):
    """When Silogtran times out, API returns HTTP 504 with SILOGTRAN_TIMEOUT code."""
    await cache.clear()
    auth_headers = {"Authorization": "Bearer test_permanent_consumer_token_123"}

    with patch(
        "app.services.silogtran_client.SilogtranClient.fetch_manifest_report",
        new=AsyncMock(side_effect=SilogtranTimeoutError("Silogtran no respondió a tiempo."))
    ):
        resp = await app_client.get(
            "/api/v1/liquidaciones?fecha_inicio=2026-01-01&fecha_fin=2026-01-15",
            headers=auth_headers
        )
        assert resp.status_code == 504
        body = resp.json()
        assert body["success"] is False
        assert body["error"]["code"] == "SILOGTRAN_TIMEOUT"
        assert "no respondió" in body["error"]["message"]
        assert "request_id" in body["error"]


@pytest.mark.asyncio
async def test_silogtran_server_error_response(app_client):
    """When Silogtran fails unexpectedly, API returns HTTP 502 with SILOGTRAN_ERROR code."""
    await cache.clear()
    auth_headers = {"Authorization": "Bearer test_permanent_consumer_token_123"}

    with patch(
        "app.services.silogtran_client.SilogtranClient.fetch_manifest_report",
        new=AsyncMock(side_effect=SilogtranError("Fallo interno en Silogtran."))
    ):
        resp = await app_client.get(
            "/api/v1/liquidaciones?fecha_inicio=2026-01-01&fecha_fin=2026-01-15",
            headers=auth_headers
        )
        assert resp.status_code == 502
        body = resp.json()
        assert body["success"] is False
        assert body["error"]["code"] == "SILOGTRAN_ERROR"


def test_secret_masking_in_logs():
    """Verifies that no passwords, tokens, or session cookies ever leak into logs."""
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.addFilter(SecretMaskingFilter())
    handler.setFormatter(StructuredFormatter())

    test_logger = logging.getLogger("test.security")
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.INFO)

    secret_token = "tok_live_abcdef1234567890abcdef12"
    secret_pass = "super_secret_password_999"
    secret_cookie = "PHPSESSID=session_secret_cookie_val123"

    # Log messages containing sensitive data
    test_logger.info(f"Petición recibida con Authorization: Bearer {secret_token}")
    test_logger.info(f"Conectando a Silogtran con password={secret_pass} y usuario=admin")
    test_logger.info(f"Cookie recibida: {secret_cookie}")

    log_output = log_stream.getvalue()

    # Verify secrets are NOT present
    assert secret_token not in log_output
    assert secret_pass not in log_output
    assert "session_secret_cookie_val123" not in log_output

    # Verify redaction markers are present
    assert "***REDACTED" in log_output
