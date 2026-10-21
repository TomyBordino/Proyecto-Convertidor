"""Fuentes reales de precios diarios (OHLCV).

Mercado local (BYMA, ARS):
  - BymaDataSource: API pública de BYMA Data (open.bymadata.com.ar), fuente oficial del
    mercado. Formato de series estilo TradingView UDF: {s, t, o, h, l, c, v}.
  - Data912Source: data912.com, API gratuita con históricos diarios de acciones y CEDEARs.

EE. UU. (USD):
  - TiingoSource: EOD de calidad institucional (requiere QB_TIINGO_API_KEY, plan gratuito).
  - StooqSource: CSV diario gratuito sin API key.

Todas devuelven precios sin ajustar por dividendos (el CCL implícito compara cierres del
mismo día en ambas plazas, así que los dividendos no deben distorsionar la serie).
"""

from __future__ import annotations

import io
import logging
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, time
from typing import Any, Protocol

import pandas as pd

from app.ingestion.providers.base import OHLCV_COLUMNS, ProviderError
from app.ingestion.providers.http import HttpClient

log = logging.getLogger(__name__)

# Aliases de columnas de las distintas APIs → nombre canónico.
_ALIASES = {
    "date": ("date", "fecha", "Date", "time", "t"),
    "open": ("open", "o", "Open", "apertura"),
    "high": ("high", "h", "High", "maximo"),
    "low": ("low", "l", "Low", "minimo"),
    "close": ("close", "c", "Close", "cierre", "ultimo"),
    "volume": ("volume", "v", "Volume", "volumen"),
}


class PriceSource(Protocol):
    name: str

    def history(self, symbol: str, start: date, end: date) -> pd.DataFrame: ...


def empty_ohlcv() -> pd.DataFrame:
    return pd.DataFrame(columns=OHLCV_COLUMNS, index=pd.DatetimeIndex([], name="day"))


def _pick(row: Mapping[str, Any], field: str) -> Any:
    for key in _ALIASES[field]:
        if key in row and row[key] is not None:
            return row[key]
    return None


def normalize_ohlcv(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    """Índice de fechas sin tz, columnas OHLCV float, sin duplicados ni cierres inválidos."""
    if df.empty:
        return empty_ohlcv()
    df = df.copy()
    df.index = pd.DatetimeIndex(pd.to_datetime(df.index)).tz_localize(None).normalize()
    df.index.name = "day"
    for c in OHLCV_COLUMNS:
        df[c] = pd.to_numeric(df[c], errors="coerce") if c in df else float("nan")
    df["volume"] = df["volume"].fillna(0.0)
    # Ruedas sin apertura/máximo/mínimo (poca liquidez): se completan con el cierre.
    for c in ("open", "high", "low"):
        df[c] = df[c].fillna(df["close"])
    df = df[df["close"] > 0]
    df = df[~df.index.duplicated(keep="last")].sort_index()
    mask = (df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))
    return df.loc[mask, OHLCV_COLUMNS]


def records_to_ohlcv(records: Iterable[Mapping[str, Any]], start: date, end: date) -> pd.DataFrame:
    rows = []
    for r in records:
        d = _pick(r, "date")
        if d is None:
            continue
        rows.append(
            {
                "day": pd.Timestamp(d),
                **{f: _pick(r, f) for f in ("open", "high", "low", "close", "volume")},
            }
        )
    if not rows:
        return empty_ohlcv()
    return normalize_ohlcv(pd.DataFrame(rows).set_index("day"), start, end)


