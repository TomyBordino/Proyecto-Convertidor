"""Cálculo de snapshots: indicadores + ratios + scoring por activo, a una fecha dada.

Serie de análisis técnico (moneda dura):
  - Activos con par en EE. UU. (CEDEARs y locales con ADR): la serie del subyacente/ADR,
    más líquida y libre del ruido del tipo de cambio.
  - Locales sin ADR: precio local convertido a USD con el CCL de mercado.
"""

from __future__ import annotations

import math
from datetime import date

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.analytics import fundamental as fa
from app.analytics.patterns import detect_breakout, last_ma_cross, rsi_divergence
from app.analytics.scoring import (
    ScoringWeights,
    TechnicalInputs,
    ccl_subscore,
    composite_score,
    fundamental_subscore,
    median_of,
    technical_subscore,
)
from app.analytics.technical import compute_all
from app.db.models import Instrument, ScoreSnapshot
from app.ingestion.ccl import ccl_deviation, implied_ccl, is_ratio_suspect
from app.ingestion.normalization import ccl_close_and_avg, statement_to_usd
from app.ingestion.universe import UNIVERSE_BY_TICKER
from app.services.data import load_bars, load_fx, load_statements, to_usd_ccl


def _f(x: object) -> float | None:
    """float JSON-safe (NaN/inf → None)."""
    if x is None:
        return None
    try:
        v = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _pct(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None or b == 0 else round((a / b - 1) * 100, 2)


def analysis_series(
    inst: Instrument, ba: pd.DataFrame, us: pd.DataFrame, ccl: pd.Series
) -> tuple[pd.DataFrame, str]:
    if inst.us_symbol and not us.empty:
        return us, "US"
    return to_usd_ccl(ba, ccl), "USD_CCL"


def per_share_close(inst: Instrument, series: pd.DataFrame, series_kind: str) -> pd.Series:
    """Precio en USD por acción ordinaria, para combinar con las acciones del balance.

    Un ADR representa `ratio` acciones locales y los balances (20-F) informan acciones
    ordinarias, así que el precio del ADR se divide por el ratio. Un CEDEAR se analiza con
    el precio de la acción subyacente, que ya es por acción.
    """
    spec = UNIVERSE_BY_TICKER.get(inst.ticker)
    per_adr = spec.shares_per_us_unit if spec else (inst.ratio if inst.kind == "LOCAL" else None)
    if series_kind == "US" and per_adr:
        return series["close"] / per_adr
    return series["close"]


def usd_statements(statements: list[fa.FinancialStatement], ccl: pd.Series) -> list:
    out = []
    for s in statements:
        if s.currency == "USD":
            out.append(s)
            continue
        fx = ccl_close_and_avg(ccl, pd.Timestamp(s.period_end))
        if fx is not None:
            out.append(statement_to_usd(s, *fx))
    return out


def price_on_or_before(series: pd.Series, day: date) -> float | None:
    s = series[series.index <= pd.Timestamp(day)]
    return None if s.empty else float(s.iloc[-1])


def ratio_history(statements: list[fa.FinancialStatement], close_usd: pd.Series) -> list[dict]:
    rows, prev = [], None
    for s in statements:
        px = price_on_or_before(close_usd, s.period_end)
        r = fa.all_ratios(px, s, prev) if px else {}
        rows.append(
            {
                "period_end": s.period_end.isoformat(),
                "price_usd": _f(px),
                "revenue": _f(s.revenue),
                "net_income": _f(s.net_income),
                "ebitda": _f(s.ebitda),
                "free_cash_flow": _f(fa.free_cash_flow(s)),
                **{k: _f(v) for k, v in r.items()},
            }
        )
        prev = s
    return rows


def _technical(ind: pd.DataFrame) -> tuple[TechnicalInputs, dict]:
    last = ind.iloc[-1]
    sma50_hist = ind["sma50"].dropna()
    slope = float(sma50_hist.iloc[-1] / sma50_hist.iloc[-21] - 1) if len(sma50_hist) > 21 else None
    cross = last_ma_cross(ind["sma50"], ind["sma200"], lookback=20)
    brk = detect_breakout(ind["close"], ind["high"], ind["volume"])
    div = rsi_divergence(ind["close"], ind["rsi14"]) if ind["rsi14"].notna().sum() > 60 else None
    hist = ind["macd_hist"].dropna()
    t = TechnicalInputs(
        close=float(last.close),
        sma50=_f(last.sma50),
        sma200=_f(last.sma200),
        sma50_slope=slope,
        rsi=_f(last.rsi14),
        macd_hist=_f(hist.iloc[-1]) if len(hist) else None,
        macd_hist_prev=_f(hist.iloc[-2]) if len(hist) > 1 else None,
        pct_b=_f(last.bb_pct_b),
        cross=cross,
        breakout=brk is not None,
        divergence=div,
    )
    close = ind["close"]
    atr14 = _f(last.atr14)
    extra = {
        "rsi14": _f(last.rsi14),
        "macd_hist": t.macd_hist,
        "bb_pct_b": t.pct_b,
        "atr_pct": round(atr14 / float(last.close) * 100, 2) if atr14 is not None else None,
        "dist_sma200_pct": _pct(t.close, t.sma200),
        "above_sma200": t.sma200 is not None and t.close > t.sma200,
        "golden_cross": cross is not None and cross.kind == "golden",
        "breakout": t.breakout,
        "rsi_divergence": div,
        "change_1d_pct": _pct(float(close.iloc[-1]), float(close.iloc[-2]))
        if len(close) > 1
        else None,
        "change_1m_pct": _pct(float(close.iloc[-1]), float(close.iloc[-22]))
        if len(close) > 22
        else None,
    }
    return t, extra


def compute_snapshots(
    session: Session, day: date | None = None, weights: ScoringWeights | None = None
) -> int:
    ccl = load_fx(session, "CCL")
    if ccl.empty:
        return 0
    # El snapshot se fecha en la última rueda con datos, no en la fecha pedida
    # (una corrida en fin de semana no debe crear un día sin mercado).
    asof = min(pd.Timestamp(day), ccl.index.max()) if day else ccl.index.max()
    ccl = ccl[ccl.index <= asof]
    ccl_market = float(ccl.iloc[-1])
    instruments = session.scalars(select(Instrument).order_by(Instrument.ticker)).all()

    staged: list[dict] = []
    for inst in instruments:
        ba = load_bars(session, inst.id, "BA")
        ba = ba[ba.index <= asof]
        if ba.empty:
            continue
        us = load_bars(session, inst.id, "US")
        us = us[us.index <= asof]
        series, series_kind = analysis_series(inst, ba, us, ccl)
        if len(series) < 30:
            continue
        ind = compute_all(series)
        tech_inputs, tech_metrics = _technical(ind)

        price_ars = float(ba["close"].iloc[-1])
        imp = None
        if inst.ratio and not us.empty:
            imp = implied_ccl(price_ars, float(us["close"].iloc[-1]), inst.ratio)
        dev = ccl_deviation(imp, ccl_market) if imp else None
        suspect = bool(imp and is_ratio_suspect(imp, ccl_market))

        statements = usd_statements(load_statements(session, inst.id), ccl)
        px_share = per_share_close(inst, series, series_kind)
        hist_rows = ratio_history(statements, px_share)
        current = (
            fa.all_ratios(
                float(px_share.iloc[-1]),
                statements[-1],
                statements[-2] if len(statements) > 1 else None,
            )
            if statements
            else {}
        )
        staged.append(
            dict(
                inst=inst,
                tech=tech_inputs,
                tech_metrics=tech_metrics,
                series_kind=series_kind,
                price_ars=price_ars,
                implied=imp,
                dev=dev,
                suspect=suspect,
                ratios={k: _f(v) for k, v in current.items()},
                hist_median=median_of(hist_rows[:-1]),
            )
        )

    session.execute(delete(ScoreSnapshot).where(ScoreSnapshot.day == asof.date()))
    for row in staged:
        inst = row["inst"]
        peers = [r["ratios"] for r in staged if r["inst"].sector == inst.sector and r is not row]
        sector_median = median_of(peers) if peers else {}
        subs = [
            technical_subscore(row["tech"]),
            fundamental_subscore(
                row["ratios"],
                row["hist_median"],
                sector_median,
                is_financial=inst.sector == "Financiero",
            ),
            ccl_subscore(row["dev"], row["suspect"]),
        ]
        res = composite_score(subs, weights)
        signals = _signals(row)
        metrics = {
            "ticker": inst.ticker,
            "name": inst.name,
            "kind": inst.kind,
            "sector": inst.sector,
            "ratio": inst.ratio,
            "us_symbol": inst.us_symbol,
            "price_ars": round(row["price_ars"], 2),
            "price_usd": round(row["price_ars"] / ccl_market, 4),
            "implied_ccl": _f(round(row["implied"], 2)) if row["implied"] else None,
            "ccl_dev_pct": round(row["dev"] * 100, 2) if row["dev"] is not None else None,
            "ratio_suspect": row["suspect"],
            "analysis_series": row["series_kind"],
            **row["tech_metrics"],
            **{
                k: row["ratios"].get(k)
                for k in (
                    "pe",
                    "ps",
                    "pb",
                    "ev_ebitda",
                    "roe",
                    "roic",
                    "revenue_growth",
                    "fcf_yield",
                    "debt_to_equity",
                    "current_ratio",
                    "altman_z",
                    "market_cap",
                )
            },
            "composite_score": res.composite,
            "technical_score": res.subscores.get("technical"),
            "fundamental_score": res.subscores.get("fundamental"),
            "ccl_score": res.subscores.get("ccl"),
            "signals": signals,
        }
        metrics = {k: round(v, 4) if isinstance(v, float) else v for k, v in metrics.items()}
        session.add(
            ScoreSnapshot(
                instrument_id=inst.id,
                day=asof.date(),
                composite=res.composite,
                technical=res.subscores.get("technical"),
                fundamental=res.subscores.get("fundamental"),
                ccl=res.subscores.get("ccl"),
                metrics=metrics,
                breakdown={
                    "weights": res.weights_used,
                    "groups": res.breakdown,
                    "ccl_market": ccl_market,
                    "sector_median": sector_median,
                    "history_median": row["hist_median"],
                },
            )
        )
    session.flush()
    return len(staged)


def _signals(row: dict) -> list[str]:
    t, m, out = row["tech"], row["tech_metrics"], []
    if m["golden_cross"]:
        out.append("Golden cross")
    elif t.cross is not None and t.cross.kind == "death":
        out.append("Death cross")
    if m["breakout"]:
        out.append("Breakout")
    if m["rsi_divergence"] == "bullish":
        out.append("Divergencia alcista RSI")
    elif m["rsi_divergence"] == "bearish":
        out.append("Divergencia bajista RSI")
    if t.rsi is not None and t.rsi > 70:
        out.append("Sobrecompra")
    elif t.rsi is not None and t.rsi < 30:
        out.append("Sobreventa")
    if row["suspect"]:
        out.append("Ratio sospechoso")
    elif row["dev"] is not None and row["dev"] <= -0.02:
        out.append("CCL barato")
    elif row["dev"] is not None and row["dev"] >= 0.02:
        out.append("CCL caro")
    return out
