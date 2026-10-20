"""Contexto macro argentino: riesgo país, inflación, dólares MEP/CCL/oficial y Merval.

Fuente: argentinadatos.com (series diarias y mensuales) y Yahoo Finance para el Merval.
"""

from __future__ import annotations

from datetime import date

import httpx
import pandas as pd

from app.ingestion.providers import yahoo
from app.ingestion.providers.base import ProviderError
from app.ingestion.providers.fx import parse_argentinadatos
from app.ingestion.providers.http import HttpClient

BASE = "https://api.argentinadatos.com/v1"
DOLLARS = {"MEP": "bolsa", "CCL_AR": "contadoconliqui", "OFICIAL": "oficial"}

# clave → (etiqueta, unidad) para el termómetro local
LOCAL_SERIES: dict[str, tuple[str, str]] = {
    "MERVAL_USD": ("Merval en dólares (CCL)", "usd"),
    "RIESGO_PAIS": ("Riesgo país (pb)", "pts"),
    "INFLACION_AR": ("Inflación mensual (INDEC, %)", "rate"),
    "MEP": ("Dólar MEP", "usd"),
    "BRECHA": ("Brecha CCL vs oficial", "ratio"),
    "CANJE": ("Canje CCL / MEP", "ratio"),
}


def parse_indice(payload: list[dict]) -> pd.Series:
    rows = [
        (pd.Timestamp(r["fecha"]), float(r["valor"]))
        for r in payload
        if r.get("fecha") and isinstance(r.get("valor"), int | float)
    ]
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series(dict(rows)).sort_index()
    return s[~s.index.duplicated(keep="last")]


class LocalMacroSource:
    name = "argentinadatos"

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self.http = HttpClient(retries=2, transport=transport)

    def _json(self, path: str) -> list[dict]:
        payload = self.http.request("GET", f"{BASE}{path}").json()
        if not isinstance(payload, list):
            raise ProviderError(f"argentinadatos {path}: formato inesperado")
        return payload

    def fetch(self, start: date, end: date) -> dict[str, pd.Series]:
        out: dict[str, pd.Series] = {}
        out["RIESGO_PAIS"] = parse_indice(self._json("/finanzas/indices/riesgo-pais"))
        out["INFLACION_AR"] = parse_indice(self._json("/finanzas/indices/inflacion"))
        for key, casa in DOLLARS.items():
            out[key] = parse_argentinadatos(self._json(f"/cotizaciones/dolares/{casa}"), start, end)
        return {
            k: v[(v.index >= pd.Timestamp(start)) & (v.index <= pd.Timestamp(end))]
            for k, v in out.items()
        }


def derived(series: dict[str, pd.Series], merval: pd.Series | None) -> dict[str, pd.Series]:
    """Brecha, canje y Merval en dólares a partir de las series base."""
    out: dict[str, pd.Series] = {}
    ccl, mep, oficial = (series.get(k) for k in ("CCL_AR", "MEP", "OFICIAL"))
    if ccl is not None and oficial is not None and len(ccl) and len(oficial):
        b = (ccl / oficial.reindex(ccl.index, method="ffill") - 1).dropna()
        out["BRECHA"] = b
    if ccl is not None and mep is not None and len(ccl) and len(mep):
        out["CANJE"] = (ccl / mep.reindex(ccl.index, method="ffill") - 1).dropna()
    if merval is not None and len(merval) and ccl is not None and len(ccl):
        out["MERVAL_USD"] = (merval / ccl.reindex(merval.index, method="ffill")).dropna()
    return out


def fetch_merval(start: date, end: date) -> pd.Series | None:
    data, _ = yahoo.batch_history(["^MERV"], start, end)
    df = data.get("^MERV")
    return None if df is None else df["close"]
