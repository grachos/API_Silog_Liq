"""Tests for simulated Silogtran login, PRADO state handling, and cost center selection."""
import pytest
import httpx
from app.core.exceptions import (
    SilogtranAuthFailedError,
    SilogtranCostCenterNotFoundError,
)
from app.services.prado_parser import PradoParser
from app.services.silogtran_client import SilogtranClient
from tests.conftest import (
    HTML_COST_CENTER_MISSING_PAGE,
    HTML_COST_CENTER_PAGE,
    HTML_DASHBOARD_PAGE,
    HTML_LOGIN_PAGE,
    HTML_REPORT_PAGE,
    SAMPLE_CSV_VALID,
)


def test_prado_parser_login_fields():
    """Extracts hidden fields and detects user/pass fields from login HTML."""
    action, hidden = PradoParser.extract_form_and_hidden_fields(HTML_LOGIN_PAGE, "https://construproyec.colombiasoftware.net")
    assert hidden.get("PRADO_PAGESTATE") == "STATE_LOGIN_PAGE_123"

    user_f, pass_f, submit_f = PradoParser.find_login_inputs(HTML_LOGIN_PAGE)
    assert user_f == "txtUsuario"
    assert pass_f == "txtClave"
    assert submit_f == "btnIngresar"


def test_prado_parser_cost_center_matching():
    """Identifies CONSTRUPROYEC-PRINCIPAL and rejects CONSORCIO."""
    match = PradoParser.find_cost_center_option(HTML_COST_CENTER_PAGE, "CONSTRUPROYEC-PRINCIPAL")
    assert match is not None
    select_name, opt_val, opt_text = match
    assert select_name == "ddlCentroCosto"
    assert opt_val == "CC_101"
    assert "PRINCIPAL" in opt_text

    # Verify that searching for an unavailable cost center returns None
    missing_match = PradoParser.find_cost_center_option(HTML_COST_CENTER_MISSING_PAGE, "CONSTRUPROYEC-PRINCIPAL")
    assert missing_match is None


@pytest.mark.asyncio
async def test_simulated_login_success():
    """Simulates the full 2-step PRADO login flow using an httpx Mock transport."""
    def handler(request: httpx.Request):
        url_str = str(request.url)

        # Step 1: GET Login page
        if request.method == "GET" and "Login" in url_str:
            return httpx.Response(200, text=HTML_LOGIN_PAGE)

        # Step 2: POST Login credentials -> Silogtran responds with Cost Center selection
        if request.method == "POST" and "Login" in url_str:
            data = request.read().decode("utf-8")
            assert "STATE_LOGIN_PAGE_123" in data
            assert "test_user" in data
            return httpx.Response(
                200,
                text=HTML_COST_CENTER_PAGE,
                headers={"Set-Cookie": "PHPSESSID=session_pre_auth_123; path=/"}
            )

        # Step 3: POST Cost Center selection -> Silogtran responds with Dashboard
        if request.method == "POST" and "CentroCosto" in url_str:
            data = request.read().decode("utf-8")
            assert "CC_101" in data  # Principal value selected!
            assert "CONSTRUPROYEC-CONSORCIO" not in data
            return httpx.Response(
                200,
                text=HTML_DASHBOARD_PAGE,
                headers={"Set-Cookie": "PHPSESSID=session_authenticated_456; path=/"}
            )

        return httpx.Response(404)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)
    silogtran = SilogtranClient(client=mock_client)

    await silogtran.ensure_authenticated()
    assert await silogtran.is_session_valid() is True
    assert silogtran._is_authenticated is True


@pytest.mark.asyncio
async def test_cost_center_not_found_error():
    """When CONSTRUPROYEC-PRINCIPAL is not available, raises SILOGTRAN_COST_CENTER_NOT_FOUND."""
    def handler(request: httpx.Request):
        url_str = str(request.url)
        if request.method == "GET" and "Login" in url_str:
            return httpx.Response(200, text=HTML_LOGIN_PAGE)
        if request.method == "POST" and "Login" in url_str:
            # Returns page with only CONSORCIO
            return httpx.Response(200, text=HTML_COST_CENTER_MISSING_PAGE)
        return httpx.Response(404)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)
    silogtran = SilogtranClient(client=mock_client)

    with pytest.raises(SilogtranCostCenterNotFoundError) as exc_info:
        await silogtran.ensure_authenticated(force=True)

    assert exc_info.value.code == "SILOGTRAN_COST_CENTER_NOT_FOUND"
    assert "CONSTRUPROYEC-PRINCIPAL" in exc_info.value.message


@pytest.mark.asyncio
async def test_session_expiration_and_renewal():
    """Simulates session expiration on report page, which triggers auto-relogin and succeeds."""
    login_attempts = 0

    def handler(request: httpx.Request):
        nonlocal login_attempts
        url_str = str(request.url)

        if request.method == "GET" and "Login" in url_str:
            login_attempts += 1
            return httpx.Response(200, text=HTML_LOGIN_PAGE)

        if request.method == "POST" and "Login" in url_str:
            return httpx.Response(
                200,
                text=HTML_COST_CENTER_PAGE,
                headers={"Set-Cookie": f"PHPSESSID=sess_{login_attempts}; path=/"}
            )

        if request.method == "POST" and "CentroCosto" in url_str:
            return httpx.Response(200, text=HTML_DASHBOARD_PAGE)

        if request.method == "GET" and "InformeGeneral" in url_str:
            if login_attempts == 1:
                # First time: session expired, returns login page indicating session expired
                login_expired_html = HTML_LOGIN_PAGE.replace("<title>Silogtran - Login</title>", "<title>Silogtran - Login</title><h1>Iniciar Sesión</h1>")
                return httpx.Response(200, text=login_expired_html, request=request)
            # After re-login: returns report page
            return httpx.Response(200, text=HTML_REPORT_PAGE, request=request)

        if request.method == "POST" and "InformeGeneral" in url_str:
            return httpx.Response(
                200,
                content=SAMPLE_CSV_VALID.encode("utf-8"),
                headers={"Content-Type": "text/csv; charset=utf-8"}
            )

        return httpx.Response(404)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)
    silogtran = SilogtranClient(client=mock_client)

    csv_data = await silogtran.fetch_manifest_report("2026-01-01", "2026-01-31")
    assert len(csv_data) > 0
    # Verified that login was performed twice (initial + automatic re-authentication after expiration)
    assert login_attempts == 2
