from app.config import Settings, get_settings
from app.ingestion.providers.base import MarketDataProvider, ProviderError
from app.ingestion.providers.demo import DemoProvider
from app.ingestion.providers.real import RealDataProvider
from app.ingestion.providers.yahoo import YahooProvider


def build_provider(kind: str, settings: Settings | None = None) -> MarketDataProvider:
    """real (default) | yahoo | demo. No hay fallback implícito a datos sintéticos."""
    if kind == "demo":
        return DemoProvider()
    if kind == "yahoo":
        return YahooProvider()
    if kind == "real":
        return RealDataProvider.from_settings(settings or get_settings())
    raise ValueError(f"Proveedor desconocido: {kind}")


__all__ = [
    "DemoProvider",
    "MarketDataProvider",
    "ProviderError",
    "RealDataProvider",
    "YahooProvider",
    "build_provider",
]
