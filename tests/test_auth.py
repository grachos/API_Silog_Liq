"""Tests for consumer permanent token auth and token management endpoints."""
import pytest
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import generate_consumer_token, hash_token, timing_safe_compare
from app.models.token_store import TokenStore


@pytest.mark.asyncio
async def test_token_generation_and_hashing():
    """Generates a secure token with prefix and verifies hashing."""
    token = generate_consumer_token()
    assert token.startswith("tok_live_")
    assert len(token) > 40

    hashed = hash_token(token)
    assert len(hashed) == 64
    assert hash_token(token) == hashed


def test_timing_safe_compare():
    """Verifies constant-time comparison against exact and manipulated strings."""
    assert timing_safe_compare("secret_token_123", "secret_token_123") is True
    assert timing_safe_compare("secret_token_123", "secret_token_999") is False
    assert timing_safe_compare("", "secret_token_123") is False
    assert timing_safe_compare("secret_token_123", "") is False


@pytest.mark.asyncio
async def test_token_store_lifecycle():
    """Tests creation, verification, usage update, listing, and revocation in TokenStore."""
    store = TokenStore(file_path="test_tokens.json")

    # 1. Create token
    raw_token, token_info = await store.create_token("Cliente de Facturación")
    assert raw_token.startswith("tok_live_")
    assert token_info.nombre == "Cliente de Facturación"
    assert token_info.activo is True

    # 2. Verify token
    verified = await store.verify_token(raw_token)
    assert verified is not None
    assert verified.id == token_info.id
    assert verified.last_used_at is not None

    # 3. Invalid token returns None
    assert await store.verify_token("tok_live_invalid_nonexistent") is None

    # 4. List tokens
    token_list = await store.list_tokens()
    assert len(token_list) >= 1
    assert any(t.id == token_info.id for t in token_list)

    # 5. Revoke token
    revoked = await store.revoke_token(token_info.id)
    assert revoked is True

    # 6. Verify revoked token returns None
    assert await store.verify_token(raw_token) is None


@pytest.mark.asyncio
async def test_admin_token_endpoints(app_client):
    """Tests /api/v1/admin/tokens creation, listing, and revocation via API."""
    admin_headers = {"Authorization": "Bearer test_admin_secret_key_456"}

    # Unauthorized access without admin key
    resp_unauth = await app_client.post("/api/v1/admin/tokens", json={"nombre": "Nuevo Cliente"})
    assert resp_unauth.status_code == 403

    # Authorized creation
    resp_create = await app_client.post(
        "/api/v1/admin/tokens",
        json={"nombre": "Integración ERP"},
        headers=admin_headers
    )
    assert resp_create.status_code == 200
    data = resp_create.json()
    assert data["success"] is True
    created_token = data["token"]
    token_id = data["token_info"]["id"]
    assert created_token.startswith("tok_live_")

    # List tokens
    resp_list = await app_client.get("/api/v1/admin/tokens", headers=admin_headers)
    assert resp_list.status_code == 200
    items = resp_list.json()["data"]
    assert any(item["id"] == token_id for item in items)

    # Revoke token
    resp_revoke = await app_client.post(f"/api/v1/admin/tokens/{token_id}/revoke", headers=admin_headers)
    assert resp_revoke.status_code == 200
    assert resp_revoke.json()["success"] is True

    # Attempting to use the revoked token in protected endpoint should fail (401)
    resp_use = await app_client.get(
        "/api/v1/liquidaciones?fecha_inicio=2026-01-01&fecha_fin=2026-01-15",
        headers={"Authorization": f"Bearer {created_token}"}
    )
    assert resp_use.status_code == 401
    assert resp_use.json()["error"]["code"] == "TOKEN_INVALID"
