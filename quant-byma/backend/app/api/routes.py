from __future__ import annotations

import math
from datetime import date

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.analytics.screener import FIELDS, FilterDefinition, apply_filter
from app.analytics.technical import compute_all
from app.api.schemas import (
    AssetDetail,
    Candle,
    CCLAsset,
    CCLResponse,
    FieldInfo,
    Point,
    PriceSeriesResponse,
    RankingItem,
    RankingsResponse,
    SavedFilterIn,
    SavedFilterOut,
)
from app.config import get_settings
from app.db.models import IngestionRun, Instrument, ModelRun, SavedFilter, ScoreSnapshot
from app.db.session import get_session
from app.ingestion.providers import build_provider
from app.services.analytics import (
    analysis_series,
    per_share_close,
    ratio_history,
    usd_statements,
)
from app.services.data import (
    instrument_by_ticker,
    load_bars,
    load_fx,
    load_splits,
    load_statements,
    split_adjust_statements,
    to_usd_ccl,
)
from app.services.events import latest_event_report, news_pressure
from app.services.ingestion import IngestionError, implied_with_ratio_history, run_ingestion

router = APIRouter(prefix="/api")
SessionDep = Depends(get_session)

INDICATOR_COLUMNS = (
    "sma20",
    "sma50",
    "sma200",
    "ema20",
    "rsi14",
    "macd",
    "macd_signal",
    "macd_hist",
    "bb_upper",
    "bb_middle",
    "bb_lower",
    "atr14",
)


def _latest_day(session: Session) -> date | None:
    return session.scalar(select(func.max(ScoreSnapshot.day)))


def _snapshot_rows(session: Session) -> tuple[date | None, list[dict]]:
    day = _latest_day(session)
    if day is None:
        return None, []
    snaps = session.scalars(select(ScoreSnapshot).where(ScoreSnapshot.day == day)).all()
    rows = [s.metrics for s in snaps]
    ctx = _context_fields(session, rows)
    return day, [{**r, **ctx.get(r.get("ticker", ""), {})} for r in rows]


def _context_fields(session: Session, rows: list[dict]) -> dict[str, dict]:
    """Campos de la capa de eventos (no alteran el puntaje ni las probabilidades)."""
    pressure, _ = news_pressure(session, get_settings().news_lookback_days)
    report = latest_event_report(session) or {}
    tone: dict[str, dict[str, int]] = {}
    for ev in report.get("events", []):
        if ev["state"] == "inactivo":
            continue
        for row in (report.get("study", {}).get(ev["key"]) or {}).get("sectors", []):
            if row["significant"]:
                t = tone.setdefault(row["sector"], {"fav": 0, "unfav": 0})
                t["fav" if row["mean_excess"] > 0 else "unfav"] += 1
    out = {}
    for r in rows:
        p = pressure.get(r.get("ticker", ""))
        t = tone.get(r.get("sector", ""), {})
        out[r.get("ticker", "")] = {
            "news_score": p["score"] if p else None,
            "news_label": p["label"] if p else None,
            "events_favorable": t.get("fav", 0),
            "events_unfavorable": t.get("unfav", 0),
        }
    return out


def _ranked(rows: list[dict]) -> list[RankingItem]:
    return [RankingItem(rank=i + 1, **r) for i, r in enumerate(rows)]


def _points(s: pd.Series) -> list[Point]:
    return [
        Point(time=ts.strftime("%Y-%m-%d"), value=round(float(v), 6))
        for ts, v in s.items()
        if v is not None and math.isfinite(float(v))
    ]


@router.get("/health")
def health(session: Session = SessionDep) -> dict:
    last = session.scalar(select(IngestionRun).order_by(IngestionRun.id.desc()))
    return {
        "status": "ok",
        "as_of": _latest_day(session),
        "provider": None if last is None else last.provider,
        "last_ingestion": None
        if last is None
        else {
            "at": last.started_at,
            "provider": last.provider,
            "status": last.status,
            "message": last.message,
        },
    }


