"""Manifest settlements query endpoint with caching and date validation."""
import logging
import math
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from app.api.deps import get_current_consumer_token
from app.core.config import settings
from app.core.exceptions import (
    DateRangeExceededError,
    DateRangeInvalidError,
    InvalidParametersError,
)
from app.models.schemas import (
    LiquidacionesMeta,
    LiquidacionesResponse,
    TokenInfo,
)
from app.services import liquidaciones_service

logger = logging.getLogger(__name__)
router = APIRouter()


def validate_and_parse_dates(fecha_inicio_str: str, fecha_fin_str: str) -> None:
    """
    Validates date formats (YYYY-MM-DD), ensures fecha_inicio <= fecha_fin,
    and checks that range does not exceed MAX_DATE_RANGE_DAYS.
    """
    date_format = "%Y-%m-%d"
    try:
        start_dt = datetime.strptime(fecha_inicio_str.strip(), date_format)
    except (ValueError, AttributeError):
        raise InvalidParametersError(
            f"La fecha de inicio '{fecha_inicio_str}' no tiene un formato válido (esperado: YYYY-MM-DD)."
        )

    try:
        end_dt = datetime.strptime(fecha_fin_str.strip(), date_format)
    except (ValueError, AttributeError):
        raise InvalidParametersError(
            f"La fecha de fin '{fecha_fin_str}' no tiene un formato válido (esperado: YYYY-MM-DD)."
        )

    if start_dt > end_dt:
        raise DateRangeInvalidError("La fecha de inicio no puede ser posterior a la fecha de fin.")

    diff_days = (end_dt - start_dt).days + 1
    if diff_days > settings.MAX_DATE_RANGE_DAYS:
        raise DateRangeExceededError(settings.MAX_DATE_RANGE_DAYS)


@router.get(
    "/liquidaciones",
    response_model=LiquidacionesResponse,
    summary="Consultar liquidación de manifiestos por rango de fechas",
    responses={
        200: {"description": "Consulta exitosa de liquidaciones"},
        400: {"description": "Rango de fechas inválido o formato incorrecto"},
        401: {"description": "Token de autenticación ausente o inválido"},
        429: {"description": "Límite de solicitudes superado"},
        502: {"description": "Error al comunicarse o procesar informe de Silogtran"},
        504: {"description": "Tiempo de espera agotado con Silogtran"},
    }
)
async def get_liquidaciones(
    fecha_inicio: str = Query(..., description="Fecha inicial en formato YYYY-MM-DD", openapi_examples={"default": {"value": "2026-01-01"}}),
    fecha_fin: str = Query(..., description="Fecha final en formato YYYY-MM-DD", openapi_examples={"default": {"value": "2026-01-31"}}),
    page: int = Query(default=1, ge=1, description="Número de página para paginar resultados"),
    page_size: int = Query(default=50, ge=1, le=500, description="Cantidad máxima de registros por página"),
    force_refresh: bool = Query(default=False, description="Forzar recarga omitiendo la caché temporal"),
    current_consumer: TokenInfo = Depends(get_current_consumer_token)
):
    """
    Consulta el informe general de liquidación de manifiestos en Silogtran.
    
    - Requiere token permanente en el encabezado `Authorization: Bearer <TOKEN>`.
    - Automatiza inicio de sesión, selección de centro de costo y descarga de CSV.
    - Soporta caché transparente con reuso de sub-rangos.
    """
    fecha_inicio = fecha_inicio.strip()
    fecha_fin = fecha_fin.strip()
    validate_and_parse_dates(fecha_inicio, fecha_fin)

    # 1-2. Assemble the range from per-month cache entries, fetching only missing months
    logger.info(
        f"Consumidor '{current_consumer.nombre}' consultando liquidaciones [{fecha_inicio} a {fecha_fin}]"
    )
    all_items, from_cache, generated_at = await liquidaciones_service.get_liquidaciones(
        fecha_inicio, fecha_fin, force_refresh=force_refresh
    )

    # 3. Apply pagination
    total_records = len(all_items)
    total_pages = max(1, math.ceil(total_records / page_size)) if total_records > 0 else 1
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_data = all_items[start_idx:end_idx]

    meta = LiquidacionesMeta(
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        total_registros=total_records,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        from_cache=from_cache,
        generated_at=generated_at
    )

    return LiquidacionesResponse(
        success=True,
        data=paginated_data,
        meta=meta
    )
