import numpy as np
import pandas as pd
import pytest

from app.analytics.model import (
    AssetInput,
    build_panel,
    predict,
    stage_statistics,
    train_horizon,
    wilson_interval,
)
from app.analytics.regime import current_regime, stage_series
from app.services.diagnosis import bias


def s(values, start="2019-01-01"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


def test_stage_series_trend_phases():
    up = np.linspace(50, 150, 400)
    down = np.linspace(150, 60, 300)
    flat = np.full(200, 60.0) + np.sin(np.arange(200) / 3)
    st = stage_series(s(np.concatenate([up, down, flat])))
    assert st.iloc[399] == 2  # fin de la suba
    assert st.iloc[699] == 4  # fin de la caída
    assert st.iloc[-1] == 1  # base luego de la caída
    assert st.iloc[:149].isna().all()  # sin media de 150 todavía no hay etapa


def test_stage_three_after_uptrend_flattens():
    up = np.linspace(50, 150, 400)
    flat = np.full(200, 150.0) + np.sin(np.arange(200) / 3)
    reg = current_regime(s(np.concatenate([up, flat])))
    assert reg.stage == 3 and reg.stage_name == "Techo / distribución"
    assert reg.days_in_stage and reg.days_in_stage < 200


def test_wilson_interval():
    lo, hi = wilson_interval(0.6, 100)
    assert 0.50 < lo < 0.6 < hi < 0.70
    assert wilson_interval(0.5, 0) == (0.0, 1.0)


def _synthetic_assets(n_assets=30, n_days=1500, seed=0):
    """Activos cuyo retorno futuro depende del momentum pasado (señal conocida)."""
    rng = np.random.default_rng(seed)
    assets = []
    for i in range(n_assets):
        drift_regime = np.repeat(rng.choice([-1.0, 1.0], n_days // 100 + 1), 100)[:n_days]
        rets = drift_regime * 0.0015 + rng.normal(0, 0.01, n_days)
        close = s(100 * np.exp(np.cumsum(rets)))
        assets.append(AssetInput(ticker=f"T{i}", close=close, volume=None))
    return assets


def test_walk_forward_model_learns_persistent_signal_and_is_calibrated():
    panel = build_panel(_synthetic_assets())
    hm = train_horizon(panel, 20)
    r = hm.report
    assert r["status"] == "ok"
    assert r["auc"] > 0.55  # la tendencia persistente es predecible
    assert r["has_skill"] and r["brier_skill"] > 0
    assert r["top_quintile_hit"] > r["bottom_quintile_hit"]
    # La calibración fuera de muestra es monótona creciente en promedio.
    obs = [b["observed"] for b in r["calibration"]]
    assert obs[-1] > obs[0]
    latest = panel.sort_values("date").groupby("ticker").tail(1)
    preds = predict(hm, latest)
    assert all(0 < p["probability"] < 1 for p in preds)
    p = preds[0]
    assert p["similar"]["n"] >= 200 and p["similar"]["ci_low"] <= p["similar"]["ci_high"]
    assert p["drivers_up"] or p["drivers_down"]
    assert all(
        d["feature"] in ("slope_200", "mom_12_1", "dist_sma200", "dd_252")
        for d in p["drivers_up"] + p["drivers_down"]
    )
    stats = stage_statistics(panel, 20)
    assert {st["stage"] for st in stats} <= {1, 2, 3, 4}


def test_no_lookahead_in_features():
    """Cambiar el futuro no puede cambiar las features del pasado."""
    a = _synthetic_assets(n_assets=1, seed=1)[0]
    p1 = build_panel([a])
    altered = a.close.copy()
    altered.iloc[-100:] *= 3
    p2 = build_panel([AssetInput("T0", altered, None)])
    cutoff = a.close.index[-101]
    cols = ["mom_20", "mom_60", "dist_sma50", "rsi14", "stage"]
    m1 = p1[p1["date"] <= cutoff][cols].reset_index(drop=True)
    m2 = p2[p2["date"] <= cutoff][cols].reset_index(drop=True)
    pd.testing.assert_frame_equal(m1, m2)


def test_insufficient_data_returns_no_model():
    panel = build_panel(_synthetic_assets(n_assets=2, n_days=400))
    hm = train_horizon(panel, 60)
    assert hm.calibrator is None and "insuficientes" in hm.report["status"]
    assert predict(hm, panel.tail(1)) == [None]


@pytest.mark.parametrize(
    ("prob", "ci", "expected"),
    [
        (0.70, (0.62, 0.75), ("Favorable", True)),
        (0.56, (0.40, 0.70), ("Neutral", False)),
        (0.40, (0.30, 0.50), ("Desfavorable", True)),
    ],
)
def test_bias(prob, ci, expected):
    pred = {
        "probability": prob,
        "base_rate": 0.55,
        "similar": {"n": 500, "ci_low": ci[0], "ci_high": ci[1]},
    }
    assert bias(pred) == expected


def test_no_skill_falls_back_to_base_rate():
    """Con caminatas aleatorias no hay ventaja: la probabilidad debe ser la tasa base."""
    rng = np.random.default_rng(7)
    assets = [
        AssetInput(f"R{i}", s(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, 1500)))), None)
        for i in range(30)
    ]
    panel = build_panel(assets)
    hm = train_horizon(panel, 60)
    latest = panel.sort_values("date").groupby("ticker").tail(1)
    preds = predict(hm, latest)
    if not hm.has_skill:
        assert {p["probability"] for p in preds} == {hm.report["base_rate"]}
    else:  # una ventaja espuria debería ser mínima
        assert hm.report["brier_skill"] < 0.01


def test_relative_target_and_stable_calibration():
    panel = build_panel(_synthetic_assets())
    rel = train_horizon(panel, 20, target_kind="rel")
    assert rel.report["target"] == "rel"
    # La tasa base de "superar a la mediana" ronda el 50% por construcción.
    assert 0.45 < rel.report["base_rate"] < 0.55
    probs = [p["probability"] for p in predict(rel, panel.sort_values("date").tail(50))]
    assert all(0.05 < p < 0.95 for p in probs)  # sin extremos absurdos por pocos casos


def test_panel_dates_are_shared_across_assets_with_gaps():
    """Con ruedas faltantes distintas por activo, todos comparten las fechas semanales: los
    percentiles se calculan contra el universo completo de cada fecha."""
    rng = np.random.default_rng(3)
    assets = []
    for i in range(6):
        idx = pd.bdate_range("2019-01-01", periods=900)
        keep = rng.random(len(idx)) > 0.03 * i  # cada activo pierde días distintos
        close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(idx)))), index=idx)
        assets.append(AssetInput(ticker=f"G{i}", close=close[keep], volume=None))
    panel = build_panel(assets)
    per_date = panel.groupby("date")["ticker"].nunique()
    assert (per_date == 6).mean() > 0.97
    assert panel["date"].max() <= max(a.close.index.max() for a in assets)
