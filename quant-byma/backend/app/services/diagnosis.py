"""Diagnóstico por activo: etapa, momento fundamental y probabilidades con evidencia."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from app.analytics.model import (
    FEATURES,
    HORIZONS,
    AssetInput,
    build_panel,
    predict,
    stage_statistics,
    train_horizon,
)
from app.analytics.ranges import fit_ranges, predict_ranges
from app.analytics.regime import STAGES, current_regime

log = logging.getLogger(__name__)

PRIMARY_HORIZON = 60
# Diferencia mínima con la tasa base para hablar de sesgo (puntos de probabilidad).
BIAS_MARGIN = 0.015
MIN_SECTOR_PEERS = 5


def _bucket(pct: float | None, labels: tuple[str, str, str]) -> str | None:
    if pct is None or not np.isfinite(pct):
        return None
    return labels[0] if pct >= 2 / 3 else labels[2] if pct < 1 / 3 else labels[1]


def fundamental_state(latest: pd.DataFrame, sectors: dict[str, str]) -> dict[str, dict]:
    """Percentiles de valuación, calidad, crecimiento y deuda vs el sector (o el universo
    si el sector tiene menos de MIN_SECTOR_PEERS activos con balances)."""
    df = latest.set_index("ticker")
    df = df[df["has_fundamentals"] > 0]
    df = df.assign(sector=[sectors.get(t, "") for t in df.index])
    metrics = {
        "earnings_yield": True,
        "sales_yield": True,
        "book_yield": True,
        "fcf_yield": True,
        "roe": True,
        "growth": True,
        "lev": False,
    }
    pct = pd.DataFrame(index=df.index)
    for col, higher_better in metrics.items():
        vals = df[col] if higher_better else -df[col]
        universe = vals.rank(pct=True)
        by_sector = vals.groupby(df["sector"]).rank(pct=True)
        counts = vals.notna().groupby(df["sector"]).transform("sum")
        pct[col] = by_sector.where(counts >= MIN_SECTOR_PEERS, universe)
    out = {}
    for t, row in pct.iterrows():
        valuation = row[["earnings_yield", "sales_yield", "book_yield"]].mean(skipna=True)
        peers = (
            "sector"
            if (
                df.loc[t, "sector"]
                and (df["sector"] == df.loc[t, "sector"]).sum() >= MIN_SECTOR_PEERS
            )
            else "universo"
        )
        out[str(t)] = {
            "compared_to": peers,
            "valuation_pct": _r(valuation),
            "valuation": _bucket(valuation, ("Barata", "Neutral", "Cara")),
            "quality_pct": _r(row["roe"]),
            "quality": _bucket(row["roe"], ("Alta", "Media", "Baja")),
            "growth_pct": _r(row["growth"]),
            "growth": _bucket(row["growth"], ("Alto", "Medio", "Bajo")),
            "leverage_pct": _r(row["lev"]),
            "leverage": _bucket(row["lev"], ("Bajo", "Medio", "Alto")),
            "fcf_pct": _r(row["fcf_yield"]),
        }
    return out


def _r(x: object) -> float | None:
    try:
        v = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return round(v, 4) if np.isfinite(v) else None


def bias(pred: dict | None) -> tuple[str, bool]:
    """Sesgo vs la tasa base. Exige que el intervalo de confianza de las situaciones
    históricas similares excluya a la tasa base; si no, el sesgo es Neutral."""
    if not pred or pred.get("base_rate") is None:
        return "Sin datos", False
    if pred.get("has_skill") is False:
        return "Neutral", False  # sin ventaja demostrada en este horizonte
    p, base = pred["probability"], pred["base_rate"]
    sim = pred["similar"]
    significant = sim["n"] > 0 and (sim["ci_low"] > base or sim["ci_high"] < base)
    # Solo se declara sesgo cuando la evidencia lo respalda: una diferencia chica sin
    # significancia no distingue al activo de uno cualquiera.
    if p >= base + BIAS_MARGIN and significant:
        return "Favorable", True
    if p <= base - BIAS_MARGIN and significant:
        return "Desfavorable", True
    return "Neutral", False


def summary(ticker: str, d: dict) -> str:
    parts = []
    if d.get("stage"):
        sub = f" ({d['substate'].lower()})" if d.get("substate") else ""
        parts.append(f"Etapa {d['stage']} · {d['stage_name']}{sub}.")
    f = d.get("fundamentals")
    if f and f.get("valuation"):
        ref = "su sector" if f["compared_to"] == "sector" else "el universo"
        parts.append(
            f"Valuación {f['valuation'].lower()} vs {ref}"
            + (f", calidad {f['quality'].lower()}" if f.get("quality") else "")
            + (f", crecimiento {f['growth'].lower()}" if f.get("growth") else "")
            + "."
        )
    pred = d.get("predictions", {}).get(str(PRIMARY_HORIZON))
    if pred and pred.get("has_skill") is False:
        parts.append(
            f"A {PRIMARY_HORIZON} ruedas el modelo no demostró ventaja sobre la tasa base "
            f"({pred['base_rate']:.0%}), que es la mejor estimación disponible."
        )
    elif pred:
        sim = pred["similar"]
        parts.append(
            f"Probabilidad de cotizar más alto en {PRIMARY_HORIZON} ruedas: "
            f"{pred['probability']:.0%} (tasa base del universo {pred['base_rate']:.0%})."
        )
        if pred.get("decile"):
            parts.append(
                f"Su puntaje está en el decil {pred['decile']} de 10, que históricamente subió "
                f"el {pred['decile_hit_rate']:.0%} de las veces."
            )
        if sim["hit_rate"] is not None:
            parts.append(
                f"En situaciones históricas similares se cumplió el {sim['hit_rate']:.0%} de las "
                f"veces (IC95 {sim['ci_low']:.0%}–{sim['ci_high']:.0%}, "
                f"n efectivo {sim['n_effective']})."
            )
    rng = d.get("ranges", {}).get(str(PRIMARY_HORIZON))
    if rng:
        r = rng["returns"]
        parts.append(
            f"Rango probable a {PRIMARY_HORIZON} ruedas (80% de confianza): "
            f"{r['p10']:+.0%} a {r['p90']:+.0%} en USD, con mediana {r['p50']:+.0%}."
        )
    return " ".join(p for p in parts if p)


def diagnose(
    assets: list[AssetInput], sectors: dict[str, str], panel: pd.DataFrame | None = None
) -> tuple[dict[str, dict], dict]:
    panel = build_panel(assets) if panel is None else panel
    report: dict = {
        "horizons": {},
        "stage_stats": {},
        "features": FEATURES,
        "stages": {str(k): {"name": v[0], "description": v[1]} for k, v in STAGES.items()},
    }
    if panel.empty:
        report["status"] = "sin datos suficientes"
        return {}, report
    report["n_assets"] = int(panel["ticker"].nunique())
    report["first_date"] = str(panel["date"].min().date())
    report["last_date"] = str(panel["date"].max().date())

    latest = panel.sort_values("date").groupby("ticker").tail(1)
    preds: dict[int, list] = {}
    rel_preds: dict[int, list] = {}
    range_preds: dict[int, list] = {}
    report["relative"] = {}
    report["ranges"] = {}
    for h in HORIZONS:
        hm = train_horizon(panel, h)
        report["horizons"][str(h)] = hm.report
        report["stage_stats"][str(h)] = stage_statistics(panel, h)
        preds[h] = predict(hm, latest)
        rel = train_horizon(panel, h, target_kind="rel")
        report["relative"][str(h)] = rel.report
        rel_preds[h] = predict(rel, latest)
        rm = fit_ranges(panel, h, hm.has_skill)
        report["ranges"][str(h)] = rm.report
        range_preds[h] = predict_ranges(rm, latest)
        log.info(
            "Modelo %d ruedas: %s",
            h,
            {
                k: v
                for k, v in hm.report.items()
                if k in ("status", "auc", "brier_skill", "base_rate")
            },
        )

    fund = fundamental_state(latest, sectors)
    # Percentil del puntaje dentro del universo actual (0–100): ordena aunque la
    # probabilidad calibrada empate en un mismo escalón.
    score_pct = {
        str(t): round(float(v) * 100, 1)
        for t, v in latest.set_index("ticker")["score"].rank(pct=True).items()
        if np.isfinite(v)
    }
    # La etapa se mide sobre el precio (lo que muestra el gráfico), no sobre el retorno total.
    closes = {a.ticker: a.price_close if a.price_close is not None else a.close for a in assets}
    out: dict[str, dict] = {}
    for i, (_, row) in enumerate(latest.iterrows()):
        t = row["ticker"]
        reg = current_regime(closes[t].dropna())
        stage_ev = {}
        for h in HORIZONS:
            for s in report["stage_stats"][str(h)]:
                if reg.stage is not None and s["stage"] == reg.stage:
                    stage_ev[str(h)] = s
        d: dict[str, Any] = {
            "as_of": str(row["date"].date()),
            "stage": reg.stage,
            "stage_name": reg.stage_name,
            "stage_description": reg.stage_description,
            "substate": reg.substate,
            "substate_description": reg.substate_description,
            "stage_since": reg.stage_since,
            "days_in_stage": reg.days_in_stage,
            "stage_evidence": stage_ev,
            "fundamentals": fund.get(t),
            "predictions": {str(h): preds[h][i] for h in HORIZONS if preds[h][i]},
            "relative": {str(h): rel_preds[h][i] for h in HORIZONS if rel_preds[h][i]},
            "ranges": {str(h): range_preds[h][i] for h in HORIZONS if range_preds[h][i]},
            "score": _r(row.get("score")),
            "score_pct": score_pct.get(t),
        }
        b, significant = bias(d["predictions"].get(str(PRIMARY_HORIZON)))
        d["bias"], d["bias_significant"] = b, significant
        d["summary"] = summary(t, d)
        out[t] = d
    return out, report
