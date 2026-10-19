"""Acceso a series almacenadas (lectura) compartido por ingesta, analytics y API."""

from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.fundamental import FinancialStatement
from app.db.models import FundamentalPeriod, FxRate, Instrument, PriceBar, SplitEvent
from app.ingestion.providers.base import OHLCV_COLUMNS

STATEMENT_FIELDS = [
    "revenue",
    "ebit",
    "ebitda",
    "net_income",
    "total_assets",
    "total_liabilities",
    "current_assets",
    "current_liabilities",
    "equity",
    "total_debt",
    "cash",
    "retained_earnings",
    "operating_cash_flow",
    "capex",
    "shares_outstanding",
    "tax_rate",
]


def load_bars(session: Session, instrument_id: int, market: str) -> pd.DataFrame:
    rows = session.execute(
        select(
            PriceBar.day,
            PriceBar.open,
            PriceBar.high,
            PriceBar.low,
            PriceBar.close,
            PriceBar.volume,
        )
        .where(PriceBar.instrument_id == instrument_id, PriceBar.market == market)
        .order_by(PriceBar.day)
    ).all()
    if not rows:
        return pd.DataFrame(columns=OHLCV_COLUMNS, index=pd.DatetimeIndex([], name="day"))
    df = pd.DataFrame(rows, columns=["day", *OHLCV_COLUMNS])
    df["day"] = pd.to_datetime(df["day"])
    return df.set_index("day")


def load_fx(session: Session, kind: str = "CCL") -> pd.Series:
    rows = session.execute(
        select(FxRate.day, FxRate.value).where(FxRate.kind == kind).order_by(FxRate.day)
    ).all()
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series([r[1] for r in rows], index=pd.to_datetime([r[0] for r in rows]))
    return s


def load_statements(session: Session, instrument_id: int) -> list[FinancialStatement]:
    rows = session.scalars(
        select(FundamentalPeriod)
        .where(FundamentalPeriod.instrument_id == instrument_id)
        .order_by(FundamentalPeriod.period_end)
    ).all()
    return [
        FinancialStatement(
            period_end=r.period_end,
            currency=r.currency,
            **{f: getattr(r, f) for f in STATEMENT_FIELDS},
        )
        for r in rows
    ]


def instrument_by_ticker(session: Session, ticker: str) -> Instrument | None:
    return session.scalar(select(Instrument).where(Instrument.ticker == ticker.upper()))


def to_usd_ccl(ba: pd.DataFrame, ccl: pd.Series) -> pd.DataFrame:
    """Convierte barras en ARS a USD CCL usando el CCL de mercado de cada día (ffill)."""
    if ba.empty or ccl.empty:
        return ba.iloc[0:0]
    fx = ccl.reindex(ba.index.union(ccl.index)).sort_index().ffill().reindex(ba.index)
    out = ba.copy()
    for c in ("open", "high", "low", "close"):
        out[c] = ba[c] / fx
    return out.dropna(subset=["close"])


def load_splits(session: Session, instrument_id: int) -> pd.Series:
    rows = session.execute(
        select(SplitEvent.day, SplitEvent.ratio)
        .where(SplitEvent.instrument_id == instrument_id)
        .order_by(SplitEvent.day)
    ).all()
    if not rows:
        return pd.Series(dtype=float)
    return pd.Series([r[1] for r in rows], index=pd.to_datetime([r[0] for r in rows]))


# Un split hasta esta cantidad de días después del cierre puede estar ya reflejado en la
# cantidad de acciones de la portada del 10-K/20-F (fechada semanas después del cierre).
SPLIT_AMBIGUITY_DAYS = 120


def split_adjust_statements(statements: list[FinancialStatement], splits: pd.Series) -> list:
    """Lleva `shares_outstanding` de cada balance a la base de acciones actual.

    Los precios vienen ajustados por splits, pero los balances informan las acciones de su
    fecha: sin este ajuste, una empresa que luego hizo un split parece barata en el pasado
    (información del futuro filtrándose en los múltiplos históricos).
    """
    if splits.empty or not statements:
        return statements
    from dataclasses import replace

    out = []
    prev_shares = None
    for s in statements:
        shares = s.shares_outstanding
        if shares:
            end = pd.Timestamp(s.period_end)
            factor = 1.0
            for day, ratio in splits.items():
                if day <= end or ratio <= 0:
                    continue
                if (day - end).days <= SPLIT_AMBIGUITY_DAYS and prev_shares:
                    # ¿La portada ya informa acciones post-split? Se ve como un salto ≈ ratio.
                    jump = shares / prev_shares
                    if abs(jump / ratio - 1) < 0.3:
                        continue
                factor *= ratio
            prev_shares = shares
            s = replace(s, shares_outstanding=shares * factor)
        out.append(s)
    return out
