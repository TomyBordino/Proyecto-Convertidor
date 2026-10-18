"""Proveedor Yahoo Finance (yfinance). Subyacentes en EE. UU. y tickers BYMA con sufijo `.BA`.

Uso responsable: una única descarga diaria por símbolo, sin paralelismo agresivo.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from app.analytics.fundamental import FinancialStatement
from app.ingestion.providers.base import OHLCV_COLUMNS, ProviderError

log = logging.getLogger(__name__)

# fila de yfinance → campo de FinancialStatement (se toma la primera fila presente)
ROWS: dict[str, tuple[str, ...]] = {
    "revenue": ("Total Revenue", "Operating Revenue"),
    "ebit": ("EBIT", "Operating Income"),
    "ebitda": ("EBITDA", "Normalized EBITDA"),
    "net_income": ("Net Income", "Net Income Common Stockholders"),
    "total_assets": ("Total Assets",),
    "total_liabilities": ("Total Liabilities Net Minority Interest", "Total Liabilities"),
    "current_assets": ("Current Assets",),
    "current_liabilities": ("Current Liabilities",),
    "equity": ("Stockholders Equity", "Common Stock Equity"),
    "total_debt": ("Total Debt",),
    "cash": ("Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"),
    "retained_earnings": ("Retained Earnings",),
    "operating_cash_flow": ("Operating Cash Flow",),
    "capex": ("Capital Expenditure",),
    "shares_outstanding": ("Ordinary Shares Number", "Share Issued"),
    "tax_rate": ("Tax Rate For Calcs",),
}


class YahooProvider:
    name = "yahoo"

    def __init__(self) -> None:
        try:
            import yfinance  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise ProviderError("yfinance no está instalado") from exc

    def is_available(self) -> bool:
        try:
            end = date.today()
            return not self.history("SPY", end - timedelta(days=10), end).empty
        except Exception as exc:  # red caída, proxy, rate limit
            log.warning("Yahoo Finance no disponible: %s", exc)
            return False

    def history(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        import yfinance as yf

        df = yf.Ticker(symbol).history(
            start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(), auto_adjust=False
        )
        if df is None or df.empty:
            return pd.DataFrame(columns=OHLCV_COLUMNS)
        df = df.rename(columns=str.lower)[OHLCV_COLUMNS]
        df.index = pd.DatetimeIndex(df.index).tz_localize(None).normalize()
        return df.dropna(subset=["close"])

    def fundamentals(self, symbol: str) -> list[FinancialStatement]:
        import yfinance as yf

        t = yf.Ticker(symbol)
        frames = [f for f in (t.income_stmt, t.balance_sheet, t.cashflow) if f is not None]
        if not frames or all(f.empty for f in frames):
            return []
        merged = pd.concat(frames)
        merged = merged[~merged.index.duplicated()]
        # `financialCurrency` es la moneda de los balances; `currency` (fast_info) es la de
        # cotización: un ADR cotiza en USD aunque el emisor reporte en ARS (p. ej. GGAL, TGS).
        try:
            currency = (t.info or {}).get("financialCurrency")
        except Exception:  # info hace un request aparte que puede fallar
            currency = None
        if not currency:
            log.warning("Yahoo no informa la moneda de los balances de %s; se descartan", symbol)
            return []
        out = []
        for col in sorted(merged.columns):
            values = {}
            for field_name, candidates in ROWS.items():
                for row in candidates:
                    if row in merged.index and pd.notna(merged.at[row, col]):
                        values[field_name] = float(merged.at[row, col])
                        break
            out.append(
                FinancialStatement(period_end=pd.Timestamp(col).date(), currency=currency, **values)
            )
        return out
