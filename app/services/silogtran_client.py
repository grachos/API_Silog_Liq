"""Silogtran client automating PRADO authentication, cost center selection, and report retrieval."""
import asyncio
import logging
import time
from typing import Dict, Optional, Tuple
import httpx
from app.core.config import settings
from app.core.exceptions import (
    SilogtranAuthFailedError,
    SilogtranCostCenterNotFoundError,
    SilogtranError,
    SilogtranTimeoutError,
)
from app.services.prado_parser import PradoParser

logger = logging.getLogger(__name__)


class SilogtranClient:
    """
    Automates the legacy PRADO web flow for Silogtran:
    1. Authenticate with credentials.
    2. Detect and select mandatory Cost Center ('CONSTRUPROYEC-PRINCIPAL').
    3. Click 'Continuar' and verify session establishment.
    4. Maintain session cookies and automatically renew before expiration.
    5. Navigate to report page, submit date range, and download CSV report.
    """

    def __init__(self, client: Optional[httpx.AsyncClient] = None):
        self._custom_client = client
        self._client: Optional[httpx.AsyncClient] = None
        self._session_lock = asyncio.Lock()
        self._is_authenticated = False
        self._authenticated_at: Optional[float] = None
        self._session_cookie_name = "PHPSESSID"

    async def get_client(self) -> httpx.AsyncClient:
        """Returns or creates the HTTP client instance with cookie persistence."""
        if self._custom_client:
            return self._custom_client

        if self._client is None or self._client.is_closed:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "es-CO,es-419;q=0.9,es;q=0.8,en;q=0.7",
                "Connection": "keep-alive",
            }
            self._client = httpx.AsyncClient(
                headers=headers,
                follow_redirects=True,
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
            )
        return self._client

    async def is_session_valid(self) -> bool:
        """Checks if session is marked authenticated and within expected lifetime."""
        if not self._is_authenticated or self._authenticated_at is None:
            return False
        elapsed = time.time() - self._authenticated_at
        return elapsed < settings.SILOGTRAN_SESSION_LIFETIME_SECONDS

    async def invalidate_session(self) -> None:
        """Invalidates current session state."""
        self._is_authenticated = False
        self._authenticated_at = None
        if self._client and not self._custom_client:
            await self._client.aclose()
            self._client = None
        logger.info("Sesión de Silogtran invalidada.")

    async def ensure_authenticated(self, force: bool = False) -> None:
        """
        Thread/async-safe session verification.
        Uses a lock to prevent concurrent redundant logins.
        """
        async with self._session_lock:
            if not force and await self.is_session_valid():
                return

            logger.info("Iniciando autenticación contra Silogtran...")
            await self._perform_login()

    async def _perform_login(self) -> None:
        """Executes full PRADO login flow including cost center selection."""
        client = await self.get_client()

        # Step 1: Request Login Page
        try:
            resp_login_page = await client.get(settings.SILOGTRAN_LOGIN_URL)
        except httpx.TimeoutException as e:
            raise SilogtranTimeoutError(f"Tiempo de espera agotado al conectar con la página de login: {e}")
        except httpx.HTTPError as e:
            raise SilogtranError(f"Error de conexión con Silogtran: {e}")

        login_html = resp_login_page.text
        form_action, hidden_fields = PradoParser.extract_form_and_hidden_fields(
            login_html, str(resp_login_page.url)
        )

        user_field, pass_field, submit_name = PradoParser.find_login_inputs(
            login_html,
            custom_user_field=settings.SILOGTRAN_USER_FIELD,
            custom_pass_field=settings.SILOGTRAN_PASS_FIELD,
        )

        if not user_field or not pass_field:
            logger.warning(
                "No se detectaron campos estándar de usuario/clave; usando nombres por defecto."
            )
            user_field = user_field or "txtUsuario"
            pass_field = pass_field or "txtClave"

        login_payload: Dict[str, str] = dict(hidden_fields)
        login_payload[user_field] = settings.SILOGTRAN_USERNAME
        login_payload[pass_field] = settings.SILOGTRAN_PASSWORD
        if submit_name:
            login_payload[submit_name] = "Ingresar"

        # Step 2: Submit Credentials
        try:
            resp_post_login = await client.post(form_action, data=login_payload)
        except httpx.TimeoutException as e:
            raise SilogtranTimeoutError(f"Tiempo de espera agotado al enviar credenciales: {e}")
        except httpx.HTTPError as e:
            raise SilogtranError(f"Error al enviar credenciales a Silogtran: {e}")

        post_login_html = resp_post_login.text

        # Check for explicit login failures
        failure_keywords = [
            "usuario o clave incorrecta",
            "credenciales invalidas",
            "credenciales inválidas",
            "usuario no existe",
            "contraseña incorrecta",
            "clave erronea",
            "acceso no autorizado",
        ]
        if any(kw in post_login_html.lower() for kw in failure_keywords):
            logger.error("Silogtran rechazó las credenciales ingresadas.")
            raise SilogtranAuthFailedError()

        # Step 3: Cost Center Selection
        # Detect if cost center dropdown is present
        cost_center_target = settings.SILOGTRAN_COST_CENTER
        cc_match = PradoParser.find_cost_center_option(
            post_login_html,
            cost_center_target,
            custom_field_name=settings.SILOGTRAN_COST_CENTER_FIELD,
        )

        if cc_match:
            select_name, option_val, option_text = cc_match
            logger.info(
                f"Seleccionando centro de costo requerido: '{option_text}' (valor={option_val}) en campo '{select_name}'"
            )

            # Extract form and hidden fields from post-login response
            cc_form_action, cc_hidden = PradoParser.extract_form_and_hidden_fields(
                post_login_html, str(resp_post_login.url)
            )

            btn_info = PradoParser.find_continue_button(post_login_html)
            cc_payload: Dict[str, str] = dict(cc_hidden)
            cc_payload[select_name] = option_val

            if btn_info:
                btn_name, btn_val = btn_info
                cc_payload[btn_name] = btn_val

            try:
                resp_cc = await client.post(cc_form_action, data=cc_payload)
            except httpx.TimeoutException as e:
                raise SilogtranTimeoutError(f"Tiempo de espera agotado al seleccionar centro de costo: {e}")
            except httpx.HTTPError as e:
                raise SilogtranError(f"Error al enviar centro de costo a Silogtran: {e}")

            final_html = resp_cc.text
            final_url = str(resp_cc.url)
        else:
            # Check if a cost center select was present but our target was NOT in it
            if "select" in post_login_html.lower() and any(
                term in post_login_html.lower()
                for term in ("centro de costo", "centro_costo", "centrocosto", "cost center")
            ):
                logger.error(
                    f"El centro de costo principal '{cost_center_target}' no está disponible entre las opciones de Silogtran."
                )
                raise SilogtranCostCenterNotFoundError(cost_center_target)

            # If no cost center prompt was rendered, check if we landed directly in main application
            logger.info("No se requirió selección explícita de centro de costo o ya está preseleccionado.")
            final_html = post_login_html
            final_url = str(resp_post_login.url)

        # Step 4: Verify authentication state
        # In PRADO/Silogtran, a successful login will set cookies and exit the login page
        cookies = client.cookies
        has_session = any("sess" in c.lower() or "phpsessid" in c.lower() for c in cookies.keys())

        if not has_session and "login" in final_url.lower():
            logger.error("No se detectaron cookies de sesión activas después del inicio de sesión.")
            raise SilogtranAuthFailedError("No se pudo establecer la sesión en Silogtran.")

        self._is_authenticated = True
        self._authenticated_at = time.time()
        logger.info("Autenticación y selección de centro de costo exitosa en Silogtran.")

    async def fetch_manifest_report(
        self,
        fecha_inicio: str,
        fecha_fin: str,
        retry_count: int = 1
    ) -> bytes:
        """
        Navigates to the manifest settlement report page, submits the date range,
        and downloads the generated CSV file.
        """
        await self.ensure_authenticated()
        client = await self.get_client()

        # Step 1: GET Report Page
        try:
            resp_report_page = await client.get(settings.SILOGTRAN_REPORT_URL)
        except httpx.TimeoutException as e:
            raise SilogtranTimeoutError(f"Tiempo de espera agotado al cargar página de informe: {e}")
        except httpx.HTTPError as e:
            raise SilogtranError(f"Error al acceder al informe de Silogtran: {e}")

        # Check if session expired and was redirected to login
        if "page=login" in str(resp_report_page.url).lower() or "iniciar sesión" in resp_report_page.text.lower():
            logger.warning("La sesión expiró al intentar acceder al informe. Reautenticando...")
            await self.invalidate_session()
            if retry_count > 0:
                return await self.fetch_manifest_report(fecha_inicio, fecha_fin, retry_count=retry_count - 1)
            raise SilogtranAuthFailedError("Sesión expirada y no se pudo reconectar.")

        report_html = resp_report_page.text
        form_action, hidden_fields = PradoParser.extract_form_and_hidden_fields(
            report_html, str(resp_report_page.url)
        )

        date_start_field, date_end_field = PradoParser.find_date_fields(
            report_html,
            custom_start=settings.SILOGTRAN_DATE_START_FIELD,
            custom_end=settings.SILOGTRAN_DATE_END_FIELD,
        )

        date_start_field = date_start_field or "txtFechaDesde"
        date_end_field = date_end_field or "txtFechaHasta"

        submit_btn = PradoParser.find_report_submit_button(report_html)

        report_payload: Dict[str, str] = dict(hidden_fields)
        report_payload.update(PradoParser.extract_form_control_defaults(report_html))
        report_payload[date_start_field] = fecha_inicio
        report_payload[date_end_field] = fecha_fin

        # 'Tipo de Impresión' defaults to PDF, which cannot be parsed: pick a text-based format
        preferred = (
            (settings.SILOGTRAN_PRINT_TYPE.lower(),) if settings.SILOGTRAN_PRINT_TYPE
            else ("csv", "texto", "txt", "plano", "excel", "xls", "html", "pantalla")
        )
        print_type = PradoParser.find_print_type_option(
            report_html, preferred, custom_field_name=settings.SILOGTRAN_PRINT_TYPE_FIELD
        )
        if print_type:
            pt_field, pt_value, pt_text, pt_options = print_type
            logger.info(f"Opciones de 'Tipo de Impresión' en '{pt_field}': {pt_options}")
            if pt_value is not None:
                report_payload[pt_field] = pt_value
                logger.info(f"Tipo de impresión seleccionado: '{pt_text}' (valor={pt_value})")
            else:
                logger.warning("No hay opción CSV/Excel/HTML en 'Tipo de Impresión'; se usará la opción por defecto.")
        else:
            logger.warning("No se encontró el campo 'Tipo de Impresión' en el formulario del informe.")

        logger.info(
            f"Campos detectados en formulario: fecha_inicio='{date_start_field}', fecha_fin='{date_end_field}', "
            f"enviados={sorted(k for k in report_payload if not k.startswith('PRADO_'))}"
        )

        if submit_btn:
            btn_name, btn_val = submit_btn
            report_payload[btn_name] = btn_val
        else:
            report_payload["btnGenerar"] = "Generar"

        # Step 2: POST Date Range and Submit Report Request
        logger.info(
            f"Enviando solicitud de informe para rango [{fecha_inicio} a {fecha_fin}] a {form_action}"
        )
        try:
            resp_post_report = await client.post(form_action, data=report_payload)
        except httpx.TimeoutException as e:
            raise SilogtranTimeoutError(f"Tiempo de espera agotado al solicitar generación del informe: {e}")
        except httpx.HTTPError as e:
            raise SilogtranError(f"Error al solicitar el informe a Silogtran: {e}")

        # Check if response is directly the CSV file
        content_type = resp_post_report.headers.get("content-type", "").lower()
        content_disp = resp_post_report.headers.get("content-disposition", "").lower()

        is_pdf = "pdf" in content_type or resp_post_report.content[:5] == b"%PDF-"
        if not is_pdf and (any(t in content_type for t in ("text/csv", "application/csv", "application/vnd.ms-excel", "octet-stream")) or ".csv" in content_disp):
            logger.info("Silogtran retornó el archivo CSV directamente en la respuesta POST.")
            return resp_post_report.content

        # Also check if raw content looks like CSV (contains typical header line or commas/semicolons)
        text_preview = resp_post_report.text[:600].lower()
        if (
            any(k in text_preview for k in ("liqman", "manifiesto", "flete", "placa"))
            and not ("<html" in text_preview or "<!doctype" in text_preview)
        ):
            logger.info("El cuerpo de la respuesta corresponde a un archivo de texto/CSV.")
            return resp_post_report.content

        # Step 3: Check if page provides a download link
        download_url = PradoParser.extract_download_link(resp_post_report.text, str(resp_post_report.url))
        if download_url:
            logger.info(f"Enlace de descarga de CSV localizado: {download_url}. Descargando...")
            try:
                resp_download = await client.get(download_url)
                return resp_download.content
            except httpx.TimeoutException as e:
                raise SilogtranTimeoutError(f"Tiempo agotado al descargar archivo CSV: {e}")
            except httpx.HTTPError as e:
                raise SilogtranError(f"Error al descargar archivo CSV desde enlace: {e}")

        # If we got HTML and no download link, check if it was a session timeout
        if "login" in str(resp_post_report.url).lower():
            logger.warning("Redirigido a login al generar el informe. Reintentando...")
            await self.invalidate_session()
            if retry_count > 0:
                return await self.fetch_manifest_report(fecha_inicio, fecha_fin, retry_count=retry_count - 1)

        # 'Excel'/'Pantalla' formats often come back as an HTML table: convert it to CSV
        if "html" in content_type or "<table" in resp_post_report.text[:50000].lower():
            table_csv = PradoParser.html_table_to_csv(resp_post_report.text)
            # Only accept a table whose header row looks like the report, never the page's menu
            header_row = table_csv.split("\n", 1)[0].lower() if table_csv else ""
            if table_csv and any(k in header_row for k in ("liqman", "manifiesto_codigo", "vehiculo_placa", "placa")):
                logger.info("Informe recibido como tabla HTML; convertido a CSV.")
                return table_csv.encode("utf-8")

        logger.error(
            "No se pudo obtener el archivo CSV de Silogtran en la respuesta generada. "
            f"status={resp_post_report.status_code}, content-type='{content_type}', "
            f"content-disposition='{content_disp}', url={resp_post_report.url}, bytes={len(resp_post_report.content)}"
        )
        if not is_pdf:
            logger.error(f"Respuesta del servidor: {PradoParser.summarize_page(resp_post_report.text)}")
            logger.error(f"Controles del formulario del informe: {PradoParser.describe_form_controls(report_html)}")
            for snippet in PradoParser.extract_diagnostic_snippets(resp_post_report.text):
                logger.error(f"Fragmento de respuesta: {snippet}")
            logger.error(f"Campos enviados (nombres): {sorted(report_payload)}")
        if is_pdf:
            raise SilogtranError(
                "Silogtran generó el informe en PDF. Configure SILOGTRAN_PRINT_TYPE con un formato de texto (CSV/Excel).",
                code="SILOGTRAN_REPORT_FAILED"
            )
        raise SilogtranError(
            "Silogtran respondió en un formato inesperado o no generó el archivo CSV.",
            code="SILOGTRAN_REPORT_FAILED"
        )


# Global singleton instance
silogtran_client = SilogtranClient()
