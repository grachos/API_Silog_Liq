"""API v1 router aggregator."""
from fastapi import APIRouter
from app.api.v1.endpoints import liquidaciones, tokens

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(liquidaciones.router, tags=["Liquidaciones"])
api_router.include_router(tokens.router)
