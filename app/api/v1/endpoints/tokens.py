"""Administrative endpoints for consumer permanent token management."""
import logging
from fastapi import APIRouter, Depends, Path
from app.api.deps import require_admin_auth
from app.core.exceptions import InvalidParametersError
from app.models.schemas import (
    TokenCreateRequest,
    TokenCreateResponse,
    TokenListResponse,
    TokenRevokeResponse,
)
from app.models.token_store import token_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/tokens", tags=["Admin Tokens"])


@router.post(
    "",
    response_model=TokenCreateResponse,
    summary="Generar un nuevo token permanente para un consumidor",
    dependencies=[Depends(require_admin_auth)]
)
async def create_token(body: TokenCreateRequest):
    """
    Crea un nuevo token permanente criptográfico.
    
    IMPORTANTE: El valor plano del token solo se muestra en esta respuesta.
    No se almacena en texto plano en el servidor ni volverá a ser mostrado.
    """
    raw_token, token_info = await token_store.create_token(nombre=body.nombre.strip())
    logger.info(f"Token permanente creado exitosamente para: '{token_info.nombre}' (id={token_info.id})")
    return TokenCreateResponse(
        success=True,
        token=raw_token,
        token_info=token_info,
        warning="Guarde este token ahora. No volverá a mostrarse completo."
    )


@router.get(
    "",
    response_model=TokenListResponse,
    summary="Listar metadatos de tokens de consumidores",
    dependencies=[Depends(require_admin_auth)]
)
async def list_tokens():
    """
    Lista todos los tokens registrados con su estado y auditoría.
    Nunca expone el token en texto plano ni hashes completos.
    """
    tokens = await token_store.list_tokens()
    return TokenListResponse(success=True, data=tokens)


@router.post(
    "/{token_id}/revoke",
    response_model=TokenRevokeResponse,
    summary="Revocar un token de consumidor",
    dependencies=[Depends(require_admin_auth)]
)
async def revoke_token(
    token_id: str = Path(..., description="Identificador único del token a revocar")
):
    """
    Revoca inmediatamente un token permanente.
    Las solicitudes futuras con dicho token serán rechazadas con HTTP 401.
    """
    success = await token_store.revoke_token(token_id)
    if not success:
        raise InvalidParametersError(f"No se encontró el token con ID '{token_id}' para revocar.")

    logger.info(f"Token ID '{token_id}' revocado exitosamente.")
    return TokenRevokeResponse(
        success=True,
        message=f"El token con ID '{token_id}' ha sido revocado exitosamente."
    )
