"""Custom exceptions and centralized error models for the API."""
from typing import Any, Dict, Optional


class AppException(Exception):
    """Base application exception."""
    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class InvalidParametersError(AppException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="INVALID_PARAMETERS",
            status_code=400,
            details=details
        )


class DateRangeInvalidError(AppException):
    def __init__(self, message: str = "El rango de fechas es inválido (fecha_inicio > fecha_fin)."):
        super().__init__(
            message=message,
            code="DATE_RANGE_INVALID",
            status_code=400
        )


class DateRangeExceededError(AppException):
    def __init__(self, max_days: int):
        super().__init__(
            message=f"El rango máximo permitido es de {max_days} días.",
            code="DATE_RANGE_EXCEEDED",
            status_code=400,
            details={"max_days": max_days}
        )


class UnauthorizedError(AppException):
    def __init__(self, message: str = "Token de API ausente o inválido.", code: str = "UNAUTHORIZED"):
        super().__init__(
            message=message,
            code=code,
            status_code=401
        )


class ForbiddenError(AppException):
    def __init__(self, message: str = "Acceso denegado. No tiene permisos suficientes."):
        super().__init__(
            message=message,
            code="FORBIDDEN",
            status_code=403
        )


class RateLimitExceededError(AppException):
    def __init__(self, message: str = "Límite de solicitudes excedido. Intente más tarde."):
        super().__init__(
            message=message,
            code="RATE_LIMIT_EXCEEDED",
            status_code=429
        )


class SilogtranTimeoutError(AppException):
    def __init__(self, message: str = "Silogtran no respondió dentro del tiempo esperado."):
        super().__init__(
            message=message,
            code="SILOGTRAN_TIMEOUT",
            status_code=504
        )


class SilogtranCostCenterNotFoundError(AppException):
    def __init__(self, cost_center_name: str):
        super().__init__(
            message=f"No se encontró el centro de costo principal '{cost_center_name}' en Silogtran.",
            code="SILOGTRAN_COST_CENTER_NOT_FOUND",
            status_code=502,
            details={"configured_cost_center": cost_center_name}
        )


class SilogtranAuthFailedError(AppException):
    def __init__(self, message: str = "Error en la autenticación con Silogtran. Verifique las credenciales."):
        super().__init__(
            message=message,
            code="SILOGTRAN_AUTH_FAILED",
            status_code=502
        )


class SilogtranError(AppException):
    def __init__(self, message: str = "Error inesperado al comunicarse con Silogtran.", code: str = "SILOGTRAN_ERROR"):
        super().__init__(
            message=message,
            code=code,
            status_code=502
        )


class CSVParseError(AppException):
    def __init__(self, message: str = "Error al procesar el archivo CSV generado por Silogtran."):
        super().__init__(
            message=message,
            code="CSV_PARSE_ERROR",
            status_code=502
        )