def udf_to_ohlcv(payload: Mapping[str, Any], start: date, end: date) -> pd.DataFrame:
    """Formato TradingView UDF: {"s": "ok", "t": [epoch], "o": [...], ...}."""
    status = payload.get("s")
    if status == "no_data":
        return empty_ohlcv()
    if status not in (None, "ok") or "t" not in payload:
        raise ProviderError(f"Respuesta UDF inválida: s={status!r}")
    idx = pd.to_datetime(payload["t"], unit="s", utc=True).tz_convert(
        "America/Argentina/Buenos_Aires"
    )
    df = pd.DataFrame(
        {
            "open": payload.get("o"),
            "high": payload.get("h"),
            "low": payload.get("l"),
            "close": payload.get("c"),
            "volume": payload.get("v", [0] * len(idx)),
        },
        index=idx.tz_localize(None),
    )
    return normalize_ohlcv(df, start, end)


def _epoch(d: date, end_of_day: bool = False) -> int:
    t = time(23, 59, 59) if end_of_day else time(0, 0)
    return int(datetime.combine(d, t, tzinfo=UTC).timestamp())


def local_ticker(symbol: str) -> str:
    """ "GGAL.BA" → "GGAL"."""
    return symbol.removesuffix(".BA").upper()


class BymaDataSource:
    """API pública de BYMA Data (datos con demora, sin autenticación)."""

    name = "bymadata"
    BASE = "https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free"

    def __init__(self, http: HttpClient, settlement: str = "24HS") -> None:
        self.http = http
        self.settlement = settlement

    def history(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        ticker = local_ticker(symbol)
        payload = self.http.get_json(
            f"{self.BASE}/chart/historical-series/history",
            params={
                "symbol": f"{ticker} {self.settlement}",
                "resolution": "D",
                "from": _epoch(start),
                "to": _epoch(end, end_of_day=True),
            },
        )
        return udf_to_ohlcv(payload, start, end)


class Data912Source:
    """data912.com: históricos diarios de acciones (`stocks`) y CEDEARs (`cedears`)."""

    name = "data912"
    BASE = "https://data912.com/historical"

    def __init__(self, http: HttpClient, cedears: set[str]) -> None:
        self.http = http
        self.cedears = cedears

    def history(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        ticker = local_ticker(symbol)
        panel = "cedears" if ticker in self.cedears else "stocks"
        payload = self.http.get_json(f"{self.BASE}/{panel}/{ticker}")
        if not isinstance(payload, list):
            raise ProviderError(f"data912 devolvió un formato inesperado para {ticker}")
        return records_to_ohlcv(payload, start, end)


class TiingoSource:
    """Tiingo EOD (https://api.tiingo.com). Precios crudos (`open`, `close`…), no `adj*`."""

    name = "tiingo"
    BASE = "https://api.tiingo.com/tiingo/daily"

    def __init__(self, http: HttpClient, api_key: str) -> None:
        self.http = http
        self.api_key = api_key

    def history(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        payload = self.http.get_json(
            f"{self.BASE}/{symbol.lower()}/prices",
            params={"startDate": start.isoformat(), "endDate": end.isoformat()},
            headers={"Authorization": f"Token {self.api_key}"},
        )
        if not isinstance(payload, list):
            raise ProviderError(f"Tiingo devolvió un formato inesperado para {symbol}")
        return records_to_ohlcv(payload, start, end)


class StooqSource:
    """Stooq: CSV diario `Date,Open,High,Low,Close,Volume` (tickers EE. UU. con sufijo .us)."""

    name = "stooq"
    BASE = "https://stooq.com/q/d/l/"

    def __init__(self, http: HttpClient) -> None:
        self.http = http

    def history(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        text = self.http.get_text(
            self.BASE,
            params={
                "s": f"{symbol.lower()}.us",
                "i": "d",
                "d1": start.strftime("%Y%m%d"),
                "d2": end.strftime("%Y%m%d"),
            },
        )
        if not text.lstrip().startswith("Date"):
            # Stooq responde 200 con "No data" o un aviso de límite diario en texto plano.
            raise ProviderError(f"Stooq sin datos para {symbol}: {text[:80]!r}")
        df = pd.read_csv(io.StringIO(text), parse_dates=["Date"]).set_index("Date")
        return normalize_ohlcv(df.rename(columns=str.lower), start, end)
