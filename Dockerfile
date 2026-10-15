# ==============================================================================
# Dockerfile para Render (Optimizado para 512 MB de RAM)
# ==============================================================================
FROM python:3.11-slim as base

# Evitar escritura de .pyc y forzar buffer de stdout/stderr inmediato
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Instalar dependencias del sistema mínimas requeridas
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar requerimientos e instalar sin cache de pip para reducir imagen y RAM
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Crear usuario sin privilegios por seguridad
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

# Copiar el código fuente
COPY --chown=appuser:appuser . .

# Exponer el puerto
EXPOSE 8000

# Healthcheck interno
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Comando de inicio con 1 solo worker para mantenerse dentro de 512 MB RAM
CMD ["sh", "-c", "gunicorn -k uvicorn.workers.UvicornWorker -w 1 -b 0.0.0.0:${PORT:-8000} app.main:app"]
