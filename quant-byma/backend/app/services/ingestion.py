"""Pipeline de ingesta: instrumentos → precios BA/US → fundamentales → CCL → scoring."""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import FundamentalPeriod, FxRate, IngestionRun, Instrument, PriceBar
from app.ingestion.ccl import implied_ccl_series, market_ccl_series
from app.ingestion.providers.base import MarketDataProvider, ProviderError
from app.ingestion.universe import UNIVERSE, AssetSpec
from app.services.analytics import compute_snapshots
from app.services.data import STATEMENT_FIELDS

log = logging.getLogger(__name__)


class IngestionError(RuntimeError):
    pass


def upsert_instrument(session: Session, spec: AssetSpec) -> Instrument:
    inst = session.scalar(select(Instrument).where(Instrument.ticker == spec.ticker))
    if inst is None:
        inst = Instrument(ticker=spec.ticker)
        session.add(inst)
    inst.ba_symbol, inst.us_symbol, inst.kind = spec.ba_symbol, spec.us_symbol, spec.kind
    inst.name, inst.sector, inst.ratio = spec.name, spec.sector, spec.ratio
    inst.reporting_currency = spec.reporting_currency
    session.flush()
    return inst


def store_bars(session: Session, inst: Instrument, market: str, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    first, last = df.index.min().date(), df.index.max().date()
    session.execute(
        delete(PriceBar).where(
            PriceBar.instrument_id == inst.id,
            PriceBar.market == market,
            PriceBar.day >= first,
            PriceBar.day <= last,
        )
    )
    session.add_all(
        PriceBar(
            instrument_id=inst.id,
            market=market,
            day=ts.date(),
            open=float(r.open),
            high=float(r.high),
            low=float(r.low),
            close=float(r.close),
            volume=float(r.volume or 0.0),
        )
        for ts, r in df.iterrows()
    )
    return len(df)


def store_fundamentals(session: Session, inst: Instrument, statements: list) -> int:
    session.execute(delete(FundamentalPeriod).where(FundamentalPeriod.instrument_id == inst.id))
    for s in statements:
        d = asdict(s)
        session.add(
            FundamentalPeriod(
                instrument_id=inst.id,
                period_end=s.period_end,
                currency=s.currency,
                **{k: d[k] for k in STATEMENT_FIELDS},
            )
        )
    return len(statements)


def run_ingestion(
    session: Session,
    provider: MarketDataProvider,
    end: date | None = None,
    history_days: int = 2200,
    universe: list[AssetSpec] | None = None,
) -> dict:
    end = end or date.today()
    start = end - timedelta(days=history_days)
    implied: dict[str, pd.Series] = {}
    volumes: dict[str, pd.Series] = {}
    counts: dict[str, int] = {"instruments": 0, "bars": 0, "fundamentals": 0}
    errors: list[str] = []

    for spec in universe or UNIVERSE:
        inst = upsert_instrument(session, spec)
        counts["instruments"] += 1
        ba = us = None
        try:
            ba = provider.history(spec.ba_symbol, start, end)
            counts["bars"] += store_bars(session, inst, "BA", ba)
        except (ProviderError, KeyError, ValueError) as exc:
            errors.append(f"{spec.ticker} (BYMA): {exc}")
        if spec.us_symbol:
            try:
                us = provider.history(spec.us_symbol, start, end)
                counts["bars"] += store_bars(session, inst, "US", us)
            except (ProviderError, KeyError, ValueError) as exc:
                errors.append(f"{spec.ticker} ({spec.us_symbol}): {exc}")
        if spec.ratio and ba is not None and us is not None and not ba.empty and not us.empty:
            implied[spec.ticker] = implied_ccl_series(ba["close"], us["close"], spec.ratio)
            volumes[spec.ticker] = ba["close"] * ba["volume"]
        try:
            statements = provider.fundamentals(spec.us_symbol or spec.ba_symbol)
            # Una fuente caída no debe borrar balances ya almacenados.
            if statements:
                counts["fundamentals"] += store_fundamentals(session, inst, statements)
        except (ProviderError, KeyError, ValueError) as exc:
            errors.append(f"{spec.ticker} (fundamentales): {exc}")

    for e in errors:
        log.warning("Ingesta: %s", e)
    if not implied:
        # Sin ningún par local/exterior no hay CCL: abortamos sin tocar los datos previos.
        session.rollback()
        raise IngestionError(
            "Ninguna fuente devolvió pares de precios BYMA/EE. UU.; no se actualizó la base. "
            f"Primeros errores: {errors[:5]}"
        )

    ccl = market_ccl_series(implied, volumes)
    session.execute(delete(FxRate).where(FxRate.kind == "CCL", FxRate.day >= start))
    session.add_all(
        FxRate(kind="CCL", day=ts.date(), value=float(r.value), n_samples=int(r.n_samples))
        for ts, r in ccl.iterrows()
    )
    reference = getattr(provider, "reference_ccl", None)
    ref = reference(start, end) if reference else pd.Series(dtype=float)
    if not ref.empty:
        session.execute(delete(FxRate).where(FxRate.kind == "CCL_REF", FxRate.day >= start))
        session.add_all(
            FxRate(kind="CCL_REF", day=ts.date(), value=float(v), n_samples=1)
            for ts, v in ref.items()
        )
    session.flush()

    snapshots = compute_snapshots(session, end)
    sources = dict(getattr(provider, "usage", {}) or {}) or provider.name
    session.add(
        IngestionRun(
            provider=provider.name,
            status="ok" if not errors else "partial",
            message=(
                f"{counts['instruments']} activos, {counts['bars']} barras, "
                f"{len(errors)} errores. Fuentes: {sources}"
            )[:512],
        )
    )
    session.commit()
    return {
        **counts,
        "errors": errors,
        "ccl_days": len(ccl),
        "snapshots": snapshots,
        "provider": provider.name,
        "sources": sources,
        "ccl_reference_days": len(ref),
    }
