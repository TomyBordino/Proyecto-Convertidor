"""Seguimiento "en papel" de la estrategia: carteras objetivo guardadas en cada rebalanceo.

Cada período compra cantidades enteras a los precios de BYMA del día de los datos y las
mantiene hasta el período siguiente (o hasta hoy). El rendimiento se encadena entre períodos y
se compara con el SPY (en USD) y con el promedio con igual peso de todo el universo (en USD
CCL), desde la misma fecha de inicio.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import Instrument, ScoreSnapshot, TrackedPeriod
from app.services.data import load_bars, load_fx


def _latest_prices(session: Session) -> tuple[date | None, dict[str, dict]]:
    day = session.scalar(select(func.max(ScoreSnapshot.day)))
    if day is None:
        return None, {}
    snaps = session.scalars(select(ScoreSnapshot).where(ScoreSnapshot.day == day)).all()
    return day, {s.metrics["ticker"]: s.metrics for s in snaps}


def save_period(
    session: Session, strategy: dict, capital: float, picks: list[dict]
) -> TrackedPeriod:
    """Guarda la cartera objetivo con los precios del último día con datos. Si ya hay un
    período con esa fecha, lo reemplaza (volver a guardar el mismo mes no duplica)."""
    day, metrics = _latest_prices(session)
    if day is None:
        raise ValueError("Todavía no hay precios: ejecutá una ingesta")
    positions, spent = [], 0.0
    for p in picks:
        m = metrics.get(p["ticker"]) or {}
        price = m.get("price_ars")
        if not price:
            continue
        qty = math.floor(capital * float(p["weight"]) / price)
        spent += qty * price
        positions.append(
            {
                "ticker": p["ticker"],
                "weight": float(p["weight"]),
                "quantity": qty,
                "price_ars": price,
                "price_usd": m.get("price_usd"),
            }
        )
    if not positions:
        raise ValueError("Ningún papel de la selección tiene precio")
    session.execute(delete(TrackedPeriod).where(TrackedPeriod.start == day))
    period = TrackedPeriod(
        start=day,
        strategy=strategy,
        capital_ars=capital,
        cash_ars=capital - spent,
        positions=positions,
    )
    session.add(period)
    session.commit()
    return period


def _ba_closes(session: Session, tickers: list[str], since: pd.Timestamp) -> pd.DataFrame:
    insts = session.scalars(select(Instrument).where(Instrument.ticker.in_(tickers))).all()
    cols = {}
    for i in insts:
        ba = load_bars(session, i.id, "BA")
        if not ba.empty:
            cols[i.ticker] = ba["close"][ba.index >= since - pd.Timedelta(days=10)]
    return pd.DataFrame(cols).sort_index().ffill()


def _r(x: float | None, n: int = 4) -> float | None:
    return None if x is None or not math.isfinite(x) else round(float(x), n)


def tracking_report(session: Session) -> dict:
    periods = session.scalars(select(TrackedPeriod).order_by(TrackedPeriod.start)).all()
    if not periods:
        return {"periods": [], "series": [], "positions": [], "summary": None}
    start0 = pd.Timestamp(periods[0].start)
    tickers = sorted({p["ticker"] for per in periods for p in per.positions})
    px = _ba_closes(session, tickers, start0)
    ccl = load_fx(session, "CCL")
    if px.empty or ccl.empty:
        return {"periods": [], "series": [], "positions": [], "summary": None}
    last_day = px.index.max()
    fx = ccl.reindex(px.index.union(ccl.index)).sort_index().ffill()

    # Cartera: valor diario de cada período, encadenado en USD (CCL) y en pesos.
    rows, rows_ars, table = [], [], []
    level_usd, level_ars = 1.0, 1.0
    for i, per in enumerate(periods):
        s = pd.Timestamp(per.start)
        e = pd.Timestamp(periods[i + 1].start) if i + 1 < len(periods) else last_day
        window = px[(px.index >= s) & (px.index <= e)]
        if window.empty:
            continue
        value = pd.Series(per.cash_ars, index=window.index)
        for p in per.positions:
            if p["ticker"] in window.columns:
                value = value + p["quantity"] * window[p["ticker"]].fillna(p["price_ars"])
        value_usd = value / fx.reindex(window.index)
        base_ars, base_usd = per.capital_ars, per.capital_ars / float(fx.asof(s))
        rel_usd = value_usd / base_usd
        rel_ars = value / base_ars
        rows.append(level_usd * rel_usd)
        rows_ars.append(level_ars * rel_ars)
        table.append(
            {
                "id": per.id,
                "start": str(per.start),
                "end": str(e.date()),
                "strategy": per.strategy,
                "capital_ars": per.capital_ars,
                "positions": len(per.positions),
                "return_usd": _r(float(rel_usd.iloc[-1]) - 1),
                "return_ars": _r(float(rel_ars.iloc[-1]) - 1),
            }
        )
        level_usd *= float(rel_usd.iloc[-1])
        level_ars *= float(rel_ars.iloc[-1])
    strat = pd.concat(rows).groupby(level=0).last() if rows else pd.Series(dtype=float)
    strat_ars = pd.concat(rows_ars).groupby(level=0).last() if rows_ars else pd.Series(dtype=float)

    # Referencias desde el mismo inicio: SPY en USD y universo con igual peso en USD CCL.
    spy_inst = session.scalar(select(Instrument).where(Instrument.ticker == "SPY"))
    spy = pd.Series(dtype=float)
    if spy_inst is not None:
        us = load_bars(session, spy_inst.id, "US")["close"]
        us = us[us.index >= start0 - pd.Timedelta(days=10)].reindex(strat.index, method="ffill")
        if len(us.dropna()):
            spy = us / float(us.dropna().iloc[0])
    universe_tickers = list(
        session.scalars(select(Instrument.ticker).where(Instrument.active.isnot(False))).all()
    )
    uni_px = _ba_closes(session, universe_tickers, start0)
    uni = pd.Series(dtype=float)
    if not uni_px.empty:
        usd = uni_px.div(fx.reindex(uni_px.index), axis=0)
        usd = usd[usd.index >= start0]
        rets = usd.pct_change(fill_method=None).mean(axis=1, skipna=True).fillna(0.0)
        uni = (1 + rets).cumprod().reindex(strat.index, method="ffill")

    series: list[dict[str, Any]] = [
        {
            "time": str(d.date()),
            "strategy": _r(float(v) * 100, 2),
            "strategy_ars": _r(float(strat_ars.get(d, float("nan"))) * 100, 2),
            "spy": _r(float(spy.get(d)) * 100, 2) if len(spy) and pd.notna(spy.get(d)) else None,
            "universe": _r(float(uni.get(d)) * 100, 2)
            if len(uni) and pd.notna(uni.get(d))
            else None,
        }
        for d, v in strat.items()
    ]

    cur = periods[-1]
    now_ccl = float(fx.asof(last_day))
    entry_ccl = float(fx.asof(pd.Timestamp(cur.start)))
    positions = []
    total_now = cur.cash_ars
    for p in cur.positions:
        price_now = float(px[p["ticker"]].asof(last_day)) if p["ticker"] in px.columns else None
        value_now = p["quantity"] * price_now if price_now else None
        total_now += value_now or 0.0
        ret_ars = price_now / p["price_ars"] - 1 if price_now else None
        positions.append(
            {
                "ticker": p["ticker"],
                "quantity": p["quantity"],
                "weight_target": p["weight"],
                "entry_price_ars": p["price_ars"],
                "price_ars": price_now,
                "value_ars": _r(value_now, 2),
                "return_ars": _r(ret_ars),
                "return_usd": _r((1 + ret_ars) * entry_ccl / now_ccl - 1)
                if ret_ars is not None
                else None,
            }
        )
    for p in positions:
        p["weight_now"] = _r(p["value_ars"] / total_now) if p["value_ars"] and total_now else None
    positions.sort(key=lambda p: -(p["return_usd"] if p["return_usd"] is not None else -9))

    last: dict[str, Any] = series[-1] if series else {}
    days = (last_day - start0).days
    summary = {
        "start": str(start0.date()),
        "as_of": str(last_day.date()),
        "days": int(days),
        "periods": len(table),
        "return_usd": _r((last.get("strategy") or 100) / 100 - 1),
        "return_ars": _r((last.get("strategy_ars") or 100) / 100 - 1),
        "spy": _r(last["spy"] / 100 - 1) if last.get("spy") else None,
        "universe": _r(last["universe"] / 100 - 1) if last.get("universe") else None,
        "cash_ars": _r(cur.cash_ars, 2),
        "value_ars": _r(total_now, 2),
    }
    return {"summary": summary, "series": series, "periods": table, "positions": positions}
