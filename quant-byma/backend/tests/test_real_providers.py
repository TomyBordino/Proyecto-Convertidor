"""Parsers y cadena de respaldo de las fuentes reales.

Los payloads replican el *formato* de cada API (no son cotizaciones reales): permiten
verificar el parseo y el manejo de errores sin depender de la red.
"""

from datetime import date

import httpx
import pandas as pd
import pytest

from app.ingestion.providers.base import ProviderError
from app.ingestion.providers.fundamentals import (
    SecEdgarSource,
    parse_companyfacts,
    parse_fmp,
)
from app.ingestion.providers.fx import ArgentinaDatosCCL, parse_argentinadatos
from app.ingestion.providers.http import HttpClient
from app.ingestion.providers.prices import (
    BymaDataSource,
    Data912Source,
    StooqSource,
    TiingoSource,
    udf_to_ohlcv,
)
from app.ingestion.providers.real import RealDataProvider

START, END = date(2025, 1, 1), date(2025, 12, 31)


def client(handler) -> HttpClient:
    return HttpClient(transport=httpx.MockTransport(handler), retries=1, min_interval={})


def epoch(d: str) -> int:
    return int(pd.Timestamp(d + " 03:00", tz="UTC").timestamp())  # 00:00 en Buenos Aires


# ------------------------------------------------------------------ precios


def test_byma_udf_request_and_parse():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(dict(req.url.params))
        return httpx.Response(
            200,
            json={
                "s": "ok",
                "t": [epoch("2025-03-03"), epoch("2025-03-04")],
                "o": [100, 102],
                "h": [105, 106],
                "l": [99, 101],
                "c": [104, 103],
                "v": [1000, 2000],
            },
        )

    df = BymaDataSource(client(handler)).history("GGAL.BA", START, END)
    assert seen["symbol"] == "GGAL 24HS" and seen["resolution"] == "D"
    assert list(df.index.strftime("%Y-%m-%d")) == ["2025-03-03", "2025-03-04"]
    assert df["close"].tolist() == [104, 103]


def test_udf_no_data_and_error():
    assert udf_to_ohlcv({"s": "no_data"}, START, END).empty
    with pytest.raises(ProviderError):
        udf_to_ohlcv({"s": "error", "errmsg": "x"}, START, END)


def test_data912_routes_cedears_and_stocks():
    paths = []

    def handler(req: httpx.Request) -> httpx.Response:
        paths.append(req.url.path)
        return httpx.Response(
            200,
            json=[
                {"date": "2025-05-02", "o": 10, "h": 11, "l": 9, "c": 10.5, "v": 50},
                {"date": "2025-05-05", "o": 10.5, "h": 12, "l": 10, "c": 11.5, "v": 70},
            ],
        )

    src = Data912Source(client(handler), cedears={"AAPL"})
    assert len(src.history("AAPL.BA", START, END)) == 2
    src.history("GGAL.BA", START, END)
    assert paths == ["/historical/cedears/AAPL", "/historical/stocks/GGAL"]


def test_data912_fills_missing_ohl_with_close():
    def handler(req):
        return httpx.Response(200, json=[{"date": "2025-05-02", "c": 10.0, "v": 0}])

    df = Data912Source(client(handler), set()).history("TXAR.BA", START, END)
    assert df.iloc[0][["open", "high", "low", "close"]].tolist() == [10.0] * 4


def test_tiingo_uses_raw_prices_and_token_header():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.headers["Authorization"] == "Token k"
        return httpx.Response(
            200,
            json=[
                {
                    "date": "2025-06-02T00:00:00.000Z",
                    "open": 200.0,
                    "high": 202.0,
                    "low": 199.0,
                    "close": 201.0,
                    "volume": 1e6,
                    "adjClose": 150.0,
                }
            ],
        )

    df = TiingoSource(client(handler), "k").history("AAPL", START, END)
    assert df.iloc[0]["close"] == 201.0  # no el ajustado


