"""CCL publicado por terceros, usado como referencia para validar el CCL calculado.

argentinadatos.com publica la serie histórica diaria del dólar "contadoconliqui"
(compra/venta) que relevan los medios. No reemplaza al CCL implícito propio: sirve para
detectar ratios mal cargados o precios desfasados cuando ambas series divergen.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.ingestion.providers.base import ProviderError
from app.ingestion.providers.http import HttpClient


def parse_argentinadatos(payload: list[dict], start: date, end: date) -> pd.Series:
    rows = []
    for r in payload:
        if not r.get("fecha"):
            continue
        compra, venta = r.get("compra"), r.get("venta")
        values = [float(v) for v in (compra, venta) if isinstance(v, int | float) and v > 0]
        if values:
            rows.append((pd.Timestamp(r["fecha"]), sum(values) / len(values)))
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series(dict(rows)).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    return s[(s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))]


class ArgentinaDatosCCL:
    name = "argentinadatos"
    URL = "https://api.argentinadatos.com/v1/cotizaciones/dolares/contadoconliqui"

    def __init__(self, http: HttpClient) -> None:
        self.http = http

    def ccl(self, start: date, end: date) -> pd.Series:
        payload = self.http.get_json(self.URL)
        if not isinstance(payload, list):
            raise ProviderError("argentinadatos devolvió un formato inesperado")
        return parse_argentinadatos(payload, start, end)
