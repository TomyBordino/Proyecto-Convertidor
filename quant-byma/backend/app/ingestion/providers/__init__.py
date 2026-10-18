from app.ingestion.providers.base import MarketDataProvider, ProviderError
from app.ingestion.providers.demo import DemoProvider
from app.ingestion.providers.yahoo import YahooProvider


def build_provider(kind: str) -> MarketDataProvider:
    """auto: usa Yahoo si responde; si no (sin red, rate limit) cae al proveedor demo."""
    if kind == "demo":
        return DemoProvider()
    yahoo = YahooProvider()
    if kind == "yahoo":
        return yahoo
    return yahoo if yahoo.is_available() else DemoProvider()


__all__ = ["DemoProvider", "MarketDataProvider", "ProviderError", "YahooProvider", "build_provider"]
