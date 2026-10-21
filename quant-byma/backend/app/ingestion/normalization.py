"""Normalización de precios y balances a una moneda dura común (USD CCL).

Regla para balances en ARS:
  - Partidas de stock (activo, pasivo, PN, caja, deuda) → CCL al cierre del período.
  - Partidas de flujo (ventas, EBIT, resultado, FCF) → CCL promedio del ejercicio, porque
    se devengan a lo largo de todo el año.
  - Alternativa "real": ajustar por CPI a moneda homogénea de la fecha de cierre antes
    de convertir (RT 6 / NIC 29), útil cuando el balance no viene ya reexpresado.
"""

from __future__ import annotations

from dataclasses import fields, replace

import pandas as pd

from app.analytics.fundamental import FinancialStatement

STOCK_FIELDS = {
    "total_assets",
    "total_liabilities",
    "current_assets",
    "current_liabilities",
    "equity",
    "total_debt",
    "cash",
    "retained_earnings",
}
FLOW_FIELDS = {"revenue", "ebit", "ebitda", "net_income", "operating_cash_flow", "capex"}


def ars_to_usd(amount_ars: float, ccl: float) -> float:
    if ccl <= 0:
        raise ValueError("CCL debe ser positivo")
    return amount_ars / ccl


def cedear_price_in_usd(price_ars: float, ccl: float) -> float:
    """Precio de un CEDEAR expresado en USD CCL (por certificado)."""
    return ars_to_usd(price_ars, ccl)


def underlying_equivalent_usd(price_ars: float, ratio: float, ccl: float) -> float:
    """Precio de la acción subyacente implícito en el CEDEAR (USD por acción)."""
    return price_ars * ratio / ccl


def statement_to_usd(
    stmt: FinancialStatement, ccl_close: float, ccl_avg: float
) -> FinancialStatement:
    if stmt.currency == "USD":
        return stmt
    changes: dict[str, float | None] = {}
    for f in fields(stmt):
        val = getattr(stmt, f.name)
        if val is None:
            continue
        if f.name in STOCK_FIELDS:
            changes[f.name] = val / ccl_close
        elif f.name in FLOW_FIELDS:
            changes[f.name] = val / ccl_avg
    return replace(stmt, currency="USD", **changes)  # type: ignore[arg-type]


def inflation_adjust(
    stmt: FinancialStatement, cpi_at_period: float, cpi_target: float
) -> FinancialStatement:
    """Reexpresa un balance en ARS a moneda de `cpi_target` (p. ej. la fecha actual)."""
    if stmt.currency != "ARS":
        return stmt
    k = cpi_target / cpi_at_period
    changes = {
        f.name: getattr(stmt, f.name) * k
        for f in fields(stmt)
        if f.name in STOCK_FIELDS | FLOW_FIELDS and getattr(stmt, f.name) is not None
    }
    return replace(stmt, **changes)


def ccl_close_and_avg(ccl: pd.Series, period_end: pd.Timestamp) -> tuple[float, float] | None:
    """CCL al cierre (último dato ≤ fecha) y promedio de los 365 días previos."""
    window = ccl[(ccl.index <= period_end) & (ccl.index > period_end - pd.Timedelta(days=365))]
    if window.empty:
        return None
    return float(window.iloc[-1]), float(window.mean())
