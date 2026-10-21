"""Titulares de noticias (Yahoo Finance search) por activo y por tema macro."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

from app.ingestion.providers.http import HttpClient

SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"

# Búsquedas temáticas: cubren eventos que no se nombran por ticker.
MACRO_QUERIES: dict[str, str] = {
    "tasas": "Federal Reserve interest rates",
    "inflacion": "inflation CPI report",
    "geopolitica": "war conflict sanctions markets",
    "petroleo": "oil prices OPEC supply",
    "clima": "hurricane drought crops weather",
    "comercio": "tariffs trade war",
    "china": "China economy stimulus",
    "argentina": "Argentina economy markets",
    "regulacion": "antitrust regulation ruling",
}


@dataclass
class Headline:
    uid: str
    title: str
    publisher: str
    link: str
    published_at: datetime
    query: str
    related: list[str] = field(default_factory=list)


def _uid(raw: dict) -> str:
    base = raw.get("uuid") or raw.get("link") or raw.get("title", "")
    return hashlib.sha1(str(base).encode()).hexdigest()[:40]


def parse_search(payload: dict, query: str) -> list[Headline]:
    out = []
    for raw in payload.get("news") or []:
        title = (raw.get("title") or "").strip()
        ts = raw.get("providerPublishTime")
        if not title or not isinstance(ts, int | float):
            continue
        out.append(
            Headline(
                uid=_uid(raw),
                title=title[:512],
                publisher=(raw.get("publisher") or "")[:128],
                link=(raw.get("link") or "")[:1024],
                published_at=datetime.fromtimestamp(ts, UTC).replace(tzinfo=None),
                query=query[:64],
                related=[str(t) for t in raw.get("relatedTickers") or []][:20],
            )
        )
    return out


class YahooNewsSource:
    name = "yahoo_news"

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        # El buscador de Yahoo rechaza user agents que no sean de navegador.
        self.http = HttpClient(
            user_agent="Mozilla/5.0 (compatible; QuantBYMA/0.1)",
            retries=1,
            min_interval={"query2.finance.yahoo.com": 0.3},
            transport=transport,
        )

    def search(self, query: str, count: int = 8) -> list[Headline]:
        resp = self.http.request(
            "GET", SEARCH_URL, params={"q": query, "newsCount": count, "quotesCount": 0}
        )
        return parse_search(resp.json(), query)
