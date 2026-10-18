"""Universo de activos y mapeo CEDEAR ↔ subyacente.

`ratio` = unidades locales necesarias para equivaler a 1 unidad en EE. UU.
  - CEDEAR AAPL 20:1 → 20 CEDEARs = 1 acción de Apple.
  - ADR GGAL 10:1 → 1 ADR = 10 acciones locales de Grupo Galicia.

IMPORTANTE: BYMA/la Caja de Valores modifican ratios ante splits del subyacente.
Los valores de este archivo son la referencia de carga inicial y deben verificarse
contra el listado oficial de BYMA. El pipeline marca como sospechoso todo activo cuyo
CCL implícito se aleje >35% de la mediana, síntoma típico de un ratio desactualizado.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssetSpec:
    ticker: str
    name: str
    sector: str
    kind: str  # "CEDEAR" | "LOCAL"
    ratio: float | None
    us_symbol: str | None
    reporting_currency: str = "USD"

    @property
    def ba_symbol(self) -> str:
        return f"{self.ticker}.BA"


def _cedear(ticker: str, name: str, sector: str, ratio: float, us: str | None = None) -> AssetSpec:
    return AssetSpec(ticker, name, sector, "CEDEAR", ratio, us or ticker)


def _local(
    ticker: str,
    name: str,
    sector: str,
    adr: str | None = None,
    ratio: float | None = None,
) -> AssetSpec:
    # Las locales con ADR se analizan con balances en USD (los del ADR, formato 20-F).
    return AssetSpec(ticker, name, sector, "LOCAL", ratio, adr, "USD" if adr else "ARS")


UNIVERSE: list[AssetSpec] = [
    # --- CEDEARs (subyacente en NYSE/NASDAQ) ---
    _cedear("AAPL", "Apple Inc.", "Tecnología", 20),
    _cedear("MSFT", "Microsoft Corp.", "Tecnología", 30),
    _cedear("GOOGL", "Alphabet Inc. A", "Comunicaciones", 58),
    _cedear("AMZN", "Amazon.com Inc.", "Consumo discrecional", 144),
    _cedear("NVDA", "NVIDIA Corp.", "Tecnología", 24),
    _cedear("META", "Meta Platforms", "Comunicaciones", 24),
    _cedear("TSLA", "Tesla Inc.", "Consumo discrecional", 15),
    _cedear("AMD", "Advanced Micro Devices", "Tecnología", 10),
    _cedear("MELI", "MercadoLibre Inc.", "Consumo discrecional", 120),
    _cedear("KO", "Coca-Cola Co.", "Consumo básico", 5),
    _cedear("WMT", "Walmart Inc.", "Consumo básico", 18),
    _cedear("JPM", "JPMorgan Chase", "Financiero", 15),
    _cedear("V", "Visa Inc.", "Financiero", 18),
    _cedear("XOM", "Exxon Mobil", "Energía", 10),
    _cedear("CVX", "Chevron Corp.", "Energía", 16),
    _cedear("PFE", "Pfizer Inc.", "Salud", 4),
    _cedear("JNJ", "Johnson & Johnson", "Salud", 15),
    _cedear("DIS", "Walt Disney Co.", "Comunicaciones", 12),
    _cedear("BABA", "Alibaba Group", "Consumo discrecional", 9),
    _cedear("GLOB", "Globant S.A.", "Tecnología", 18),
    _cedear("VIST", "Vista Energy", "Energía", 3),
    _cedear("BRKB", "Berkshire Hathaway B", "Financiero", 22, "BRK-B"),
    _cedear("SPY", "SPDR S&P 500 ETF", "ETF", 20),
    _cedear("QQQ", "Invesco QQQ ETF", "ETF", 20),
    # --- Acciones locales (panel líder) ---
    _local("GGAL", "Grupo Financiero Galicia", "Financiero", "GGAL", 10),
    _local("BMA", "Banco Macro", "Financiero", "BMA", 10),
    _local("BBAR", "BBVA Argentina", "Financiero", "BBAR", 3),
    _local("SUPV", "Grupo Supervielle", "Financiero", "SUPV", 5),
    _local("YPFD", "YPF S.A.", "Energía", "YPF", 1),
    _local("PAMP", "Pampa Energía", "Energía", "PAM", 25),
    _local("CEPU", "Central Puerto", "Utilities", "CEPU", 10),
    _local("EDN", "Edenor", "Utilities", "EDN", 20),
    _local("TGSU2", "Transportadora Gas del Sur", "Energía", "TGS", 5),
    _local("LOMA", "Loma Negra", "Materiales", "LOMA", 5),
    _local("TECO2", "Telecom Argentina", "Comunicaciones", "TEO", 5),
    _local("CRES", "Cresud", "Real Estate", "CRESY", 10),
    _local("IRSA", "IRSA", "Real Estate", "IRS", 10),
    _local("TXAR", "Ternium Argentina", "Materiales"),
    _local("ALUA", "Aluar", "Materiales"),
    _local("COME", "Sociedad Comercial del Plata", "Industrial"),
    _local("TRAN", "Transener", "Utilities"),
    _local("BYMA", "Bolsas y Mercados Argentinos", "Financiero"),
]

UNIVERSE_BY_TICKER = {a.ticker: a for a in UNIVERSE}