def test_stooq_csv_and_no_data():
    csv = (
        "Date,Open,High,Low,Close,Volume\n2025-06-02,1,2,0.5,1.5,100\n2025-06-03,1.5,2,1,1.8,120\n"
    )
    df = StooqSource(client(lambda r: httpx.Response(200, text=csv))).history("AAPL", START, END)
    assert df["close"].tolist() == [1.5, 1.8]
    with pytest.raises(ProviderError):
        StooqSource(client(lambda r: httpx.Response(200, text="No data"))).history("X", START, END)


def test_http_does_not_retry_client_errors():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(404)

    with pytest.raises(ProviderError):
        client(handler).get_json("https://example.com/x")
    assert len(calls) == 1


# ------------------------------------------------------------ fundamentales


def fact(val, end, start=None, form="10-K", filed="2025-02-01", fp="FY"):
    f = {"val": val, "end": end, "form": form, "filed": filed, "fp": fp}
    if start:
        f["start"] = start
    return f


def usd(*facts):
    return {"units": {"USD": list(facts)}}


COMPANYFACTS = {
    "facts": {
        "dei": {
            "EntityCommonStockSharesOutstanding": {
                "units": {"shares": [fact(1000, "2025-01-20"), fact(990, "2024-01-22")]}
            }
        },
        "us-gaap": {
            "RevenueFromContractWithCustomerExcludingAssessedTax": usd(
                fact(500, "2023-12-31", "2023-01-01"),
                fact(600, "2024-12-31", "2024-01-01"),
                # trimestre: debe ignorarse
                fact(160, "2024-12-31", "2024-10-01", form="10-Q"),
            ),
            "OperatingIncomeLoss": usd(fact(120, "2024-12-31", "2024-01-01")),
            "DepreciationDepletionAndAmortization": usd(fact(30, "2024-12-31", "2024-01-01")),
            "NetIncomeLoss": usd(
                fact(80, "2023-12-31", "2023-01-01"),
                fact(90, "2024-12-31", "2024-01-01", filed="2025-02-01"),
                # re-expresión posterior del mismo ejercicio: pisa al original
                fact(95, "2024-12-31", "2024-01-01", filed="2026-02-01"),
            ),
            "Assets": usd(fact(2000, "2024-12-31")),
            "LiabilitiesAndStockholdersEquity": usd(fact(2000, "2024-12-31")),
            "StockholdersEquity": usd(fact(800, "2024-12-31")),
            "AssetsCurrent": usd(fact(700, "2024-12-31")),
            "LiabilitiesCurrent": usd(fact(400, "2024-12-31")),
            "LongTermDebtNoncurrent": usd(fact(300, "2024-12-31")),
            "LongTermDebtCurrent": usd(fact(50, "2024-12-31")),
            "CashAndCashEquivalentsAtCarryingValue": usd(fact(150, "2024-12-31")),
            "NetCashProvidedByUsedInOperatingActivities": usd(
                fact(140, "2024-12-31", "2024-01-01")
            ),
            "PaymentsToAcquirePropertyPlantAndEquipment": usd(fact(40, "2024-12-31", "2024-01-01")),
        },
    }
}


def test_parse_companyfacts_us_gaap():
    st = parse_companyfacts(COMPANYFACTS)
    assert [s.period_end for s in st] == [date(2023, 12, 31), date(2024, 12, 31)]
    last = st[-1]
    assert last.currency == "USD"
    assert last.revenue == 600
    assert last.net_income == 95
    assert last.ebitda == 150
    assert last.total_liabilities == 1200  # derivado: pasivo + PN − PN
    assert last.total_debt == 350
    assert last.shares_outstanding == 1000  # portada del 10-K más cercana al cierre
    assert st[0].revenue == 500


