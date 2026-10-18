from datetime import date

import pytest

from app.analytics import fundamental as fa
from app.analytics.fundamental import FinancialStatement
from app.ingestion.normalization import (
    inflation_adjust,
    statement_to_usd,
    underlying_equivalent_usd,
)

S = FinancialStatement(
    period_end=date(2024, 12, 31),
    currency="USD",
    revenue=1000,
    ebit=200,
    ebitda=250,
    net_income=150,
    total_assets=2000,
    total_liabilities=1200,
    current_assets=600,
    current_liabilities=400,
    equity=800,
    total_debt=500,
    cash=100,
    retained_earnings=300,
    operating_cash_flow=220,
    capex=-70,
    shares_outstanding=100,
    tax_rate=0.25,
)
PREV = FinancialStatement(period_end=date(2023, 12, 31), currency="USD", revenue=800)


def test_valuation_ratios():
    mcap = fa.market_cap(30, S.shares_outstanding)
    assert mcap == 3000
    assert fa.pe(mcap, S) == pytest.approx(20)
    assert fa.ps(mcap, S) == pytest.approx(3)
    assert fa.pb(mcap, S) == pytest.approx(3.75)
    ev = fa.enterprise_value(mcap, S)
    assert ev == 3400
    assert fa.ev_ebitda(ev, S) == pytest.approx(13.6)


def test_efficiency_and_growth():
    assert fa.roe(S) == pytest.approx(0.1875)
    # NOPAT 150 / capital invertido (500 + 800 - 100 = 1200)
    assert fa.roic(S) == pytest.approx(0.125)
    assert fa.revenue_growth_yoy(S, PREV) == pytest.approx(0.25)
    assert fa.free_cash_flow(S) == 150
    assert fa.fcf_yield(3000, S) == pytest.approx(0.05)


def test_health_ratios_and_altman():
    assert fa.debt_to_equity(S) == pytest.approx(0.625)
    assert fa.current_ratio(S) == pytest.approx(1.5)
    z = 1.2 * 0.1 + 1.4 * 0.15 + 3.3 * 0.1 + 0.6 * 2.5 + 1.0 * 0.5
    assert fa.altman_z(3000, S) == pytest.approx(z)


def test_negative_earnings_and_missing_data_return_none():
    loss = FinancialStatement(period_end=date(2024, 12, 31), currency="USD", net_income=-10)
    assert fa.pe(1000, loss) is None
    assert fa.roe(loss) is None
    assert fa.altman_z(1000, loss) is None
    assert fa.market_cap(10, None) is None


def test_statement_to_usd_uses_close_for_stocks_and_average_for_flows():
    ars = FinancialStatement(
        period_end=date(2024, 12, 31),
        currency="ARS",
        revenue=1_200_000,
        total_assets=2_600_000,
        shares_outstanding=10,
    )
    usd = statement_to_usd(ars, ccl_close=1300, ccl_avg=1200)
    assert usd.currency == "USD"
    assert usd.revenue == pytest.approx(1000)
    assert usd.total_assets == pytest.approx(2000)
    assert usd.shares_outstanding == 10


def test_inflation_adjust_only_ars():
    ars = FinancialStatement(period_end=date(2023, 12, 31), currency="ARS", revenue=100, equity=50)
    adj = inflation_adjust(ars, cpi_at_period=100, cpi_target=250)
    assert adj.revenue == 250 and adj.equity == 125
    assert inflation_adjust(S, 100, 250) is S


def test_underlying_equivalent():
    assert underlying_equivalent_usd(15_000, 20, 1300) == pytest.approx(230.769, rel=1e-4)
