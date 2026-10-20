"""Rango probable de precio a 20/60/120 ruedas, con cobertura validada fuera de muestra.

El retorno logarítmico a H ruedas se expresa en unidades de la volatilidad propia del activo:
z = log(1 + fwd_H) / (vol_60 · √(H/252)). Los cuantiles de z se estiman por decil de puntaje
(si el modelo de ese horizonte demostró ventaja) o para todo el universo (si no), con los
mismos cortes anuales walk-forward que el modelo de probabilidades. El rango de un activo es
precio × exp(z_q · σ_H): el ancho lo da su volatilidad y el centro, la historia de su decil.

Validación: para cada año se usan solo cuantiles estimados con años anteriores (con embargo)
y se mide qué porcentaje de los resultados reales cayó dentro del rango del 50% y del 80%.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.analytics.model import MIN_TRAIN_SAMPLES, MIN_TRAIN_YEARS

QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90)
DECILES = 10
# Piso de volatilidad anual: evita rangos de ancho casi nulo en series casi planas.
MIN_VOL = 0.10


@dataclass
class RangeModel:
    horizon: int
    report: dict
    conditional: bool = False
    edges: np.ndarray | None = None  # cortes de puntaje entre deciles
    table: dict[int, np.ndarray] = field(default_factory=dict)  # decil → cuantiles de z


def _sigma(vol: pd.Series, horizon: int) -> pd.Series:
    return vol.clip(lower=MIN_VOL) * math.sqrt(horizon / 252)


def _prepare(panel: pd.DataFrame, horizon: int) -> pd.DataFrame:
    target = f"fwd_{horizon}"
    data = panel.dropna(subset=["score", "vol_60", target]).copy()
    data = data[(data[target] > -1) & np.isfinite(data["vol_60"])]
    data["sigma"] = _sigma(data["vol_60"], horizon)
    data["z"] = np.log1p(data[target]) / data["sigma"]
    return data[np.isfinite(data["z"])]


def _fit(train: pd.DataFrame, conditional: bool) -> tuple[np.ndarray | None, dict[int, np.ndarray]]:
    if not conditional:
        return None, {0: train["z"].quantile(QUANTILES).to_numpy()}
    edges = train["score"].quantile(np.linspace(0, 1, DECILES + 1)[1:-1]).to_numpy()
    dec = np.searchsorted(edges, train["score"].to_numpy(), side="right")
    table = {
        int(d): train.loc[dec == d, "z"].quantile(QUANTILES).to_numpy() for d in range(DECILES)
    }
    return edges, table


def _bucket(edges: np.ndarray | None, score: np.ndarray) -> np.ndarray:
    if edges is None:
        return np.zeros(len(score), dtype=int)
    return np.searchsorted(edges, score, side="right")


def _pinball(z: np.ndarray, q: np.ndarray) -> float:
    """Pérdida pinball media sobre QUANTILES (regla de puntaje propia para cuantiles)."""
    taus = np.array(QUANTILES)
    diff = z[:, None] - q
    return float(np.mean(np.maximum(taus * diff, (taus - 1) * diff)))


def fit_ranges(panel: pd.DataFrame, horizon: int, allow_conditional: bool) -> RangeModel:
    """Cuantiles por decil de puntaje solo si `allow_conditional` (el modelo de probabilidad
    del horizonte tiene ventaja demostrada) y si además mejoran la pérdida pinball fuera de
    muestra frente a los cuantiles del universo; si no, el centro por decil sería ruido."""
    data = _prepare(panel, horizon)
    report: dict = {"horizon": horizon, "quantiles": list(QUANTILES), "n_samples": int(len(data))}
    if len(data) < MIN_TRAIN_SAMPLES:
        report["status"] = f"muestras insuficientes ({len(data)})"
        return RangeModel(horizon, report)
    years = sorted(data["date"].dt.year.unique())
    embargo = pd.Timedelta(days=int(horizon * 1.5) + 7)
    parts: dict[bool, list[pd.DataFrame]] = {False: [], True: []}
    loss: dict[bool, list[float]] = {False: [], True: []}
    for y in years[MIN_TRAIN_YEARS:]:
        test = data[data["date"].dt.year == y]
        train = data[data["date"] < pd.Timestamp(year=y, month=1, day=1) - embargo]
        if len(train) < MIN_TRAIN_SAMPLES or test.empty:
            continue
        z = test["z"].to_numpy()
        for cond in (False, True):
            edges, table = _fit(train, cond)
            q = np.vstack([table[int(b)] for b in _bucket(edges, test["score"].to_numpy())])
            loss[cond].append(_pinball(z, q) * len(z))
            parts[cond].append(
                pd.DataFrame(
                    {
                        "year": y,
                        "in80": (z >= q[:, 0]) & (z <= q[:, 4]),
                        "in50": (z >= q[:, 1]) & (z <= q[:, 3]),
                        "below": z < q[:, 0],
                    }
                )
            )
    if not parts[False]:
        report["status"] = "historia insuficiente para validación walk-forward"
        return RangeModel(horizon, report)
    n = sum(len(p) for p in parts[False])
    pin = {c: sum(v) / n for c, v in loss.items()}
    conditional = bool(allow_conditional and pin[True] < pin[False])
    oos = pd.concat(parts[conditional])
    by_year = [
        {"year": int(y), "cov80": round(float(g["in80"].mean()), 4), "n": int(len(g))}
        for y, g in oos.groupby("year")
    ]
    edges, table = _fit(data, conditional)
    mid = table[DECILES // 2 if conditional else 0]
    sigma30 = 0.3 * math.sqrt(horizon / 252)
    report.update(
        {
            "status": "ok",
            "conditional": conditional,
            "pinball_universe": round(pin[False], 5),
            "pinball_decile": round(pin[True], 5),
            "oos_samples": int(len(oos)),
            "coverage_80": round(float(oos["in80"].mean()), 4),
            "coverage_50": round(float(oos["in50"].mean()), 4),
            "below_80": round(float(oos["below"].mean()), 4),
            "by_year": by_year,
            "years_80_within_10pp": sum(1 for r in by_year if abs(r["cov80"] - 0.8) <= 0.1),
            # Rango de referencia para una acción con 30% de volatilidad anual (decil medio).
            "example_vol30": [round(math.expm1(float(zq) * sigma30), 4) for zq in mid],
            # Cuantiles de z de todo el universo (para escalar con otra volatilidad, p. ej. la
            # de una cartera).
            "z_universe": [round(float(z), 4) for z in _fit(data, False)[1][0]],
        }
    )
    return RangeModel(horizon, report, conditional, edges, table)


def predict_ranges(rm: RangeModel, rows: pd.DataFrame) -> list[dict | None]:
    """Retornos en los cuantiles QUANTILES para cada fila (score, vol_60)."""
    if not rm.table:
        return [None] * len(rows)
    out: list[dict | None] = []
    for _, row in rows.iterrows():
        score, vol = row.get("score"), row.get("vol_60")
        if score is None or vol is None or not (np.isfinite(score) and np.isfinite(vol)):
            out.append(None)
            continue
        b = int(_bucket(rm.edges, np.array([score]))[0])
        sigma = max(float(vol), MIN_VOL) * math.sqrt(rm.horizon / 252)
        rets = [round(float(math.expm1(zq * sigma)), 4) for zq in rm.table[b]]
        out.append(
            {
                "horizon": rm.horizon,
                "returns": dict(zip(("p10", "p25", "p50", "p75", "p90"), rets, strict=True)),
                "vol": round(float(vol), 4),
                "decile": b + 1 if rm.conditional else None,
                "conditional": rm.conditional,
                "coverage_80": rm.report.get("coverage_80"),
                "coverage_50": rm.report.get("coverage_50"),
            }
        )
    return out
