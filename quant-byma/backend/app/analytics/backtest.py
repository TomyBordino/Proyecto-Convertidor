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
    end_year: int | None = None  # para separar períodos de diseño y de prueba
    benchmark: str = "SPY"
    # "equal": igual peso. "inv_vol": peso proporcional a 1 / volatilidad de 3 meses.
    weighting: str = "equal"
    # Filtro de régimen: "none"; "spy_bear": a liquidez si el SPY está en etapa 4 (bajista);
    # "spy_weak": también en etapa 3 (techo). La liquidez rinde la tasa a 3 meses.
    regime: str = "none"


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


def _ranked(day: pd.DataFrame, s: Strategy, key: str) -> list[str]:
    d = day.dropna(subset=[key]).sort_values(key, ascending=False)
    if s.max_per_sector:
        d = d[d.groupby("sector").cumcount() < s.max_per_sector]
    return list(d["ticker"])


WEIGHTINGS = ("equal", "inv_vol", "rank", "risk_parity")
RP_MONTHS = 36  # meses de historia para las correlaciones de la paridad de riesgo


def monthly_history(panel: pd.DataFrame) -> pd.DataFrame:
    """Retornos de 20 ruedas por fecha de inicio (fecha × ticker), para estimar correlaciones."""
    if "fwd_20" not in panel.columns:
        return pd.DataFrame()
    return panel.pivot_table(index="date", columns="ticker", values="fwd_20", aggfunc="last")


def _risk_parity(cov: np.ndarray, iters: int = 200) -> np.ndarray:
    """Pesos de contribución al riesgo igual (iteración multiplicativa)."""
    n = len(cov)
    w = 1 / np.sqrt(np.clip(np.diag(cov), 1e-8, None))
    w /= w.sum()
    for _ in range(iters):
        port = float(w @ cov @ w)
        if port <= 0:
            break
        rc = w * (cov @ w) / port
        w = w * np.sqrt((1 / n) / np.clip(rc, 1e-10, None))
        w /= w.sum()
    return w


def _weights(
    day: pd.DataFrame,
    picks: list[str],
    s: Strategy,
    hist: pd.DataFrame | None = None,
    when: pd.Timestamp | None = None,
) -> dict[str, float]:
    if not picks:
        return {}
    n = len(picks)
    if s.weighting == "rank":
        raw = pd.Series([n - i for i in range(n)], index=picks, dtype=float)
        return {t: round(float(v), 4) for t, v in (raw / raw.sum()).items()}
    if s.weighting == "inv_vol" and "vol_60" in day.columns:
        inv = 1 / day.set_index("ticker").loc[picks, "vol_60"].clip(lower=0.1).fillna(0.3)
        return {t: round(float(v), 4) for t, v in (inv / inv.sum()).items()}
    if s.weighting == "risk_parity" and hist is not None and when is not None and not hist.empty:
        # Solo retornos ya cerrados a la fecha: períodos que empezaron hace 28+ días.
        past = hist[hist.index <= when - pd.Timedelta(days=28)]
        past = past.iloc[::-1].iloc[::4].iloc[:RP_MONTHS]  # mensuales sin solapamiento
        cols = [t for t in picks if t in past.columns]
        r = past[cols].dropna(axis=1, thresh=12)
        if r.shape[1] >= 2:
            cov = r.cov().to_numpy()
            # Contracción hacia la diagonal: con pocos meses la matriz es inestable.
            cov = 0.5 * cov + 0.5 * np.diag(np.diag(cov))
            cov = np.nan_to_num(cov, nan=0.0) + np.eye(len(cov)) * 1e-6
            w = pd.Series(_risk_parity(cov), index=r.columns)
            missing = [t for t in picks if t not in w.index]
            if missing:  # sin historia suficiente: peso promedio
                w = pd.concat([w * (1 - len(missing) / n), pd.Series(1 / n, index=missing)])
            w = w / w.sum()
            return {t: round(float(w[t]), 4) for t in picks}
        return _weights(day, picks, Strategy(weighting="inv_vol"), None, None)
    return {t: round(1 / n, 4) for t in picks}


