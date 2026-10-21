"""Descubrimiento del universo operable y estimación de ratios de CEDEARs.

1. Universo: el panel en vivo de data912 lista cada especie de BYMA en pesos y sus
   variantes en dólar MEP (sufijo D) y cable (sufijo C). Una especie en pesos es la que
   tiene variante D o C. Se toman las que operaron volumen en la última rueda.
2. Subyacente: por defecto el mismo ticker en EE. UU.; `US_SYMBOL_OVERRIDES` cubre las
   diferencias conocidas. Un mapeo incorrecto se detecta solo: el ratio implícito resulta
   inestable en el tiempo y el activo queda inactivo.
3. Ratio: ninguna API pública accesible publica los ratios oficiales, así que se deducen
   de precios reales usando el CCL de mercado de los activos ancla (ratios curados):

       ratio_t = CCL_t × precio_US_t / precio_BA_t

   Se toma la mediana de las últimas ruedas y se redondea al entero más cercano (los
   ratios de CEDEAR son enteros). La confianza combina la estabilidad de la serie y la
   distancia al entero.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.ingestion.providers.base import ProviderError
from app.ingestion.providers.http import HttpClient

DATA912_LIVE = "https://data912.com/live"

# Tickers de BYMA cuyo subyacente cotiza con otro símbolo en EE. UU. (formato Yahoo).
US_SYMBOL_OVERRIDES: dict[str, str] = {
    "DISN": "DIS",
    "BRKB": "BRK-B",
    "NOKA": "NOK",
    "TXR": "TX",
    "KOFM": "KOF",
    "PBRA": "PBR-A",
    "SNE": "SONY",
    "AUY": "AUY",
    "GOLD": "B",  # Barrick cambió su ticker a "B" en 2025
    "TEN": "TS",
    "BBV": "BBVA",
    "SAN": "SAN",
    "BCS": "BCS",
    "LYG": "LYG",
    "ERJ": "EMBJ",  # Embraer cambió su ticker a "EMBJ" en 2025
    "BA.C": "BAC",
    "ADGO": "AGRO",
    "TRVV": "TRV",
    "XROX": "XRX",
    "BNG": "BG",
}

# Ventana para estimar el ratio vigente y umbrales de aceptación.
RATIO_WINDOW = 20
MAX_RATIO_DISPERSION = 0.03  # MAD relativa de ratio_t en la ventana
MAX_ROUNDING_GAP = 0.03  # |mediana − entero| / entero
MIN_CONFIDENCE = 0.5


@dataclass(frozen=True)
class LiveQuote:
    ticker: str
    close: float
    volume_ars: float


# Especies reales cuyo nombre coincide con el patrón de una variante en dólares.
_BASES_LIKE_VARIANTS = {"AMD"}


def dollar_variants(base: str) -> set[str]:
    """Nombres que BYMA usa para la especie `base` en dólar MEP (D) o cable (C):
    GGAL → GGALD/GGALC, BMA → BMA.D, TGSU2 → TGSUD, TGNO4 → TGN4D."""
    out = {base + "D", base + "C", base + ".D", base + ".C"}
    if base[-1:].isdigit():
        out |= {base[:-1] + "D", base[:-1] + "C", base[:-2] + base[-1] + "D"}
    return out


def parse_live_panel(rows: list[dict]) -> list[LiveQuote]:
    """Especies en pesos de un panel de data912 (descarta las variantes en dólares)."""
    symbols: set[str] = {str(r["symbol"]) for r in rows if r.get("symbol")}
    variants = set().union(*(dollar_variants(b) for b in symbols)) if symbols else set()
    out = []
    for r in rows:
        s = r.get("symbol")
        if not s or (s in variants and s not in _BASES_LIKE_VARIANTS):
            continue
        close = r.get("c") or 0.0
        volume = r.get("v") or 0.0
        if close > 0:
            out.append(LiveQuote(s, float(close), float(close) * float(volume)))
    return out


def discover_panel(http: HttpClient, panel: str) -> list[LiveQuote]:
    rows = http.get_json(f"{DATA912_LIVE}/{panel}")
    if not isinstance(rows, list):
        raise ProviderError(f"data912 {panel} devolvió un formato inesperado")
    return parse_live_panel(rows)


def us_symbol_for(ticker: str) -> str:
    return US_SYMBOL_OVERRIDES.get(ticker, ticker)


def us_candidates(ticker: str) -> list[str]:
    """Símbolos de EE. UU. a probar, en orden: el override conocido y luego el mismo ticker
    (cubre tickers que cambiaron hace poco y cuya historia vive bajo el símbolo viejo)."""
    first = us_symbol_for(ticker)
    return [first] if first == ticker else [first, ticker]


@dataclass(frozen=True)
class RatioEstimate:
    ratio: float | None
    raw_median: float | None
    dispersion: float | None
    confidence: float
    note: str


def implied_ratio_series(ba_close: pd.Series, us_close: pd.Series, ccl: pd.Series) -> pd.Series:
    df = pd.concat({"ba": ba_close, "us": us_close, "ccl": ccl}, axis=1, join="inner").dropna()
    df = df[(df["ba"] > 0) & (df["us"] > 0) & (df["ccl"] > 0)]
    return df["ccl"] * df["us"] / df["ba"]


def snap_ratio(raw: float) -> float:
    """Ratios de CEDEAR: enteros ≥ 1; por debajo de 1 se admite 1/k (un CEDEAR = k acciones)."""
    if raw >= 1:
        return float(max(1, round(raw)))
    k = max(1, round(1 / raw))
    return 1.0 / k


def estimate_ratio(
    ba_close: pd.Series, us_close: pd.Series, ccl: pd.Series, window: int = RATIO_WINDOW
) -> RatioEstimate:
    r = implied_ratio_series(ba_close, us_close, ccl).iloc[-window:]
    if len(r) < max(5, window // 2):
        return RatioEstimate(None, None, None, 0.0, f"solo {len(r)} ruedas comunes BYMA/EE. UU.")
    med = float(r.median())
    dispersion = float((r - med).abs().median() / med)
    snapped = snap_ratio(med)
    gap = abs(med - snapped) / snapped
    # Confianza: 1 si la serie es estable y la mediana cae sobre el entero; 0 en los umbrales.
    conf = max(0.0, 1 - dispersion / MAX_RATIO_DISPERSION) * max(0.0, 1 - gap / MAX_ROUNDING_GAP)
    if dispersion > MAX_RATIO_DISPERSION:
        return RatioEstimate(None, med, dispersion, conf, f"ratio inestable ({dispersion:.1%})")
    if gap > MAX_ROUNDING_GAP:
        return RatioEstimate(None, med, dispersion, conf, f"ratio {med:.2f} lejos de un entero")
    if conf < MIN_CONFIDENCE:
        return RatioEstimate(None, med, dispersion, conf, f"confianza baja ({conf:.2f})")
    return RatioEstimate(snapped, med, dispersion, round(conf, 3), "estimado de precios")


def ratio_history(
    ba_close: pd.Series, us_close: pd.Series, ccl: pd.Series, current: float, window: int = 10
) -> pd.Series:
    """Ratio vigente en cada rueda (escalonado), para detectar cambios de ratio pasados.

    Se redondea la mediana móvil del ratio implícito. Donde no hay datos suficientes se
    usa el ratio actual. Permite calcular CCL implícitos históricos correctos aunque
    BYMA haya cambiado el ratio y la fuente publique precios sin ajustar.
    """
    r = implied_ratio_series(ba_close, us_close, ccl)
    if r.empty:
        return pd.Series(dtype=float)
    rolled = r.rolling(window, min_periods=max(3, window // 2), center=True).median()
    snapped = rolled.dropna().map(snap_ratio)
    out = snapped.reindex(r.index).ffill().bfill().fillna(current)
    # Solo se acepta un cambio de ratio si es material (≥ 20%): ruido no cambia el escalón.
    vals = out.to_numpy(dtype=float, copy=True)
    for i in range(1, len(vals)):
        if abs(vals[i] / vals[i - 1] - 1) < 0.2:
            vals[i] = vals[i - 1]
    return pd.Series(vals, index=out.index)


def volume_weighted_liquidity(ba: pd.DataFrame, window: int = 20) -> float | None:
    if ba.empty:
        return None
    v = (ba["close"] * ba["volume"]).iloc[-window:]
    return float(np.nanmean(v)) if len(v) else None