@router.get("/rankings", response_model=RankingsResponse)
def rankings(
    session: Session = SessionDep,
    kind: str | None = Query(None, pattern="^(CEDEAR|LOCAL)$"),
    sector: str | None = None,
    min_score: float = Query(0, ge=0, le=100),
    sort_by: str = "composite_score",
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(100, ge=1, le=1000),
    min_volume: float = Query(0, ge=0, description="Volumen promedio mínimo en ARS/día"),
) -> RankingsResponse:
    day, rows = _snapshot_rows(session)
    conditions: list[dict] = [{"field": "composite_score", "op": "gte", "value": min_score}]
    if min_volume > 0:
        conditions.append({"field": "avg_volume_ars", "op": "gte", "value": min_volume})
    if kind:
        conditions.append({"field": "kind", "op": "eq", "value": kind})
    if sector:
        conditions.append({"field": "sector", "op": "eq", "value": sector})
    try:
        f = FilterDefinition.model_validate(
            {"conditions": conditions, "sort_by": sort_by, "sort_dir": sort_dir, "limit": limit}
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    ccl = load_fx(session, "CCL")
    items = _ranked(apply_filter(rows, f))
    return RankingsResponse(
        as_of=day,
        ccl_market=None if ccl.empty else round(float(ccl.iloc[-1]), 2),
        count=len(items),
        items=items,
    )


@router.get("/model")
def model_report(session: Session = SessionDep) -> dict:
    """Métricas fuera de muestra, calibración y estadística por etapa del último modelo."""
    run = session.scalar(select(ModelRun).order_by(ModelRun.as_of.desc(), ModelRun.id.desc()))
    if run is None:
        raise HTTPException(404, "Todavía no se entrenó el modelo: ejecutá una ingesta")
    return run.report


@router.post("/screener/run", response_model=RankingsResponse)
def run_screener(definition: FilterDefinition, session: Session = SessionDep) -> RankingsResponse:
    day, rows = _snapshot_rows(session)
    ccl = load_fx(session, "CCL")
    items = _ranked(apply_filter(rows, definition))
    return RankingsResponse(
        as_of=day,
        ccl_market=None if ccl.empty else round(float(ccl.iloc[-1]), 2),
        count=len(items),
        items=items,
    )


@router.get("/screener/fields", response_model=list[FieldInfo])
def screener_fields() -> list[FieldInfo]:
    return [FieldInfo(key=k, label=v[0], type=v[1]) for k, v in FIELDS.items()]


@router.get("/instruments")
def instruments(session: Session = SessionDep) -> list[dict]:
    rows = session.scalars(select(Instrument).order_by(Instrument.kind, Instrument.ticker)).all()
    return [
        {
            "active": i.active is not False,
            "status_note": i.status_note,
            "ratio_source": i.ratio_source,
            "ratio_confidence": i.ratio_confidence,
            "avg_volume_ars": i.avg_volume_ars,
            "ticker": i.ticker,
            "name": i.name,
            "kind": i.kind,
            "sector": i.sector,
            "ratio": i.ratio,
            "us_symbol": i.us_symbol,
            "ba_symbol": i.ba_symbol,
        }
        for i in rows
    ]


def _get_instrument(session: Session, ticker: str) -> Instrument:
    inst = instrument_by_ticker(session, ticker)
    if inst is None:
        raise HTTPException(404, f"Activo {ticker} no encontrado")
    return inst


@router.get("/instruments/{ticker}", response_model=AssetDetail)
def asset_detail(ticker: str, session: Session = SessionDep) -> AssetDetail:
    inst = _get_instrument(session, ticker)
    snap = session.scalar(
        select(ScoreSnapshot)
        .where(ScoreSnapshot.instrument_id == inst.id)
        .order_by(ScoreSnapshot.day.desc())
    )
    return AssetDetail(
        ticker=inst.ticker,
        name=inst.name,
        kind=inst.kind,
        sector=inst.sector,
        ratio=inst.ratio,
        us_symbol=inst.us_symbol,
        ba_symbol=inst.ba_symbol,
        as_of=snap.day if snap else None,
        metrics=snap.metrics if snap else {},
        breakdown=snap.breakdown if snap else {},
    )


@router.get("/instruments/{ticker}/prices", response_model=PriceSeriesResponse)
def asset_prices(
    ticker: str,
    session: Session = SessionDep,
    currency: str = Query("ARS", pattern="^(ARS|USD|US)$"),
    days: int = Query(365, ge=30, le=2000),
) -> PriceSeriesResponse:
    """ARS = cotización en BYMA; USD = BYMA / CCL de mercado; US = subyacente/ADR en EE. UU."""
    inst = _get_instrument(session, ticker)
    ba = load_bars(session, inst.id, "BA")
    us = load_bars(session, inst.id, "US")
    ccl = load_fx(session, "CCL")
    series = {"ARS": ba, "USD": to_usd_ccl(ba, ccl), "US": us}[currency]
    if series.empty:
        raise HTTPException(404, f"Sin serie {currency} para {inst.ticker}")
    ind = compute_all(series).iloc[-days:]
    candles = [
        Candle(
            time=ts.strftime("%Y-%m-%d"),
            open=round(r.open, 4),
            high=round(r.high, 4),
            low=round(r.low, 4),
            close=round(r.close, 4),
            volume=round(r.volume, 0),
        )
        for ts, r in ind.iterrows()
    ]
    implied = (
        implied_with_ratio_history(ba["close"], us["close"], inst.ratio, ccl).iloc[-days:]
        if inst.ratio and not us.empty
        else pd.Series(dtype=float)
    )
    return PriceSeriesResponse(
        ticker=inst.ticker,
        currency=currency,
        candles=candles,
        indicators={c: _points(ind[c].dropna()) for c in INDICATOR_COLUMNS},
        implied_ccl=_points(implied),
        market_ccl=_points(ccl.iloc[-days:]),
    )


@router.get("/instruments/{ticker}/fundamentals")
def asset_fundamentals(ticker: str, session: Session = SessionDep) -> dict:
    inst = _get_instrument(session, ticker)
    ccl = load_fx(session, "CCL")
    raw = split_adjust_statements(load_statements(session, inst.id), load_splits(session, inst.id))
    statements = usd_statements(raw, ccl)
    series, series_kind = analysis_series(
        inst, load_bars(session, inst.id, "BA"), load_bars(session, inst.id, "US"), ccl
    )
    close = per_share_close(inst, series, series_kind)
    return {
        "ticker": inst.ticker,
        "reporting_currency": raw[0].currency if raw else None,
        "currency": "USD",
        "periods": ratio_history(statements, close) if not close.empty else [],
    }


@router.get("/ccl", response_model=CCLResponse)
def ccl_overview(
    session: Session = SessionDep, days: int = Query(365, ge=5, le=2000)
) -> CCLResponse:
    day, rows = _snapshot_rows(session)
    ccl = load_fx(session, "CCL")
    assets = sorted(
        (
            CCLAsset(
                ticker=r["ticker"],
                kind=r["kind"],
                implied_ccl=r["implied_ccl"],
                deviation_pct=r["ccl_dev_pct"],
                ratio_suspect=r.get("ratio_suspect", False),
            )
            for r in rows
            if r.get("implied_ccl") is not None
        ),
        key=lambda a: a.deviation_pct,
    )
    ref = load_fx(session, "CCL_REF")
    ref_dev = None
    if not ccl.empty and not ref.empty:
        aligned = pd.concat({"own": ccl, "ref": ref}, axis=1, join="inner")
        if not aligned.empty:
            last = aligned.iloc[-1]
            ref_dev = round((last["own"] / last["ref"] - 1) * 100, 2)
    return CCLResponse(
        as_of=day,
        market=None if ccl.empty else round(float(ccl.iloc[-1]), 2),
        history=_points(ccl.iloc[-days:]),
        reference=_points(ref.iloc[-days:]),
        reference_source="argentinadatos.com" if not ref.empty else None,
        reference_deviation_pct=ref_dev,
        assets=assets,
    )


# ------------------------------------------------------------ filtros guardados


def _filter_out(f: SavedFilter) -> SavedFilterOut:
    return SavedFilterOut(
        id=f.id,
        name=f.name,
        definition=FilterDefinition.model_validate(f.definition),
        created_at=f.created_at,
    )


@router.get("/filters", response_model=list[SavedFilterOut])
def list_filters(session: Session = SessionDep) -> list[SavedFilterOut]:
    return [_filter_out(f) for f in session.scalars(select(SavedFilter).order_by(SavedFilter.name))]


@router.post("/filters", response_model=SavedFilterOut, status_code=201)
def create_filter(body: SavedFilterIn, session: Session = SessionDep) -> SavedFilterOut:
    f = SavedFilter(name=body.name.strip(), definition=body.definition.model_dump())
    session.add(f)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, f"Ya existe un filtro llamado '{body.name}'") from exc
    session.refresh(f)
    return _filter_out(f)


@router.delete("/filters/{filter_id}", status_code=204)
def delete_filter(filter_id: int, session: Session = SessionDep) -> None:
    res = session.execute(delete(SavedFilter).where(SavedFilter.id == filter_id))
    if res.rowcount == 0:  # type: ignore[attr-defined]
        raise HTTPException(404, "Filtro no encontrado")
    session.commit()


@router.post("/ingest")
def ingest(
    session: Session = SessionDep,
    provider: str | None = Query(None, pattern="^(real|yahoo|demo)$"),
) -> dict:
    settings = get_settings()
    p = build_provider(provider or settings.data_provider)
    try:
        return run_ingestion(
            session,
            p,
            history_days=settings.history_days,
            us_history_start=settings.model_history_start,
        )
    except IngestionError as exc:
        raise HTTPException(502, str(exc)) from exc