def current_plan(panel: pd.DataFrame, meta: dict[str, dict], s: Strategy) -> dict:
    """Qué indica la estrategia hoy: selección con pesos, zona de permanencia (los primeros
    buffer × N, que pueden conservarse si ya están en cartera) y si el filtro de mercado
    está activo."""
    key = SORT_KEYS[s.sort]
    last = panel["date"].max()
    day = panel[panel["date"] == last].copy()
    day["kind"] = day["ticker"].map(lambda t: meta.get(t, {}).get("kind"))
    day["sector"] = day["ticker"].map(lambda t: meta.get(t, {}).get("sector") or "Sin clasificar")
    spy = day.loc[day["ticker"] == s.benchmark, "stage"]
    off = {"spy_bear": {4}, "spy_weak": {3, 4}}.get(s.regime, set())
    out = bool(off) and not spy.empty and spy.iloc[0] in off
    if s.kind:
        day = day[day["kind"] == s.kind]
    if s.stages:
        day = day[day["stage"].isin(s.stages)]
    if s.sectors:
        day = day[day["sector"].isin(s.sectors)]
    ranked = _ranked(day, s, key)
    picks = ranked[: s.top_n]
    return {
        "as_of": str(pd.Timestamp(last).date()),
        "out_of_market": out,
        "benchmark_stage": int(spy.iloc[0]) if not spy.empty and pd.notna(spy.iloc[0]) else None,
        "weights": {}
        if out
        else _weights(
            day, picks, s, monthly_history(panel) if s.weighting == "risk_parity" else None, last
        ),
        "keep_zone": ranked[: int(round(s.top_n * max(1.0, s.buffer)))],
    }


def _select(day: pd.DataFrame, s: Strategy, key: str, held: set[str] | None = None) -> list[str]:
    ranked = _ranked(day, s, key)
    if not held or s.buffer <= 1:
        return ranked[: s.top_n]
    keep = [t for t in ranked[: int(round(s.top_n * s.buffer))] if t in held][: s.top_n]
    fill = [t for t in ranked if t not in keep][: s.top_n - len(keep)]
    return keep + fill


