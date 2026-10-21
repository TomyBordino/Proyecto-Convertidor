"""Universo de activos y mapeo CEDEAR ↔ subyacente.

`ratio` = unidades locales necesarias para equivaler a 1 unidad en EE. UU.
  - CEDEAR AAPL 20:1 → 20 CEDEARs = 1 acción de Apple.
  - ADR GGAL 10:1 → 1 ADR = 10 acciones locales de Grupo Galicia.

IMPORTANTE: BYMA/la Caja de Valores modifican ratios ante splits del subyacente.
Los valores de este archivo son la referencia de carga inicial y deben verificarse
contra el listado oficial de BYMA. El pipeline marca como sospechoso todo activo cuyo
CCL implícito se aleje >35% de la mediana, síntoma típico de un ratio desactualizado.
Revisión contra precios reales del 2026-10-16 (CCL de mercado 1.618,76): SPY da 60:1 e
YPFD 10:1 (split local del 2026-08-03 visible en la serie cruda de data912).
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
    # Acciones del balance (unidad de `shares_outstanding`) por unidad que cotiza en EE. UU.
    # ADRs: acciones ordinarias por ADR según el 20-F; coincide con `ratio` salvo un split
    # local posterior al balance. Clases: BRK-B vale 1/1500 de una acción Clase A.
    reported_shares_per_unit: float | None = None

    @property
    def shares_per_us_unit(self) -> float | None:
        if self.reported_shares_per_unit:
            return self.reported_shares_per_unit
        if self.kind == "LOCAL" and self.us_symbol:
            return self.ratio
        return None

    @property
    def ba_symbol(self) -> str:
        return f"{self.ticker}.BA"


def _cedear(
    ticker: str,
    name: str,
    sector: str,
    ratio: float,
    us: str | None = None,
    reported_shares_per_unit: float | None = None,
) -> AssetSpec:
    return AssetSpec(
        ticker, name, sector, "CEDEAR", ratio, us or ticker, "USD", reported_shares_per_unit
    )


def _local(
    ticker: str,
    name: str,
    sector: str,
    adr: str | None = None,
    ratio: float | None = None,
    reported_shares_per_unit: float | None = None,
) -> AssetSpec:
    # Las locales con ADR se analizan con balances en USD (los del ADR, formato 20-F).
    currency = "USD" if adr else "ARS"
    return AssetSpec(ticker, name, sector, "LOCAL", ratio, adr, currency, reported_shares_per_unit)


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
    _cedear("DISN", "Walt Disney Co.", "Comunicaciones", 12, "DIS"),
    _cedear("BABA", "Alibaba Group", "Consumo discrecional", 9),
    _cedear("GLOB", "Globant S.A.", "Tecnología", 18),
    _cedear("VIST", "Vista Energy", "Energía", 3),
    # Berkshire informa acciones equivalentes Clase A; 1 Clase A = 1.500 Clase B.
    _cedear("BRKB", "Berkshire Hathaway B", "Financiero", 22, "BRK-B", 1 / 1500),
    _cedear("SPY", "SPDR S&P 500 ETF", "ETF", 60),
    _cedear("QQQ", "Invesco QQQ ETF", "ETF", 20),
    # --- Acciones locales (panel líder) ---
    _local("GGAL", "Grupo Financiero Galicia", "Financiero", "GGAL", 10),
    _local("BMA", "Banco Macro", "Financiero", "BMA", 10),
    _local("BBAR", "BBVA Argentina", "Financiero", "BBAR", 3),
    _local("SUPV", "Grupo Supervielle", "Financiero", "SUPV", 5),
    # Split local 10:1 (ago-2026): 1 ADR = 10 YPFD, pero el 20-F 2025 informa acciones
    # previas al split (1 ADR = 1 acción). Actualizar reported_shares_per_unit cuando el
    # 20-F lo refleje.
    _local("YPFD", "YPF S.A.", "Energía", "YPF", 10, reported_shares_per_unit=1),
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
