"""Proveedor DEMO determinístico (datos sintéticos, NO son cotizaciones reales).

Sirve para desarrollar y testear sin red. Respeta la estructura del mercado real:
  - Subyacente en USD sigue un GBM con drift/vol propio de cada ticker.
  - El CCL de mercado es un proceso común con drift de devaluación.
  - El precio local = subyacente × CCL / ratio × (1 + descalce), con un descalce AR(1)
    que revierte a la media: justamente la ineficiencia que el score de CCL intenta capturar.
"""

from __future__ import annotations

import zlib
from datetime import date

import numpy as np
import pandas as pd

from app.analytics.fundamental import FinancialStatement
from app.ingestion.providers.base import OHLCV_COLUMNS, ProviderError
from app.ingestion.universe import UNIVERSE, AssetSpec

CCL_START = 380.0
CCL_ANNUAL_DRIFT = 0.25
CCL_DAILY_VOL = 0.009
HISTORY_START = date(2020, 1, 2)


def _seed(text: str) -> int:
    return zlib.crc32(text.encode())


class DemoProvider:
    name = "demo"

    def __init__(self, universe: list[AssetSpec] | None = None, end: date | None = None) -> None:
        self.universe = universe or UNIVERSE
        self.end = end or date.today()
        self.days = pd.bdate_range(HISTORY_START, self.end)
        self._ccl = self._make_ccl()
        self._by_ba = {a.ba_symbol: a for a in self.universe}
        self._by_us = {a.us_symbol: a for a in self.universe if a.us_symbol}
        self._cache: dict[str, pd.DataFrame] = {}

    # ---------------------------------------------------------------- series

    def _make_ccl(self) -> pd.Series:
        rng = np.random.default_rng(42)
        mu = CCL_ANNUAL_DRIFT / 252
        rets = rng.normal(mu - 0.5 * CCL_DAILY_VOL**2, CCL_DAILY_VOL, len(self.days))
        return pd.Series(CCL_START * np.exp(np.cumsum(rets)), index=self.days)

    def _gbm(self, key: str, start_price: float, drift: float, vol: float) -> pd.Series:
        rng = np.random.default_rng(_seed(key))
        # Regímenes: alterna tramos alcistas y bajistas para generar cruces de medias.
        regime = np.sin(np.linspace(0, rng.uniform(3, 9), len(self.days)) + rng.uniform(0, 6))
        mu = drift / 252 + regime * vol * 0.12
        rets = rng.normal(mu - 0.5 * vol**2, vol, len(self.days))
        return pd.Series(start_price * np.exp(np.cumsum(rets)), index=self.days)

    def _ohlcv(self, close: pd.Series, key: str, base_volume: float) -> pd.DataFrame:
        rng = np.random.default_rng(_seed(key + ":ohlc"))
        n = len(close)
        prev = close.shift(1).fillna(close.iloc[0])
        spread = np.abs(rng.normal(0, 0.008, n)) + 0.004
        open_ = prev * (1 + rng.normal(0, 0.004, n))
        high = np.maximum(open_, close) * (1 + spread)
        low = np.minimum(open_, close) * (1 - spread)
        volume = base_volume * np.exp(rng.normal(0, 0.45, n))
        return pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
            index=close.index,
        )[OHLCV_COLUMNS]

    def _params(self, spec: AssetSpec) -> tuple[float, float, float]:
        rng = np.random.default_rng(_seed(spec.ticker + ":params"))
        price = float(rng.uniform(15, 450))
        drift = float(rng.uniform(-0.10, 0.35))
        vol = float(rng.uniform(0.012, 0.03))
        return price, drift, vol

    def _underlying(self, spec: AssetSpec) -> pd.Series:
        price, drift, vol = self._params(spec)
        return self._gbm(spec.ticker + ":us", price, drift, vol)

    def _local_close(self, spec: AssetSpec) -> pd.Series:
        if spec.us_symbol and spec.ratio:
            rng = np.random.default_rng(_seed(spec.ticker + ":mispricing"))
            eps = np.zeros(len(self.days))
            shocks = rng.normal(0, 0.006, len(self.days))
            for i in range(1, len(eps)):
                eps[i] = 0.9 * eps[i - 1] + shocks[i]  # AR(1), vida media ≈ 6.6 ruedas
            return self._underlying(spec) * self._ccl / spec.ratio * (1 + eps)
        price, drift, vol = self._params(spec)
        # Acciones sin ADR: precio en USD CCL × CCL con más volatilidad local.
        return self._gbm(spec.ticker + ":ba", price / 10, drift, vol * 1.25) * self._ccl

    def history(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        if symbol not in self._cache:
            if symbol in self._by_ba:
                spec = self._by_ba[symbol]
                df = self._ohlcv(self._local_close(spec), symbol, 2.5e8)
            elif symbol in self._by_us:
                spec = self._by_us[symbol]
                df = self._ohlcv(self._underlying(spec), symbol, 5e6)
            else:
                raise ProviderError(f"Símbolo desconocido para el proveedor demo: {symbol}")
            self._cache[symbol] = df
        df = self._cache[symbol]
        return df[(df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))]

    # ---------------------------------------------------------- fundamentals

    def fundamentals(self, symbol: str) -> list[FinancialStatement]:
        spec = self._by_us.get(symbol) or self._by_ba.get(symbol)
        if spec is None:
            raise ProviderError(f"Símbolo desconocido para el proveedor demo: {symbol}")
        if spec.sector == "ETF":
            return []
        rng = np.random.default_rng(_seed(spec.ticker + ":fund"))
        is_ars = spec.reporting_currency == "ARS"
        financial = spec.sector == "Financiero"
        growth = rng.uniform(-0.04, 0.22)
        last_fy = pd.Timestamp(date(self.end.year - 1, 12, 31))
        px_usd = self._underlying(spec) if spec.us_symbol else self._local_close(spec) / self._ccl
        last_px = float(px_usd[px_usd.index <= last_fy].iloc[-1])
        target_ps = rng.uniform(0.8, 7.0)
        revenue = rng.uniform(2e9, 8e10)
        # Calibra las acciones para que el P/S del último ejercicio ronde target_ps.
        shares = target_ps * revenue * (1 + growth) ** 5 / last_px
        margin_ebit = rng.uniform(0.06, 0.32)
        out = []
        for i, year in enumerate(range(self.end.year - 5, self.end.year)):
            period_end = date(year, 12, 31)
            g = growth + rng.normal(0, 0.05)
            revenue *= 1 + g
            ebit = revenue * (margin_ebit + rng.normal(0, 0.02))
            ebitda = ebit * rng.uniform(1.1, 1.4)
            net = ebit * rng.uniform(0.55, 0.8)
            assets = revenue * rng.uniform(1.0, 2.5) * (4 if financial else 1)
            equity = assets * rng.uniform(0.12 if financial else 0.3, 0.6)
            liabilities = assets - equity
            debt = liabilities * rng.uniform(0.2, 0.6)
            ocf = net * rng.uniform(1.0, 1.5)
            stmt = dict(
                revenue=revenue,
                ebit=ebit,
                ebitda=ebitda,
                net_income=net,
                total_assets=assets,
                total_liabilities=liabilities,
                current_assets=None if financial else assets * rng.uniform(0.25, 0.5),
                current_liabilities=None if financial else liabilities * rng.uniform(0.3, 0.6),
                equity=equity,
                total_debt=debt,
                cash=assets * rng.uniform(0.03, 0.15),
                retained_earnings=equity * rng.uniform(0.3, 0.8),
                operating_cash_flow=ocf,
                capex=-ocf * rng.uniform(0.2, 0.6),
                shares_outstanding=shares * (1 - 0.01 * i),
                tax_rate=0.21 if not is_ars else 0.35,
            )
            if is_ars:
                ccl_avg = float(self._ccl[self._ccl.index.year == year].mean())
                ccl_close = float(self._ccl[self._ccl.index <= pd.Timestamp(period_end)].iloc[-1])
                stock = {
                    "total_assets",
                    "total_liabilities",
                    "current_assets",
                    "current_liabilities",
                    "equity",
                    "total_debt",
                    "cash",
                    "retained_earnings",
                }
                for k, v in list(stmt.items()):
                    if v is None or k in ("shares_outstanding", "tax_rate"):
                        continue
                    stmt[k] = v * (ccl_close if k in stock else ccl_avg)
            out.append(
                FinancialStatement(
                    period_end=period_end, currency="ARS" if is_ars else "USD", **stmt
                )
            )
        return out

    def ccl_truth(self) -> pd.Series:
        """CCL "verdadero" del proceso sintético (solo para tests)."""
        return self._ccl
