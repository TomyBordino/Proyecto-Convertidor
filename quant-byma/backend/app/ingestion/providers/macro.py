"""Series de mercado que reflejan eventos macro, descargadas de Yahoo Finance."""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.ingestion.providers import yahoo

# clave → (símbolo de Yahoo, etiqueta, unidad). "pct" = rendimiento en puntos porcentuales.
MACRO_SERIES: dict[str, tuple[str, str, str]] = {
    "UST10Y": ("^TNX", "Tasa del Tesoro a 10 años", "pct"),
    "UST3M": ("^IRX", "Tasa del Tesoro a 3 meses (proxy Fed)", "pct"),
    "VIX": ("^VIX", "Volatilidad implícita S&P 500 (VIX)", "pts"),
    "WTI": ("CL=F", "Petróleo WTI", "usd"),
    "BRENT": ("BZ=F", "Petróleo Brent", "usd"),
    "GOLD": ("GC=F", "Oro", "usd"),
    "DXY": ("DX-Y.NYB", "Índice dólar (DXY)", "pts"),
    "SOY": ("ZS=F", "Soja", "usd"),
    "CORN": ("ZC=F", "Maíz", "usd"),
    "WHEAT": ("ZW=F", "Trigo", "usd"),
    "NATGAS": ("NG=F", "Gas natural", "usd"),
    "COPPER": ("HG=F", "Cobre", "usd"),
}


def fetch_macro(start: date, end: date) -> dict[str, pd.Series]:
    """Cierres diarios de cada serie macro (claves de MACRO_SERIES)."""
    symbols = {sym: key for key, (sym, _, _) in MACRO_SERIES.items()}
    data, _ = yahoo.batch_history(list(symbols), start, end)
    out = {}
    for sym, df in data.items():
        s = df["close"].dropna()
        s = s[s > 0]
        if len(s):
            out[symbols[sym]] = s
    return out
