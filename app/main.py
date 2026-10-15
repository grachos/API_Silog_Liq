"""Main FastAPI application entry point."""
import asyncio
import contextlib
import logging
import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logging import request_id_ctx, setup_logging
from app.services.silogtran_client import silogtran_client

# Initialize logging configuration with secret masking
setup_logging()
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logger.info(f"Iniciando {settings.PROJECT_NAME} v{settings.VERSION} en ambiente '{settings.ENVIRONMENT}'...")
    keepalive_task = None
    if settings.SILOGTRAN_KEEPALIVE_SECONDS > 0 and settings.SILOGTRAN_USERNAME and settings.SILOGTRAN_PASSWORD:
        keepalive_task = asyncio.create_task(silogtran_client.run_keepalive_loop())
    yield
    logger.info("Cerrando recursos y conexiones de la aplicación...")
    if keepalive_task:
        keepalive_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await keepalive_task
    await silogtran_client.invalidate_session()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "API REST para la consulta y extracción automatizada del informe general de liquidación "
        "de manifiestos desde la plataforma Silogtran (PRADO Framework) con despliegue en Render."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context_and_logging_middleware(request: Request, call_next):
    """
    Assigns a unique request_id to every incoming request, measures duration,
    and logs structured execution metrics.
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
    token = request_id_ctx.set(request_id)
    start_time = time.time()

    try:
        response = await call_next(request)
        duration_ms = round((time.time() - start_time) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            f"{request.method} {request.url.path} - Status: {response.status_code} - Duration: {duration_ms}ms"
        )
        return response
    except Exception as exc:
        duration_ms = round((time.time() - start_time) * 1000, 2)
        logger.error(
            f"{request.method} {request.url.path} - Unhandled exception after {duration_ms}ms: {exc}",
            exc_info=True
        )
        raise exc
    finally:
        request_id_ctx.reset(token)


# Centralized Exception Handlers
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """Handles custom domain and integration exceptions with standard JSON schema."""
    req_id = request_id_ctx.get() or request.headers.get("X-Request-ID", "-")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": req_id
            }
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Converts Pydantic parameter validation errors into clean Spanish responses."""
    req_id = request_id_ctx.get() or request.headers.get("X-Request-ID", "-")
    error_messages = []
    for error in exc.errors():
        loc = " -> ".join(str(l) for l in error.get("loc", []))
        msg = error.get("msg", "Parámetro inválido")
        error_messages.append(f"{loc}: {msg}")

    return JSONResponse(
        status_code=400,
        content={
            "success": False,
            "error": {
                "code": "INVALID_PARAMETERS",
                "message": f"Parámetros de consulta inválidos. {'; '.join(error_messages)}",
                "request_id": req_id
            }
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all handler to avoid leaking internal server stack traces to consumers."""
    req_id = request_id_ctx.get() or request.headers.get("X-Request-ID", "-")
    logger.critical(f"Error interno no controlado: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Ha ocurrido un error interno en el servidor. Intente más tarde.",
                "request_id": req_id
            }
        }
    )


@app.get("/", include_in_schema=False)
async def root():
    """Redirects the base URL to the interactive API documentation."""
    return RedirectResponse(url="/docs")


# Include routes
app.include_router(health_router)
app.include_router(api_router)
