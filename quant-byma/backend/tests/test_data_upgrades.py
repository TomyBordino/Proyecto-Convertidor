from datetime import date

import httpx
import numpy as np
import pandas as pd
import pytest

from app.analytics.fundamental import FinancialStatement, year_ago
from app.analytics.model import FILING_LAG_DAYS, TTM_FILING_LAG_DAYS, point_in_time_fundamentals
from app.ingestion.providers.fundamentals import parse_companyfacts, parse_quarterly_ttm
from app.ingestion.providers.local_macro import LocalMacroSource, derived, parse_indice
from app.services.data import total_return_close
from tests.test_real_providers import fact, usd


def q(val, end, start):
    return fact(val, end, start, form="10-Q", filed=end)


QUARTERLY = {
    "facts": {
        "dei": {
            "EntityCommonStockSharesOutstanding": {
                "units": {"shares": [fact(1000, "2025-01-20"), q(1010, "2025-10-25", None)]}
            }
        },
        "us-gaap": {
            "Revenues": usd(
                fact(400, "2023-12-31", "2023-01-01"),
                # 2024: trimestre directo + acumulados del ejercicio (como en los 10-Q)
                q(100, "2024-03-31", "2024-01-01"),
                q(210, "2024-06-30", "2024-01-01"),
                q(330, "2024-09-30", "2024-01-01"),
                fact(460, "2024-12-31", "2024-01-01"),
                q(140, "2025-03-31", "2025-01-01"),
                q(290, "2025-06-30", "2025-01-01"),
                q(450, "2025-09-30", "2025-01-01"),
            ),
            "NetIncomeLoss": usd(
                fact(40, "2023-12-31", "2023-01-01"),
                fact(46, "2024-12-31", "2024-01-01"),
                q(10, "2024-03-31", "2024-01-01"),
                q(21, "2024-06-30", "2024-01-01"),
                q(33, "2024-09-30", "2024-01-01"),
                q(14, "2025-03-31", "2025-01-01"),
                q(29, "2025-06-30", "2025-01-01"),
                q(45, "2025-09-30", "2025-01-01"),
            ),
            "StockholdersEquity": usd(fact(800, "2024-12-31"), q(900, "2025-09-30", None)),
        },
    }
}


def test_quarterly_ttm_from_year_to_date_facts():
    annual = parse_companyfacts(QUARTERLY)
    assert [s.period_end for s in annual] == [date(2023, 12, 31), date(2024, 12, 31)]
    ttm = parse_quarterly_ttm(QUARTERLY, annual)
    assert [s.period_end for s in ttm] == [date(2025, 3, 31), date(2025, 6, 30), date(2025, 9, 30)]
    last = ttm[-1]
    assert last.period_type == "TTM"
    # Q4'24 = 460 − 330 = 130; TTM = 130 + 140 + 150 + 160
    assert last.revenue == pytest.approx(580)
    assert last.net_income == pytest.approx(13 + 14 + 15 + 16)
    assert last.equity == 900 and last.shares_outstanding == 1010
    assert ttm[0].revenue == pytest.approx(110 + 120 + 130 + 140)
    # El crecimiento interanual de un TTM se compara con el TTM de un año antes.
    older = FinancialStatement(date(2024, 9, 30), "USD", revenue=500, period_type="TTM")
    assert year_ago([*annual, older, *ttm], last) is older


def test_point_in_time_uses_shorter_lag_for_quarters_and_keeps_shares():
    fy = FinancialStatement(
        date(2024, 12, 31), "USD", revenue=460, net_income=46, equity=800, shares_outstanding=1000
    )
    ttm = FinancialStatement(
        date(2025, 6, 30), "USD", revenue=540, net_income=58, equity=900, period_type="TTM"
    )
    dates = pd.bdate_range("2025-03-01", "2025-10-31")
    px = pd.Series(10.0, index=dates)
    out = point_in_time_fundamentals(dates, [fy, ttm], px)
    fy_known = pd.Timestamp("2024-12-31") + pd.Timedelta(days=FILING_LAG_DAYS)
    ttm_known = pd.Timestamp("2025-06-30") + pd.Timedelta(days=TTM_FILING_LAG_DAYS)
    assert out.loc[out.index < fy_known, "earnings_yield"].isna().all()
    assert out.loc[fy_known : ttm_known - pd.Timedelta(days=1), "earnings_yield"].iloc[
        -1
    ] == pytest.approx(46 / 10000)
    # El TTM no trae acciones: usa las últimas conocidas (1000).
    assert out.loc[ttm_known:, "earnings_yield"].iloc[0] == pytest.approx(58 / 10000)


def test_total_return_adds_dividends_and_keeps_last_price():
    idx = pd.bdate_range("2025-01-01", periods=6)
    close = pd.Series([100, 100, 100, 98, 98, 98], index=idx, dtype=float)  # cae 2 por el pago
    div = pd.Series([2.0], index=[idx[3]])
    tr = total_return_close(close, div)
    assert tr.iloc[-1] == 98
    assert tr.iloc[3] / tr.iloc[2] - 1 == pytest.approx(0.0, abs=1e-9)  # sin caída en retorno total
    assert total_return_close(close, pd.Series(dtype=float)).equals(close)


def test_local_macro_parsing_and_derived_series():
    assert parse_indice([{"fecha": "2026-01-02", "valor": 600}, {"fecha": "x"}]).iloc[0] == 600

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path.endswith("riesgo-pais"):
            return httpx.Response(200, json=[{"fecha": "2026-10-01", "valor": 650}])
        if path.endswith("inflacion"):
            return httpx.Response(200, json=[{"fecha": "2026-09-30", "valor": 2.1}])
        casa = path.rsplit("/", 1)[-1]
        price = {"bolsa": 1500, "contadoconliqui": 1560, "oficial": 1300}[casa]
        return httpx.Response(200, json=[{"fecha": "2026-10-01", "compra": price, "venta": price}])

    base = LocalMacroSource(transport=httpx.MockTransport(handler)).fetch(
        date(2026, 1, 1), date(2026, 10, 20)
    )
    assert base["RIESGO_PAIS"].iloc[-1] == 650 and base["MEP"].iloc[-1] == 1500
    merval = pd.Series([2_340_000.0], index=[pd.Timestamp("2026-10-01")])
    d = derived(base, merval)
    assert d["BRECHA"].iloc[-1] == pytest.approx(1560 / 1300 - 1)
    assert d["CANJE"].iloc[-1] == pytest.approx(1560 / 1500 - 1)
    assert d["MERVAL_USD"].iloc[-1] == pytest.approx(1500)
    assert np.isfinite(d["MERVAL_USD"]).all()
