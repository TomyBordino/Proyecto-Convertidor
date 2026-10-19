from __future__ import annotations

from datetime import date
from typing import Protocol

import pandas as pd

from app.analytics.fundamental import FinancialStatement

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


class ProviderError(RuntimeError):
    """La fuente respondió pero no tiene el dato (símbolo inexistente, sin historia…)."""


class SourceUnavailableError(ProviderError):
    """La fuente no responde (red, proxy, 5xx persistentes): cuenta para el circuit breaker."""


class MarketDataProvider(Protocol):
    name: str

    def history(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """OHLCV diario (columnas OHLCV_COLUMNS, índice DatetimeIndex sin tz)."""
        ...

    def fundamentals(self, symbol: str) -> list[FinancialStatement]:
        """Estados anuales ordenados del más antiguo al más reciente."""
        ...
