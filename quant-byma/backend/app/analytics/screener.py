"""DSL de filtros personalizados del screener.

Un filtro es una conjunción (AND) de condiciones sobre las métricas planas de cada
snapshot, más un criterio de orden. Se valida con Pydantic y se persiste como JSON.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# campo → (etiqueta, tipo). Es la única lista de campos filtrables/ordenables.
FIELDS: dict[str, tuple[str, str]] = {
    "ticker": ("Ticker", "str"),
    "kind": ("Tipo", "str"),
    "sector": ("Sector", "str"),
    "composite_score": ("Score de revalorización", "num"),
    "technical_score": ("Score técnico", "num"),
    "fundamental_score": ("Score fundamental", "num"),
    "ccl_score": ("Score CCL", "num"),
    "price_ars": ("Precio ARS", "num"),
    "price_usd": ("Precio USD (CCL)", "num"),
    "change_1d_pct": ("Var. 1D % (USD)", "num"),
    "change_1m_pct": ("Var. 1M % (USD)", "num"),
    "rsi14": ("RSI 14", "num"),
    "macd_hist": ("MACD histograma", "num"),
    "bb_pct_b": ("Bollinger %B", "num"),
    "atr_pct": ("ATR % del precio", "num"),
    "dist_sma200_pct": ("Distancia a SMA200 %", "num"),
    "implied_ccl": ("CCL implícito", "num"),
    "ccl_dev_pct": ("Desvío CCL %", "num"),
    "pe": ("P/E", "num"),
    "ps": ("P/S", "num"),
    "pb": ("P/B", "num"),
    "ev_ebitda": ("EV/EBITDA", "num"),
    "roe": ("ROE", "num"),
    "roic": ("ROIC", "num"),
    "revenue_growth": ("Crecimiento revenue YoY", "num"),
    "fcf_yield": ("FCF Yield", "num"),
    "debt_to_equity": ("Deuda/Patrimonio", "num"),
    "current_ratio": ("Current ratio", "num"),
    "altman_z": ("Altman Z", "num"),
    "stage": ("Etapa (1 base · 2 alcista · 3 techo · 4 bajista)", "num"),
    "substate": ("Submomento", "str"),
    "bias": ("Sesgo del modelo", "str"),
    "bias_significant": ("Sesgo estadísticamente significativo", "bool"),
    "prob_up_20": ("Prob. de suba a 20 ruedas", "num"),
    "prob_up_60": ("Prob. de suba a 60 ruedas", "num"),
    "prob_up_120": ("Prob. de suba a 120 ruedas", "num"),
    "valuation_state": ("Valuación vs sector", "str"),
    "score_pct": ("Puntaje del modelo (percentil 0–100)", "num"),
    "prob_outperform_20": ("Prob. de superar al universo a 20 ruedas", "num"),
    "prob_outperform_60": ("Prob. de superar al universo a 60 ruedas", "num"),
    "prob_outperform_120": ("Prob. de superar al universo a 120 ruedas", "num"),
    "avg_volume_ars": ("Volumen promedio (ARS/día)", "num"),
    "news_score": ("Presión de noticias (Claude)", "num"),
    "news_label": ("Noticias: viento a favor / en contra", "str"),
    "events_favorable": ("Eventos macro vigentes favorables al sector", "num"),
    "events_unfavorable": ("Eventos macro vigentes desfavorables al sector", "num"),
    "ratio_source": ("Origen del ratio", "str"),
    "golden_cross": ("Golden cross reciente", "bool"),
    "breakout": ("Breakout", "bool"),
    "above_sma200": ("Sobre SMA200", "bool"),
}

Op = Literal["gt", "gte", "lt", "lte", "eq", "neq", "between", "in"]


class Condition(BaseModel):
    field: str
    op: Op
    value: Any

    @field_validator("field")
    @classmethod
    def known_field(cls, v: str) -> str:
        if v not in FIELDS:
            raise ValueError(f"Campo desconocido: {v}")
        return v

    @model_validator(mode="after")
    def check_value(self) -> Condition:
        ftype = FIELDS[self.field][1]
        if self.op == "between":
            if not (isinstance(self.value, list) and len(self.value) == 2):
                raise ValueError("'between' requiere [min, max]")
        elif self.op == "in":
            if not isinstance(self.value, list):
                raise ValueError("'in' requiere una lista")
        elif ftype == "num" and not isinstance(self.value, int | float):
            raise ValueError(f"{self.field} requiere un valor numérico")
        if ftype == "str" and self.op in ("gt", "gte", "lt", "lte", "between"):
            raise ValueError(f"Operador {self.op} no aplica a texto")
        return self


class FilterDefinition(BaseModel):
    conditions: list[Condition] = Field(default_factory=list)
    sort_by: str = "composite_score"
    sort_dir: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=100, ge=1, le=1000)

    @field_validator("sort_by")
    @classmethod
    def known_sort(cls, v: str) -> str:
        if v not in FIELDS:
            raise ValueError(f"Campo de orden desconocido: {v}")
        return v


def _match(row: dict, c: Condition) -> bool:
    x = row.get(c.field)
    if x is None:
        return False
    v = c.value
    if isinstance(x, str) and isinstance(v, str):
        x, v = x.lower(), v.lower()
    match c.op:
        case "gt":
            return x > v
        case "gte":
            return x >= v
        case "lt":
            return x < v
        case "lte":
            return x <= v
        case "eq":
            return x == v
        case "neq":
            return x != v
        case "between":
            return v[0] <= x <= v[1]
        case "in":
            values = [i.lower() if isinstance(i, str) else i for i in v]
            return (x.lower() if isinstance(x, str) else x) in values
    return False


def apply_filter(rows: list[dict], f: FilterDefinition) -> list[dict]:
    matched = [r for r in rows if all(_match(r, c) for c in f.conditions)]
    present = [r for r in matched if r.get(f.sort_by) is not None]
    missing = [r for r in matched if r.get(f.sort_by) is None]
    present.sort(key=lambda r: r[f.sort_by], reverse=f.sort_dir == "desc")
    return (present + missing)[: f.limit]
