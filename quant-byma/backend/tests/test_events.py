import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import numpy as np
import pandas as pd
import pytest

from app.analytics import events as ev
from app.db.models import NewsAnalysis, NewsItem
from app.db.session import session_factory
from app.ingestion.providers.news import YahooNewsSource, parse_search
from app.services.events import (
    classify_pending,
    compute_event_report,
    news_pressure,
    store_macro,
)
from app.services.news_ai import FALLBACK_BETA, Classified, Impact, NewsClassifier, sanitize

DATES = pd.bdate_range("2015-01-01", "2026-10-16")


def _flat(value: float) -> pd.Series:
    return pd.Series(value, index=DATES, dtype=float)


def _macro(rng: np.random.Generator) -> dict[str, pd.Series]:
    walk = lambda scale: pd.Series(  # noqa: E731
        np.exp(np.cumsum(rng.normal(0, scale, len(DATES)))), index=DATES
    )
    tnx = _flat(3.0)
    tnx.iloc[-15:] = np.linspace(3.05, 3.6, 15)  # +60 pb en las últimas ruedas
    return {
        "UST10Y": tnx,
        "UST3M": _flat(2.0),
        "VIX": _flat(15.0),
        "WTI": 70 * walk(0.02),
        "BRENT": 75 * walk(0.02),
        "GOLD": 1500 * walk(0.01),
        "DXY": 100 * walk(0.004),
        "SOY": 1000 * walk(0.015),
        "CORN": 400 * walk(0.015),
        "WHEAT": 600 * walk(0.015),
        "NATGAS": 3 * walk(0.03),
        "COPPER": 4 * walk(0.015),
    }


def test_detect_flags_rate_shock_as_active():
    macro = _macro(np.random.default_rng(0))
    state = {e["key"]: e for e in ev.detect(macro)}
    assert state["tasas_suba"]["state"] == "activo"
    assert state["tasas_suba"]["value_label"].endswith("pb")
    assert state["tasas_baja"]["state"] == "inactivo"
    assert state["estres"]["state"] == "inactivo"  # VIX 15 < 25


def test_onsets_decluster_consecutive_days():
    idx = pd.bdate_range("2020-01-01", periods=200)
    flags = pd.Series(False, index=idx)
    flags.iloc[10:15] = True  # un episodio
    flags.iloc[40:42] = True  # vuelve a dispararse dentro del cooldown: mismo episodio
    flags.iloc[150:151] = True  # episodio nuevo
    on = ev.onsets(flags, cooldown=60)
    assert list(on) == [idx[10], idx[150]]


def test_event_study_measures_sector_excess_after_events():
    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2010-01-01", "2024-12-31")
    oil = pd.Series(70.0, index=idx)
    # Shocks de +20% cada ~300 ruedas; tras cada uno, Energía le gana al resto.
    shocks = list(range(100, len(idx) - 100, 300))
    energy_boost = np.zeros(len(idx))
    for s in shocks:
        oil.iloc[s:] *= 1.2
        energy_boost[s : s + 60] = 0.002
    closes, sectors = {}, {}
    for k in range(4):
        r = rng.normal(0.0003, 0.01, len(idx))
        closes[f"E{k}"] = pd.Series(100 * np.exp(np.cumsum(r + energy_boost)), index=idx)
        sectors[f"E{k}"] = "Energía"
        closes[f"T{k}"] = pd.Series(100 * np.exp(np.cumsum(r)), index=idx)
        sectors[f"T{k}"] = "Tecnología"
    study = ev.event_study({"BRENT": oil}, closes, sectors)
    st = study["petroleo_shock"]
    assert st["n"] == len(shocks)
    energia = next(r for r in st["sectors"] if r["sector"] == "Energía")
    tech = next(r for r in st["sectors"] if r["sector"] == "Tecnología")
    assert energia["mean_excess"] > 0.03 > tech["mean_excess"]
    assert energia["hit_rate"] == 1.0 and energia["significant"]
    assert 0 <= energia["ci_low"] <= energia["hit_rate"] <= energia["ci_high"] <= 1


