"""FastAPI dependencies for authentication, rate limiting, and authorization."""
import logging
from typing import Optional
from fastapi import Header, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.core.config import settings
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import timing_safe_compare
from app.models.schemas import TokenInfo
from app.models.token_store import token_store
from app.services.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)

# Registers Bearer auth in OpenAPI so /docs shows the "Authorize" button
bearer_scheme = HTTPBearer(auto_error=False, description="Token de API permanente")


def extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    """Extracts raw token from 'Bearer <token>' string."""
    if not authorization:
        return None
    parts = authorization.strip().split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


async def get_current_consumer_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
) -> TokenInfo:
    """
    Validates the consumer's permanent Bearer token.
    Applies rate limiting per token or client IP.
    """
    token_str = credentials.credentials.strip() if credentials else None
    if not token_str:
        logger.warning("Intento de acceso sin encabezado Authorization Bearer válido.")
        raise UnauthorizedError(
            message="Token de API ausente. Envíe el token mediante el encabezado 'Authorization: Bearer <TOKEN>'.",
            code="TOKEN_MISSING"
        )

    token_info = await token_store.verify_token(token_str)
    if not token_info or not token_info.activo:
        logger.warning("Intento de acceso con token inválido o revocado.")
        raise UnauthorizedError(
            message="Token de API inválido o revocado.",
            code="TOKEN_INVALID"
        )

    # Apply rate limiting by token ID (or fallback to client host)
    rate_limit_key = f"token:{token_info.id}"
    await rate_limiter.check(rate_limit_key)

    return token_info


async def require_admin_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key")
) -> bool:
    """
    Validates administrative access for creating/revoking tokens.
    Accepts ADMIN_API_KEY via Bearer or X-Admin-Key header, or falls back to API_TOKEN.
    """
    admin_key = settings.ADMIN_API_KEY or settings.API_TOKEN
    if not admin_key:
        logger.error("No se ha configurado ADMIN_API_KEY ni API_TOKEN para operaciones de administración.")
        raise ForbiddenError("La administración de tokens no está habilitada en la configuración del servidor.")

    candidate_token = (credentials.credentials.strip() if credentials else None) or x_admin_key

    if not candidate_token or not timing_safe_compare(candidate_token, admin_key):
        logger.warning("Intento fallido de autenticación administrativa.")
        raise ForbiddenError("Clave administrativa inválida o ausente.")

    return True