def test_parse_companyfacts_ifrs_in_ars():
    payload = {
        "facts": {
            "ifrs-full": {
                "Revenue": {
                    "units": {"ARS": [fact(9e12, "2024-12-31", "2024-01-01", form="20-F")]}
                },
                "ProfitLoss": {
                    "units": {"ARS": [fact(1e12, "2024-12-31", "2024-01-01", form="20-F")]}
                },
                "Equity": {"units": {"ARS": [fact(5e12, "2024-12-31", form="20-F")]}},
                "Borrowings": {"units": {"ARS": [fact(2e12, "2024-12-31", form="20-F")]}},
            }
        }
    }
    st = parse_companyfacts(payload)
    assert st[-1].currency == "ARS"
    assert st[-1].revenue == 9e12 and st[-1].total_debt == 2e12


def test_sec_source_resolves_cik_with_dash_variant():
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("company_tickers.json"):
            return httpx.Response(200, json={"0": {"cik_str": 1067983, "ticker": "BRK.B"}})
        assert req.url.path.endswith("CIK0001067983.json")
        return httpx.Response(200, json=COMPANYFACTS)

    assert len(SecEdgarSource(client(handler)).fundamentals("BRK-B")) == 2


def test_parse_fmp():
    st = parse_fmp(
        [
            {
                "date": "2024-12-31",
                "revenue": 600,
                "operatingIncome": 120,
                "ebitda": 150,
                "netIncome": 90,
                "incomeBeforeTax": 100,
                "incomeTaxExpense": 21,
                "weightedAverageShsOutDil": 1000,
                "reportedCurrency": "USD",
            }
        ],
        [{"date": "2024-12-31", "totalAssets": 2000, "totalDebt": 350}],
        [{"date": "2024-12-31", "operatingCashFlow": 140, "capitalExpenditure": -40}],
    )
    assert st[0].tax_rate == pytest.approx(0.21)
    assert st[0].total_debt == 350 and st[0].capex == -40


# --------------------------------------------------------------- CCL ref


def test_argentinadatos_mid_price():
    payload = [
        {"casa": "contadoconliqui", "compra": 1180, "venta": 1200, "fecha": "2025-06-02"},
        {"casa": "contadoconliqui", "compra": None, "venta": 1210, "fecha": "2025-06-03"},
        {"casa": "contadoconliqui", "compra": 900, "venta": 910, "fecha": "2019-01-02"},
    ]
    s = parse_argentinadatos(payload, START, END)
    assert s.tolist() == [1190, 1210]
    src = ArgentinaDatosCCL(client(lambda r: httpx.Response(200, json=payload)))
    assert len(src.ccl(START, END)) == 2


# ------------------------------------------------------------- cadena


class FakeSource:
    def __init__(self, name, result):
        self.name, self.result, self.calls = name, result, 0

    def history(self, symbol, start, end):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def fundamentals(self, symbol):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def bars(n):
    idx = pd.bdate_range("2025-01-01", periods=n)
    return pd.DataFrame({c: 1.0 for c in ("open", "high", "low", "close", "volume")}, index=idx)


def test_chain_falls_back_and_records_usage():
    broken = FakeSource("bymadata", ProviderError("caído"))
    short = FakeSource("data912", bars(3))  # muy pocas ruedas → se descarta
    good = FakeSource("yahoo", bars(30))
    p = RealDataProvider([broken, short, good], [], [])
    assert len(p.history("GGAL.BA", START, END)) == 30
    assert p.usage == {"yahoo": 1}


def test_chain_routes_us_symbols_and_never_fabricates():
    local = FakeSource("bymadata", bars(30))
    us = FakeSource("stooq", ProviderError("bloqueado"))
    p = RealDataProvider([local], [us], [])
    with pytest.raises(ProviderError, match="Sin precios para AAPL"):
        p.history("AAPL", START, END)
    assert local.calls == 0


def test_fundamentals_chain_returns_empty_when_all_fail():
    p = RealDataProvider([], [], [FakeSource("sec_edgar", ProviderError("x"))])
    assert p.fundamentals("AAPL") == []
