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


# Sectores de Yahoo → nombres usados en la plataforma.
SECTOR_ES = {
    "Technology": "Tecnología",
    "Communication Services": "Comunicaciones",
    "Consumer Cyclical": "Consumo discrecional",
    "Consumer Defensive": "Consumo básico",
    "Financial Services": "Financiero",
    "Energy": "Energía",
    "Healthcare": "Salud",
    "Industrials": "Industrial",
    "Basic Materials": "Materiales",
    "Real Estate": "Real Estate",
    "Utilities": "Utilities",
}


def batch_history(
    symbols: list[str], start: date, end: date, chunk: int = 80
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.Series]]:
    """Descarga diaria en lote (una request por bloque de símbolos).

    Devuelve ({símbolo: OHLCV}, {símbolo: splits}). Los precios vienen ajustados por splits
    (no por dividendos); los splits sirven para llevar las acciones de cada balance a la
    misma base que el precio.
    """
    import yfinance as yf

    out: dict[str, pd.DataFrame] = {}
    splits: dict[str, pd.Series] = {}
    for i in range(0, len(symbols), chunk):
        part = symbols[i : i + chunk]
        raw = yf.download(
            part,
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            auto_adjust=False,
            actions=True,
            progress=False,
            group_by="ticker",
            threads=True,
        )
        if raw is None or raw.empty:
            continue
        for sym in part:
            if sym not in raw.columns.get_level_values(0):
                continue
            df = raw[sym].rename(columns=str.lower)
            if "close" not in df:
                continue
            if "stock splits" in df:
                sp = df["stock splits"].dropna()
                sp = sp[sp > 0]
                if not sp.empty:
                    sp.index = pd.DatetimeIndex(sp.index).tz_localize(None).normalize()
                    splits[sym] = sp.astype(float)
            df = df[[c for c in OHLCV_COLUMNS if c in df]].dropna(subset=["close"])
            if df.empty:
                continue
            df.index = pd.DatetimeIndex(df.index).tz_localize(None).normalize()
            out[sym] = df
    return out, splits


def metadata(symbol: str) -> dict:
    """Nombre, sector y tipo (EQUITY/ETF) de un símbolo."""
    import yfinance as yf

    info = yf.Ticker(symbol).info or {}
    quote_type = info.get("quoteType")
    sector = "ETF" if quote_type in ("ETF", "MUTUALFUND") else SECTOR_ES.get(info.get("sector", ""))
    return {
        "name": info.get("longName") or info.get("shortName"),
        "sector": sector or info.get("sector") or "Sin clasificar",
        "quote_type": quote_type,
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
