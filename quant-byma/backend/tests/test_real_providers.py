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


def test_concepts_are_merged_per_period():
    # Como Apple: `Revenues` solo en ejercicios viejos, el concepto ASC 606 en los nuevos.
    facts = {
        "us-gaap": {
            "Revenues": usd(fact(229, "2017-09-30", "2016-10-01")),
            "RevenueFromContractWithCustomerExcludingAssessedTax": usd(
                fact(391, "2024-09-28", "2023-10-01")
            ),
            "NetIncomeLoss": usd(
                fact(48, "2017-09-30", "2016-10-01"), fact(94, "2024-09-28", "2023-10-01")
            ),
        }
    }
    st = parse_companyfacts({"facts": facts})
    assert [s.revenue for s in st] == [229, 391]


def test_backfill_extends_short_primary_history():
    recent = bars(30)  # arranca 2025-01-01
    full_idx = pd.bdate_range("2024-06-03", periods=170)
    full = pd.DataFrame(
        {c: 2.0 for c in ("open", "high", "low", "close", "volume")}, index=full_idx
    )
    p = RealDataProvider([FakeSource("bymadata", recent), FakeSource("data912", full)], [], [])
    df = p.history("GGAL.BA", date(2024, 6, 1), END)
    assert df.index.min() == pd.Timestamp("2024-06-03")
    assert df.index.is_unique and df.index.is_monotonic_increasing
    # en el tramo superpuesto manda la fuente principal y el respaldo se reescala (2.0 → 1.0)
    assert df.loc["2025-01-01", "close"] == 1.0
    assert df["close"].eq(1.0).all()
    assert p.usage == {"bymadata": 1, "backfill:data912": 1}


def test_circuit_breaker_skips_failing_source():
    from app.ingestion.providers.base import SourceUnavailableError

    dead = FakeSource("stooq", SourceUnavailableError("connection reset"))
    good = FakeSource("yahoo", bars(30))
    p = RealDataProvider([], [dead, good], [])
    for _ in range(5):
        p.history("AAPL", START, END)
    assert dead.calls == 3


def test_missing_symbols_do_not_trip_circuit_breaker():
    missing = FakeSource("data912", ProviderError("no tengo ese ticker"))
    good = FakeSource("yahoo", bars(30))
    p = RealDataProvider([missing, good], [], [])
    for _ in range(5):
        p.history("NEW.BA", START, END)
    assert missing.calls == 5


def test_splice_rescales_unadjusted_backfill():
    # Fuente principal ajustada por un split 10:1; el respaldo trae precios crudos.
    from app.ingestion.providers.real import splice_older

    idx = pd.bdate_range("2025-01-01", periods=60)
    raw = pd.DataFrame(
        {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 10.0}, index=idx
    )
    raw.iloc[40:, :4] = 10.0  # split visible en la serie cruda
    adjusted = raw.iloc[20:].copy()
    adjusted.iloc[:, :4] = 10.0
    older = splice_older(adjusted, raw)
    assert older["close"].eq(10.0).all() and older["volume"].eq(100.0).all()
    assert splice_older(adjusted, raw.iloc[:15]) is None  # sin superposición


def stmt(year, currency="ARS", ni=1.0):
    from app.analytics.fundamental import FinancialStatement

    return FinancialStatement(period_end=date(year, 12, 31), currency=currency, net_income=ni)


def test_stale_fundamentals_extended_with_same_currency_only():
    sec = FakeSource("sec_edgar", [stmt(2023), stmt(2024)])
    yahoo = FakeSource("yahoo", [stmt(2024, ni=9), stmt(2025, ni=2)])
    p = RealDataProvider([], [], [sec, yahoo])
    out = p.fundamentals("GGAL", today=date(2026, 10, 18))
    assert [(s.period_end.year, s.net_income) for s in out] == [(2023, 1), (2024, 1), (2025, 2)]

    other_ccy = FakeSource("yahoo", [stmt(2025, currency="USD")])
    p = RealDataProvider([], [], [FakeSource("sec_edgar", [stmt(2024)]), other_ccy])
    assert [s.period_end.year for s in p.fundamentals("X", today=date(2026, 10, 18))] == [2024]


def test_fresh_fundamentals_not_extended():
    sec = FakeSource("sec_edgar", [stmt(2025)])
    yahoo = FakeSource("yahoo", ProviderError("no debería llamarse"))
    p = RealDataProvider([], [], [sec, yahoo])
    assert len(p.fundamentals("X", today=date(2026, 6, 1))) == 1


PRETAX = (
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"
)


def test_ebit_and_da_fallbacks():
    facts = {
        "us-gaap": {
            "Revenues": usd(fact(100, "2025-12-31", "2025-01-01")),
            "NetIncomeLoss": usd(fact(10, "2025-12-31", "2025-01-01")),
            PRETAX: usd(fact(14, "2025-12-31", "2025-01-01")),
            "InterestExpense": usd(fact(2, "2025-12-31", "2025-01-01")),
            "Depreciation": usd(fact(5, "2025-12-31", "2025-01-01")),
            "AmortizationOfIntangibleAssets": usd(fact(1, "2025-12-31", "2025-01-01")),
        }
    }
    s = parse_companyfacts({"facts": facts})[-1]
    assert s.ebit == 16 and s.ebitda == 22


def test_missing_shares_filled_from_next_source():
    from dataclasses import replace as dc_replace

    sec = FakeSource("sec_edgar", [stmt(2025, currency="USD")])
    yahoo = FakeSource("yahoo", [dc_replace(stmt(2025, currency="USD"), shares_outstanding=1950.0)])
    p = RealDataProvider([], [], [sec, yahoo])
    assert p.fundamentals("V", today=date(2026, 3, 1))[-1].shares_outstanding == 1950.0


def test_incremental_window_accepts_few_bars():
    p = RealDataProvider([FakeSource("bymadata", bars(8))], [], [])
    df = p.history("GGAL.BA", date(2025, 1, 1), date(2025, 1, 15))
    assert len(df) == 8


def test_live_panel_drops_dollar_variants():
    from app.ingestion.discovery import parse_live_panel

    rows = [
        {"symbol": "AAPL", "c": 100.0, "v": 10.0},
        {"symbol": "AAPLD", "c": 0.07, "v": 5.0},
        {"symbol": "AAPLC", "c": 0.07, "v": 5.0},
        {"symbol": "TXAR", "c": 700.0, "v": 3.0},  # local sin variante en dólares
        {"symbol": "AMD", "c": 50.0, "v": 1.0},  # termina en D pero "AM" no cotiza
        {"symbol": "TGSU2", "c": 9000.0, "v": 1.0},
        {"symbol": "TGSUD", "c": 5.5, "v": 1.0},
        {"symbol": "BMA", "c": 9000.0, "v": 1.0},
        {"symbol": "BMA.D", "c": 5.5, "v": 1.0},
    ]
    assert [q.ticker for q in parse_live_panel(rows)] == ["AAPL", "TXAR", "AMD", "TGSU2", "BMA"]
