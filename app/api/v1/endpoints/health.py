"""Health check endpoint for Render monitoring and uptime checks."""
from datetime import datetime, timezone
from fastapi import APIRouter
from app.core.config import settings
from app.services.silogtran_client import silogtran_client

router = APIRouter()


@router.get("/health", summary="Health check del servicio")
async def health_check():
    """
    Endpoint público de comprobación de estado para Render.
    No expone información sensible ni credenciales.
    """
    is_valid = await silogtran_client.is_session_valid()
    return {
        "status": "ok",
        "version": settings.VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "silogtran_session": "active" if is_valid else "inactive"
    }
