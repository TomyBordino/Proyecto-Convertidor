"""Capa de eventos: series macro, estudio de eventos y noticias interpretadas con Claude.

Es contexto al lado de las probabilidades validadas: nada de lo que se calcula acá entra en
el modelo de `analytics/model.py` (ver CLAUDE.md: un factor nuevo entra al modelo solo si
mejora AUC y Brier skill fuera de muestra).
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, date, datetime, timedelta

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.analytics import events as ev
from app.config import Settings
from app.db.models import EventReport, Instrument, MacroPoint, NewsAnalysis, NewsItem
from app.ingestion.providers.base import ProviderError
from app.ingestion.providers.local_macro import (
    LOCAL_SERIES,
    LocalMacroSource,
    derived,
    fetch_merval,
)
from app.ingestion.providers.macro import MACRO_SERIES, fetch_macro
from app.ingestion.providers.news import MACRO_QUERIES, Headline, YahooNewsSource
from app.services.analytics import analysis_series
from app.services.data import load_bars, load_fx
from app.services.news_ai import BATCH_SIZE, NewsClassifier, build_instructions, sanitize

log = logging.getLogger(__name__)

NEWS_HALF_LIFE_DAYS = 5.0
LEVEL_W = {"baja": 1.0, "media": 2.0, "alta": 3.0}
CONF_W = {"baja": 0.4, "media": 0.7, "alta": 1.0}
DIR_SIGN = {"positivo": 1.0, "negativo": -1.0, "mixto": 0.0}
# Una noticia sectorial pesa la mitad sobre cada activo del sector que una noticia propia.
SECTOR_SPILLOVER = 0.5
PRESSURE_THRESHOLD = 1.0


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# --- series macro ---------------------------------------------------------------------


def store_macro(session: Session, series: dict[str, pd.Series]) -> int:
    n = 0
    for key, s in series.items():
        if s.empty:
            continue
        start = s.index.min().date()
        session.execute(delete(MacroPoint).where(MacroPoint.key == key, MacroPoint.day >= start))
        session.add_all(MacroPoint(key=key, day=d.date(), value=float(v)) for d, v in s.items())
        n += len(s)
    session.flush()
    return n


def load_macro(session: Session) -> dict[str, pd.Series]:
    rows = session.execute(
        select(MacroPoint.key, MacroPoint.day, MacroPoint.value).order_by(MacroPoint.day)
    ).all()
    out: dict[str, list] = {}
    for key, day, value in rows:
        out.setdefault(key, []).append((pd.Timestamp(day), value))
    return {
        k: pd.Series([v for _, v in pts], index=pd.DatetimeIndex([d for d, _ in pts]))
        for k, pts in out.items()
    }


def refresh_macro(session: Session, history_start: date, end: date | None = None) -> int:
    end = end or date.today()
    last = session.scalar(
        select(MacroPoint.day)
        .where(MacroPoint.key.in_(list(MACRO_SERIES)))
        .order_by(MacroPoint.day.desc())
        .limit(1)
    )
    start = last - timedelta(days=30) if last else history_start
    return store_macro(session, fetch_macro(start, end))


def refresh_local_macro(session: Session, history_start: date, end: date | None = None) -> int:
    """Series argentinas completas (son pocas filas: se reemplazan en cada corrida)."""
    end = end or date.today()
    base = LocalMacroSource().fetch(history_start, end)
    merval = fetch_merval(history_start, end)
    series = {**base, **derived(base, merval)}
    if merval is not None:
        series["MERVAL"] = merval
    return store_macro(session, series)


# --- reporte de eventos -----------------------------------------------------------------


def _universe(session: Session) -> list[Instrument]:
    return list(
        session.scalars(
            select(Instrument).where(Instrument.active.isnot(False)).order_by(Instrument.ticker)
        ).all()
    )


def asset_closes(session: Session, instruments: list[Instrument]) -> dict[str, pd.Series]:
    """Cierres en USD (subyacente en EE. UU. o precio BYMA convertido por CCL)."""
    ccl = load_fx(session, "CCL")
    out = {}
    for inst in instruments:
        us = load_bars(session, inst.id, "US")
        ba = load_bars(session, inst.id, "BA") if us.empty else pd.DataFrame()
        if us.empty and (ba.empty or ccl.empty):
            continue
        series, _ = analysis_series(inst, ba, us, ccl)
        if len(series) >= 60:
            out[inst.ticker] = series["close"]
    return out


def compute_event_report(session: Session) -> dict:
    macro = load_macro(session)
    if not macro:
        return {"status": "sin series macro"}
    instruments = _universe(session)
    sectors = {i.ticker: i.sector for i in instruments}
    closes = asset_closes(session, instruments)
    active = ev.detect(macro)
    sens = ev.sensitivities(macro, closes)
    as_of = max(str(s.index.max().date()) for s in macro.values())
    report = {
        "as_of": as_of,
        "horizon": ev.EVENT_HORIZON,
        "events": active,
        "study": ev.event_study(macro, closes, sectors),
        "sensitivities": sens,
        "sector_sensitivities": ev.sector_sensitivities(sens, sectors),
        "factors": {k: {"label": v[3]} for k, v in ev.FACTORS.items()},
        "macro": ev.macro_snapshot(macro, {k: (v[1], v[2]) for k, v in MACRO_SERIES.items()}),
        "local": ev.local_snapshot(macro, LOCAL_SERIES),
    }
    session.add(EventReport(as_of=date.fromisoformat(as_of), report=report))
    session.flush()
    return report


def latest_event_report(session: Session) -> dict | None:
    row = session.scalars(select(EventReport).order_by(EventReport.id.desc()).limit(1)).first()
    return row.report if row else None


# --- noticias -------------------------------------------------------------------------


def _news_targets(instruments: list[Instrument], limit: int) -> list[Instrument]:
    ranked = sorted(instruments, key=lambda i: i.avg_volume_ars or 0.0, reverse=True)
    return ranked[:limit]


def store_headlines(
    session: Session, headlines: list[Headline], us_to_ticker: dict[str, str]
) -> int:
    known = set(
        session.scalars(
            select(NewsItem.uid).where(NewsItem.uid.in_([h.uid for h in headlines]))
        ).all()
    )
    added = 0
    for h in headlines:
        if h.uid in known:
            continue
        known.add(h.uid)
        related = sorted({us_to_ticker[s] for s in h.related if s in us_to_ticker})
        session.add(
            NewsItem(
                uid=h.uid,
                title=h.title,
                publisher=h.publisher,
                link=h.link,
                published_at=h.published_at,
                source="yahoo",
                query=h.query,
                related=related,
            )
        )
        added += 1
    session.flush()
    return added


def fetch_news(
    session: Session, source: YahooNewsSource, max_tickers: int
) -> tuple[int, list[str]]:
    instruments = _universe(session)
    us_to_ticker = {(i.us_symbol or i.ticker).upper(): i.ticker for i in instruments}
    errors: list[str] = []
    headlines: list[Headline] = []
    queries = [(i.us_symbol or i.ticker) for i in _news_targets(instruments, max_tickers)]
    queries += list(MACRO_QUERIES.values())
    for q in queries:
        try:
            headlines += source.search(q)
        except ProviderError as exc:  # incluye SourceUnavailableError
            errors.append(f"{q}: {exc}")
            if len(errors) >= 5 and not headlines:
                break  # la fuente está caída: no insistir con cada ticker
    return store_headlines(session, headlines, us_to_ticker), errors


def classify_pending(
    session: Session, classifier: NewsClassifier, lookback_days: int
) -> dict[str, int]:
    since = _utcnow() - timedelta(days=lookback_days)
    pending = session.scalars(
        select(NewsItem)
        .outerjoin(NewsAnalysis)
        .where(NewsAnalysis.id.is_(None), NewsItem.published_at >= since)
        .order_by(NewsItem.published_at.desc())
    ).all()
    if not pending:
        return {"classified": 0, "refused": 0}
    instruments = _universe(session)
    universe = {i.ticker: (i.us_symbol or "", i.sector) for i in instruments}
    instructions = build_instructions(universe)
    tickers = set(universe)
    sectors = {sec for _, sec in universe.values() if sec}
    counts = {"classified": 0, "refused": 0}
    for k in range(0, len(pending), BATCH_SIZE):
        part = pending[k : k + BATCH_SIZE]
        result = classifier.classify(
            [(n.id, n.title, n.publisher, n.related or []) for n in part], instructions
        )
        for n in part:
            c = result.analyses.get(n.id)
            if c is None:
                if result.refused:
                    # No reintentar indefinidamente un titular que el modelo declina.
                    session.add(
                        NewsAnalysis(
                            news_id=n.id,
                            model=result.model,
                            relevant=False,
                            event_type="otro",
                            scope="empresa",
                            summary="El modelo declinó clasificar este titular.",
                        )
                    )
                    counts["refused"] += 1
                continue
            c = sanitize(c, tickers, sectors)
            session.add(
                NewsAnalysis(
                    news_id=n.id,
                    model=result.model,
                    relevant=c.relevant,
                    event_type=c.event_type,
                    scope=c.scope,
                    summary=c.summary,
                    rationale=c.rationale,
                    impacts=[i.model_dump() for i in c.impacts],
                )
            )
            counts["classified"] += 1
        session.flush()
    return counts


def _weight(imp: dict, age_days: float) -> float:
    return (
        DIR_SIGN.get(imp.get("direction", ""), 0.0)
        * LEVEL_W.get(imp.get("magnitude", ""), 1.0)
        * CONF_W.get(imp.get("confidence", ""), 0.4)
        * math.exp(-math.log(2) * max(age_days, 0.0) / NEWS_HALF_LIFE_DAYS)
    )


def pressure_label(score: float) -> str:
    if score >= PRESSURE_THRESHOLD:
        return "Viento a favor"
    if score <= -PRESSURE_THRESHOLD:
        return "Viento en contra"
    return "Neutral"


def news_rows(session: Session, days: int, limit: int = 300) -> list[tuple[NewsItem, dict]]:
    since = _utcnow() - timedelta(days=days)
    items = session.scalars(
        select(NewsItem)
        .where(NewsItem.published_at >= since)
        .order_by(NewsItem.published_at.desc())
        .limit(limit)
    ).all()
    return [(n, serialize_news(n)) for n in items]


def serialize_news(n: NewsItem) -> dict:
    a = n.analysis
    return {
        "id": n.id,
        "title": n.title,
        "publisher": n.publisher,
        "link": n.link,
        "published_at": n.published_at.isoformat() + "Z",
        "related": n.related or [],
        "analysis": None
        if a is None
        else {
            "relevant": a.relevant,
            "event_type": a.event_type,
            "scope": a.scope,
            "summary": a.summary,
            "rationale": a.rationale,
            "impacts": a.impacts or [],
            "model": a.model,
        },
    }


def news_pressure(
    session: Session, days: int, now: datetime | None = None
) -> tuple[dict[str, dict], dict[str, dict]]:
    """Presión de noticias por activo y por sector: suma de impactos (dirección × magnitud ×
    confianza) con decaimiento exponencial de vida media NEWS_HALF_LIFE_DAYS."""
    now = now or _utcnow()
    instruments = _universe(session)
    sector_of = {i.ticker: i.sector for i in instruments}
    by_ticker: dict[str, dict] = {}
    by_sector: dict[str, dict] = {}

    def add(bucket: dict[str, dict], key: str, w: float, news_id: int) -> None:
        b = bucket.setdefault(key, {"score": 0.0, "pos": 0, "neg": 0, "news": []})
        b["score"] += w
        if w > 0:
            b["pos"] += 1
        elif w < 0:
            b["neg"] += 1
        if news_id not in b["news"]:
            b["news"].append(news_id)

    for n, _ in news_rows(session, days, limit=2000):
        a = n.analysis
        if a is None or not a.relevant:
            continue
        age = (now - n.published_at).total_seconds() / 86400
        for imp in a.impacts or []:
            w = _weight(imp, age)
            if imp["target_type"] == "ticker":
                add(by_ticker, imp["target"], w, n.id)
            else:
                add(by_sector, imp["target"], w, n.id)
    # Las noticias sectoriales se trasladan a cada activo del sector.
    for t, sec in sector_of.items():
        s = by_sector.get(sec)
        if not s:
            continue
        b = by_ticker.setdefault(t, {"score": 0.0, "pos": 0, "neg": 0, "news": []})
        b["sector_score"] = round(s["score"], 3)
        b["score"] += SECTOR_SPILLOVER * s["score"]
    for bucket in (by_ticker, by_sector):
        for b in bucket.values():
            b["score"] = round(b["score"], 3)
            b["label"] = pressure_label(b["score"])
            b["news"] = b["news"][:20]
    return by_ticker, by_sector


def refresh_events(session: Session, settings: Settings) -> dict:
    """Actualiza series macro, reporte de eventos y noticias. Ningún paso es fatal."""
    out: dict = {"errors": []}
    try:
        out["macro_points"] = refresh_macro(session, settings.model_history_start)
    except Exception as exc:  # la capa de eventos nunca debe tumbar la ingesta
        out["errors"].append(f"series macro: {exc}")
    try:
        out["local_points"] = refresh_local_macro(session, settings.model_history_start)
    except Exception as exc:
        out["errors"].append(f"series argentinas: {exc}")
    try:
        rep = compute_event_report(session)
        out["active_events"] = [e["key"] for e in rep.get("events", []) if e["state"] != "inactivo"]
    except Exception as exc:
        log.exception("Reporte de eventos")
        out["errors"].append(f"reporte de eventos: {exc}")
    if settings.news_enabled:
        try:
            out["news_added"], errs = fetch_news(
                session, YahooNewsSource(), settings.news_max_tickers
            )
            out["errors"] += errs[:5]
        except Exception as exc:
            out["errors"].append(f"noticias: {exc}")
        if settings.anthropic_api_key:
            try:
                clf = NewsClassifier(settings.anthropic_api_key, settings.news_model)
                out.update(classify_pending(session, clf, settings.news_lookback_days))
            except Exception as exc:
                out["errors"].append(f"clasificación con Claude: {exc}")
        else:
            out["errors"].append("ANTHROPIC_API_KEY no configurada: titulares sin clasificar")
    session.commit()
    return out