def test_sensitivity_recovers_known_beta():
    rng = np.random.default_rng(2)
    idx = pd.bdate_range("2021-01-01", "2026-10-16")
    oil = pd.Series(70 * np.exp(np.cumsum(rng.normal(0, 0.02, len(idx)))), index=idx)
    weekly = oil.resample("W-FRI").last()
    r_oil = weekly.pct_change().fillna(0)
    asset_w = 100 * np.cumprod(1 + 2.0 * r_oil + rng.normal(0, 0.005, len(r_oil)))
    asset = asset_w.reindex(idx, method="ffill").bfill()
    sens = ev.sensitivities({"WTI": oil}, {"XOM": asset})
    s = sens["XOM"]["WTI"]
    assert s["beta"] == pytest.approx(2.0, abs=0.15)
    assert s["impact"] == pytest.approx(0.2, abs=0.015)  # ante +10% de petróleo
    assert s["t"] > 10


def test_asset_exposure_uses_reaction_sign_for_negative_shock():
    active = [{"key": "tasas_baja", "name": "Baja", "state": "activo"}]
    sens = {"AAPL": {"UST10Y": {"impact": -0.03, "t": -3.0}}}
    out = ev.asset_exposure("AAPL", "Tecnología", active, {}, sens)
    assert out[0]["reaction"]["impact"] == pytest.approx(0.03)  # tasas bajan → sube
    assert out[0]["reaction"]["shock"].startswith("−25 pb")
    assert out[0]["tone"] == "favorable"


SEARCH_PAYLOAD = {
    "news": [
        {
            "uuid": "abc-1",
            "title": "Oil jumps as Middle East conflict escalates",
            "publisher": "Reuters",
            "link": "https://example.com/1",
            "providerPublishTime": 1792381315,
            "relatedTickers": ["XOM", "CVX"],
        },
        {"uuid": "bad", "title": "", "providerPublishTime": 1792381315},
    ]
}


def test_parse_search_and_source_with_mock_transport():
    items = parse_search(SEARCH_PAYLOAD, "petroleo")
    assert len(items) == 1 and items[0].related == ["XOM", "CVX"]
    assert items[0].published_at.year == 2026

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.params["q"] == "XOM"
        assert "Mozilla" in req.headers["user-agent"]
        return httpx.Response(200, json=SEARCH_PAYLOAD)

    src = YahooNewsSource(transport=httpx.MockTransport(handler))
    assert src.search("XOM")[0].title.startswith("Oil jumps")


class FakeMessages:
    def __init__(self, payload: dict | None, stop_reason: str = "end_turn") -> None:
        self.payload = payload
        self.stop_reason = stop_reason
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        lines = json.loads(kwargs["messages"][0]["content"].split("\n", 1)[1])
        items = self.payload(lines) if callable(self.payload) else self.payload
        content = (
            [SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text=json.dumps(items))]
            if items is not None
            else []
        )
        return SimpleNamespace(stop_reason=self.stop_reason, content=content, model="test-model")


def _client(messages: FakeMessages):
    return SimpleNamespace(beta=SimpleNamespace(messages=messages))


def _answer(lines: list[dict]) -> dict:
    out = []
    for line in lines:
        oil = "Oil" in line["titular"]
        out.append(
            {
                "id": line["id"],
                "relevant": oil,
                "event_type": "geopolitico" if oil else "otro",
                "scope": "sector" if oil else "empresa",
                "summary": "El petróleo sube por el conflicto.",
                "rationale": "Mayor precio del crudo mejora márgenes de petroleras.",
                "impacts": [
                    {
                        "target_type": "sector",
                        "target": "energía",
                        "direction": "positivo",
                        "magnitude": "alta",
                        "confidence": "alta",
                        "horizon": "semanas",
                    },
                    {
                        "target_type": "ticker",
                        "target": "ypfd",
                        "direction": "positivo",
                        "magnitude": "media",
                        "confidence": "media",
                        "horizon": "semanas",
                    },
                    {
                        "target_type": "ticker",
                        "target": "NOEXISTE",
                        "direction": "negativo",
                        "magnitude": "alta",
                        "confidence": "alta",
                        "horizon": "dias",
                    },
                ]
                if oil
                else [],
            }
        )
    return {"items": out}


