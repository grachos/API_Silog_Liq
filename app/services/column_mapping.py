"""Column mapping and schema definitions for Silogtran CSV export."""
import unicodedata
from typing import Dict, List, Optional, Set


def normalize_column_name(col: str) -> str:
    """
    Normalizes header names: lowercases, removes accents, strips spaces,
    and replaces non-alphanumeric characters with underscores.
    Example: 'N° Manifiesto' -> 'n_manifiesto', 'Valor Flete' -> 'valor_flete'
    """
    if not col:
        return ""
    text = unicodedata.normalize("NFKD", str(col).strip().lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    # Replace non alphanumeric with underscore
    clean = []
    prev_under = False
    for char in text:
        if char.isalnum():
            clean.append(char)
            prev_under = False
        elif not prev_under:
            clean.append("_")
            prev_under = True
    return "".join(clean).strip("_")


# Synonyms dictionary mapping possible header variations to canonical fields
DEFAULT_COLUMN_SYNONYMS: Dict[str, str] = {
    # id_manifiesto
    "id_manifiesto": "id_manifiesto",
    "id": "id_manifiesto",
    "id_despacho": "id_manifiesto",
    "consecutivo_interno": "id_manifiesto",
    "id_liquidacion": "id_manifiesto",

    # numero_manifiesto
    "numero_manifiesto": "numero_manifiesto",
    "nro_manifiesto": "numero_manifiesto",
    "manifiesto": "numero_manifiesto",
    "num_manifiesto": "numero_manifiesto",
    "manifiesto_de_carga": "numero_manifiesto",
    "numero_de_manifiesto": "numero_manifiesto",
    "nro_de_manifiesto": "numero_manifiesto",
    "n_manifiesto": "numero_manifiesto",

    # Silogtran "Informe General de Liquidación Manifiesto" real export headers
    "manifiesto_codigo": "numero_manifiesto",
    "vehiculo_placa": "placa",
    "liqman_fechacreacion": "fecha",
    "flete_real_despacho": "valor_flete",
    "valor_total_anticipos": "valor_anticipo",
    "impuesto_manifiesto_retefuente": "valor_retencion",
    "descuento_liquidacion_manifiesto": "valor_descuento",
    "liqman_valortotal": "valor_neto",
    "liqman_observacion": "observaciones",

    # fecha
    "fecha": "fecha",
    "fecha_manifiesto": "fecha",
    "fecha_despacho": "fecha",
    "fecha_liquidacion": "fecha",
    "fec_manifiesto": "fecha",
    "fec_liquidacion": "fecha",
    "fecha_de_emision": "fecha",

    # placa
    "placa": "placa",
    "placa_vehiculo": "placa",
    "vehiculo": "placa",
    "placas": "placa",

    # conductor
    "conductor": "conductor",
    "nombre_conductor": "conductor",
    "conductor_nombre": "conductor",
    "nombres_conductor": "conductor",

    # documento_conductor
    "documento_conductor": "documento_conductor",
    "cedula_conductor": "documento_conductor",
    "doc_conductor": "documento_conductor",
    "cc_conductor": "documento_conductor",
    "cedula": "documento_conductor",
    "identificacion_conductor": "documento_conductor",

    # origen
    "origen": "origen",
    "ciudad_origen": "origen",
    "municipio_origen": "origen",

    # destino
    "destino": "destino",
    "ciudad_destino": "destino",
    "municipio_destino": "destino",

    # valor_flete
    "valor_flete": "valor_flete",
    "flete": "valor_flete",
    "vlr_flete": "valor_flete",
    "valor_del_flete": "valor_flete",
    "total_flete": "valor_flete",
    "vr_flete": "valor_flete",

    # valor_anticipo
    "valor_anticipo": "valor_anticipo",
    "anticipo": "valor_anticipo",
    "anticipos": "valor_anticipo",
    "vlr_anticipo": "valor_anticipo",
    "vr_anticipo": "valor_anticipo",

    # valor_retencion
    "valor_retencion": "valor_retencion",
    "retencion": "valor_retencion",
    "retenciones": "valor_retencion",
    "vlr_retencion": "valor_retencion",
    "vr_retencion": "valor_retencion",
    "retencion_fuente": "valor_retencion",
    "retefuente": "valor_retencion",

    # valor_descuento
    "valor_descuento": "valor_descuento",
    "descuento": "valor_descuento",
    "descuentos": "valor_descuento",
    "deducciones": "valor_descuento",
    "vlr_descuento": "valor_descuento",
    "vr_descuento": "valor_descuento",

    # valor_neto
    "valor_neto": "valor_neto",
    "neto": "valor_neto",
    "total_a_pagar": "valor_neto",
    "vlr_neto": "valor_neto",
    "vr_neto": "valor_neto",
    "saldo_a_pagar": "valor_neto",
    "valor_saldo": "valor_neto",
    "saldo": "valor_neto",

    # estado
    "estado": "estado",
    "estado_liquidacion": "estado",
    "estado_manifiesto": "estado",

    # observaciones
    "observaciones": "observaciones",
    "observacion": "observaciones",
    "detalle": "observaciones",
    "comentarios": "observaciones",
}

# The minimum required column to consider a manifest record valid
CRITICAL_CANONICAL_COLUMNS: Set[str] = {"numero_manifiesto"}


class ColumnMapper:
    """Maps arbitrary CSV headers to canonical field names."""

    def __init__(self, custom_synonyms: Optional[Dict[str, str]] = None):
        self.synonyms = dict(DEFAULT_COLUMN_SYNONYMS)
        if custom_synonyms:
            for k, v in custom_synonyms.items():
                self.synonyms[normalize_column_name(k)] = v

    def resolve_headers(self, raw_headers: List[str]) -> Dict[int, str]:
        """
        Maps column indices to canonical field names or normalized custom names.
        Returns a dict: {col_index: canonical_or_normalized_name}.
        """
        mapping: Dict[int, str] = {}
        for idx, col in enumerate(raw_headers):
            normalized = normalize_column_name(col)
            canonical = self.synonyms.get(normalized, normalized)
            mapping[idx] = canonical
        return mapping
