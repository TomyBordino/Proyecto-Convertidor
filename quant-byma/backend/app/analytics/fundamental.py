"""Ratios fundamentales. Toda función devuelve None si falta un dato o el divisor es ≤ 0
en los casos donde el ratio pierde sentido económico (p. ej. P/E con ganancias negativas)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class FinancialStatement:
    period_end: date
    currency: str
    revenue: float | None = None
    ebit: float | None = None
    ebitda: float | None = None
    net_income: float | None = None
    total_assets: float | None = None
    total_liabilities: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    equity: float | None = None
    total_debt: float | None = None
    cash: float | None = None
    retained_earnings: float | None = None
    operating_cash_flow: float | None = None
    capex: float | None = None  # negativo o positivo; se toma el valor absoluto
    shares_outstanding: float | None = None
    tax_rate: float | None = None


def _div(a: float | None, b: float | None, positive_denominator: bool = True) -> float | None:
    if a is None or b is None or b == 0:
        return None
    if positive_denominator and b < 0:
        return None
    return a / b


def market_cap(price: float, shares: float | None) -> float | None:
    return price * shares if shares else None


def enterprise_value(mcap: float | None, s: FinancialStatement) -> float | None:
    if mcap is None:
        return None
    return mcap + (s.total_debt or 0.0) - (s.cash or 0.0)


def free_cash_flow(s: FinancialStatement) -> float | None:
    if s.operating_cash_flow is None or s.capex is None:
        return None
    return s.operating_cash_flow - abs(s.capex)


def pe(mcap: float | None, s: FinancialStatement) -> float | None:
    return _div(mcap, s.net_income)


def ps(mcap: float | None, s: FinancialStatement) -> float | None:
    return _div(mcap, s.revenue)


def pb(mcap: float | None, s: FinancialStatement) -> float | None:
    return _div(mcap, s.equity)


def ev_ebitda(ev: float | None, s: FinancialStatement) -> float | None:
    return _div(ev, s.ebitda)


def roe(s: FinancialStatement) -> float | None:
    return _div(s.net_income, s.equity)


def roic(s: FinancialStatement) -> float | None:
    """ROIC = NOPAT / (Deuda + PN - Caja), con NOPAT = EBIT * (1 - tasa impositiva)."""
    if s.ebit is None or s.equity is None:
        return None
    tax = s.tax_rate if s.tax_rate is not None else 0.25
    invested = (s.total_debt or 0.0) + s.equity - (s.cash or 0.0)
    return _div(s.ebit * (1 - tax), invested)


def revenue_growth_yoy(current: FinancialStatement, previous: FinancialStatement) -> float | None:
    if current.revenue is None or previous.revenue is None or previous.revenue <= 0:
        return None
    return current.revenue / previous.revenue - 1.0


def fcf_yield(mcap: float | None, s: FinancialStatement) -> float | None:
    return _div(free_cash_flow(s), mcap)


def debt_to_equity(s: FinancialStatement) -> float | None:
    return _div(s.total_debt, s.equity)


def current_ratio(s: FinancialStatement) -> float | None:
    return _div(s.current_assets, s.current_liabilities)


def altman_z(mcap: float | None, s: FinancialStatement) -> float | None:
    """Altman Z-Score original (1968): Z = 1.2A + 1.4B + 3.3C + 0.6D + 1.0E.

    A = capital de trabajo / activo, B = resultados acumulados / activo, C = EBIT / activo,
    D = valor de mercado del PN / pasivo total, E = ventas / activo.
    Zonas: > 2.99 segura, 1.81–2.99 gris, < 1.81 riesgo de quiebra.
    """
    ta, tl = s.total_assets, s.total_liabilities
    needed = (s.current_assets, s.current_liabilities, s.retained_earnings, s.ebit, s.revenue)
    if not ta or ta <= 0 or not tl or tl <= 0 or mcap is None or any(v is None for v in needed):
        return None
    assert s.current_assets is not None and s.current_liabilities is not None
    assert s.retained_earnings is not None and s.ebit is not None and s.revenue is not None
    a = (s.current_assets - s.current_liabilities) / ta
    b = s.retained_earnings / ta
    c = s.ebit / ta
    d = mcap / tl
    e = s.revenue / ta
    return 1.2 * a + 1.4 * b + 3.3 * c + 0.6 * d + 1.0 * e


def all_ratios(price: float, s: FinancialStatement, previous: FinancialStatement | None) -> dict:
    mcap = market_cap(price, s.shares_outstanding)
    ev = enterprise_value(mcap, s)
    return {
        "market_cap": mcap,
        "pe": pe(mcap, s),
        "ps": ps(mcap, s),
        "pb": pb(mcap, s),
        "ev_ebitda": ev_ebitda(ev, s),
        "roe": roe(s),
        "roic": roic(s),
        "revenue_growth": revenue_growth_yoy(s, previous) if previous else None,
        "fcf_yield": fcf_yield(mcap, s),
        "debt_to_equity": debt_to_equity(s),
        "current_ratio": current_ratio(s),
        "altman_z": altman_z(mcap, s),
    }
