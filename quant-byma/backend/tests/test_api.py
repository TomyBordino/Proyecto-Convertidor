import json

import pytest

from app.ingestion.providers.demo import DemoProvider
from tests.conftest import END, TICKERS


def test_health(seeded_client):
    r = seeded_client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["as_of"] == END.isoformat()


def test_rankings_valid_json_and_ordering(seeded_client):
    r = seeded_client.get("/api/rankings")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    body = json.loads(r.text)  # JSON estricto: sin NaN/Infinity
    assert body["count"] == len(TICKERS) == len(body["items"])
    assert body["ccl_market"] > 0
    items = body["items"]
    assert [i["rank"] for i in items] == list(range(1, len(items) + 1))
    scores = [i["composite_score"] for i in items]
    assert scores == sorted(scores, reverse=True)
    for i in items:
        assert 0 <= i["composite_score"] <= 100
        assert i["price_ars"] > 0 and i["price_usd"] > 0
        assert isinstance(i["signals"], list)
        if i["kind"] == "CEDEAR":
            assert i["implied_ccl"] > 0 and i["ccl_dev_pct"] is not None
    assert "NaN" not in r.text and "Infinity" not in r.text


def test_rankings_filters(seeded_client):
    body = seeded_client.get("/api/rankings", params={"kind": "LOCAL"}).json()
    assert {i["kind"] for i in body["items"]} == {"LOCAL"}
    assert seeded_client.get("/api/rankings", params={"kind": "BOND"}).status_code == 422
    assert seeded_client.get("/api/rankings", params={"sort_by": "hack"}).status_code == 422


def test_market_ccl_tracks_true_process(seeded_client):
    truth = DemoProvider(end=END).ccl_truth()
    market = seeded_client.get("/api/ccl", params={"days": 5}).json()["market"]
    assert market == pytest.approx(float(truth.iloc[-1]), rel=0.03)


def test_asset_detail_and_breakdown(seeded_client):
    d = seeded_client.get("/api/instruments/aapl").json()
    assert d["ticker"] == "AAPL" and d["ratio"] == 20
    groups = {g["group"]: g for g in d["breakdown"]["groups"]}
    assert set(groups) == {"technical", "fundamental", "ccl"}
    assert sum(d["breakdown"]["weights"].values()) == pytest.approx(1)
    assert seeded_client.get("/api/instruments/ZZZZ").status_code == 404


@pytest.mark.parametrize("currency", ["ARS", "USD", "US"])
def test_price_series(seeded_client, currency):
    r = seeded_client.get(
        "/api/instruments/GGAL/prices", params={"currency": currency, "days": 250}
    )
    body = r.json()
    assert len(body["candles"]) == 250
    assert len(body["indicators"]["sma200"]) == 250
    times = [c["time"] for c in body["candles"]]
    assert times == sorted(times)


def test_local_without_adr_has_no_us_series(seeded_client):
    assert (
        seeded_client.get("/api/instruments/TXAR/prices", params={"currency": "US"}).status_code
        == 404
    )
    f = seeded_client.get("/api/instruments/TXAR/fundamentals").json()
    assert f["reporting_currency"] == "ARS" and f["currency"] == "USD"
    assert len(f["periods"]) >= 4


def test_screener_and_saved_filters(seeded_client):
    definition = {
        "conditions": [
            {"field": "rsi14", "op": "between", "value": [0, 100]},
            {"field": "kind", "op": "eq", "value": "CEDEAR"},
        ],
        "sort_by": "ccl_dev_pct",
        "sort_dir": "asc",
        "limit": 3,
    }
    r = seeded_client.post("/api/screener/run", json=definition).json()
    assert r["count"] == 3
    devs = [i["ccl_dev_pct"] for i in r["items"]]
    assert devs == sorted(devs)

    created = seeded_client.post(
        "/api/filters", json={"name": "CCL barato", "definition": definition}
    )
    assert created.status_code == 201
    assert (
        seeded_client.post(
            "/api/filters", json={"name": "CCL barato", "definition": definition}
        ).status_code
        == 409
    )
    listed = seeded_client.get("/api/filters").json()
    assert listed[0]["definition"]["sort_by"] == "ccl_dev_pct"
    assert seeded_client.delete(f"/api/filters/{created.json()['id']}").status_code == 204
    assert seeded_client.delete(f"/api/filters/{created.json()['id']}").status_code == 404

    bad = {"conditions": [{"field": "rsi14", "op": "gt", "value": "x"}]}
    assert seeded_client.post("/api/screener/run", json=bad).status_code == 422


def test_screener_fields(seeded_client):
    fields = seeded_client.get("/api/screener/fields").json()
    assert {"key": "composite_score", "label": "Score de revalorización", "type": "num"} in fields


def test_model_report_and_diagnosis(seeded_client):
    r = seeded_client.get("/api/model")
    assert r.status_code == 200
    report = r.json()
    assert set(report["horizons"]) == {"20", "60", "120"}
    assert "NaN" not in r.text
    for stats in report["stage_stats"].values():
        for s in stats:
            assert 0 <= s["ci_low"] <= s["hit_rate"] <= s["ci_high"] <= 1

    d = seeded_client.get("/api/instruments/AAPL").json()
    diag = d["breakdown"]["diagnosis"]
    assert diag["stage"] in (1, 2, 3, 4)
    assert diag["summary"]
    items = seeded_client.get("/api/rankings").json()["items"]
    assert all("prob_up_60" in i and "stage" in i for i in items)


def test_screener_by_stage_and_probability(seeded_client):
    body = {
        "conditions": [{"field": "stage", "op": "in", "value": [1, 2, 3, 4]}],
        "sort_by": "prob_up_60",
        "sort_dir": "desc",
    }
    r = seeded_client.post("/api/screener/run", json=body)
    assert r.status_code == 200
    assert r.json()["count"] > 0
