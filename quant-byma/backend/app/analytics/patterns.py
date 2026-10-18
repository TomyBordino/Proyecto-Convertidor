"""Detección de patrones de precio sobre series con indicadores ya calculados."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class CrossEvent:
    kind: str  # "golden" | "death"
    bars_ago: int


def last_ma_cross(fast: pd.Series, slow: pd.Series, lookback: int = 20) -> CrossEvent | None:
    """Último cruce de `fast` sobre/bajo `slow` dentro de las últimas `lookback` barras."""
    diff = (fast - slow).dropna()
    if len(diff) < 2:
        return None
    sign = np.sign(diff.to_numpy())
    window = sign[-(lookback + 1) :]
    for i in range(len(window) - 1, 0, -1):
        if window[i] != window[i - 1] and window[i] != 0:
            kind = "golden" if window[i] > 0 else "death"
            return CrossEvent(kind, len(window) - 1 - i)
    return None


@dataclass
class Breakout:
    level: float
    volume_ratio: float


def detect_breakout(
    close: pd.Series, high: pd.Series, volume: pd.Series, window: int = 55, vol_mult: float = 1.5
) -> Breakout | None:
    """Cierre por encima del máximo de las `window` barras previas con volumen confirmatorio."""
    if len(close) < window + 1:
        return None
    prior_high = float(high.iloc[-(window + 1) : -1].max())
    avg_vol = float(volume.iloc[-(window + 1) : -1].mean())
    last_close, last_vol = float(close.iloc[-1]), float(volume.iloc[-1])
    vol_ratio = last_vol / avg_vol if avg_vol > 0 else 0.0
    if last_close > prior_high and vol_ratio >= vol_mult:
        return Breakout(prior_high, vol_ratio)
    return None


def _pivot_lows(values: np.ndarray, order: int) -> list[int]:
    idx = []
    for i in range(order, len(values) - order):
        seg = values[i - order : i + order + 1]
        if np.isfinite(values[i]) and values[i] == np.nanmin(seg):
            idx.append(i)
    return idx


def _pivot_highs(values: np.ndarray, order: int) -> list[int]:
    idx = []
    for i in range(order, len(values) - order):
        seg = values[i - order : i + order + 1]
        if np.isfinite(values[i]) and values[i] == np.nanmax(seg):
            idx.append(i)
    return idx


def rsi_divergence(
    close: pd.Series, rsi: pd.Series, lookback: int = 60, order: int = 5
) -> str | None:
    """Divergencia entre los dos últimos pivotes de precio y RSI.

    - "bullish": el precio marca un mínimo más bajo y el RSI un mínimo más alto.
    - "bearish": el precio marca un máximo más alto y el RSI un máximo más bajo.
    """
    c = close.iloc[-lookback:].to_numpy(dtype=float)
    r = rsi.iloc[-lookback:].to_numpy(dtype=float)
    lows = _pivot_lows(c, order)
    if len(lows) >= 2:
        a, b = lows[-2], lows[-1]
        if c[b] < c[a] and r[b] > r[a]:
            return "bullish"
    highs = _pivot_highs(c, order)
    if len(highs) >= 2:
        a, b = highs[-2], highs[-1]
        if c[b] > c[a] and r[b] < r[a]:
            return "bearish"
    return None
