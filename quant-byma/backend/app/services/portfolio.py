"""Valuación y riesgo de la cartera del usuario."""

from __future__ import annotations

import math
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.ranges import QUANTILES
from app.db.models import Holding, Instrument, ModelRun, ScoreSnapshot
from app.services.data import load_fx
from app.services.events import asset_closes, latest_event_report, load_macro, news_pressure

SENS_WEEKS = 156


class Fx:
    """Dólar MEP y CCL por fecha (el último conocido a esa fecha)."""

    def __init__(self, session: Session) -> None:
        macro = load_macro(session)
        self.ccl = load_fx(session, "CCL")
        self.mep = macro.get("MEP", pd.Series(dtype=float))
        if self.mep.empty:
            self.mep = self.ccl  # sin MEP publicado, el CCL es la mejor aproximación

    @staticmethod
    def _at(s: pd.Series, day: date | None) -> float | None:
        if s.empty:
            return None
        if day is None:
            return float(s.iloc[-1])
        prev = s[s.index <= pd.Timestamp(day)]
        return float(prev.iloc[-1]) if len(prev) else float(s.iloc[0])

    def mep_at(self, day: date | None = None) -> float | None:
        return self._at(self.mep, day)

    def ccl_at(self, day: date | None = None) -> float | None:
        return self._at(self.ccl, day)

    def convert(self, amount: float, currency: str, day: date | None) -> tuple[float, float]:
        """(dólares MEP, pesos). El cable se pasa a MEP con el canje del día (CCL ÷ MEP)."""
        mep = self.mep_at(day) or 1.0
        if currency == "ARS":
            return amount / mep, amount
        if currency == "CABLE":
            ccl = self.ccl_at(day) or mep
            return amount * ccl / mep, amount * ccl
        return amount, amount * mep


def _latest_metrics(session: Session) -> dict[str, dict]:
    day = session.scalar(select(func.max(ScoreSnapshot.day)))
    if day is None:
        return {}
    snaps = session.scalars(select(ScoreSnapshot).where(ScoreSnapshot.day == day)).all()
    return {s.metrics["ticker"]: s.metrics for s in snaps}


def _r(x: float | None, n: int = 4) -> float | None:
    return None if x is None or not math.isfinite(x) else round(float(x), n)


def analyze(session: Session) -> dict:
    holdings = session.scalars(select(Holding).order_by(Holding.ticker)).all()
    fx = Fx(session)
    mep = fx.mep_at()
    metrics = _latest_metrics(session)
    pressure, _ = news_pressure(session, 14)
    rows: list[dict[str, Any]] = []
    for h in holdings:
        m = metrics.get(h.ticker)
        price = m.get("price_ars") if m else None
        value_ars = h.quantity * price if price else None
        value_usd = value_ars / mep if value_ars is not None and mep else None
        pnl = value_usd - h.cost_usd if value_usd is not None and h.cost_usd else None
        p = pressure.get(h.ticker)
        rows.append(
            {
                "id": h.id,
                "ticker": h.ticker,
                "in_universe": m is not None,
                "name": m.get("name") if m else None,
                "sector": m.get("sector") if m else None,
                "kind": m.get("kind") if m else None,
                "quantity": h.quantity,
                "price_ars": price,
                "value_ars": _r(value_ars, 2),
                "value_usd": _r(value_usd, 2),
                "cost_usd": _r(h.cost_usd, 2),
                "cost_ars": _r(h.cost_ars, 2),
                "pnl_usd": _r(pnl, 2),
                "pnl_pct": _r(pnl / h.cost_usd) if pnl is not None and h.cost_usd else None,
                "income_usd": _r(h.income_usd, 2),
                "opened_at": h.opened_at.isoformat() if h.opened_at else None,
                "source": h.source,
                "stage": m.get("stage") if m else None,
                "substate": m.get("substate") if m else None,
                "prob_up_60": m.get("prob_up_60") if m else None,
                "range_low_60": m.get("range_low_60") if m else None,
                "range_mid_60": m.get("range_mid_60") if m else None,
                "range_high_60": m.get("range_high_60") if m else None,
                "news_label": p["label"] if p else None,
                "weight": None,
            }
        )
    total = sum(r["value_usd"] or 0 for r in rows)
    for r in rows:
        r["weight"] = _r(r["value_usd"] / total) if r["value_usd"] and total else None
    priced = [r for r in rows if r["weight"]]
    cost = sum(r["cost_usd"] or 0 for r in priced)
    summary = {
        "value_usd": _r(total, 2),
        "value_ars": _r(sum(r["value_ars"] or 0 for r in rows), 2),
        "cost_usd": _r(cost, 2) if cost else None,
        "pnl_usd": _r(total - cost, 2) if cost else None,
        "pnl_pct": _r(total / cost - 1) if cost else None,
        "income_usd": _r(sum(r["income_usd"] or 0 for r in rows), 2),
        "mep": _r(mep, 2),
        "n": len(rows),
        "unpriced": [r["ticker"] for r in rows if r["value_usd"] is None],
        "prob_up_60": _r(
            sum(r["weight"] * r["prob_up_60"] for r in priced if r["prob_up_60"])
            / max(1e-9, sum(r["weight"] for r in priced if r["prob_up_60"]))
        )
        if any(r["prob_up_60"] for r in priced)
        else None,
        "top_weight": _r(max((r["weight"] for r in priced), default=0)),
        "hhi": _r(sum(r["weight"] ** 2 for r in priced)),
    }
    sectors: dict[str, float] = {}
    for r in priced:
        sectors[r["sector"] or "Sin clasificar"] = (
            sectors.get(r["sector"] or "Sin clasificar", 0) + r["weight"]
        )
    risk = _risk(session, priced)
    return {
        "summary": summary,
        "holdings": rows,
        "sectors": [
            {"sector": k, "weight": _r(v)} for k, v in sorted(sectors.items(), key=lambda x: -x[1])
        ],
        "risk": risk,
        "events": _events(session, priced),
    }


