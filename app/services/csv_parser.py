"""Robust, memory-efficient CSV parser for Silogtran manifest settlement reports."""
import csv
import io
import logging
import re
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional, Tuple, Union
from app.core.exceptions import CSVParseError
from app.models.schemas import LiquidacionItem
from app.services.column_mapping import CRITICAL_CANONICAL_COLUMNS, ColumnMapper

logger = logging.getLogger(__name__)


class CSVParser:
    """Parses Silogtran CSV reports using the standard library to minimize memory footprint."""

    def __init__(self, mapper: Optional[ColumnMapper] = None):
        self.mapper = mapper or ColumnMapper()

    @staticmethod
    def detect_encoding_and_decode(content: bytes) -> str:
        """
        Detects UTF-8, UTF-8-BOM, Latin-1 / Windows-1252 encodings.
        Decodes content to string safely.
        """
        # Check for UTF-8 with BOM
        if content.startswith(b"\xef\xbb\xbf"):
            return content[3:].decode("utf-8", errors="replace")

        # Try standard UTF-8
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            pass

        # Try Windows-1252 / Latin-1
        try:
            return content.decode("cp1252")
        except UnicodeDecodeError:
            return content.decode("latin-1", errors="replace")

    @staticmethod
    def detect_delimiter(first_lines: str) -> str:
        """
        Detects delimiter from candidate list: ';', ',', '\t', '|'.
        Prefers ';' as standard for Latin American / Colombian Excel CSVs.
        """
        lines = [line for line in first_lines.splitlines() if line.strip()]
        if not lines:
            return ";"

        sample = "\n".join(lines[:5])
        try:
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(sample, delimiters=";,|\t")
            return dialect.delimiter
        except Exception:
            # Fallback heuristic: count occurrences in header line
            header = lines[0]
            counts = {
                ";": header.count(";"),
                ",": header.count(","),
                "\t": header.count("\t"),
                "|": header.count("|")
            }
            best_delimiter = max(counts, key=counts.get)
            return best_delimiter if counts[best_delimiter] > 0 else ";"

    @staticmethod
    def parse_number(val: Optional[str]) -> Optional[float]:
        """
        Parses Spanish and US numerical formats:
        - '$ 1.500.000,50' -> 1500000.5
        - '1.500.000' -> 1500000.0
        - '1500.50' -> 1500.5
        - '- 20.000,00' -> -20000.0
        - '(500.00)' -> -500.0
        """
        if val is None:
            return None
        s = str(val).strip()
        if not s or s in ("-", "N/A", "null", "None", "."):
            return None

        # Check negative in parentheses
        is_negative = False
        if s.startswith("(") and s.endswith(")"):
            is_negative = True
            s = s[1:-1].strip()
        elif s.startswith("-"):
            is_negative = True
            s = s[1:].strip()

        # Remove currency symbols and spaces
        s = re.sub(r"[\$\sA-Za-z]", "", s)
        if not s:
            return None

        # Determine decimal separator
        if "," in s and "." in s:
            # e.g. 1.234.567,89 (Spanish) or 1,234,567.89 (US)
            if s.rfind(",") > s.rfind("."):
                # Spanish: thousand '.' and decimal ','
                s = s.replace(".", "").replace(",", ".")
            else:
                # US: thousand ',' and decimal '.'
                s = s.replace(",", "")
        elif "," in s:
            # Could be decimal '150,50' or thousand '1,500'
            parts = s.split(",")
            if len(parts) == 2 and len(parts[1]) in (1, 2):
                s = s.replace(",", ".")
            else:
                s = s.replace(",", "")

        try:
            res = float(s)
            return -res if is_negative else res
        except ValueError:
            return None

    @staticmethod
    def parse_integer(val: Optional[str]) -> Optional[int]:
        """Parses integer identifiers, stripping dots or commas."""
        if val is None:
            return None
        s = str(val).strip()
        if not s:
            return None
        # Remove commas, dots, currency
        s = re.sub(r"[^\d\-]", "", s)
        try:
            return int(s)
        except ValueError:
            return None

    @staticmethod
    def parse_date(val: Optional[str]) -> Optional[str]:
        """
        Normalizes diverse date formats to ISO 8601 YYYY-MM-DD.
        Supports: DD/MM/YYYY, YYYY-MM-DD, DD-MM-YYYY, YYYY/MM/DD, with or without time.
        """
        if val is None:
            return None
        s = str(val).strip()
        if not s or s in ("-", "null", "None"):
            return None

        # If it includes time, take only the date portion
        if " " in s:
            s = s.split()[0]
        if "T" in s:
            s = s.split("T")[0]

        formats = [
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%Y/%m/%d",
            "%d/%m/%y",
            "%d-%m-%y"
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(s, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        # Return stripped string if format was unrecognizable but non-empty
        return s if len(s) >= 4 else None

    @staticmethod
    def clean_string(val: Optional[str]) -> Optional[str]:
        """Trims whitespace and converts empty strings to None."""
        if val is None:
            return None
        s = str(val).strip()
        return s if s and s.lower() not in ("null", "none", "-", "n/a") else None

    def parse(self, csv_data: Union[str, bytes]) -> List[LiquidacionItem]:
        """
        Parses CSV data (string or bytes) into a list of typed LiquidacionItem models.
        """
        if isinstance(csv_data, bytes):
            text = self.detect_encoding_and_decode(csv_data)
        else:
            text = str(csv_data)

        text = text.strip()
        if not text:
            return []

        delimiter = self.detect_delimiter(text)
        logger.info(f"Delimitador detectado para CSV: '{delimiter}'")

        reader = csv.reader(io.StringIO(text), delimiter=delimiter)

        try:
            raw_headers = next(reader)
        except StopIteration:
            return []

        if not raw_headers:
            return []

        # Strip spaces and BOM quotes from headers
        clean_headers = [h.strip().strip('"\'') for h in raw_headers]
        col_mapping = self.mapper.resolve_headers(clean_headers)

        # Validate minimum critical columns
        recognized_fields = set(col_mapping.values())
        if not any(crit in recognized_fields for crit in CRITICAL_CANONICAL_COLUMNS):
            logger.warning(
                f"No se reconoció columna crítica ('numero_manifiesto') en: {clean_headers}. "
                f"Columnas mapeadas: {list(recognized_fields)}"
            )
            # If there are columns, use the first column as numero_manifiesto fallback if possible
            if 0 in col_mapping:
                col_mapping[0] = "numero_manifiesto"
            else:
                raise CSVParseError("El CSV de Silogtran no contiene columnas de manifiesto reconocibles.")

        items: List[LiquidacionItem] = []
        known_canonical_fields = {
            "id_manifiesto", "numero_manifiesto", "fecha", "placa", "conductor",
            "documento_conductor", "origen", "destino", "valor_flete", "valor_anticipo",
            "valor_retencion", "valor_descuento", "valor_neto", "estado", "observaciones"
        }

        for row_idx, row in enumerate(reader, start=2):
            if not row or all(not cell.strip() for cell in row):
                continue  # skip empty lines

            row_data: Dict[str, Any] = {}
            extra_data: Dict[str, Any] = {}

            for idx, cell in enumerate(row):
                field_name = col_mapping.get(idx)
                if not field_name:
                    continue

                cleaned_val = self.clean_string(cell)

                if field_name in known_canonical_fields:
                    row_data[field_name] = cleaned_val
                else:
                    if cleaned_val is not None:
                        extra_data[field_name] = cleaned_val

            # Require at least manifest number or license plate or id
            manifiesto_val = row_data.get("numero_manifiesto")
            if not manifiesto_val and not row_data.get("placa") and not row_data.get("id_manifiesto"):
                continue

            # Typed conversions
            item = LiquidacionItem(
                id_manifiesto=self.parse_integer(row_data.get("id_manifiesto")),
                numero_manifiesto=str(manifiesto_val or f"M-UNKNOWN-{row_idx}"),
                fecha=self.parse_date(row_data.get("fecha")),
                placa=self.clean_string(row_data.get("placa")),
                conductor=self.clean_string(row_data.get("conductor")),
                documento_conductor=self.clean_string(row_data.get("documento_conductor")),
                origen=self.clean_string(row_data.get("origen")),
                destino=self.clean_string(row_data.get("destino")),
                valor_flete=self.parse_number(row_data.get("valor_flete")),
                valor_anticipo=self.parse_number(row_data.get("valor_anticipo")),
                valor_retencion=self.parse_number(row_data.get("valor_retencion")),
                valor_descuento=self.parse_number(row_data.get("valor_descuento")),
                valor_neto=self.parse_number(row_data.get("valor_neto")),
                estado=self.clean_string(row_data.get("estado")),
                observaciones=self.clean_string(row_data.get("observaciones")),
                campos_adicionales=extra_data
            )
            items.append(item)

        logger.info(f"CSV procesado con éxito: {len(items)} registros extraídos.")
        return items
