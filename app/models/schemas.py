"""Pydantic schemas and data models for API requests and responses."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class LiquidacionItem(BaseModel):
    """Representa una fila procesada de la liquidación de manifiesto."""
    id_manifiesto: Optional[int] = Field(default=None, description="Identificador numérico del manifiesto si está disponible")
    numero_manifiesto: str = Field(description="Número de manifiesto de carga")
    fecha: Optional[str] = Field(default=None, description="Fecha del manifiesto o liquidación en formato ISO (YYYY-MM-DD)")
    placa: Optional[str] = Field(default=None, description="Placa del vehículo")
    conductor: Optional[str] = Field(default=None, description="Nombre o identificación del conductor")
    documento_conductor: Optional[str] = Field(default=None, description="Número de cédula o documento del conductor")
    origen: Optional[str] = Field(default=None, description="Ciudad o municipio de origen")
    destino: Optional[str] = Field(default=None, description="Ciudad o municipio de destino")
    valor_flete: Optional[float] = Field(default=None, description="Valor del flete en pesos colombianos")
    valor_anticipo: Optional[float] = Field(default=None, description="Valor de anticipos")
    valor_retencion: Optional[float] = Field(default=None, description="Valor de retenciones aplicadas")
    valor_descuento: Optional[float] = Field(default=None, description="Valor de descuentos o deducciones")
    valor_neto: Optional[float] = Field(default=None, description="Valor neto a pagar")
    estado: Optional[str] = Field(default=None, description="Estado de la liquidación (ej. LIQUIDADO, ANULADO)")
    observaciones: Optional[str] = Field(default=None, description="Observaciones registradas")
    campos_adicionales: Dict[str, Any] = Field(default_factory=dict, description="Columnas adicionales detectadas en el CSV")


class LiquidacionesMeta(BaseModel):
    """Metadatos de la consulta de liquidaciones."""
    fecha_inicio: str = Field(description="Fecha inicial consultada (YYYY-MM-DD)")
    fecha_fin: str = Field(description="Fecha final consultada (YYYY-MM-DD)")
    total_registros: int = Field(description="Total de registros encontrados")
    page: int = Field(default=1, description="Número de página actual")
    page_size: int = Field(default=50, description="Cantidad de registros por página")
    total_pages: int = Field(default=1, description="Total de páginas disponibles")
    from_cache: bool = Field(description="Indica si la respuesta provino de la memoria caché")
    generated_at: str = Field(description="Fecha y hora de generación en ISO 8601")


class LiquidacionesResponse(BaseModel):
    """Respuesta exitosa de consulta de liquidaciones."""
    success: bool = True
    data: List[LiquidacionItem]
    meta: LiquidacionesMeta


class ErrorDetail(BaseModel):
    """Detalle del error en formato estandarizado."""
    code: str
    message: str
    request_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    """Estructura de respuesta de error unificada."""
    success: bool = False
    error: ErrorDetail


class TokenCreateRequest(BaseModel):
    """Solicitud de creación de token permanente."""
    nombre: str = Field(min_length=2, max_length=100, description="Nombre o descripción del consumidor")


class TokenInfo(BaseModel):
    """Información pública del token."""
    id: str
    nombre: str
    prefijo: str
    activo: bool
    created_at: str
    last_used_at: Optional[str] = None
    revoked_at: Optional[str] = None


class TokenCreateResponse(BaseModel):
    """Respuesta de creación con token en texto plano (una sola vez)."""
    success: bool = True
    token: str = Field(description="Token de acceso permanente. Guárdelo en un lugar seguro.")
    token_info: TokenInfo
    warning: str = "Guarde este token ahora. No volverá a mostrarse completo."


class TokenListResponse(BaseModel):
    """Listado de tokens administrados."""
    success: bool = True
    data: List[TokenInfo]


class TokenRevokeResponse(BaseModel):
    """Respuesta a revocación de token."""
    success: bool = True
    message: str


class HealthResponse(BaseModel):
    """Estado de salud de la API."""
    status: str = "ok"
    version: str
    timestamp: str
    silogtran_session: str
