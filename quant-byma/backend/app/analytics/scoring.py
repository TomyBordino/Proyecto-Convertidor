"""Motor de scoring: Composite Score de revalorización (0–100).

Cada sub-score se arma con componentes de puntaje máximo fijo. Un componente cuyo dato
falta (None) se excluye y el resto se re-escala, de modo que un banco sin Altman Z o una
acción local sin par externo no queda penalizada por falta de información.

    composite = Σ w_g · subscore_g / Σ w_g     (sobre los grupos g disponibles)

Pesos por defecto: técnico 40%, fundamental 35%, descalce de CCL 25%.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from statistics import median

from app.analytics.patterns import CrossEvent


def linear(x: float, x0: float, x1: float) -> float:
    """Mapea x linealmente a [0, 1]: x0 → 0, x1 → 1 (admite x1 < x0 para escalas inversas)."""
    if x1 == x0:
        raise ValueError("x0 y x1 deben ser distintos")
    return max(0.0, min(1.0, (x - x0) / (x1 - x0)))


@dataclass
class Component:
    key: str
    label: str
    max_points: float
    fraction: float | None  # 0..1, None = sin datos
    value: float | None = None
    note: str = ""

    @property
    def points(self) -> float | None:
        return None if self.fraction is None else round(self.fraction * self.max_points, 2)


@dataclass
class SubScore:
    group: str
    components: list[Component]

    @property
    def score(self) -> float | None:
        avail = [(c.fraction, c.max_points) for c in self.components if c.fraction is not None]
        total_max = sum(m for _, m in avail)
        if not avail or total_max == 0:
            return None
        return round(100.0 * sum(f * m for f, m in avail) / total_max, 2)

    def to_dict(self) -> dict:
        return {
            "group": self.group,
            "score": self.score,
            "components": [{**asdict(c), "points": c.points} for c in self.components],
        }


# ---------------------------------------------------------------- Técnico


@dataclass
class TechnicalInputs:
    close: float
    sma50: float | None
    sma200: float | None
    sma50_slope: float | None  # variación relativa de la SMA50 en 20 ruedas
    rsi: float | None
    macd_hist: float | None
    macd_hist_prev: float | None
    pct_b: float | None
    cross: CrossEvent | None = None
    breakout: bool = False
    divergence: str | None = None


def rsi_fraction(rsi: float, uptrend: bool) -> float:
    """Zona óptima 40–60 (pullback sano); sobrecompra/sobreventa extremas puntúan 0."""
    if 40 <= rsi <= 60:
        base = 1.0 - abs(rsi - 50) / 25.0  # 1.0 en 50, 0.6 en los bordes
    elif 30 <= rsi < 40 or 60 < rsi <= 70:
        base = 0.32
    else:
        base = 0.0
    return base if uptrend else base * 0.5


def technical_subscore(t: TechnicalInputs) -> SubScore:
    trend_parts: list[float] = []
    if t.sma200 is not None:
        trend_parts.append(1.0 if t.close > t.sma200 else 0.0)
    if t.sma50 is not None and t.sma200 is not None:
        trend_parts.append(1.0 if t.sma50 > t.sma200 else 0.0)
    if t.sma50_slope is not None:
        trend_parts.append(linear(t.sma50_slope, -0.02, 0.04))
    uptrend = bool((t.sma200 is not None and t.close > t.sma200) or (t.sma50_slope or 0) > 0)

    macd_frac = None
    if t.macd_hist is not None:
        macd_frac = 0.5 * (t.macd_hist > 0)
        if t.macd_hist_prev is not None:
            macd_frac += 0.5 * (t.macd_hist > t.macd_hist_prev)

    bb_frac = None
    if t.pct_b is not None:
        if 0.2 <= t.pct_b <= 0.8:
            bb_frac = 1.0
        elif t.pct_b < 0.2:
            bb_frac = 0.6  # cerca de la banda inferior: posible reversión a la media
        elif t.pct_b <= 1.0:
            bb_frac = 0.4
        else:
            bb_frac = 0.0  # por encima de la banda superior: sobreextendido

    ev_points, notes = 5.0, []
    if t.cross is not None:
        if t.cross.kind == "golden":
            ev_points += 6
            notes.append(f"Golden cross hace {t.cross.bars_ago} ruedas")
        else:
            ev_points -= 5
            notes.append(f"Death cross hace {t.cross.bars_ago} ruedas")
    if t.breakout:
        ev_points += 4
        notes.append("Breakout de máximos de 55 ruedas con volumen")
    if t.divergence == "bullish":
        ev_points += 4
        notes.append("Divergencia alcista de RSI")
    elif t.divergence == "bearish":
        ev_points -= 4
        notes.append("Divergencia bajista de RSI")

    return SubScore(
        "technical",
        [
            Component(
                "trend",
                "Tendencia (SMA 50/200)",
                30,
                sum(trend_parts) / len(trend_parts) if trend_parts else None,
                t.sma50_slope,
                "Precio vs SMA200, SMA50 vs SMA200 y pendiente de SMA50",
            ),
            Component(
                "rsi",
                "RSI 14 en zona 40–60",
                25,
                None if t.rsi is None else rsi_fraction(t.rsi, uptrend),
                t.rsi,
                "con tendencia alcista previa" if uptrend else "sin tendencia alcista (×0.5)",
            ),
            Component(
                "macd", "MACD histograma", 20, macd_frac, t.macd_hist, "Positivo y creciente"
            ),
            Component("bollinger", "Bollinger %B", 10, bb_frac, t.pct_b, "Sin sobreextensión"),
            Component(
                "events",
                "Patrones (cruces, breakouts, divergencias)",
                15,
                max(0.0, min(1.0, ev_points / 15.0)),
                None,
                "; ".join(notes) or "Sin eventos",
            ),
        ],
    )


# ------------------------------------------------------------ Fundamental

VALUATION_KEYS = ("pe", "ev_ebitda", "ps")


def discount(current: float | None, reference: float | None) -> float | None:
    """Descuento relativo de un múltiplo vs referencia (positivo = más barato)."""
    if current is None or reference is None or current <= 0 or reference <= 0:
        return None
    return 1.0 - current / reference


def _avg_discount_fraction(current: dict, reference: dict) -> tuple[float | None, float | None]:
    raw = [discount(current.get(k), reference.get(k)) for k in VALUATION_KEYS]
    ds = [d for d in raw if d is not None]
    if not ds:
        return None, None
    avg = sum(ds) / len(ds)
    return linear(avg, -0.30, 0.30), avg


def fundamental_subscore(
    ratios: dict, history_median: dict, sector_median: dict, is_financial: bool = False
) -> SubScore:
    hist_frac, hist_disc = _avg_discount_fraction(ratios, history_median)
    sect_frac, sect_disc = _avg_discount_fraction(ratios, sector_median)

    def frac(key: str, x0: float, x1: float) -> float | None:
        v = ratios.get(key)
        return None if v is None else linear(v, x0, x1)

    # En bancos/aseguradoras el apalancamiento es el negocio: Altman Z y D/E no aplican.
    altman = None if is_financial else frac("altman_z", 1.81, 2.99)
    de = None if is_financial else frac("debt_to_equity", 2.0, 0.3)

    return SubScore(
        "fundamental",
        [
            Component(
                "hist_discount",
                "Descuento vs histórico propio",
                30,
                hist_frac,
                hist_disc,
                "P/E, EV/EBITDA y P/S vs mediana de sus últimos ejercicios",
            ),
            Component(
                "sector_discount",
                "Descuento vs sector",
                20,
                sect_frac,
                sect_disc,
                "Mismos múltiplos vs mediana del sector",
            ),
            Component("roe", "ROE", 10, frac("roe", 0.0, 0.25), ratios.get("roe")),
            Component("roic", "ROIC", 10, frac("roic", 0.0, 0.20), ratios.get("roic")),
            Component(
                "growth",
                "Crecimiento de revenue YoY",
                10,
                frac("revenue_growth", -0.05, 0.25),
                ratios.get("revenue_growth"),
            ),
            Component(
                "fcf_yield",
                "Free Cash Flow Yield",
                10,
                frac("fcf_yield", 0.0, 0.08),
                ratios.get("fcf_yield"),
            ),
            Component(
                "altman_z",
                "Altman Z-Score",
                5,
                altman,
                ratios.get("altman_z"),
                "No aplica a financieras" if is_financial else "1.81 → 0, 2.99 → máx",
            ),
            Component(
                "leverage",
                "Deuda / Patrimonio",
                5,
                de,
                ratios.get("debt_to_equity"),
                "No aplica a financieras" if is_financial else "2.0 → 0, 0.3 → máx",
            ),
        ],
    )


def median_of(dicts: list[dict], keys: tuple[str, ...] = VALUATION_KEYS) -> dict:
    out = {}
    for k in keys:
        vals = [d[k] for d in dicts if d.get(k) is not None and d[k] > 0]
        out[k] = median(vals) if vals else None
    return out


# -------------------------------------------------------------------- CCL

CCL_FULL_SCALE = 0.05  # ±5% de desvío satura el puntaje


def ccl_subscore(deviation: float | None, ratio_suspect: bool = False) -> SubScore:
    """Un CEDEAR que cotiza a un CCL implícito por debajo del de mercado es una compra de
    dólares "barata": el desvío negativo suma puntos (convergencia esperada a la media)."""
    frac = None
    note = "CCL implícito vs mediana de mercado"
    if deviation is not None and not ratio_suspect:
        frac = linear(deviation, CCL_FULL_SCALE, -CCL_FULL_SCALE)
    elif ratio_suspect:
        note = "Excluido: desvío >35%, posible ratio de conversión desactualizado"
    return SubScore(
        "ccl", [Component("ccl_dev", "Descalce de CCL implícito", 100, frac, deviation, note)]
    )


# ------------------------------------------------------------- Composite


@dataclass
class ScoringWeights:
    technical: float = 0.40
    fundamental: float = 0.35
    ccl: float = 0.25

    def as_dict(self) -> dict[str, float]:
        return {"technical": self.technical, "fundamental": self.fundamental, "ccl": self.ccl}


@dataclass
class CompositeResult:
    composite: float
    subscores: dict[str, float | None]
    weights_used: dict[str, float]
    breakdown: list[dict] = field(default_factory=list)


def composite_score(subs: list[SubScore], weights: ScoringWeights | None = None) -> CompositeResult:
    w = (weights or ScoringWeights()).as_dict()
    avail = {s.group: s.score for s in subs if s.score is not None and w.get(s.group, 0) > 0}
    total_w = sum(w[g] for g in avail)
    composite = sum(w[g] * v for g, v in avail.items()) / total_w if total_w else 0.0  # type: ignore[misc]
    return CompositeResult(
        composite=round(composite, 2),
        subscores={s.group: s.score for s in subs},
        weights_used={g: round(w[g] / total_w, 4) for g in avail} if total_w else {},
        breakdown=[s.to_dict() for s in subs],
    )
