"""Pipeline de ingesta.

1. Universo: activos ancla curados (`universe.py`) + especies descubiertas en el panel en
   vivo de BYMA (CEDEARs y acciones locales con operaciones).
2. Precios BYMA en paralelo e incrementales (si ya hay historia se baja solo lo nuevo).
3. Precios en EE. UU. (descarga en lote cuando la fuente lo permite).
4. CCL de mercado con los anclas, en dos pasadas: la segunda corrige cambios de ratio
   históricos detectados con el CCL de la primera.
5. CEDEARs descubiertos: se elige el subyacente y se estima el ratio con ese CCL; los que
   no validan quedan inactivos con el motivo.
6. CCL final con todos los pares activos, metadatos (nombre/sector), balances y snapshots.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import FundamentalPeriod, FxRate, IngestionRun, Instrument, PriceBar
from app.ingestion.ccl import market_ccl_series
from app.ingestion.discovery import (
    estimate_ratio,
    ratio_history,
    us_candidates,
    volume_weighted_liquidity,
)
from app.ingestion.providers.base import MarketDataProvider, ProviderError
from app.ingestion.universe import UNIVERSE, AssetSpec
from app.services.analytics import compute_snapshots
from app.services.data import STATEMENT_FIELDS, load_bars

log = logging.getLogger(__name__)

MIN_BARS_ACTIVE = 60  # ruedas mínimas en BYMA para analizar un activo
INCREMENTAL_OVERLAP_DAYS = 15
METADATA_TTL = timedelta(days=30)
FUNDAMENTALS_TTL = timedelta(days=7)


class IngestionError(RuntimeError):
    pass


def upsert_instrument(session: Session, spec: AssetSpec, curated: bool) -> Instrument:
    inst = session.scalar(select(Instrument).where(Instrument.ticker == spec.ticker))
    if inst is None:
        inst = Instrument(ticker=spec.ticker, name=spec.name, sector=spec.sector)
        session.add(inst)
    inst.ba_symbol, inst.kind = spec.ba_symbol, spec.kind
    inst.reporting_currency = spec.reporting_currency
    if curated:
        # Los anclas mandan sobre lo descubierto: nombre, sector, subyacente y ratio verificados.
        inst.name, inst.sector, inst.us_symbol, inst.ratio = (
            spec.name,
            spec.sector,
            spec.us_symbol,
            spec.ratio,
        )
        inst.ratio_source = "curado" if spec.ratio else None
        inst.ratio_confidence = 1.0 if spec.ratio else None
    elif inst.us_symbol is None:
        inst.us_symbol = spec.us_symbol
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


def _last_day(session: Session, inst: Instrument, market: str) -> date | None:
    return session.scalar(
        select(func.max(PriceBar.day)).where(
            PriceBar.instrument_id == inst.id, PriceBar.market == market
        )
    )


def _fetch_window(session: Session, inst: Instrument, market: str, start: date) -> date:
    last = _last_day(session, inst, market)
    return max(start, last - timedelta(days=INCREMENTAL_OVERLAP_DAYS)) if last else start


def _us_window(session: Session, inst: Instrument, us_start: date) -> date:
    """Incremental si ya hay historia larga en EE. UU.; completa si falta el tramo viejo."""
    first = session.scalar(
        select(func.min(PriceBar.day)).where(
            PriceBar.instrument_id == inst.id, PriceBar.market == "US"
        )
    )
    if first is None or first > us_start + timedelta(days=30):
        return us_start
    return _fetch_window(session, inst, "US", us_start)


def _parallel(fn: Callable[[Any], Any], items: Iterable[Any], workers: int) -> list[Any]:
    """Ejecuta `fn` en paralelo devolviendo (item, resultado | excepción)."""

    def safe(item: Any) -> tuple[Any, Any]:
        try:
            return item, fn(item)
        except Exception as exc:  # se reporta por activo, no corta la corrida
            return item, exc

    items = list(items)
    if workers <= 1 or len(items) <= 1:
        return [safe(i) for i in items]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(safe, items))


def implied_with_ratio_history(
    ba: pd.Series, us: pd.Series, ratio: float, ccl: pd.Series | None
) -> pd.Series:
    """CCL implícito diario con el ratio vigente en cada rueda (constante si no hay CCL)."""
    df = pd.concat({"ba": ba, "us": us}, axis=1, join="inner").dropna()
    df = df[(df["ba"] > 0) & (df["us"] > 0)]
    if df.empty:
        return pd.Series(dtype=float)
    r = pd.Series(ratio, index=df.index, dtype=float)
    if ccl is not None and not ccl.empty:
        hist = ratio_history(df["ba"], df["us"], ccl, ratio)
        if not hist.empty:
            r = hist.reindex(df.index).ffill().bfill().fillna(ratio)
        # El tramo final siempre usa el ratio vigente conocido.
        r.iloc[-5:] = ratio
    return df["ba"] * r / df["us"]


def build_market_ccl(pairs: dict[str, tuple[pd.Series, pd.Series, float, pd.Series]]) -> pd.Series:
    """Dos pasadas: ratio constante → CCL₀ → historia de ratios → CCL₁."""
    first = {t: implied_with_ratio_history(ba, us, r, None) for t, (ba, us, r, _) in pairs.items()}
    vols = {t: v for t, (_, _, _, v) in pairs.items()}
    ccl0 = market_ccl_series(first, vols)
    if ccl0.empty:
        return pd.Series(dtype=float)
    second = {
        t: implied_with_ratio_history(ba, us, r, ccl0["value"])
        for t, (ba, us, r, _) in pairs.items()
    }
    return market_ccl_series(second, vols)


# Versiones anteriores guardaban 6 ejercicios: se refrescan una vez para tener historia larga.
SHORT_HISTORY_PERIODS = 6


def _stored_periods(session: Session, inst: Instrument) -> int:
    return (
        session.scalar(select(func.count()).where(FundamentalPeriod.instrument_id == inst.id)) or 0
    )


def _stale(ts: datetime | None, now: datetime, ttl: timedelta) -> bool:
    return ts is None or now - ts > ttl


def run_ingestion(
    session: Session,
    provider: MarketDataProvider,
    end: date | None = None,
    history_days: int = 2200,
    universe: list[AssetSpec] | None = None,
    workers: int = 8,
    us_history_start: date | None = None,
) -> dict:
    end = end or date.today()
    start = end - timedelta(days=history_days)
    # Los subyacentes en EE. UU. se guardan con historia larga para el modelo.
    us_start = min(start, us_history_start) if us_history_start else start
    now = datetime.now()
    errors: list[str] = []
    counts = {"instruments": 0, "bars": 0, "fundamentals": 0, "discovered": 0}

    # ---------------------------------------------------------------- universo
    anchors = universe or UNIVERSE
    specs: dict[str, AssetSpec] = {a.ticker: a for a in anchors}
    curated = set(specs)
    discover = getattr(provider, "discover", None)
    if universe is None and discover is not None:
        for kind, quotes in discover().items():
            for q in quotes:
                if q.ticker in specs or q.volume_ars <= 0:
                    continue
                us = us_candidates(q.ticker)[0] if kind == "CEDEAR" else None
                specs[q.ticker] = AssetSpec(
                    q.ticker,
                    q.ticker,
                    "Sin clasificar",
                    kind,
                    None,
                    us,
                    "USD" if kind == "CEDEAR" else "ARS",
                )
                counts["discovered"] += 1
    register = getattr(provider, "register_cedears", None)
    if register:
        register({t for t, s in specs.items() if s.kind == "CEDEAR"})

    insts = {t: upsert_instrument(session, s, t in curated) for t, s in specs.items()}
    counts["instruments"] = len(insts)

    # ------------------------------------------------------------ precios BYMA
    ba_jobs = [(t, _fetch_window(session, insts[t], "BA", start)) for t in insts]
    for (t, _), res in _parallel(
        lambda job: provider.history(specs[job[0]].ba_symbol, job[1], end), ba_jobs, workers
    ):
        if isinstance(res, Exception):
            errors.append(f"{t} (BYMA): {res}")
        else:
            counts["bars"] += store_bars(session, insts[t], "BA", res)
    session.flush()

    # --------------------------------------------------------- precios EE. UU.
    us_symbols: dict[str, list[str]] = {}
    for t, s in specs.items():
        if s.kind == "CEDEAR" and t not in curated:
            us_symbols[t] = us_candidates(t)
        elif s.us_symbol:
            us_symbols[t] = [s.us_symbol]
    prefetch = getattr(provider, "prefetch_us", None)
    if prefetch:
        prefetch(sorted({c for cands in us_symbols.values() for c in cands}), us_start, end)

    us_from = {t: _us_window(session, insts[t], us_start) for t in us_symbols}

    def fetch_us(t: str) -> dict[str, pd.DataFrame]:
        out = {}
        for cand in us_symbols[t]:
            try:
                out[cand] = provider.history(cand, us_from[t], end)
            except ProviderError:
                continue
        if not out:
            raise ProviderError(f"sin precios para {us_symbols[t]}")
        return out

    us_data: dict[str, dict[str, pd.DataFrame]] = {}
    for t, res in _parallel(fetch_us, us_symbols, workers):
        if isinstance(res, Exception):
            errors.append(f"{t} (EE. UU.): {res}")
        else:
            us_data[t] = res

    ba_full = {t: load_bars(session, inst.id, "BA") for t, inst in insts.items()}

    def us_series(t: str, cand: str) -> pd.DataFrame:
        """Serie completa de EE. UU.: lo recién bajado + lo almacenado (si es el mismo símbolo)."""
        fresh = us_data[t][cand]
        if insts[t].us_symbol != cand:
            return fresh
        stored = load_bars(session, insts[t].id, "US")
        if stored.empty:
            return fresh
        old = stored[stored.index < fresh.index.min()] if not fresh.empty else stored
        return pd.concat([old, fresh]).sort_index()

    vol_ars = {t: df["close"] * df["volume"] for t, df in ba_full.items() if not df.empty}

    # ------------------------------------------------------- CCL con anclas
    anchor_pairs = {}
    for t in curated:
        s = specs[t]
        if s.ratio and s.us_symbol and t in us_data and not ba_full[t].empty:
            counts["bars"] += store_bars(session, insts[t], "US", us_data[t][s.us_symbol])
            us = us_series(t, s.us_symbol)
            anchor_pairs[t] = (ba_full[t]["close"], us["close"], s.ratio, vol_ars.get(t))
    if not anchor_pairs:
        session.rollback()
        raise IngestionError(
            "Ninguna fuente devolvió pares de precios BYMA/EE. UU.; no se actualizó la base. "
            f"Primeros errores: {errors[:5]}"
        )
    anchor_ccl = build_market_ccl(anchor_pairs)["value"]

    # -------------------------------------- validar CEDEARs descubiertos
    pairs = dict(anchor_pairs)
    for t, s in specs.items():
        inst = insts[t]
        ba = ba_full[t]
        if len(ba) < MIN_BARS_ACTIVE:
            inst.active = False
            inst.status_note = f"solo {len(ba)} ruedas en BYMA"
            continue
        inst.avg_volume_ars = volume_weighted_liquidity(ba)
        if t in curated:
            inst.active, inst.status_note = True, None
            if s.ratio and t in pairs:
                est = estimate_ratio(ba["close"], pairs[t][1], anchor_ccl)
                if est.ratio and est.ratio != s.ratio and est.confidence > 0.8:
                    inst.status_note = (
                        f"ratio curado {s.ratio:g} difiere del estimado {est.ratio:g}"
                    )
            continue
        if s.kind != "CEDEAR":
            inst.active, inst.status_note = True, None  # local sin ADR: se analiza en USD CCL
            continue
        best = None
        notes = []
        for cand in us_data.get(t, {}):
            us = us_series(t, cand)
            est = estimate_ratio(ba["close"], us["close"], anchor_ccl)
            notes.append(f"{cand}: {est.note}")
            if est.ratio and (best is None or est.confidence > best[1].confidence):
                best = (cand, est, us)
        if best is None:
            inst.active = False
            inst.status_note = ("; ".join(notes) or "sin subyacente en EE. UU.")[:256]
            continue
        cand, est, us = best
        assert est.ratio is not None  # `best` solo guarda estimaciones aceptadas
        inst.us_symbol, inst.ratio = cand, est.ratio
        inst.ratio_source, inst.ratio_confidence = "estimado", est.confidence
        inst.active, inst.status_note = True, None
        counts["bars"] += store_bars(session, inst, "US", us_data[t][cand])
        pairs[t] = (ba["close"], us["close"], est.ratio, vol_ars.get(t))
    session.flush()

    # -------------------------------------------------------- CCL final
    ccl = build_market_ccl(pairs)
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

    active = [t for t, inst in insts.items() if inst.active is not False]

    # ------------------------------------------------------------ metadatos
    meta_fn = getattr(provider, "metadata", None)
    if meta_fn:
        stale = [
            t
            for t in active
            if t not in curated and _stale(insts[t].metadata_updated_at, now, METADATA_TTL)
        ]
        symbol = {t: insts[t].us_symbol or specs[t].ba_symbol for t in stale}
        for t, res in _parallel(lambda t: meta_fn(symbol[t]), stale, workers):
            if isinstance(res, Exception):
                errors.append(f"{t} (metadatos): {res}")
                continue
            inst = insts[t]
            inst.name = (res.get("name") or t)[:128]
            inst.sector = (res.get("sector") or "Sin clasificar")[:64]
            inst.metadata_updated_at = now

    # ------------------------------------------------------------ balances
    due = [
        t
        for t in active
        if insts[t].sector != "ETF"
        and (
            _stale(insts[t].fundamentals_updated_at, now, FUNDAMENTALS_TTL)
            or _stored_periods(session, insts[t]) <= SHORT_HISTORY_PERIODS
        )
    ]
    fsym = {t: insts[t].us_symbol or specs[t].ba_symbol for t in due}
    for t, res in _parallel(lambda t: provider.fundamentals(fsym[t]), due, max(1, workers // 2)):
        if isinstance(res, Exception):
            errors.append(f"{t} (fundamentales): {res}")
            continue
        # Una fuente caída no debe borrar balances ya almacenados.
        if res:
            counts["fundamentals"] += store_fundamentals(session, insts[t], res)
            if res[0].currency != insts[t].reporting_currency:
                insts[t].reporting_currency = res[0].currency
        insts[t].fundamentals_updated_at = now
    session.flush()

    for e in errors:
        log.warning("Ingesta: %s", e)

    snapshots = compute_snapshots(session, end)
    sources = dict(getattr(provider, "usage", {}) or {}) or provider.name
    counts["active"] = len(active)
    session.add(
        IngestionRun(
            provider=provider.name,
            status="ok" if not errors else "partial",
            message=(
                f"{len(active)} activos analizados de {counts['instruments']}, "
                f"{counts['bars']} barras, {len(errors)} errores. Fuentes: {sources}"
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
