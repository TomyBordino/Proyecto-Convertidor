"""Rutas de la capa de eventos (contexto macro y noticias)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.analytics.events import asset_exposure
from app.config import get_settings
from app.db.session import get_session
from app.services.data import instrument_by_ticker
from app.services.events import (
    latest_event_report,
    news_pressure,
    news_rows,
    refresh_events,
)
from app.services.news_ai import EVENT_LABELS

router = APIRouter(prefix="/api")
SessionDep = Depends(get_session)


def _status() -> dict:
    s = get_settings()
    return {
        "news_enabled": s.news_enabled,
        "classifier": bool(s.anthropic_api_key),
        "model": s.news_model if s.anthropic_api_key else None,
        "lookback_days": s.news_lookback_days,
    }


@router.get("/events")
def events_overview(session: Session = SessionDep, days: int = Query(7, ge=1, le=60)) -> dict:
    report = latest_event_report(session) or {}
    by_ticker, by_sector = news_pressure(session, days)
    news = [row for _, row in news_rows(session, days)]
    return {
        "status": _status(),
        "as_of": report.get("as_of"),
        "horizon": report.get("horizon"),
        "events": report.get("events", []),
        "study": report.get("study", {}),
        "sector_sensitivities": report.get("sector_sensitivities", {}),
        "factors": report.get("factors", {}),
        "macro": report.get("macro", []),
        "local": report.get("local", []),
        "event_labels": EVENT_LABELS,
        "sector_pressure": by_sector,
        "ticker_pressure": {
            t: {k: v for k, v in b.items() if k != "news"} for t, b in by_ticker.items()
        },
        "news": news,
    }


@router.get("/instruments/{ticker}/events")
def asset_events(
    ticker: str, session: Session = SessionDep, days: int = Query(14, ge=1, le=60)
) -> dict:
    inst = instrument_by_ticker(session, ticker)
    if inst is None:
        raise HTTPException(404, f"Activo {ticker} no encontrado")
    report = latest_event_report(session) or {}
    sens = report.get("sensitivities", {})
    exposure = asset_exposure(
        inst.ticker, inst.sector, report.get("events", []), report.get("study", {}), sens
    )
    by_ticker, by_sector = news_pressure(session, days)
    mine = by_ticker.get(inst.ticker)
    ids = set(mine["news"]) if mine else set()
    news = []
    for n, row in news_rows(session, days, limit=2000):
        a = row["analysis"]
        targets = {(i["target_type"], i["target"]) for i in (a or {}).get("impacts", [])}
        if n.id in ids or inst.ticker in (n.related or []) or ("sector", inst.sector) in targets:
            news.append(row)
    return {
        "status": _status(),
        "ticker": inst.ticker,
        "sector": inst.sector,
        "as_of": report.get("as_of"),
        "exposure": exposure,
        "sensitivities": sens.get(inst.ticker, {}),
        "sector_sensitivities": report.get("sector_sensitivities", {}).get(inst.sector, {}),
        "factors": report.get("factors", {}),
        "pressure": {k: v for k, v in (mine or {}).items() if k != "news"} or None,
        "sector_pressure": {
            k: v for k, v in (by_sector.get(inst.sector) or {}).items() if k != "news"
        }
        or None,
        "event_labels": EVENT_LABELS,
        "news": news[:40],
    }


@router.post("/events/refresh")
def events_refresh(session: Session = SessionDep) -> dict:
    return refresh_events(session, get_settings())
