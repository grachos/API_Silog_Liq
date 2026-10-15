"""Pytest fixtures, mock HTTP clients, sample PRADO HTML responses, and sample CSV data."""
import os
import pytest
import pytest_asyncio
import httpx
from app.core.config import settings
from app.models.token_store import TokenStore, token_store
from app.services.cache import InMemoryCache, cache

# Set deterministic test configuration
os.environ["API_TOKEN"] = "test_permanent_consumer_token_123"
os.environ["ADMIN_API_KEY"] = "test_admin_secret_key_456"
os.environ["SILOGTRAN_USERNAME"] = "test_user"
os.environ["SILOGTRAN_PASSWORD"] = "test_secret_pass"
os.environ["SILOGTRAN_COST_CENTER"] = "CONSTRUPROYEC-PRINCIPAL"
os.environ["TOKEN_STORAGE_PATH"] = "test_tokens.json"

settings.API_TOKEN = "test_permanent_consumer_token_123"
settings.ADMIN_API_KEY = "test_admin_secret_key_456"
settings.SILOGTRAN_USERNAME = "test_user"
settings.SILOGTRAN_PASSWORD = "test_secret_pass"
settings.SILOGTRAN_COST_CENTER = "CONSTRUPROYEC-PRINCIPAL"
settings.TOKEN_STORAGE_PATH = "test_tokens.json"


# Sample HTML for PRADO Login
HTML_LOGIN_PAGE = """<!DOCTYPE html>
<html>
<head><title>Silogtran - Login</title></head>
<body>
<form name="loginForm" method="post" action="/index.php?page=Login">
    <input type="hidden" name="PRADO_PAGESTATE" value="STATE_LOGIN_PAGE_123" />
    <input type="hidden" name="PRADO_POSTBACK_TARGET" value="" />
    <input type="text" name="txtUsuario" id="txtUsuario" />
    <input type="password" name="txtClave" id="txtClave" />
    <input type="submit" name="btnIngresar" value="Ingresar" />
</form>
</body>
</html>"""

# Sample HTML for PRADO Cost Center selection
HTML_COST_CENTER_PAGE = """<!DOCTYPE html>
<html>
<head><title>Silogtran - Centro de Costo</title></head>
<body>
<form name="costCenterForm" method="post" action="/index.php?page=CentroCosto">
    <input type="hidden" name="PRADO_PAGESTATE" value="STATE_COST_CENTER_456" />
    <label>Centro de Costo:</label>
    <select name="ddlCentroCosto" id="ddlCentroCosto">
        <option value="">Seleccione un centro de costo</option>
        <option value="CC_101">CONSTRUPROYEC-PRINCIPAL</option>
        <option value="CC_102">CONSTRUPROYEC-CONSORCIO</option>
    </select>
    <input type="submit" name="btnContinuar" value="Continuar" />
</form>
</body>
</html>"""

# Sample HTML when principal cost center is missing
HTML_COST_CENTER_MISSING_PAGE = """<!DOCTYPE html>
<html>
<head><title>Silogtran - Centro de Costo</title></head>
<body>
<form name="costCenterForm" method="post" action="/index.php?page=CentroCosto">
    <input type="hidden" name="PRADO_PAGESTATE" value="STATE_CC_MISSING" />
    <select name="ddlCentroCosto">
        <option value="">Seleccione un centro de costo</option>
        <option value="CC_102">CONSTRUPROYEC-CONSORCIO</option>
    </select>
    <input type="submit" name="btnContinuar" value="Continuar" />
</form>
</body>
</html>"""

# Sample HTML for Landing Page (After successful login and cost center)
HTML_DASHBOARD_PAGE = """<!DOCTYPE html>
<html>
<head><title>Silogtran - Inicio</title></head>
<body>
    <div class="user-info">Bienvenido, Usuario Test | Centro: CONSTRUPROYEC-PRINCIPAL</div>
    <a href="/index.php?page=Despacho.Liquidacionmanifiesto.InformeGeneral_111">Informe Liquidación</a>
</body>
</html>"""

# Sample HTML for Report Page
HTML_REPORT_PAGE = """<!DOCTYPE html>
<html>
<head><title>Silogtran - Informe General Liquidación</title></head>
<body>
<form name="reportForm" method="post" action="/index.php?page=Despacho.Liquidacionmanifiesto.InformeGeneral_111">
    <input type="hidden" name="PRADO_PAGESTATE" value="STATE_REPORT_789" />
    <input type="text" name="txtFechaDesde" id="txtFechaDesde" value="" />
    <input type="text" name="txtFechaHasta" id="txtFechaHasta" value="" />
    <input type="submit" name="btnGenerar" value="Generar" />
</form>
</body>
</html>"""

# Sample CSV standard with Colombian formatting
SAMPLE_CSV_VALID = (
    "NUMERO MANIFIESTO;FECHA;PLACA;CONDUCTOR;DOCUMENTO CONDUCTOR;ORIGEN;DESTINO;VALOR FLETE;VALOR ANTICIPO;VALOR RETENCION;VALOR DESCUENTO;VALOR NETO;ESTADO;OBSERVACIONES\n"
    "M-2026-000123;15/01/2026;ABC123;JUAN PEREZ;12345678;BOGOTA;MEDELLIN;$ 1.500.000,50;500.000,00;15.000,00;0,00;985.000,50;LIQUIDADO;DESPACHO NORMAL\n"
    "M-2026-000124;20/01/2026;XYZ789;CARLOS LOPEZ;87654321;CALI;BARRANQUILLA;2.400.000,00;800.000,00;24.000,00;10.000,00;1.566.000,00;LIQUIDADO;\n"
)


@pytest.fixture(autouse=True)
def clean_test_environment():
    """Cleans cache and test token files before/after each test."""
    if os.path.exists("test_tokens.json"):
        try:
            os.remove("test_tokens.json")
        except Exception:
            pass
    yield
    if os.path.exists("test_tokens.json"):
        try:
            os.remove("test_tokens.json")
        except Exception:
            pass


@pytest_asyncio.fixture
async def async_cache():
    """Provides an isolated clean memory cache."""
    c = InMemoryCache(max_entries=100, default_ttl=900)
    await c.clear()
    return c


@pytest_asyncio.fixture
async def app_client():
    """Async HTTP client to test FastAPI endpoints."""
    from app.main import app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
