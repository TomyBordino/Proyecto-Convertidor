"""Indicadores técnicos sobre series de pandas indexadas por fecha.

Convenciones (coinciden con TradingView/TA-Lib):
  - EMA: alpha = 2 / (n + 1), sembrada con la SMA de las primeras n barras.
  - RSI y ATR: suavizado de Wilder (alpha = 1 / n), sembrado con la media simple.
  - Bollinger: SMA(n) ± k * desvío estándar poblacional (ddof=0).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def sma(close: pd.Series, n: int) -> pd.Series:
    return close.rolling(window=n, min_periods=n).mean()


def _seeded_ewm(values: pd.Series, n: int, alpha: float) -> pd.Series:
    """EWM recursiva sembrada con la media de las primeras n observaciones válidas."""
    arr = values.to_numpy(dtype=float)
    out = np.full(arr.shape, np.nan)
    valid = np.flatnonzero(~np.isnan(arr))
    if valid.size < n:
        return pd.Series(out, index=values.index)
    start = valid[0]
    seed_end = start + n - 1
    out[seed_end] = np.nanmean(arr[start : seed_end + 1])
    for i in range(seed_end + 1, arr.size):
        x = arr[i]
        out[i] = out[i - 1] if np.isnan(x) else alpha * x + (1 - alpha) * out[i - 1]
    return pd.Series(out, index=values.index)


def ema(close: pd.Series, n: int) -> pd.Series:
    return _seeded_ewm(close, n, 2.0 / (n + 1))


def wilder(values: pd.Series, n: int) -> pd.Series:
    return _seeded_ewm(values, n, 1.0 / n)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = wilder(gain.iloc[1:], n).reindex(close.index)
    avg_loss = wilder(loss.iloc[1:], n).reindex(close.index)
    rs = avg_gain / avg_loss
    out = 100.0 - 100.0 / (1.0 + rs)
    # Sin pérdidas en la ventana → RSI = 100; sin movimiento → 50.
    out = out.where(avg_loss != 0, np.where(avg_gain > 0, 100.0, 50.0))
    return out.where(avg_gain.notna())


@dataclass
class MACD:
    macd: pd.Series
    signal: pd.Series
    histogram: pd.Series


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> MACD:
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return MACD(line, sig, line - sig)


@dataclass
class Bollinger:
    middle: pd.Series
    upper: pd.Series
    lower: pd.Series
    percent_b: pd.Series
    bandwidth: pd.Series


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> Bollinger:
    mid = sma(close, n)
    std = close.rolling(window=n, min_periods=n).std(ddof=0)
    upper, lower = mid + k * std, mid - k * std
    width = upper - lower
    pct_b = (close - lower) / width.replace(0, np.nan)
    return Bollinger(mid, upper, lower, pct_b, width / mid)


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    tr.iloc[0] = high.iloc[0] - low.iloc[0]
    return tr


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    return wilder(true_range(high, low, close), n)


def compute_all(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Agrega todas las columnas de indicadores a un DataFrame OHLCV."""
    c = ohlcv["close"]
    out = ohlcv.copy()
    for n in (20, 50, 200):
        out[f"sma{n}"] = sma(c, n)
        out[f"ema{n}"] = ema(c, n)
    out["rsi14"] = rsi(c, 14)
    m = macd(c)
    out["macd"], out["macd_signal"], out["macd_hist"] = m.macd, m.signal, m.histogram
    bb = bollinger(c)
    out["bb_upper"], out["bb_middle"], out["bb_lower"] = bb.upper, bb.middle, bb.lower
    out["bb_pct_b"], out["bb_width"] = bb.percent_b, bb.bandwidth
    out["atr14"] = atr(ohlcv["high"], ohlcv["low"], c, 14)
    return out
