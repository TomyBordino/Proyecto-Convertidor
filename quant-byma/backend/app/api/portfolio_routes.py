"""Rutas de la cartera del usuario y del backtest."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.analytics.backtest import REBALANCE, Strategy, quintile_returns, run_backtest
from app.db.models import Holding, Instrument
from app.db.session import get_session
from app.services.analytics import load_panel
from app.services.portfolio import Fx, analyze
from app.services.portfolio_import import import_file

router = APIRouter(prefix="/api")
SessionDep = Depends(get_session)
MAX_UPLOAD = 5 * 1024 * 1024


class HoldingIn(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    quantity: float = Field(gt=0)
    price: float | None = Field(default=None, gt=0, description="Precio promedio de compra")
    currency: Literal["ARS", "USD"] = "ARS"
    opened_at: date | None = None


@router.get("/portfolio")
def portfolio(session: Session = SessionDep) -> dict:
    return analyze(session)


@router.post("/portfolio/holdings", status_code=201)
def upsert_holding(body: HoldingIn, session: Session = SessionDep) -> dict:
    ticker = body.ticker.strip().upper()
    cost_usd = cost_ars = None
    if body.price:
        cur = "MEP" if body.currency == "USD" else "ARS"
        cost_usd, cost_ars = Fx(session).convert(body.quantity * body.price, cur, body.opened_at)
    h = session.scalar(select(Holding).where(Holding.ticker == ticker))
    if h is None:
        h = Holding(ticker=ticker, quantity=body.quantity, income_usd=0.0)
        session.add(h)
    h.quantity, h.cost_usd, h.cost_ars = body.quantity, cost_usd, cost_ars
    h.opened_at, h.source = body.opened_at, "manual"
    session.commit()
    return {"id": h.id, "ticker": ticker}


@router.delete("/portfolio/holdings/{holding_id}", status_code=204)
def delete_holding(holding_id: int, session: Session = SessionDep) -> None:
    session.execute(delete(Holding).where(Holding.id == holding_id))
    session.commit()


@router.post("/portfolio/import")
async def import_portfolio(
    file: Annotated[UploadFile, File()],
    replace: bool = Query(True, description="Reemplazar la cartera actual"),
    session: Session = SessionDep,
) -> dict:
    content = await file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, "Archivo demasiado grande (máximo 5 MB)")
    try:
        res = import_file(content, file.filename or "archivo.csv", Fx(session).convert)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not res.positions:
        raise HTTPException(422, "No se encontraron tenencias abiertas en el archivo")
    if replace:
        session.execute(delete(Holding))
    known = set(session.scalars(select(Instrument.ticker)).all())
    for ticker, p in res.positions.items():
        h = session.scalar(select(Holding).where(Holding.ticker == ticker))
        if h is None:
            h = Holding(ticker=ticker)
            session.add(h)
        h.quantity, h.cost_usd, h.cost_ars = p.quantity, p.cost_usd or None, p.cost_ars or None
        h.income_usd, h.opened_at, h.source = p.income_usd, p.opened_at, res.kind
    session.commit()
    return {
        "kind": res.kind,
        "positions": len(res.positions),
        "outside_universe": sorted(t for t in res.positions if t not in known),
        "rows_used": res.rows_used,
        "rows_skipped": res.rows_skipped,
        "warnings": res.warnings[:20],
    }


@router.get("/backtest")
def backtest(
    session: Session = SessionDep,
    top_n: int = Query(20, ge=3, le=100),
    rebalance: int = Query(20),
    sort: Literal["score", "trend", "value"] = "score",
    stages: str = Query("", description="Etapas separadas por coma, p. ej. 1,2"),
    kind: Literal["CEDEAR", "LOCAL"] | None = None,
    max_per_sector: int | None = Query(None, ge=1, le=50),
    cost_bps: float = Query(50, ge=0, le=500),
    buffer: float = Query(2.0, ge=1.0, le=5.0),
    start_year: int | None = Query(None, ge=2000, le=2100),
) -> dict:
    if rebalance not in REBALANCE:
        raise HTTPException(422, f"rebalanceo debe ser uno de {REBALANCE}")
    panel = load_panel()
    if panel is None or panel.empty:
        raise HTTPException(404, "Todavía no hay panel histórico: ejecutá una ingesta")
    meta = {
        i.ticker: {"kind": i.kind, "sector": i.sector} for i in session.scalars(select(Instrument))
    }
    st = Strategy(
        top_n=top_n,
        rebalance=rebalance,
        sort=sort,
        stages=[int(x) for x in stages.split(",") if x.strip().isdigit()],
        kind=kind,
        max_per_sector=max_per_sector,
        cost_bps=cost_bps,
        buffer=buffer,
        start_year=start_year,
    )
    out = run_backtest(panel, meta, st)
    out["quintiles"] = quintile_returns(
        panel
        if not kind
        else panel[panel["ticker"].map(lambda t: meta.get(t, {}).get("kind")) == kind],
        rebalance,
    )
    names = {i.ticker: i.name for i in session.scalars(select(Instrument))}
    out["picks"] = [{"ticker": t, "name": names.get(t)} for t in out.get("picks", [])]
    return out
