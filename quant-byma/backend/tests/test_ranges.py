import numpy as np
import pandas as pd

from app.analytics.model import AssetInput, build_panel
from app.analytics.ranges import fit_ranges, predict_ranges
from tests.test_model import _synthetic_assets


def _random_walks(n_assets=30, n_days=1500, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2019-01-01", periods=n_days)
    out = []
    for i in range(n_assets):
        vol = 0.10 + 0.5 * i / n_assets  # 10% a 60% anual
        rets = rng.normal(0, vol / np.sqrt(252), n_days)
        out.append(AssetInput(f"R{i}", pd.Series(100 * np.exp(np.cumsum(rets)), index=idx), None))
    return out


def test_ranges_are_calibrated_out_of_sample_and_scale_with_volatility():
    panel = build_panel(_random_walks())
    rm = fit_ranges(panel, 20, allow_conditional=False)
    r = rm.report
    assert r["status"] == "ok" and r["conditional"] is False
    assert abs(r["coverage_80"] - 0.80) < 0.05
    assert abs(r["coverage_50"] - 0.50) < 0.05
    latest = panel.sort_values("date").groupby("ticker").tail(1).set_index("ticker")
    preds = dict(zip(latest.index, predict_ranges(rm, latest.reset_index()), strict=True))
    lo, hi = preds["R1"]["returns"], preds["R29"]["returns"]
    assert lo["p10"] < lo["p50"] < lo["p90"]
    assert (hi["p90"] - hi["p10"]) > 2 * (lo["p90"] - lo["p10"])  # más volatilidad, más ancho


def test_decile_conditioning_only_when_allowed_and_it_helps():
    panel = build_panel(_synthetic_assets())
    off = fit_ranges(panel, 20, allow_conditional=False)
    assert off.report["conditional"] is False and off.edges is None
    on = fit_ranges(panel, 20, allow_conditional=True)
    assert on.report["pinball_decile"] < on.report["pinball_universe"]
    assert on.report["conditional"] is True
    # Con señal real, el decil superior tiene la mediana más alta que el inferior.
    assert on.table[9][2] > on.table[0][2]
