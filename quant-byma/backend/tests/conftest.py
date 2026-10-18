import os
import tempfile
from datetime import date
from pathlib import Path

# La app lee QB_DATABASE_URL en su lifespan: apuntamos a una DB temporal antes de importarla.
_DB = Path(tempfile.mkdtemp()) / "test.db"
os.environ["QB_DATABASE_URL"] = f"sqlite:///{_DB}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db.session import init_engine, session_factory  # noqa: E402
from app.ingestion.providers.demo import DemoProvider  # noqa: E402
from app.ingestion.universe import UNIVERSE_BY_TICKER  # noqa: E402
from app.main import app  # noqa: E402
from app.services.ingestion import run_ingestion  # noqa: E402

get_settings.cache_clear()

END = date(2026, 10, 16)
TICKERS = ["AAPL", "MSFT", "KO", "MELI", "GGAL", "YPFD", "BMA", "TXAR", "SPY"]


@pytest.fixture(scope="session")
def seeded_client():
    init_engine()
    universe = [UNIVERSE_BY_TICKER[t] for t in TICKERS]
    with session_factory()() as s:
        run_ingestion(
            s, DemoProvider(universe, end=END), end=END, history_days=2200, universe=universe
        )
    with TestClient(app) as client:
        yield client
