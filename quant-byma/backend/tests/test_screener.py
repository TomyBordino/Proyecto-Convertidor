import pytest
from pydantic import ValidationError

from app.analytics.screener import Condition, FilterDefinition, apply_filter

ROWS = [
    {
        "ticker": "AAPL",
        "kind": "CEDEAR",
        "sector": "Tecnología",
        "composite_score": 70,
        "rsi14": 55,
        "pe": 25,
    },
    {
        "ticker": "GGAL",
        "kind": "LOCAL",
        "sector": "Financiero",
        "composite_score": 80,
        "rsi14": 45,
        "pe": None,
    },
    {
        "ticker": "KO",
        "kind": "CEDEAR",
        "sector": "Consumo básico",
        "composite_score": 40,
        "rsi14": 72,
        "pe": 22,
    },
]


def test_and_conditions_and_sort():
    f = FilterDefinition(
        conditions=[
            Condition(field="kind", op="eq", value="cedear"),
            Condition(field="rsi14", op="between", value=[40, 60]),
        ]
    )
    assert [r["ticker"] for r in apply_filter(ROWS, f)] == ["AAPL"]
    f2 = FilterDefinition(sort_by="pe", sort_dir="asc")
    assert [r["ticker"] for r in apply_filter(ROWS, f2)] == ["KO", "AAPL", "GGAL"]  # None al final


def test_in_operator_and_missing_values():
    f = FilterDefinition(conditions=[Condition(field="ticker", op="in", value=["ggal", "KO"])])
    assert {r["ticker"] for r in apply_filter(ROWS, f)} == {"GGAL", "KO"}
    f = FilterDefinition(conditions=[Condition(field="pe", op="lt", value=100)])
    assert "GGAL" not in [r["ticker"] for r in apply_filter(ROWS, f)]


@pytest.mark.parametrize(
    "bad",
    [
        {"field": "nope", "op": "gt", "value": 1},
        {"field": "rsi14", "op": "between", "value": 5},
        {"field": "rsi14", "op": "gt", "value": "alto"},
        {"field": "sector", "op": "gt", "value": "A"},
    ],
)
def test_validation(bad):
    with pytest.raises(ValidationError):
        Condition(**bad)