def test_classifier_request_shape_and_validation():
    msgs = FakeMessages(_answer)
    clf = NewsClassifier("k", model="claude-opus-5-5", client=_client(msgs))
    res = clf.classify([(7, "Oil jumps on conflict", "Reuters", [])], "instr")
    call = msgs.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["fallbacks"] == "default" and call["betas"] == [FALLBACK_BETA]
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["thinking"] == {"type": "adaptive"}
    assert "tool_choice" not in call
    assert res.analyses[7].relevant and res.model == "test-model"


def test_classifier_refusal_and_invalid_json():
    refused = NewsClassifier("k", client=_client(FakeMessages(None, stop_reason="refusal")))
    assert refused.classify([(1, "x", "y", [])], "i").refused
    broken = NewsClassifier("k", client=_client(FakeMessages({"items": [{"id": 1}]})))
    assert broken.classify([(1, "x", "y", [])], "i").analyses == {}


def test_sanitize_drops_targets_outside_universe():
    c = Classified(
        id=1,
        relevant=True,
        event_type="inventado",
        scope="sector",
        summary="s",
        rationale="r",
        impacts=[
            Impact(
                target_type="ticker",
                target="ggal",
                direction="positivo",
                magnitude="baja",
                confidence="baja",
                horizon="dias",
            ),
            Impact(
                target_type="sector",
                target="Cripto",
                direction="positivo",
                magnitude="baja",
                confidence="baja",
                horizon="dias",
            ),
        ],
    )
    out = sanitize(c, {"GGAL"}, {"Financiero"})
    assert [i.target for i in out.impacts] == ["GGAL"]
    assert out.event_type == "otro"


def test_events_pipeline_and_api(seeded_client):
    now = datetime.now(UTC).replace(tzinfo=None)
    sector_energy = next(
        r["sector"]
        for r in seeded_client.get("/api/rankings").json()["items"]
        if r["ticker"] == "YPFD"
    )
    with session_factory()() as s:
        store_macro(s, _macro(np.random.default_rng(3)))
        report = compute_event_report(s)
        assert any(e["key"] == "tasas_suba" for e in report["events"])
        s.add_all(
            [
                NewsItem(
                    uid="t1",
                    title="Oil jumps as conflict escalates",
                    published_at=now - timedelta(hours=6),
                    source="yahoo",
                    related=["YPFD"],
                ),
                NewsItem(
                    uid="t2",
                    title="5 stocks to buy now",
                    published_at=now - timedelta(days=1),
                    source="yahoo",
                    related=[],
                ),
            ]
        )
        s.flush()
        msgs = FakeMessages(
            lambda lines: {
                "items": [
                    {
                        **it,
                        "impacts": [
                            {**i, "target": sector_energy} if i["target_type"] == "sector" else i
                            for i in it["impacts"]
                        ],
                    }
                    for it in _answer(lines)["items"]
                ]
            }
        )
        counts = classify_pending(s, NewsClassifier("k", client=_client(msgs)), 14)
        assert counts["classified"] == 2
        # Lo ya clasificado no se vuelve a enviar.
        assert classify_pending(s, NewsClassifier("k", client=_client(msgs)), 14)["classified"] == 0
        rows = s.query(NewsAnalysis).all()
        assert all(i["target"] != "NOEXISTE" for r in rows for i in r.impacts)
        by_ticker, by_sector = news_pressure(s, 14, now=now)
        assert by_ticker["YPFD"]["score"] > by_sector[sector_energy]["score"] * 0.5 > 0
        assert by_ticker["YPFD"]["label"] == "Viento a favor"
        s.commit()

    body = seeded_client.get("/api/events").json()
    assert body["status"]["news_enabled"] is True
    assert {"events", "study", "macro", "news", "sector_pressure"} <= set(body)
    assert len(body["news"]) >= 2
    r = seeded_client.get("/api/instruments/YPFD/events")
    assert r.status_code == 200 and "NaN" not in r.text
    detail = r.json()
    assert detail["pressure"]["label"] == "Viento a favor"
    assert any(n["analysis"] and n["analysis"]["relevant"] for n in detail["news"])
    items = seeded_client.get("/api/rankings").json()["items"]
    ypfd = next(i for i in items if i["ticker"] == "YPFD")
    assert ypfd["news_label"] == "Viento a favor"
    screened = seeded_client.post(
        "/api/screener/run",
        json={"conditions": [{"field": "news_score", "op": "gt", "value": 0}]},
    ).json()
    assert "YPFD" in {i["ticker"] for i in screened["items"]}
