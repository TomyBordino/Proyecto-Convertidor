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
from collections import Counter
from collections.abc import Sequence
from datetime import date

import pandas as pd

from app.analytics.fundamental import FinancialStatement
from app.config import Settings
from app.ingestion.providers.base import ProviderError
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

log = logging.getLogger(__name__)

# Mínimo de ruedas para aceptar una serie; menos suele indicar un símbolo mal mapeado.
MIN_BARS = 20


class _YahooPrices:
    name = "yahoo"

    def __init__(self) -> None:
        from app.ingestion.providers.yahoo import YahooProvider

        self._y = YahooProvider()

    def history(self, symbol: str, start: date, end: date) -> pd.DataFrame:
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
        return cls(local, us, fund, ArgentinaDatosCCL(http))

    def history(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        chain = self.local if symbol.endswith(".BA") else self.us
        errors = []
        for src in chain:
            try:
                df = src.history(symbol, start, end)
            except ProviderError as exc:
                errors.append(f"{src.name}: {exc}")
                continue
            except Exception as exc:  # una fuente rota no debe frenar la cadena
                errors.append(f"{src.name}: {type(exc).__name__}: {exc}")
                continue
            if len(df) >= MIN_BARS:
                self.usage[src.name] += 1
                return df
            errors.append(f"{src.name}: {len(df)} ruedas")
        raise ProviderError(f"Sin precios para {symbol} ({'; '.join(errors)})")

    def fundamentals(self, symbol: str) -> list[FinancialStatement]:
        errors = []
        for src in self.fund_sources:
            try:
                statements = src.fundamentals(symbol)
            except ProviderError as exc:
                errors.append(f"{src.name}: {exc}")
                continue
            except Exception as exc:
                errors.append(f"{src.name}: {type(exc).__name__}: {exc}")
                continue
            if statements:
                self.usage[f"fund:{src.name}"] += 1
                return statements
        log.info("Sin fundamentales para %s (%s)", symbol, "; ".join(errors))
        return []

    def reference_ccl(self, start: date, end: date) -> pd.Series:
        if self.ccl_reference is None:
            return pd.Series(dtype=float)
        try:
            return self.ccl_reference.ccl(start, end)
        except ProviderError as exc:
            log.warning("CCL de referencia no disponible: %s", exc)
            return pd.Series(dtype=float)
