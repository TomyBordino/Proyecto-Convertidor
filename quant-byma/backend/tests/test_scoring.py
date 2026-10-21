import pytest

from app.analytics.patterns import CrossEvent
from app.analytics.scoring import (
    Component,
    ScoringWeights,
    SubScore,
    TechnicalInputs,
    ccl_subscore,
    composite_score,
    discount,
    fundamental_subscore,
    linear,
    rsi_fraction,
    technical_subscore,
)


def test_linear_mapping_and_inverse():
    assert linear(5, 0, 10) == 0.5
    assert linear(-1, 0, 10) == 0 and linear(11, 0, 10) == 1
    assert linear(0.3, 2.0, 0.3) == 1  # escala inversa (menos deuda = mejor)
    with pytest.raises(ValueError):
        linear(1, 1, 1)


def test_rsi_fraction_sweet_spot():
    assert rsi_fraction(50, True) == 1.0
    assert rsi_fraction(40, True) == pytest.approx(0.6)
    assert rsi_fraction(75, True) == 0
    assert rsi_fraction(50, False) == 0.5


def test_subscore_renormalizes_missing_components():
    sub = SubScore("x", [Component("a", "A", 30, 1.0), Component("b", "B", 70, None)])
    assert sub.score == 100.0


def test_ccl_subscore_direction():
    assert ccl_subscore(-0.05).score == 100
    assert ccl_subscore(0.0).score == 50
    assert ccl_subscore(0.05).score == 0
    assert ccl_subscore(-0.5, ratio_suspect=True).score is None


def test_discount():
    assert discount(10, 20) == 0.5
    assert discount(-5, 20) is None


def test_technical_bullish_beats_bearish():
    bull = TechnicalInputs(
        close=110,
        sma50=105,
        sma200=100,
        sma50_slope=0.03,
        rsi=52,
        macd_hist=0.4,
        macd_hist_prev=0.2,
        pct_b=0.6,
        cross=CrossEvent("golden", 2),
        breakout=True,
    )
    bear = TechnicalInputs(
        close=90,
        sma50=95,
        sma200=100,
        sma50_slope=-0.03,
        rsi=78,
        macd_hist=-0.4,
        macd_hist_prev=-0.2,
        pct_b=1.1,
        cross=CrossEvent("death", 2),
        divergence="bearish",
    )
    sb, sr = technical_subscore(bull).score, technical_subscore(bear).score
    assert sb > 85 and sr < 15
    assert 0 <= sr <= sb <= 100


def test_fundamental_financials_skip_altman_and_leverage():
    ratios = {"pe": 8, "ev_ebitda": 5, "ps": 1, "roe": 0.2, "altman_z": 0.5, "debt_to_equity": 9}
    sub = fundamental_subscore(ratios, {"pe": 10, "ev_ebitda": 6, "ps": 1.2}, {}, is_financial=True)
    keys = {c.key: c for c in sub.components}
    assert keys["altman_z"].fraction is None and keys["leverage"].fraction is None
    assert keys["sector_discount"].fraction is None
    assert keys["hist_discount"].fraction > 0.5


def test_composite_weights_and_renormalization():
    t = SubScore("technical", [Component("a", "A", 1, 0.8)])
    f = SubScore("fundamental", [Component("a", "A", 1, 0.6)])
    c = SubScore("ccl", [Component("a", "A", 1, None)])
    res = composite_score([t, f, c], ScoringWeights())
    assert res.composite == pytest.approx((0.4 * 80 + 0.35 * 60) / 0.75, abs=0.01)
    assert set(res.weights_used) == {"technical", "fundamental"}
    assert sum(res.weights_used.values()) == pytest.approx(1)
