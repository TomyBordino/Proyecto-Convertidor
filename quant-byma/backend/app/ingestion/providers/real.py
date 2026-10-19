"""Proveedor de datos reales: combina fuentes con cadena de respaldo.

  BYMA (.BA, ARS):   BYMA Data → data912 → Yahoo Finance (.BA)
  EE. UU. (USD):     Tiingo (si hay API key) → Stooq → Yahoo Finance
  Fundamentales:     SEC EDGAR → FMP (si hay API key) → Yahoo Finance
  CCL de referencia: argentinadatos.com

Nunca recurre a datos sintéticos: si ninguna fuente responde se levanta ProviderError y
la ingesta lo registra como error del activo.
"""

from __future__ import annotations

import logging
import threading
from collections import Counter
from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from app.analytics.fundamental import FinancialStatement
from app.config import Settings
from app.ingestion.providers.base import ProviderError, SourceUnavailableError
from app.ingestion.providers.fundamentals import FmpSource, FundamentalsSource, SecEdgarSource
from app.ingestion.providers.fx import ArgentinaDatosCCL
from app.ingestion.providers.http import HttpClient
from app.ingestion.providers.prices import (
    BymaDataSource,
    Data912Source,
    PriceSource,
    StooqSource,
    TiingoSource,
)
from app.ingestion.universe import UNIVERSE

if TYPE_CHECKING:
    from app.ingestion.discovery import LiveQuote

log = logging.getLogger(__name__)

# Mínimo de ruedas para aceptar una serie; menos suele indicar un símbolo mal mapeado.
MIN_BARS = 20
MAX_CONSECUTIVE_FAILURES = 3
# Si la serie arranca dentro de este margen respecto de `start`, no se busca backfill.
BACKFILL_TOLERANCE_DAYS = 10
SPLICE_MIN_OVERLAP = 10
# Cierre de ejercicio + plazo de presentación del 20-F (4 meses) + margen.
STALE_FUNDAMENTALS_DAYS = 15 * 30


def splice_older(primary: pd.DataFrame, secondary: pd.DataFrame) -> pd.DataFrame | None:
    """Tramo de `secondary` anterior a `primary`, reescalado a la base de precios de `primary`.

    Las fuentes difieren en el ajuste por splits/cambios de ratio (BYMA Data y Yahoo publican
    series ajustadas; data912, crudas). El factor se mide como la mediana de
    primary/secondary en las fechas comunes; sin superposición suficiente no se empalma.
    """
    common = primary.index.intersection(secondary.index)
    if len(common) < SPLICE_MIN_OVERLAP:
        return None
    ratio = primary.loc[common, "close"] / secondary.loc[common, "close"]
    # Solo las primeras ruedas comunes: el ajuste de la fuente principal aplica hacia atrás.
    factor = float(ratio.iloc[:SPLICE_MIN_OVERLAP].median())
    if not np.isfinite(factor) or factor <= 0:
        return None
    older = secondary[secondary.index < primary.index.min()].copy()
    for c in ("open", "high", "low", "close"):
        older[c] = older[c] * factor
    older["volume"] = older["volume"] / factor
    return older


class _YahooPrices:
    name = "yahoo"

    def __init__(self) -> None:
        from app.ingestion.providers.yahoo import YahooProvider

        self._y = YahooProvider()
        self._cache: dict[str, pd.DataFrame] = {}

    def prefetch(self, symbols: list[str], start: date, end: date) -> int:
        from app.ingestion.providers.yahoo import batch_history

        self._cache.update(batch_history(symbols, start, end))
        return len(self._cache)

    def history(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        if symbol in self._cache:
            df = self._cache[symbol]
            return df[(df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))]
        return self._y.history(symbol, start, end)

    def fundamentals(self, symbol: str) -> list[FinancialStatement]:
        return self._y.fundamentals(symbol)