def run_backtest(
    panel: pd.DataFrame, meta: dict[str, dict], s: Strategy, cash: pd.Series | None = None
) -> dict:
    """`meta`: ticker → {"kind", "sector"}. `cash`: tasa anual de la liquidez por fecha (fracción,
    p. ej. 0,045), usada cuando el filtro de régimen saca la cartera del mercado."""
    if s.rebalance not in REBALANCE:
        raise ValueError(f"rebalanceo debe ser uno de {REBALANCE}")
    if s.sort not in SORT_KEYS:
        raise ValueError(f"orden debe ser uno de {list(SORT_KEYS)}")
    key, target = SORT_KEYS[s.sort], f"fwd_{s.rebalance}"
    cols = ["date", "ticker", "score", "trend_score", "value_score", "stage", target]
    df = panel[cols + (["vol_60"] if "vol_60" in panel.columns else [])].copy()
    df["kind"] = df["ticker"].map(lambda t: meta.get(t, {}).get("kind"))
    df["sector"] = df["ticker"].map(lambda t: meta.get(t, {}).get("sector") or "Sin clasificar")
    bench_rows = df[df["ticker"] == s.benchmark].set_index("date")
    bench = bench_rows[target]
    bench_stage = bench_rows["stage"]
    off_stages = {"spy_bear": {4}, "spy_weak": {3, 4}}.get(s.regime, set())
    universe = df.dropna(subset=["score"])
    if s.kind:
        universe = universe[universe["kind"] == s.kind]
    if s.start_year:
        universe = universe[universe["date"].dt.year >= s.start_year]
    if s.end_year:
        universe = universe[universe["date"].dt.year <= s.end_year]
    eligible = universe
    if s.stages:
        eligible = eligible[eligible["stage"].isin(s.stages)]
    if s.sectors:
        eligible = eligible[eligible["sector"].isin(s.sectors)]

    dates = sorted(universe["date"].unique())
    every = max(1, s.rebalance // STEP)
    rebal = dates[len(dates) - 1 :: -every][::-1]  # alineado a la última fecha
    by_date = dict(tuple(eligible.groupby("date")))
    hist = monthly_history(panel) if s.weighting == "risk_parity" else None
    uni_by_date = dict(tuple(universe.groupby("date")))

    rows: list[dict] = []
    prev: set[str] = set()
    picks_now: list[str] = []
    for d in rebal:
        day = by_date.get(d)
        out_of_market = bool(off_stages) and bench_stage.get(d) in off_stages
        picks = _select(day, s, key, prev) if day is not None else []
        if d == rebal[-1]:
            picks_now = [] if out_of_market else picks
        if not picks or day is None:
            continue
        uni = uni_by_date[d][target]
        fwd = day.set_index("ticker").loc[picks, target]
        if fwd.isna().all() or uni.isna().all():
            continue  # período todavía abierto (sin retorno futuro observado)
        if out_of_market:
            rate = float(cash.asof(d)) if cash is not None and len(cash) else 0.0
            gross = (rate if np.isfinite(rate) else 0.0) * s.rebalance / 252
            cost = 2 * s.cost_bps / 10_000 if prev else 0.0  # se vende todo una sola vez
            rows.append(
                {
                    "date": d,
                    "strategy": gross - cost,
                    "gross": gross,
                    "universe": float(uni.mean(skipna=True)),
                    "benchmark": float(bench.get(d)) if pd.notna(bench.get(d)) else np.nan,
                    "turnover": 1.0 if prev else 0.0,
                    "n": 0,
                }
            )
            prev = set()
            continue
        held = set(picks)
        turnover = 1.0 if not prev else len(held - prev) / len(held)
        cost = 2 * turnover * s.cost_bps / 10_000
        if s.weighting == "equal":
            gross = float(fwd.mean(skipna=True))
        else:
            w = pd.Series(_weights(day, picks, s, hist, d)).reindex(fwd.index).where(fwd.notna())
            gross = float((fwd.fillna(0) * w).sum() / w.sum()) if w.sum() > 0 else 0.0
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
        "time_in_market": round(float((res["n"] > 0).mean()), 4),
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


TOP_N_OPTIONS = (5, 10, 20, 30, 50)
BUFFER_OPTIONS = (1.0, 1.5, 2.0, 3.0)
DESIGN_END = 2015
PRESETS: dict[str, dict] = {
    "robusta": {"sort": "trend", "stages": [1, 2, 3], "weighting": "inv_vol"},
    "proteccion": {
        "sort": "trend",
        "stages": [1, 2, 3],
        "weighting": "inv_vol",
        "regime": "spy_bear",
    },
    "basica": {"sort": "score"},
}


def _summary(r: dict) -> dict:
    m = r.get("metrics", {})
    s, u = m.get("strategy", {}), m.get("universe", {})
    return {
        "cagr": s.get("cagr"),
        "sharpe": s.get("sharpe"),
        "max_drawdown": s.get("max_drawdown"),
        "vol": s.get("vol"),
        "universe_cagr": u.get("cagr"),
        "universe_sharpe": u.get("sharpe"),
        "universe_drawdown": u.get("max_drawdown"),
        "years_beat_universe": r.get("years_beat_universe"),
        "years": len(r.get("by_year", [])),
        "avg_turnover": r.get("avg_turnover"),
    }


def preset_table(
    panel: pd.DataFrame, meta: dict[str, dict], cash: pd.Series | None, cost_bps: float = 50.0
) -> dict:
    """Para cada estrategia y cantidad de papeles: el colchón se elige con el mejor Sharpe en
    el período de diseño (hasta DESIGN_END) y se informa el resultado en diseño, en prueba
    (después de DESIGN_END) y en toda la historia. Rebalanceo mensual."""
    out: dict[str, dict] = {}
    for name, cfg in PRESETS.items():
        out[name] = {}
        for n in TOP_N_OPTIONS:
            best: tuple[float, float, dict] | None = None
            for b in BUFFER_OPTIONS:
                st = Strategy(top_n=n, buffer=b, cost_bps=cost_bps, end_year=DESIGN_END, **cfg)
                r = run_backtest(panel, meta, st, cash)
                sharpe = (r.get("metrics", {}).get("strategy", {}) or {}).get("sharpe")
                score = sharpe if sharpe is not None else -9.0
                if best is None or score > best[0]:
                    best = (score, b, r)
            assert best is not None
            b = best[1]
            test = run_backtest(
                panel,
                meta,
                Strategy(top_n=n, buffer=b, cost_bps=cost_bps, start_year=DESIGN_END + 1, **cfg),
                cash,
            )
            full = run_backtest(
                panel, meta, Strategy(top_n=n, buffer=b, cost_bps=cost_bps, **cfg), cash
            )
            out[name][str(n)] = {
                "buffer": b,
                "design": _summary(best[2]),
                "test": _summary(test),
                "full": _summary(full),
            }
    return {"design_end": DESIGN_END, "cost_bps": cost_bps, "presets": out}