def _risk(session: Session, priced: list[dict[str, Any]]) -> dict | None:
    if not priced:
        return None
    insts = session.scalars(
        select(Instrument).where(Instrument.ticker.in_([r["ticker"] for r in priced]))
    ).all()
    closes = asset_closes(session, list(insts))
    weekly = pd.DataFrame(
        {
            t: s.sort_index().resample("W-FRI").last().pct_change(fill_method=None)
            for t, s in closes.items()
        }
    ).iloc[-SENS_WEEKS:]
    w = pd.Series({r["ticker"]: r["weight"] for r in priced if r["ticker"] in weekly.columns})
    if w.empty:
        return None
    w = w / w.sum()
    rets = weekly[w.index].dropna(how="all").fillna(0.0)
    if len(rets) < 26:
        return None
    cov = rets.cov() * 52
    vol_p = float(math.sqrt(max(float(w @ cov @ w), 0.0)))
    vols = np.sqrt(np.diag(cov))
    avg_vol = float((w * vols).sum())
    port_hist = rets @ w
    run = session.scalar(select(ModelRun).order_by(ModelRun.id.desc()))
    z = (((run.report if run else {}).get("ranges") or {}).get("60") or {}).get("z_universe")
    ranges = {}
    if z:
        for h in (20, 60, 120):
            sig = vol_p * math.sqrt(h / 252)
            ranges[str(h)] = dict(
                zip(
                    ("p10", "p25", "p50", "p75", "p90"),
                    (round(math.expm1(q * sig), 4) for q in z),
                    strict=True,
                )
            )
    corr = rets.corr()
    pair = None
    if len(w) > 1:
        c = corr.where(~np.eye(len(corr), dtype=bool)).stack()
        if len(c):
            (a, b), v = c.idxmax(), float(c.max())
            pair = {"a": a, "b": b, "corr": round(v, 3)}
    return {
        "vol": round(vol_p, 4),
        "avg_vol": round(avg_vol, 4),
        "diversification": round(1 - vol_p / avg_vol, 4) if avg_vol else None,
        "max_drawdown_3y": round(
            float(((1 + port_hist).cumprod() / (1 + port_hist).cumprod().cummax() - 1).min()), 4
        ),
        "ranges": ranges,
        "quantiles": list(QUANTILES),
        "most_correlated": pair,
        "weeks": int(len(rets)),
    }


def _events(session: Session, priced: list[dict[str, Any]]) -> dict:
    report = latest_event_report(session) or {}
    w = {r["ticker"]: r["weight"] for r in priced}
    sec_w: dict[str, float] = {}
    for r in priced:
        sec_w[r["sector"] or ""] = sec_w.get(r["sector"] or "", 0) + r["weight"]
    active = []
    for ev in report.get("events", []):
        if ev["state"] == "inactivo":
            continue
        fav = unfav = 0.0
        for row in (report.get("study", {}).get(ev["key"]) or {}).get("sectors", []):
            if row["significant"]:
                if row["mean_excess"] > 0:
                    fav += sec_w.get(row["sector"], 0)
                else:
                    unfav += sec_w.get(row["sector"], 0)
        active.append(
            {
                "key": ev["key"],
                "name": ev["name"],
                "state": ev["state"],
                "weight_favorable": round(fav, 4),
                "weight_unfavorable": round(unfav, 4),
            }
        )
    sens = report.get("sensitivities", {})
    factors = []
    for f, meta in (report.get("factors") or {}).items():
        covered = {t: wt for t, wt in w.items() if (sens.get(t) or {}).get(f)}
        if not covered:
            continue
        tot = sum(covered.values())
        impact = sum(wt * sens[t][f]["impact"] for t, wt in covered.items()) / tot
        factors.append(
            {
                "factor": f,
                "label": meta["label"],
                "impact": round(impact, 4),
                "coverage": round(tot, 4),
            }
        )
    return {"active": active, "factors": factors}