class RealDataProvider:
    name = "real"

    def __init__(
        self,
        local: Sequence[PriceSource],
        us: Sequence[PriceSource],
        fundamentals: Sequence[FundamentalsSource],
        ccl_reference: ArgentinaDatosCCL | None = None,
    ) -> None:
        self.local = list(local)
        self.us = list(us)
        self.fund_sources = list(fundamentals)
        self.ccl_reference = ccl_reference
        self.usage: Counter[str] = Counter()  # fuente → cantidad de series servidas
        self._failures: Counter[str] = Counter()
        self._lock = threading.Lock()
        self.http: HttpClient | None = None
        self._data912: Data912Source | None = None

    @classmethod
    def from_settings(cls, s: Settings) -> RealDataProvider:
        http = HttpClient(
            user_agent=s.sec_user_agent,
            min_interval={"data.sec.gov": 0.12, "www.sec.gov": 0.12},
        )
        cedears = {a.ticker for a in UNIVERSE if a.kind == "CEDEAR"}
        local: list[PriceSource] = [
            BymaDataSource(http, s.byma_settlement),
            Data912Source(http, cedears),
        ]
        us: list[PriceSource] = [TiingoSource(http, s.tiingo_api_key)] if s.tiingo_api_key else []
        us.append(StooqSource(http))
        fund: list[FundamentalsSource] = [SecEdgarSource(http)]
        if s.fmp_api_key:
            fund.append(FmpSource(http, s.fmp_api_key))
        if s.yahoo_fallback:
            yahoo = _YahooPrices()
            local.append(yahoo)
            us.append(yahoo)
            fund.append(yahoo)
        provider = cls(local, us, fund, ArgentinaDatosCCL(http))
        provider.http = http
        provider._data912 = local[1]  # type: ignore[assignment]
        return provider

    # ------------------------------------------------------------ universo

    def discover(self) -> dict[str, list[LiveQuote]]:
        """Especies con cotización en BYMA según el panel en vivo de data912."""
        # Import diferido: discovery importa el paquete de proveedores.
        from app.ingestion.discovery import discover_panel

        if self.http is None:
            return {}
        out = {}
        for kind, panel in (("CEDEAR", "arg_cedears"), ("LOCAL", "arg_stocks")):
            try:
                out[kind] = discover_panel(self.http, panel)
            except ProviderError as exc:
                log.warning("No se pudo descubrir el panel %s: %s", panel, exc)
                out[kind] = []
        return out

    def register_cedears(self, tickers: set[str]) -> None:
        """data912 separa los históricos por panel: necesita saber cuáles son CEDEARs."""
        if self._data912 is not None:
            self._data912.cedears |= tickers

    def prefetch_us(self, symbols: list[str], start: date, end: date) -> None:
        """Descarga en lote de Yahoo. Si funciona, Yahoo pasa a ser la fuente de EE. UU.
        después de Tiingo (si hay key): evita cientos de requests individuales a Stooq, que
        además es intermitente desde algunas redes."""
        for src in list(self.us):
            if not isinstance(src, _YahooPrices):
                continue
            try:
                n = src.prefetch(symbols, start, end)
            except Exception as exc:
                log.warning("Descarga en lote de Yahoo falló: %s", exc)
                return
            log.info("Yahoo: %d series de EE. UU. descargadas en lote", n)
            if n:
                self.us.remove(src)
                pos = 1 if self.us and isinstance(self.us[0], TiingoSource) else 0
                self.us.insert(pos, src)
            return

    def metadata(self, symbol: str) -> dict:
        from app.ingestion.providers.yahoo import metadata

        return metadata(symbol)

    def _call(self, src: PriceSource, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Llama a una fuente aplicando un circuit breaker: tras MAX_CONSECUTIVE_FAILURES
        errores seguidos (p. ej. host caído o bloqueado) se la saltea por el resto de la corrida
        en lugar de pagar reintentos en cada símbolo."""
        if self._failures[src.name] >= MAX_CONSECUTIVE_FAILURES:
            raise ProviderError("deshabilitada en esta corrida por fallas consecutivas")
        try:
            df = src.history(symbol, start, end)
        except ProviderError as exc:
            # Un símbolo que la fuente no tiene no indica que la fuente esté caída.
            if isinstance(exc, SourceUnavailableError):
                with self._lock:
                    self._failures[src.name] += 1
            raise
        except Exception as exc:  # errores de red de librerías de terceros (yfinance)
            with self._lock:
                self._failures[src.name] += 1
            raise ProviderError(f"{type(exc).__name__}: {exc}") from exc
        if not df.empty:
            with self._lock:
                self._failures[src.name] = 0
        return df

    def history(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Primera fuente con datos suficientes; si su historia empieza tarde (BYMA Data solo
        publica ~2 años) se completa el tramo anterior con las fuentes siguientes."""
        chain = self.local if symbol.endswith(".BA") else self.us
        errors: list[str] = []
        result: pd.DataFrame | None = None
        # En una actualización incremental la ventana es corta: el mínimo escala con ella.
        expected = len(pd.bdate_range(start, end))
        min_bars = max(1, min(MIN_BARS, expected // 2))
        for src in chain:
            try:
                df = self._call(src, symbol, start, end)
            except ProviderError as exc:
                errors.append(f"{src.name}: {exc}")
                continue
            if result is None:
                if len(df) < min_bars:
                    errors.append(f"{src.name}: {len(df)} ruedas")
                    continue
                result = df
                self.usage[src.name] += 1
            else:
                older = splice_older(result, df)
                if older is None:
                    errors.append(f"{src.name}: sin superposición confiable para empalmar")
                    continue
                if older.empty:
                    continue
                result = pd.concat([older, result]).sort_index()
                self.usage[f"backfill:{src.name}"] += 1
            if result.index.min() <= pd.Timestamp(start) + pd.Timedelta(
                days=BACKFILL_TOLERANCE_DAYS
            ):
                break
        if result is None:
            raise ProviderError(f"Sin precios para {symbol} ({'; '.join(errors)})")
        return result

    def _fetch_fundamentals(self, src: FundamentalsSource, symbol: str, errors: list[str]):
        try:
            return src.fundamentals(symbol)
        except ProviderError as exc:
            errors.append(f"{src.name}: {exc}")
        except Exception as exc:
            errors.append(f"{src.name}: {type(exc).__name__}: {exc}")
        return []

    def fundamentals(self, symbol: str, today: date | None = None) -> list[FinancialStatement]:
        """Primera fuente con balances. Si su último ejercicio está desactualizado (la API
        XBRL de la SEC a veces no incluye los estados de 20-F recientes), se agregan los
        ejercicios posteriores de las fuentes siguientes, solo si reportan en la misma moneda."""
        today = today or date.today()
        errors: list[str] = []
        result: list[FinancialStatement] = []
        for i, src in enumerate(self.fund_sources):
            statements = self._fetch_fundamentals(src, symbol, errors)
            if not statements:
                continue
            result = statements
            self.usage[f"fund:{src.name}"] += 1
            for extra in self.fund_sources[i + 1 :]:
                if (today - result[-1].period_end).days <= STALE_FUNDAMENTALS_DAYS:
                    break
                newer = [
                    s
                    for s in self._fetch_fundamentals(extra, symbol, errors)
                    if s.period_end > result[-1].period_end
                    and s.currency == result[-1].currency
                    and (s.net_income is not None or s.revenue is not None)
                ]
                if newer:
                    result = [*result, *newer]
                    self.usage[f"fund_extend:{extra.name}"] += 1
            return self._fill_missing_shares(result, symbol, self.fund_sources[i + 1 :], errors)
        log.info("Sin fundamentales para %s (%s)", symbol, "; ".join(errors))
        return []

    def _fill_missing_shares(
        self,
        statements: list[FinancialStatement],
        symbol: str,
        others: list[FundamentalsSource],
        errors: list[str],
    ) -> list[FinancialStatement]:
        """Emisores con varias clases de acciones (Visa, Berkshire) no informan un total en la
        portada XBRL: se toma la cantidad de acciones de otra fuente para el mismo ejercicio."""
        if not statements or statements[-1].shares_outstanding:
            return statements
        for src in others:
            shares = {
                s.period_end: s.shares_outstanding
                for s in self._fetch_fundamentals(src, symbol, errors)
                if s.shares_outstanding
            }
            if statements[-1].period_end in shares:
                self.usage[f"fund_shares:{src.name}"] += 1
                return [
                    s
                    if s.shares_outstanding or s.period_end not in shares
                    else replace(s, shares_outstanding=shares[s.period_end])
                    for s in statements
                ]
        return statements

    def reference_ccl(self, start: date, end: date) -> pd.Series:
        if self.ccl_reference is None:
            return pd.Series(dtype=float)
        try:
            return self.ccl_reference.ccl(start, end)
        except ProviderError as exc:
            log.warning("CCL de referencia no disponible: %s", exc)
            return pd.Series(dtype=float)
