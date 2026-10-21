import numpy as np
import pandas as pd
import pytest

from app.analytics.technical import atr, bollinger, ema, macd, rsi, sma


def series(values):
    return pd.Series(values, index=pd.bdate_range("2024-01-01", periods=len(values)), dtype=float)


# Serie clásica de Wilder/StockCharts para RSI(14).
WILDER = [
    44.34,
    44.09,
    44.15,
    43.61,
    44.33,
    44.83,
    45.10,
    45.42,
    45.84,
    46.08,
    45.89,
    46.03,
    45.61,
    46.28,
    46.28,
    46.00,
    46.03,
    46.41,
    46.22,
    45.64,
]


def test_sma_known_values():
    s = sma(series([1, 2, 3, 4, 5]), 3)
    assert s.isna().sum() == 2
    assert s.iloc[2:].tolist() == [2.0, 3.0, 4.0]


def test_ema_seeded_with_sma_and_recursive():
    s = series([2, 4, 6, 8, 10])
    e = ema(s, 3)
    alpha = 0.5
    assert np.isnan(e.iloc[1])
    assert e.iloc[2] == pytest.approx(4.0)  # SMA de las primeras 3
    assert e.iloc[3] == pytest.approx(alpha * 8 + (1 - alpha) * 4.0)
    assert e.iloc[4] == pytest.approx(alpha * 10 + (1 - alpha) * e.iloc[3])


def test_rsi_matches_wilder_reference():
    r = rsi(series(WILDER), 14)
    assert r.iloc[:14].isna().all()
    expected = [70.46, 66.25, 66.48, 69.35, 66.29, 57.92]
    assert r.iloc[14:].round(2).tolist() == pytest.approx(expected, abs=0.1)


def test_rsi_bounds_and_edge_cases():
    up = rsi(series(range(1, 40)), 14)
    assert up.dropna().eq(100).all()
    flat = rsi(series([10] * 30), 14)
    assert flat.dropna().eq(50).all()
    rnd = rsi(series(100 + np.cumsum(np.random.default_rng(1).normal(0, 1, 300))), 14).dropna()
    assert ((rnd >= 0) & (rnd <= 100)).all()


def test_macd_on_linear_ramp_converges_to_lag_difference():
    # En una rampa de pendiente m, EMA(n) rezaga m·(n-1)/2 → MACD = m·(25-11)/2 = 7m.
    slope = 0.5
    m = macd(series(100 + slope * np.arange(400)))
    assert m.macd.iloc[-1] == pytest.approx(7 * slope, rel=1e-6)
    assert m.signal.iloc[-1] == pytest.approx(7 * slope, rel=1e-6)
    assert m.histogram.iloc[-1] == pytest.approx(0, abs=1e-6)


def test_bollinger_bands_population_std():
    vals = [1, 2, 3, 4, 5]
    b = bollinger(series(vals), n=5, k=2)
    std = np.std(vals)  # ddof=0
    assert b.middle.iloc[-1] == pytest.approx(3)
    assert b.upper.iloc[-1] == pytest.approx(3 + 2 * std)
    assert b.lower.iloc[-1] == pytest.approx(3 - 2 * std)
    assert b.percent_b.iloc[-1] == pytest.approx((5 - b.lower.iloc[-1]) / (4 * std))


def test_atr_constant_range():
    n = 40
    close = series([100.0] * n)
    a = atr(close + 1, close - 1, close, 14)
    assert a.dropna().round(10).eq(2.0).all()


def test_atr_includes_gaps():
    close = series([10, 20])
    high = series([11, 21])
    low = series([9, 19])
    from app.analytics.technical import true_range

    tr = true_range(high, low, close)
    assert tr.tolist() == [2.0, 11.0]  # |21 - 10| supera high-low por el gap
