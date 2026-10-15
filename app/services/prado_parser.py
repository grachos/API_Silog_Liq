"""Helper utilities for parsing and extracting state from PRADO PHP web pages."""
import csv
import io
import logging
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class PradoParser:
    """Parser for PRADO framework forms, hidden fields, viewstates, and controls."""

    @staticmethod
    def extract_form_and_hidden_fields(
        html_content: str,
        base_url: str,
        form_id_or_index: int = 0
    ) -> Tuple[str, Dict[str, str]]:
        """
        Extracts the form action URL and all hidden inputs (including PRADO_PAGESTATE).
        """
        soup = BeautifulSoup(html_content, "html.parser")
        forms = soup.find_all("form")

        if not forms:
            return base_url, {}

        form = forms[min(form_id_or_index, len(forms) - 1)]
        action = form.get("action", "")
        resolved_action = urljoin(base_url, action) if action else base_url

        hidden_fields: Dict[str, str] = {}
        for inp in form.find_all("input", {"type": "hidden"}):
            name = inp.get("name")
            if name:
                hidden_fields[name] = inp.get("value", "")

        return resolved_action, hidden_fields

    @staticmethod
    def extract_all_hidden_fields(html_content: str) -> Dict[str, str]:
        """Extracts all hidden inputs present in the document."""
        soup = BeautifulSoup(html_content, "html.parser")
        hidden_fields: Dict[str, str] = {}
        for inp in soup.find_all("input", {"type": "hidden"}):
            name = inp.get("name")
            if name:
                hidden_fields[name] = inp.get("value", "")
        return hidden_fields

    @staticmethod
    def find_login_inputs(
        html_content: str,
        custom_user_field: Optional[str] = None,
        custom_pass_field: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Identifies username input, password input, and submit button name.
        """
        soup = BeautifulSoup(html_content, "html.parser")

        user_name = custom_user_field
        pass_name = custom_pass_field
        submit_name = None

        # Detect password field if not configured
        if not pass_name:
            pwd_input = soup.find("input", {"type": "password"})
            if pwd_input:
                pass_name = pwd_input.get("name")

        # Detect username field if not configured
        if not user_name:
            for inp in soup.find_all("input"):
                inp_type = inp.get("type", "text").lower()
                name = inp.get("name", "")
                if inp_type in ("text", "email"):
                    name_lower = name.lower()
                    if any(k in name_lower for k in ("user", "usuario", "login", "usr", "username")):
                        user_name = name
                        break
            # Fallback: first text input before the password field
            if not user_name:
                for inp in soup.find_all("input"):
                    if inp.get("type", "text").lower() == "text":
                        user_name = inp.get("name")
                        break

        # Detect submit button
        for btn in soup.find_all(["input", "button"]):
            btype = btn.get("type", "").lower()
            if btype in ("submit", "image") or btn.name == "button":
                submit_name = btn.get("name")
                if submit_name:
                    break

        return user_name, pass_name, submit_name

    @staticmethod
    def find_cost_center_option(
        html_content: str,
        target_name: str,
        custom_field_name: Optional[str] = None
    ) -> Optional[Tuple[str, str, str]]:
        """
        Searches all select dropdowns for an option matching target_name
        (e.g. CONSTRUPROYEC-PRINCIPAL).
        Returns: (select_name, option_value, matched_option_text) or None if not found.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        normalized_target = target_name.strip().upper()

        selects = soup.find_all("select")
        if custom_field_name:
            named_select = soup.find("select", {"name": custom_field_name})
            if named_select:
                selects = [named_select]

        for select in selects:
            select_name = select.get("name")
            if not select_name:
                continue

            for option in select.find_all("option"):
                opt_value = option.get("value", "").strip()
                opt_text = option.get_text().strip().upper()

                # Don't match empty or prompt options like "Seleccione..."
                if not opt_value or "SELECCIONE" in opt_text:
                    continue

                # Exact match or substring normalized match
                if normalized_target == opt_text or normalized_target == opt_value.upper() or (normalized_target in opt_text and "CONSORCIO" not in opt_text):
                    logger.info(f"Centro de costo localizado: '{option.get_text().strip()}' con valor '{opt_value}'")
                    return select_name, opt_value, option.get_text().strip()

        return None

    @staticmethod
    def find_continue_button(html_content: str) -> Optional[Tuple[str, str]]:
        """
        Finds the 'Continuar' or submit button/event on the cost center page.
        Returns (button_name, button_value).
        """
        soup = BeautifulSoup(html_content, "html.parser")
        for btn in soup.find_all(["input", "button"]):
            val = (btn.get("value", "") or btn.get_text() or "").strip().lower()
            btype = btn.get("type", "").lower()
            name = btn.get("name")
            if name and (btype in ("submit", "button", "image") or btn.name == "button"):
                if any(k in val for k in ("continuar", "ingresar", "aceptar", "enviar", "next", "login")):
                    return name, btn.get("value", "Continuar")

        # Fallback to first submit input
        first_submit = soup.find("input", {"type": "submit"})
        if first_submit and first_submit.get("name"):
            return first_submit.get("name"), first_submit.get("value", "Submit")

        return None

    @staticmethod
    def find_date_fields(
        html_content: str,
        custom_start: Optional[str] = None,
        custom_end: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Detects start and end date input field names in the report form.
        """
        soup = BeautifulSoup(html_content, "html.parser")

        start_name = custom_start
        end_name = custom_end

        if start_name and end_name:
            return start_name, end_name

        all_text_inputs = soup.find_all("input", {"type": ["text", "date"]})
        # Prefer inputs that are explicitly date fields; menus/search boxes share the page
        text_inputs = [
            i for i in all_text_inputs
            if any(k in i.get("name", "").lower() for k in ("fecha", "fec", "date"))
        ] or all_text_inputs

        for inp in text_inputs:
            name = inp.get("name", "")
            name_lower = name.lower()

            if not start_name:
                if any(k in name_lower for k in ("inicio", "desde", "fecini", "inicial", "start")):
                    start_name = name
                    continue

            if not end_name:
                if any(k in name_lower for k in ("final", "fecfin", "hasta", "fechafin", "fecha_fin", "end")):
                    end_name = name
                    continue

        # If not detected by name, take the first two text inputs
        if not start_name and len(text_inputs) >= 1:
            start_name = text_inputs[0].get("name")
        if not end_name and len(text_inputs) >= 2:
            end_name = text_inputs[1].get("name")

        return start_name, end_name

    @staticmethod
    def find_report_submit_button(html_content: str) -> Optional[Tuple[str, str]]:
        """
        Finds the action/button to generate the report or export to CSV.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        buttons = [
            btn for btn in soup.find_all(["input", "button"])
            if btn.get("name") and (btn.get("type", "").lower() in ("submit", "button") or btn.name == "button")
        ]
        # 'Generar' is the report button; generic words like 'buscar' also match menu widgets
        for keywords in (("generar",), ("consultar", "exportar", "csv", "excel")):
            for btn in buttons:
                val = (btn.get("value", "") or btn.get_text() or "").strip().lower()
                if any(k in val for k in keywords):
                    return btn.get("name"), btn.get("value", "Generar")

        # Fallback submit button
        submit = soup.find("input", {"type": "submit"})
        if submit and submit.get("name"):
            return submit.get("name"), submit.get("value", "Generar")

        return None

    @staticmethod
    def extract_form_control_defaults(html_content: str) -> Dict[str, str]:
        """
        Collects the values a browser would submit for visible text inputs and
        selects (the selected option, or the first one), mimicking a real form post.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        values: Dict[str, str] = {}
        for inp in soup.find_all("input"):
            name = inp.get("name")
            if name and inp.get("type", "text").lower() in ("text", "date"):
                values[name] = inp.get("value", "")
        for select in soup.find_all("select"):
            name = select.get("name")
            if not name:
                continue
            option = select.find("option", selected=True) or select.find("option")
            if option is not None:
                values[name] = option.get("value", option.get_text().strip())
        return values

    @staticmethod
    def find_print_type_option(
        html_content: str,
        preferred_keywords: Tuple[str, ...],
        custom_field_name: Optional[str] = None
    ) -> Optional[Tuple[str, Optional[str], Optional[str], List[str]]]:
        """
        Locates the 'Tipo de Impresión' select (the one offering a PDF option, or the
        configured field) and picks the first option matching preferred_keywords in order.
        Returns (select_name, option_value, option_text, all_option_texts) or None.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        target = None
        if custom_field_name:
            target = soup.find("select", {"name": custom_field_name})
        if target is None:
            for select in soup.find_all("select"):
                texts = [o.get_text().strip().lower() for o in select.find_all("option")]
                if select.get("name") and any("pdf" in t for t in texts):
                    target = select
                    break
        if target is None:
            return None

        options = [
            (o.get("value", o.get_text().strip()), o.get_text().strip())
            for o in target.find_all("option")
        ]
        all_texts = [f"{text} (valor={value})" for value, text in options]
        for keyword in preferred_keywords:
            for value, text in options:
                if keyword in text.lower() or keyword in str(value).lower():
                    return target.get("name"), value, text, all_texts
        return target.get("name"), None, None, all_texts

    @staticmethod
    def describe_form_controls(html_content: str) -> str:
        """Compact description of inputs/selects/buttons for diagnostics (no values of hidden fields)."""
        soup = BeautifulSoup(html_content, "html.parser")
        parts: List[str] = [f"forms={len(soup.find_all('form'))}"]
        for el in soup.find_all(["input", "select", "button"]):
            etype = el.get("type", "select" if el.name == "select" else el.name).lower()
            if etype == "hidden":
                continue
            parts.append(
                f"{el.name}[{etype}] name='{el.get('name', '')}' value='{str(el.get('value', ''))[:30]}' "
                f"onclick='{str(el.get('onclick', ''))[:80]}'"
            )
        return " | ".join(parts)[:3000]

    @staticmethod
    def summarize_page(html_content: str) -> str:
        """Title, visible error-looking text and a short text preview for diagnostics."""
        soup = BeautifulSoup(html_content, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else ""
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = " ".join(soup.get_text(" ", strip=True).split())
        return f"title='{title}' text='{text[:400]}'"

    @staticmethod
    def html_table_to_csv(html_content: str) -> Optional[str]:
        """
        Converts the largest HTML table in a page (e.g. an 'Excel' export that is really
        HTML, or an on-screen report) into semicolon-delimited CSV text.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        tables = soup.find_all("table")
        if not tables:
            return None
        table = max(tables, key=lambda t: len(t.find_all("tr")))
        rows = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if any(cells):
                rows.append(cells)
        if len(rows) < 2:
            return None
        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")
        writer.writerows(rows)
        return output.getvalue()

    @staticmethod
    def extract_download_link(html_content: str, base_url: str) -> Optional[str]:
        """
        Finds any CSV or file download link generated on the response page.
        """
        soup = BeautifulSoup(html_content, "html.parser")

        # Check links
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if any(ext in href.lower() for ext in (".csv", "exportar", "descargar", "download", ".xls")):
                return urljoin(base_url, href)

        # Check iframes
        for iframe in soup.find_all("iframe", src=True):
            src = iframe["src"]
            if any(ext in src.lower() for ext in (".csv", "exportar", "descargar")):
                return urljoin(base_url, src)

        # Check javascript redirects e.g. window.location = '...'
        match = re.search(r"window\.location(?:\.href)?\s*=\s*['\"]([^'\"]+\.csv[^'\"]*)['\"]", html_content, re.IGNORECASE)
        if match:
            return urljoin(base_url, match.group(1))

        return None
