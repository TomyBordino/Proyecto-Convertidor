import io
from datetime import date

import openpyxl
import pandas as pd
import pytest

from app.analytics.backtest import Strategy, quintile_returns, run_backtest
from app.analytics.model import build_panel
from app.services.portfolio_import import import_file, parse_number
from tests.test_model import _synthetic_assets

MEP = 1000.0


def convert(amount, currency, day):
    if currency == "ARS":
        return amount / MEP, amount
    if currency == "CABLE":
        return amount * 1.02, amount * MEP * 1.02
    return amount, amount * MEP


def _xlsx(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Movimientos de la cuenta 12345"])  # título antes de los encabezados
    ws.append([])
    ws.append(
        [
            "Concertación",
            "Tipo",
            "Descripción",
            "Ticker",
            "Cantidad",
            "Precio",
            "Liquidación",
            "Moneda",
            "Importe",
        ]
    )
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_number_argentine_format():
    assert parse_number("1.234,56") == pytest.approx(1234.56)
    assert parse_number(None) is None and parse_number("-") is None


def test_balanz_movements_rebuild_positions_with_average_cost():
    content = _xlsx(
        [
            [
                "02/01/2026",
                "Boleto",
                "COMPRA AAPL",
                "AAPL",
                10,
                20000,
                "03/01/2026",
                "Pesos",
                -200000,
            ],
            [
                "10/02/2026",
                "Boleto",
                "COMPRA AAPL",
                "AAPL",
                10,
                30000,
                "11/02/2026",
                "Pesos",
                -300000,
            ],
            [
                "01/03/2026",
                "Boleto",
                "VENTA AAPL",
                "AAPL",
                -5,
                32000,
                "02/03/2026",
                "Pesos",
                160000,
            ],
            [
                "15/03/2026",
                "Dividendo en efectivo",
                "Dividendo AAPL",
                "AAPL",
                0,
                0,
                "15/03/2026",
                "Dólares (MEP)",
                3.5,
            ],
            ["20/03/2026", "Boleto", "COMPRA KO", "KO", 4, 50, "21/03/2026", "Dólares Cable", -200],
            [
                "25/03/2026",
                "Suscripción desde Balanz",
                "FCI",
                "BCMMA",
                100,
                1,
                "25/03/2026",
                "Pesos",
                -100,
            ],
            ["01/04/2026", "Boleto", "VENTA KO", "KO", -4, 60, "02/04/2026", "Dólares Cable", 240],
        ]
    )
    res = import_file(content, "movimientos.xlsx", convert)
    assert res.kind == "balanz"
    assert set(res.positions) == {"AAPL"}  # KO se cerró y el FCI se ignora
    a = res.positions["AAPL"]
    assert a.quantity == 15
    # costo promedio: 500.000 ARS por 20 → vendo 5 → queda 375.000 ARS = 375 USD MEP
    assert a.cost_ars == pytest.approx(375_000)
    assert a.cost_usd == pytest.approx(375)
    assert a.income_usd == pytest.approx(3.5)
    assert a.opened_at == date(2026, 1, 2)


def test_simple_holdings_csv():
    csv = b"Ticker;Cantidad;Precio;Moneda\nGGAL;100;5.000,50;ARS\nMSFT;3;400;USD\n"
    res = import_file(csv, "tenencias.csv", convert)
    assert res.kind == "tenencias"
    assert res.positions["GGAL"].cost_ars == pytest.approx(500_050)
    assert res.positions["MSFT"].cost_usd == pytest.approx(1200)


def test_import_without_ticker_column_fails_clearly():
    with pytest.raises(ValueError, match="encabezados"):
        import_file(b"a,b\n1,2\n", "x.csv", convert)


def test_backtest_on_persistent_signal_beats_universe_and_reports_costs():
    panel = build_panel(_synthetic_assets(n_assets=40))
    meta = {
        t: {"kind": "CEDEAR", "sector": f"S{i % 4}"} for i, t in enumerate(panel["ticker"].unique())
    }
    r = run_backtest(panel, meta, Strategy(top_n=8, rebalance=20, cost_bps=0, buffer=1.0))
    assert r["status"] == "ok" and r["periods"] > 30
    m = r["metrics"]
    assert m["strategy"]["cagr"] > m["universe"]["cagr"]  # la señal persistente se cobra
    costly = run_backtest(panel, meta, Strategy(top_n=8, rebalance=20, cost_bps=100, buffer=1.0))
    buffered = run_backtest(panel, meta, Strategy(top_n=8, rebalance=20, buffer=2.5))
    assert buffered["avg_turnover"] < r["avg_turnover"]  # el colchón reduce la rotación
    assert costly["metrics"]["strategy"]["cagr"] < m["strategy"]["cagr"]
    capped = run_backtest(panel, meta, Strategy(top_n=8, max_per_sector=1))
    assert len(capped["picks"]) == 4
    vw = run_backtest(panel, meta, Strategy(top_n=8, weighting="inv_vol"))
    assert vw["status"] == "ok"
    # Con el SPY "en etapa bajista" siempre, la cartera queda en liquidez a la tasa dada.
    always_bear = panel.copy()
    always_bear.loc[always_bear["ticker"] == "T0", "stage"] = 4
    cash = pd.Series(0.12, index=pd.DatetimeIndex([panel["date"].min()]))
    off = run_backtest(
        always_bear, meta, Strategy(top_n=8, regime="spy_bear", benchmark="T0", cost_bps=0), cash
    )
    assert off["time_in_market"] == 0.0
    assert off["metrics"]["strategy"]["cagr"] == pytest.approx(1.12**1 - 1, abs=0.02)
    q = quintile_returns(panel, 20)
    assert q[-1]["cagr"] > q[0]["cagr"]
    with pytest.raises(ValueError):
        run_backtest(panel, meta, Strategy(rebalance=7))


def test_portfolio_endpoints(seeded_client):
    r = seeded_client.post(
        "/api/portfolio/holdings",
        json={"ticker": "aapl", "quantity": 10, "price": 15000, "currency": "ARS"},
    )
    assert r.status_code == 201
    body = seeded_client.get("/api/portfolio").json()
    h = next(x for x in body["holdings"] if x["ticker"] == "AAPL")
    assert h["in_universe"] and h["value_usd"] > 0 and h["weight"] == pytest.approx(1.0)
    assert body["summary"]["value_usd"] > 0 and "NaN" not in str(body)
    csv = b"Ticker,Cantidad\nGGAL,50\nAL30,1000\n"
    imp = seeded_client.post("/api/portfolio/import", files={"file": ("t.csv", csv, "text/csv")})
    assert imp.status_code == 200, imp.text
    assert imp.json()["outside_universe"] == ["AL30"]
    tickers = {x["ticker"] for x in seeded_client.get("/api/portfolio").json()["holdings"]}
    assert tickers == {"GGAL", "AL30"}  # reemplazó la cartera
    for x in seeded_client.get("/api/portfolio").json()["holdings"]:
        assert seeded_client.delete(f"/api/portfolio/holdings/{x['id']}").status_code == 204
    assert seeded_client.get("/api/portfolio").json()["holdings"] == []


def test_backtest_endpoint(seeded_client):
    r = seeded_client.get("/api/backtest", params={"top_n": 3, "rebalance": 20})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "quintiles" in body and "NaN" not in r.text
    plan = body["plan"]
    assert len(plan["picks"]) <= 3 and len(plan["keep_zone"]) >= len(plan["picks"])
    if plan["picks"]:
        assert sum(p["weight"] for p in plan["picks"]) == pytest.approx(1.0, abs=0.01)
    assert seeded_client.get("/api/backtest", params={"rebalance": 7}).status_code == 422
