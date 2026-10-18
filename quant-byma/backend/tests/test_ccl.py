import pandas as pd
import pytest

from app.ingestion.ccl import (
    ccl_deviation,
    implied_ccl,
    implied_ccl_series,
    is_ratio_suspect,
    mad_filter,
    market_ccl,
    market_ccl_series,
    weighted_median,
)


def test_implied_ccl_cedear_example():
    # 20 CEDEARs de AAPL a $15.000 = 1 acción de USD 230 → CCL = 15000*20/230
    assert implied_ccl(15_000, 230, 20) == pytest.approx(1304.3478, rel=1e-6)


def test_implied_ccl_adr_example():
    # 1 ADR GGAL = 10 acciones locales: local $6.500, ADR USD 50 → 1300
    assert implied_ccl(6_500, 50, 10) == pytest.approx(1300)


@pytest.mark.parametrize("args", [(0, 230, 20), (15000, 0, 20), (15000, 230, 0), (-1, 1, 1)])
def test_implied_ccl_invalid_inputs(args):
    assert implied_ccl(*args) is None


def test_implied_series_aligns_dates():
    ba = pd.Series(
        [1300.0, 1310.0, 1320.0], index=pd.to_datetime(["2024-07-03", "2024-07-04", "2024-07-05"])
    )
    us = pd.Series(
        [10.0, 10.0], index=pd.to_datetime(["2024-07-03", "2024-07-05"])
    )  # 4/7 feriado EE.UU.
    s = implied_ccl_series(ba, us, 10)
    assert list(s.index.strftime("%m-%d")) == ["07-03", "07-05"]
    assert s.tolist() == [1300.0, 1320.0]


def test_weighted_median():
    assert weighted_median([1, 2, 3]) == 2
    assert weighted_median([1, 2, 3, 4]) == 2.5
    assert weighted_median([1, 2, 3], [1, 1, 10]) == 3
    with pytest.raises(ValueError):
        weighted_median([])


def test_mad_filter_removes_ratio_mismatch():
    values = [1300, 1305, 1298, 1310, 1302, 2604]  # el último tiene el ratio duplicado
    assert mad_filter(values).tolist() == [True] * 5 + [False]


def test_market_ccl_is_robust_to_outliers_and_volume_weighted():
    res = market_ccl([1300, 1305, 1298, 1310, 2600], [1, 1, 1, 1, 100])
    assert res.n_discarded == 1
    assert 1298 <= res.value <= 1310


def test_deviation_sign_and_ratio_suspect():
    assert ccl_deviation(1274, 1300) == pytest.approx(-0.02)
    assert ccl_deviation(1326, 1300) == pytest.approx(0.02)
    assert not is_ratio_suspect(1326, 1300)
    assert is_ratio_suspect(2600, 1300)


def test_market_ccl_series():
    idx = pd.to_datetime(["2024-01-02", "2024-01-03"])
    implied = {
        "A": pd.Series([1000.0, 1010.0], index=idx),
        "B": pd.Series([1002.0, 1012.0], index=idx),
        "C": pd.Series([1004.0, None], index=idx),
    }
    s = market_ccl_series(implied)
    assert s.loc["2024-01-02", "value"] == 1002.0
    assert s.loc["2024-01-03", "value"] == 1011.0
    assert s.loc["2024-01-03", "n_samples"] == 2
