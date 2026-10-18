from datetime import date

import pytest
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, FxRate
from app.db.session import make_engine
from app.ingestion.providers import build_provider
from app.ingestion.providers.base import ProviderError
from app.ingestion.providers.demo import DemoProvider
from app.ingestion.providers.real import RealDataProvider
from app.ingestion.universe import UNIVERSE_BY_TICKER
from app.services.ingestion import IngestionError, run_ingestion

END = date(2026, 10, 16)


class Offline:
    name = "real"

    def history(self, symbol, start, end):
        raise ProviderError("bloqueado por el proxy de red")

    def fundamentals(self, symbol):
        return []


def test_default_provider_is_real_not_demo():
    assert isinstance(build_provider("real"), RealDataProvider)
    with pytest.raises(ValueError):
        build_provider("auto")


def test_failed_ingestion_keeps_existing_data(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'x.db'}")
    Base.metadata.create_all(engine)
    universe = [UNIVERSE_BY_TICKER[t] for t in ("AAPL", "GGAL")]
    with sessionmaker(bind=engine)() as s:
        run_ingestion(s, DemoProvider(universe, end=END), end=END, universe=universe)
        before = s.query(FxRate).count()
        with pytest.raises(IngestionError):
            run_ingestion(s, Offline(), end=END, universe=universe)
        assert s.query(FxRate).count() == before > 0
