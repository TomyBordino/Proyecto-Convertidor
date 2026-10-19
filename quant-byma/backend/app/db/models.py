"""Modelo relacional.

En PostgreSQL + TimescaleDB, `price_bars`, `fx_rates` y `score_snapshots` se convierten
en hypertables (ver `timescale.sql`). El mismo modelo corre sobre SQLite para desarrollo.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Instrument(Base):
    """Activo operado en BYMA.

    kind = "CEDEAR": certificado sobre una acción/ETF extranjero (`us_symbol`).
    kind = "LOCAL": acción argentina; `us_symbol` es su ADR si existe.
    `ratio` = cantidad de unidades locales equivalentes a 1 unidad en EE. UU.
    """

    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    ba_symbol: Mapped[str] = mapped_column(String(24))
    us_symbol: Mapped[str | None] = mapped_column(String(24), nullable=True)
    kind: Mapped[str] = mapped_column(String(8))
    name: Mapped[str] = mapped_column(String(128))
    sector: Mapped[str] = mapped_column(String(64))
    ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Moneda en la que el proveedor reporta los balances (USD para CEDEARs/ADRs, ARS si no).
    reporting_currency: Mapped[str] = mapped_column(String(3), default="USD")
    # "curado": verificado en universe.py; "estimado": deducido de precios reales.
    ratio_source: Mapped[str | None] = mapped_column(String(12), nullable=True)
    # 0..1: estabilidad del ratio estimado y cercanía a un valor entero.
    ratio_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Volumen operado promedio en BYMA (ARS/día, últimas 20 ruedas).
    avg_volume_ars: Mapped[float | None] = mapped_column(Float, nullable=True)
    # False si el activo se descubrió pero no pudo validarse (sin subyacente, ratio inestable).
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    status_note: Mapped[str | None] = mapped_column(String(256), nullable=True)
    metadata_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fundamentals_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    prices: Mapped[list[PriceBar]] = relationship(back_populates="instrument")


class PriceBar(Base):
    __tablename__ = "price_bars"
    __table_args__ = (UniqueConstraint("instrument_id", "market", "day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    market: Mapped[str] = mapped_column(String(2))  # "BA" (ARS) | "US" (USD)
    day: Mapped[date] = mapped_column(Date, index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float, default=0.0)

    instrument: Mapped[Instrument] = relationship(back_populates="prices")


class FxRate(Base):
    """Tipos de cambio diarios. kind: CCL (implícito de mercado), CPI_AR (índice de precios)."""

    __tablename__ = "fx_rates"
    __table_args__ = (UniqueConstraint("kind", "day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    day: Mapped[date] = mapped_column(Date, index=True)
    value: Mapped[float] = mapped_column(Float)
    n_samples: Mapped[int] = mapped_column(Integer, default=0)


class FundamentalPeriod(Base):
    """Estados contables anuales tal como los reporta el proveedor (moneda original)."""

    __tablename__ = "fundamentals"
    __table_args__ = (UniqueConstraint("instrument_id", "period_end"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    period_end: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3))
    revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    ebit: Mapped[float | None] = mapped_column(Float, nullable=True)
    ebitda: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_income: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_assets: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_liabilities: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_assets: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_liabilities: Mapped[float | None] = mapped_column(Float, nullable=True)
    equity: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_debt: Mapped[float | None] = mapped_column(Float, nullable=True)
    cash: Mapped[float | None] = mapped_column(Float, nullable=True)
    retained_earnings: Mapped[float | None] = mapped_column(Float, nullable=True)
    operating_cash_flow: Mapped[float | None] = mapped_column(Float, nullable=True)
    capex: Mapped[float | None] = mapped_column(Float, nullable=True)
    shares_outstanding: Mapped[float | None] = mapped_column(Float, nullable=True)
    tax_rate: Mapped[float | None] = mapped_column(Float, nullable=True)


class ScoreSnapshot(Base):
    """Resultado del motor de scoring por activo y fecha (incluye métricas planas en JSON)."""

    __tablename__ = "score_snapshots"
    __table_args__ = (UniqueConstraint("instrument_id", "day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    composite: Mapped[float] = mapped_column(Float)
    technical: Mapped[float | None] = mapped_column(Float, nullable=True)
    fundamental: Mapped[float | None] = mapped_column(Float, nullable=True)
    ccl: Mapped[float | None] = mapped_column(Float, nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON)
    breakdown: Mapped[dict] = mapped_column(JSON)

    instrument: Mapped[Instrument] = relationship()


class SavedFilter(Base):
    __tablename__ = "saved_filters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    definition: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    provider: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(String(512), default="")


class ModelRun(Base):
    """Resultado del entrenamiento del modelo probabilístico (métricas fuera de muestra)."""

    __tablename__ = "model_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    as_of: Mapped[date] = mapped_column(Date)
    report: Mapped[dict] = mapped_column(JSON)


class SplitEvent(Base):
    """Split del activo en EE. UU. (ratio = acciones nuevas por acción vieja)."""

    __tablename__ = "splits"
    __table_args__ = (UniqueConstraint("instrument_id", "day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    day: Mapped[date] = mapped_column(Date)
    ratio: Mapped[float] = mapped_column(Float)


class MacroPoint(Base):
    """Series de mercado que reflejan eventos macro (tasas, petróleo, VIX, dólar, granos)."""

    __tablename__ = "macro_points"
    __table_args__ = (UniqueConstraint("key", "day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(16), index=True)
    day: Mapped[date] = mapped_column(Date)
    value: Mapped[float] = mapped_column(Float)


class EventReport(Base):
    """Eventos macro activos, estudio de eventos y sensibilidades (capa de contexto)."""

    __tablename__ = "event_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    as_of: Mapped[date] = mapped_column(Date)
    report: Mapped[dict] = mapped_column(JSON)


class NewsItem(Base):
    """Titular de una fuente de noticias (sin análisis)."""

    __tablename__ = "news_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(512))
    publisher: Mapped[str] = mapped_column(String(128), default="")
    link: Mapped[str] = mapped_column(String(1024), default="")
    published_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    source: Mapped[str] = mapped_column(String(24))
    query: Mapped[str] = mapped_column(String(64), default="")
    related: Mapped[list] = mapped_column(JSON, default=list)

    analysis: Mapped[NewsAnalysis | None] = relationship(back_populates="item", uselist=False)


class NewsAnalysis(Base):
    """Interpretación de un titular por Claude: tipo de evento e impacto por sector/activo."""

    __tablename__ = "news_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    news_id: Mapped[int] = mapped_column(ForeignKey("news_items.id"), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    model: Mapped[str] = mapped_column(String(64))
    relevant: Mapped[bool] = mapped_column(Boolean, default=False)
    event_type: Mapped[str] = mapped_column(String(24), default="otro")
    scope: Mapped[str] = mapped_column(String(12), default="empresa")
    summary: Mapped[str] = mapped_column(String(512), default="")
    rationale: Mapped[str] = mapped_column(String(1024), default="")
    impacts: Mapped[list] = mapped_column(JSON, default=list)

    item: Mapped[NewsItem] = relationship(back_populates="analysis")
