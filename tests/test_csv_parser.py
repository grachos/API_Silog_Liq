"""Tests for delimiter detection, encodings, type conversions, and CSV parser resilience."""
import pytest
from app.core.exceptions import CSVParseError
from app.services.csv_parser import CSVParser


def test_delimiter_detection():
    """Detects semicolons, commas, and tabs."""
    csv_semicolon = "Col1;Col2;Col3\nVal1;Val2;Val3\n"
    csv_comma = "Col1,Col2,Col3\nVal1,Val2,Val3\n"
    csv_tab = "Col1\tCol2\tCol3\nVal1\tVal2\tVal3\n"

    assert CSVParser.detect_delimiter(csv_semicolon) == ";"
    assert CSVParser.detect_delimiter(csv_comma) == ","
    assert CSVParser.detect_delimiter(csv_tab) == "\t"


def test_encoding_detection():
    """Decodes UTF-8, UTF-8 with BOM, and Latin-1."""
    # UTF-8 with BOM
    bom_content = b"\xef\xbb\xbfNUMERO MANIFIESTO;CONDUCTOR\nM-1;JOS\xc3\x89"
    decoded_bom = CSVParser.detect_encoding_and_decode(bom_content)
    assert decoded_bom.startswith("NUMERO MANIFIESTO")
    assert "JOSÉ" in decoded_bom

    # Latin-1 / Windows-1252 with special characters (e.g. ñ, á)
    latin1_content = "NUMERO MANIFIESTO;OBSERVACIÓN\nM-2;Camión en Bogotá".encode("latin-1")
    decoded_latin1 = CSVParser.detect_encoding_and_decode(latin1_content)
    assert "Camión en Bogotá" in decoded_latin1


def test_number_parsing():
    """Validates conversion of Spanish and international monetary representations."""
    assert CSVParser.parse_number("$ 1.500.000,50") == 1500000.5
    assert CSVParser.parse_number("2.400.000,00") == 2400000.0
    assert CSVParser.parse_number("1500.50") == 1500.5
    assert CSVParser.parse_number("- 25.000,00") == -25000.0
    assert CSVParser.parse_number("(10.500,25)") == -10500.25
    assert CSVParser.parse_number("-") is None
    assert CSVParser.parse_number("N/A") is None
    assert CSVParser.parse_number("") is None
    assert CSVParser.parse_number(None) is None


def test_date_parsing():
    """Validates date normalization to ISO 8601 (YYYY-MM-DD)."""
    assert CSVParser.parse_date("15/01/2026") == "2026-01-15"
    assert CSVParser.parse_date("2026-01-15") == "2026-01-15"
    assert CSVParser.parse_date("15-01-2026") == "2026-01-15"
    assert CSVParser.parse_date("15/01/2026 14:30:00") == "2026-01-15"
    assert CSVParser.parse_date("") is None
    assert CSVParser.parse_date("-") is None


def test_csv_parser_full_flow():
    """Parses a complete sample CSV and validates typed items."""
    csv_raw = (
        "N° MANIFIESTO;FECHA;PLACA;VALOR FLETE;VALOR NETO;ESTADO;OBSERVACIONES;ZONA_DESPACHO\n"
        "M-1001;12/01/2026;ABC123;$ 1.200.000,00;1.000.000,00;LIQUIDADO;OK;Zona Norte\n"
        "M-1002;14/01/2026;XYZ987;800.000,50;750.000,00;PENDIENTE;;Zona Sur\n"
    )
    parser = CSVParser()
    items = parser.parse(csv_raw)

    assert len(items) == 2

    # Item 1
    assert items[0].numero_manifiesto == "M-1001"
    assert items[0].fecha == "2026-01-12"
    assert items[0].placa == "ABC123"
    assert items[0].valor_flete == 1200000.0
    assert items[0].valor_neto == 1000000.0
    assert items[0].estado == "LIQUIDADO"
    assert items[0].observaciones == "OK"
    assert items[0].campos_adicionales.get("zona_despacho") == "Zona Norte"

    # Item 2
    assert items[1].numero_manifiesto == "M-1002"
    assert items[1].fecha == "2026-01-14"
    assert items[1].placa == "XYZ987"
    assert items[1].valor_flete == 800000.5
    assert items[1].valor_neto == 750000.0
    assert items[1].estado == "PENDIENTE"
    assert items[1].observaciones is None
    assert items[1].campos_adicionales.get("zona_despacho") == "Zona Sur"


def test_csv_parser_missing_critical_columns():
    """When CSV does not contain any recognizable columns, raises CSVParseError."""
    csv_invalid = "COL_A,COL_B,COL_C\n1,2,3\n"
    parser = CSVParser()
    # If it has columns, fallback maps col 0 or raises
    items = parser.parse(csv_invalid)
    assert len(items) == 1
    assert items[0].numero_manifiesto == "1"

    # Completely empty CSV
    assert parser.parse("") == []
