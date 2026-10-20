"""Backtest de estrategias sobre el panel histórico point-in-time.

En cada fecha de rebalanceo se eligen los N activos mejor ordenados (con los filtros de la
estrategia) usando solo información disponible ese día, y se mantienen, con igual peso,
hasta el rebalanceo siguiente. El retorno de cada período es el retorno futuro observado
(`fwd_H`) de esos activos, en USD y con retorno total cuando hay dividendos. Los costos se
descuentan por la rotación de la cartera.

El puntaje usa pesos fijos (no ajustados a estos datos), así que el backtest no tiene sesgo
de ajuste. Sí tiene sesgo de supervivencia: el universo son los activos que cotizan hoy.
Por eso la comparación relevante es contra el promedio del mismo universo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.analytics.model import STEP

REBALANCE = (20, 60, 120)
SORT_KEYS = {"score": "score", "trend": "trend_score", "value": "value_score"}


@dataclass
class Strategy:
    top_n: int = 20
    rebalance: int = 20  # ruedas; debe ser uno de REBALANCE
    sort: str = "score"  # score | trend | value
    stages: list[int] = field(default_factory=list)  # vacío = todas
    kind: str | None = None  # CEDEAR | LOCAL | None
    sectors: list[str] = field(default_factory=list)
    max_per_sector: int | None = None
    cost_bps: float = 50.0  # costo por lado (comisión + derechos + spread), en puntos básicos
    # Colchón de permanencia: un activo en cartera se conserva mientras siga dentro de los
    # primeros buffer × N (1 = sin colchón). Baja la rotación y, con ella, los costos.
    buffer: float = 2.0
    start_year: int | None = None
    benchmark: str = "SPY"


def _annualize(r: pd.Series, per_year: float) -> dict:
    if r.empty:
        return {}
    eq = (1 + r).cumprod()
    years = len(r) / per_year
    cagr = float(eq.iloc[-1] ** (1 / years) - 1) if years > 0 and eq.iloc[-1] > 0 else None
    vol = float(r.std() * math.sqrt(per_year)) if len(r) > 1 else None
    dd = float((eq / eq.cummax() - 1).min())
    return {
        "cagr": round(cagr, 4) if cagr is not None else None,
        "vol": round(vol, 4) if vol else None,
        "sharpe": round(cagr / vol, 2) if cagr is not None and vol else None,
        "max_drawdown": round(dd, 4),
        "total_return": round(float(eq.iloc[-1] - 1), 4),
        "hit_rate": round(float((r > 0).mean()), 4),
        "worst_period": round(float(r.min()), 4),
        "best_period": round(float(r.max()), 4),
    }


def _select(day: pd.DataFrame, s: Strategy, key: str, held: set[str] | None = None) -> list[str]:
    d = day.dropna(subset=[key]).sort_values(key, ascending=False)
    if s.max_per_sector:
        d = d[d.groupby("sector").cumcount() < s.max_per_sector]
    ranked = list(d["ticker"])
    if not held or s.buffer <= 1:
        return ranked[: s.top_n]
    keep = [t for t in ranked[: int(round(s.top_n * s.buffer))] if t in held][: s.top_n]
    fill = [t for t in ranked if t not in keep][: s.top_n - len(keep)]
    return keep + fill


def run_backtest(panel: pd.DataFrame, meta: dict[str, dict], s: Strategy) -> dict:
    """`meta`: ticker → {"kind", "sector"}. Devuelve curvas, métricas y la selección actual."""
    if s.rebalance not in REBALANCE:
        raise ValueError(f"rebalanceo debe ser uno de {REBALANCE}")
    if s.sort not in SORT_KEYS:
        raise ValueError(f"orden debe ser uno de {list(SORT_KEYS)}")
    key, target = SORT_KEYS[s.sort], f"fwd_{s.rebalance}"
    df = panel[["date", "ticker", "score", "trend_score", "value_score", "stage", target]].copy()
    df["kind"] = df["ticker"].map(lambda t: meta.get(t, {}).get("kind"))
    df["sector"] = df["ticker"].map(lambda t: meta.get(t, {}).get("sector") or "Sin clasificar")
    bench = df[df["ticker"] == s.benchmark].set_index("date")[target]
    universe = df.dropna(subset=["score"])
    if s.kind:
        universe = universe[universe["kind"] == s.kind]
    if s.start_year:
        universe = universe[universe["date"].dt.year >= s.start_year]
    eligible = universe
    if s.stages:
        eligible = eligible[eligible["stage"].isin(s.stages)]
    if s.sectors:
        eligible = eligible[eligible["sector"].isin(s.sectors)]

    dates = sorted(universe["date"].unique())
    every = max(1, s.rebalance // STEP)
    rebal = dates[len(dates) - 1 :: -every][::-1]  # alineado a la última fecha
    by_date = dict(tuple(eligible.groupby("date")))
    uni_by_date = dict(tuple(universe.groupby("date")))

    rows: list[dict] = []
    prev: set[str] = set()
    picks_now: list[str] = []
    for d in rebal:
        day = by_date.get(d)
        picks = _select(day, s, key, prev) if day is not None else []
        if d == rebal[-1]:
            picks_now = picks
        if not picks or day is None:
            continue
        fwd = day.set_index("ticker").loc[picks, target]
        uni = uni_by_date[d][target]
        if fwd.isna().all() or uni.isna().all():
            continue  # período todavía abierto (sin retorno futuro observado)
        held = set(picks)
        turnover = 1.0 if not prev else len(held - prev) / len(held)
        cost = 2 * turnover * s.cost_bps / 10_000
        gross = float(fwd.mean(skipna=True))
        rows.append(
            {
                "date": d,
                "strategy": gross - cost,
                "gross": gross,
                "universe": float(uni.mean(skipna=True)),
                "benchmark": float(bench.get(d)) if pd.notna(bench.get(d)) else np.nan,
                "turnover": turnover,
                "n": len(picks),
            }
        )
        prev = held
    if not rows:
        return {"status": "sin períodos con datos", "picks": picks_now}
    res = pd.DataFrame(rows).set_index("date")
    per_year = 252 / s.rebalance
    curves = (1 + res[["strategy", "universe", "benchmark"]].fillna(0)).cumprod()
    years = res.groupby(res.index.year)[["strategy", "universe", "benchmark"]].apply(
        lambda g: (1 + g.fillna(0)).prod() - 1
    )
    excess = res["strategy"] - res["universe"]
    return {
        "status": "ok",
        "strategy": s.__dict__,
        "periods": len(res),
        "first_date": str(pd.Timestamp(res.index[0]).date()),
        "last_date": str(pd.Timestamp(res.index[-1]).date()),
        "metrics": {
            "strategy": _annualize(res["strategy"], per_year),
            "strategy_gross": _annualize(res["gross"], per_year),
            "universe": _annualize(res["universe"], per_year),
            "benchmark": _annualize(res["benchmark"].dropna(), per_year),
        },
        "beat_universe": round(float((excess > 0).mean()), 4),
        "avg_turnover": round(float(res["turnover"].iloc[1:].mean()), 4) if len(res) > 1 else None,
        "years_beat_universe": int((years["strategy"] > years["universe"]).sum()),
        "curves": [
            {
                "time": str(pd.Timestamp(d).date()),
                "strategy": round(float(r.strategy), 4),
                "universe": round(float(r.universe), 4),
                "benchmark": round(float(r.benchmark), 4),
            }
            for d, r in curves.iterrows()
        ],
        "by_year": [
            {
                "year": int(y),
                "strategy": round(float(r.strategy), 4),
                "universe": round(float(r.universe), 4),
                "benchmark": round(float(r.benchmark), 4),
            }
            for y, r in years.iterrows()
        ],
        "picks": picks_now,
    }


def quintile_returns(panel: pd.DataFrame, horizon: int = 20, key: str = "score") -> list[dict]:
    """Retorno anualizado de cada quintil del puntaje (rebalanceo cada `horizon` ruedas, sin
    costos): muestra si el orden del modelo se traduce en plata en todo el universo."""
    target = f"fwd_{horizon}"
    d = panel.dropna(subset=[key, target])
    dates = sorted(d["date"].unique())
    keep = set(dates[len(dates) - 1 :: -max(1, horizon // STEP)])
    d = d[d["date"].isin(keep)].copy()
    counts = d.groupby("date")[key].transform("size")
    d = d[counts >= 25].copy()  # quintiles con al menos 5 activos cada uno
    d["q"] = d.groupby("date")[key].transform(
        lambda x: pd.qcut(x.rank(method="first"), 5, labels=False) + 1
    )
    per = d.groupby(["date", "q"])[target].mean().unstack()
    per_year = 252 / horizon
    out = []
    for q in per.columns:
        r = per[q].dropna()
        eq = float((1 + r).prod())
        yrs = len(r) / per_year
        out.append(
            {
                "quintile": int(q),
                "cagr": round(eq ** (1 / yrs) - 1, 4) if yrs > 0 and eq > 0 else None,
                "hit_rate": round(float((r > 0).mean()), 4),
                "periods": int(len(r)),
            }
        )
    return out
