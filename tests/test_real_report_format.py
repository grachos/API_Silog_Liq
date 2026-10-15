"""Regression tests for the real Silogtran 'Informe General de Liquidación Manifiesto' export."""
from app.services.csv_parser import CSVParser
from app.services.prado_parser import PradoParser

HEADERS = [
    "liqman_codigo", "liqman_fechacreacion", "beneficiario", "vehiculo_placa", "manifiesto_codigo",
    "ruta", "flete_real_despacho", "impuesto_manifiesto_retefuente", "valor_total_anticipos",
    "descuento_liquidacion_manifiesto", "liqman_valortotal", "estado_liquidacion", "liqman_observacion",
]


def _csv(*rows: str) -> bytes:
    header = ";".join(f'"{h}"' for h in HEADERS) + ";"
    return ("\n".join([header, *rows]) + "\n").encode("cp1252")


def test_real_headers_are_mapped_to_canonical_fields():
    data = _csv("0101000001;2026-01-15;JUAN PEREZ;ABC123;0101000002;BOGOTÁ - CALI;7000000;70000;4900000;0;1960000;PENDIENTE;;")
    item = CSVParser().parse(data)[0]
    assert item.numero_manifiesto == "0101000002"
    assert item.placa == "ABC123"
    assert item.fecha == "2026-01-15"
    assert item.valor_flete == 7000000
    assert item.valor_anticipo == 4900000
    assert item.valor_retencion == 70000
    assert item.valor_neto == 1960000
    assert item.estado == "PENDIENTE"
    assert item.campos_adicionales["ruta"] == "BOGOTÁ - CALI"


def test_annulled_liquidation_without_manifest_is_kept():
    data = _csv("0101000003;2026-01-15;JUAN PEREZ;;;;;;;;;ANULADO;;")
    items = CSVParser().parse(data)
    assert len(items) == 1
    assert items[0].estado == "ANULADO"
    assert items[0].campos_adicionales["liqman_codigo"] == "0101000003"


MENU_AND_FORM = """<form>
<input type=text name="ctl0$Menu$txtBuscar"><input type=submit name="ctl0$Menu$btnBuscar" value="Buscar Home">
<input type=text name="ctl0$Menu$financiero">
<input type=text name="ctl0$Main$fechaInicial"><input type=text name="ctl0$Main$fechaFinal">
<select name="ctl0$Main$tipo"><option value=1 selected>PDF</option><option value=3>CSV</option></select>
<input type=submit name="ctl0$Main$btnGenerar" value="Generar"></form>"""


def test_form_detection_ignores_menu_controls():
    assert PradoParser.find_date_fields(MENU_AND_FORM) == ("ctl0$Main$fechaInicial", "ctl0$Main$fechaFinal")
    assert PradoParser.find_report_submit_button(MENU_AND_FORM) == ("ctl0$Main$btnGenerar", "Generar")


def test_print_type_prefers_csv_over_pdf_default():
    field, value, text, _ = PradoParser.find_print_type_option(MENU_AND_FORM, ("csv", "excel"))
    assert (field, value, text) == ("ctl0$Main$tipo", "3", "CSV")


def test_download_link_from_window_open_script_is_found_before_menu_links():
    html = """<a href="index.php?page=Despacho.Liquidacionmanifiesto.Buscar">Buscar</a>
    <script type='text/javascript'> <!-- window.open('../reportes/DOC_f7487f950e589c7cf34dcbc440cbb4d6.csv'); --> </script>"""
    url = PradoParser.extract_download_link(
        html, "https://construproyec.colombiasoftware.net/index.php?page=Despacho.Liquidacionmanifiesto.InformeGeneral_111"
    )
    assert url == "https://construproyec.colombiasoftware.net/reportes/DOC_f7487f950e589c7cf34dcbc440cbb4d6.csv"
