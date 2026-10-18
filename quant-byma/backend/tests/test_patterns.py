import numpy as np
import pandas as pd

from app.analytics.patterns import detect_breakout, last_ma_cross, rsi_divergence


def s(values):
    return pd.Series(values, index=pd.bdate_range("2024-01-01", periods=len(values)), dtype=float)


def test_golden_and_death_cross():
    slow = s([10.0] * 10)
    fast = s([9, 9, 9, 9, 9, 9, 11, 11, 11, 11])
    ev = last_ma_cross(fast, slow, lookback=20)
    assert ev is not None and ev.kind == "golden" and ev.bars_ago == 3
    ev2 = last_ma_cross(s([11] * 8 + [9, 9]), slow, lookback=20)
    assert ev2.kind == "death" and ev2.bars_ago == 1
    assert last_ma_cross(fast, slow, lookback=2) is None


def test_breakout_requires_volume():
    close = s([10] * 60 + [12])
    high = close + 0.5
    assert detect_breakout(close, high, s([100] * 60 + [200])) is not None
    assert detect_breakout(close, high, s([100] * 61)) is None


def test_bullish_divergence():
    t = np.arange(60)
    price = 100 - 0.2 * t + 3 * np.sin(t / 3)
    rsi = 40 + 0.2 * t + 5 * np.sin(t / 3)  # mínimos crecientes
    assert rsi_divergence(s(price), s(rsi), lookback=60, order=3) == "bullish"
