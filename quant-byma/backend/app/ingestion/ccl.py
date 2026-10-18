"""Contado con Liquidez (CCL) implícito.

Para un par local/exterior con ratio r (unidades locales por unidad en EE. UU.):

    CCL_implícito = precio_local_ARS * r / precio_exterior_USD

El CCL de mercado es la mediana ponderada por volumen (en ARS) de los CCL implícitos,
luego de descartar outliers por MAD. La mediana es robusta a ratios desactualizados y
a papeles ilíquidos, a diferencia del promedio simple.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeAlias

import numpy as np
import pandas as pd

RATIO_MISMATCH_THRESHOLD = 0.35

Floats: TypeAlias = Sequence[float] | np.ndarray


def implied_ccl(price_local_ars: float, price_us_usd: float, ratio: float) -> float | None:
    if price_local_ars <= 0 or price_us_usd <= 0 or ratio <= 0:
        return None
    return price_local_ars * ratio / price_us_usd


def implied_ccl_series(local_ars: pd.Series, us_usd: pd.Series, ratio: float) -> pd.Series:
    """CCL implícito diario; alinea fechas (solo días con cotización en ambas plazas)."""
    df = pd.concat({"ba": local_ars, "us": us_usd}, axis=1, join="inner")
    df = df[(df["ba"] > 0) & (df["us"] > 0)]
    return (df["ba"] * ratio / df["us"]).rename("ccl")


def weighted_median(values: Floats, weights: Floats | None = None) -> float:
    v = np.asarray(values, dtype=float)
    if v.size == 0:
        raise ValueError("weighted_median de una secuencia vacía")
    w = np.ones_like(v) if weights is None else np.asarray(weights, dtype=float)
    if w.shape != v.shape:
        raise ValueError("values y weights deben tener el mismo largo")
    if np.all(w <= 0):
        w = np.ones_like(v)
    order = np.argsort(v)
    v, w = v[order], w[order]
    cum = np.cumsum(w)
    half = cum[-1] / 2.0
    idx = int(np.searchsorted(cum, half))
    # Si el peso acumulado cae exactamente en la mitad, promediamos los dos centrales.
    if np.isclose(cum[idx], half) and idx + 1 < v.size:
        return float((v[idx] + v[idx + 1]) / 2.0)
    return float(v[idx])


def mad_filter(values: Floats, z: float = 3.5) -> np.ndarray:
    """Máscara booleana de valores no-outliers según el z-score modificado (Iglewicz-Hoaglin)."""
    v = np.asarray(values, dtype=float)
    med = np.median(v)
    mad = np.median(np.abs(v - med))
    if mad == 0:
        return np.ones_like(v, dtype=bool)
    modified_z = 0.6745 * (v - med) / mad
    return np.abs(modified_z) <= z


@dataclass
class MarketCCL:
    value: float
    n_samples: int
    n_discarded: int


def market_ccl(implied: Floats, volumes_ars: Floats | None = None) -> MarketCCL:
    v = np.asarray(implied, dtype=float)
    w = np.ones_like(v) if volumes_ars is None else np.asarray(volumes_ars, dtype=float)
    valid = np.isfinite(v) & (v > 0)
    v, w = v[valid], w[valid]
    if v.size == 0:
        raise ValueError("Sin CCL implícitos válidos")
    keep = mad_filter(v) if v.size >= 4 else np.ones_like(v, dtype=bool)
    return MarketCCL(weighted_median(v[keep], w[keep]), int(keep.sum()), int((~keep).sum()))


def ccl_deviation(implied: float, market: float) -> float:
    """Desvío relativo. Negativo = el activo cotiza a un dólar implícito más barato."""
    return implied / market - 1.0


def is_ratio_suspect(implied: float, market: float) -> bool:
    return abs(ccl_deviation(implied, market)) > RATIO_MISMATCH_THRESHOLD


def market_ccl_series(
    implied_by_asset: dict[str, pd.Series], volume_by_asset: dict[str, pd.Series] | None = None
) -> pd.DataFrame:
    """CCL de mercado diario a partir de las series implícitas de cada activo."""
    ccl = pd.DataFrame(implied_by_asset).sort_index()
    vol = (
        pd.DataFrame(volume_by_asset).reindex(index=ccl.index, columns=ccl.columns).fillna(0.0)
        if volume_by_asset
        else pd.DataFrame(1.0, index=ccl.index, columns=ccl.columns)
    )
    rows = []
    for day, row in ccl.iterrows():
        mask = row.notna()
        if mask.sum() == 0:
            continue
        res = market_ccl(row[mask].to_numpy(), vol.loc[day, mask].to_numpy())
        rows.append({"day": day, "value": res.value, "n_samples": res.n_samples})
    return pd.DataFrame(rows).set_index("day") if rows else pd.DataFrame(columns=["value"])
