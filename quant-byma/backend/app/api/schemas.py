from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.analytics.screener import FilterDefinition


class RankingItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    rank: int
    ticker: str
    name: str
    kind: str
    sector: str
    price_ars: float
    price_usd: float
    implied_ccl: float | None = None
    ccl_dev_pct: float | None = None
    rsi14: float | None = None
    pe: float | None = None
    ev_ebitda: float | None = None
    composite_score: float
    technical_score: float | None = None
    fundamental_score: float | None = None
    ccl_score: float | None = None
    signals: list[str] = []


class RankingsResponse(BaseModel):
    as_of: date | None
    ccl_market: float | None
    count: int
    items: list[RankingItem]


class Candle(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class Point(BaseModel):
    time: str
    value: float


class PriceSeriesResponse(BaseModel):
    ticker: str
    currency: str
    candles: list[Candle]
    indicators: dict[str, list[Point]]
    implied_ccl: list[Point]
    market_ccl: list[Point]


class AssetDetail(BaseModel):
    ticker: str
    name: str
    kind: str
    sector: str
    ratio: float | None
    us_symbol: str | None
    ba_symbol: str
    as_of: date | None
    metrics: dict
    breakdown: dict


class CCLAsset(BaseModel):
    ticker: str
    kind: str
    implied_ccl: float
    deviation_pct: float
    ratio_suspect: bool


class CCLResponse(BaseModel):
    as_of: date | None
    market: float | None
    history: list[Point]
    assets: list[CCLAsset]


class SavedFilterIn(BaseModel):
    name: str
    definition: FilterDefinition


class SavedFilterOut(BaseModel):
    id: int
    name: str
    definition: FilterDefinition
    created_at: datetime | None


class FieldInfo(BaseModel):
    key: str
    label: str
    type: str
