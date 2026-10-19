"""Eventos macro medidos con series de mercado.

Capa de contexto, separada del modelo probabilístico: no modifica las probabilidades
validadas. Tiene tres piezas:
- detección: reglas sobre series reales (tasas, petróleo, VIX, dólar, granos, metales);
- estudio de eventos: qué hizo cada sector, contra el universo, en las 60 ruedas que
  siguieron a cada ocurrencia histórica de la regla (n, media, % de veces e IC95);
- sensibilidades: beta semanal de cada activo frente a cada factor en los últimos 3 años.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.analytics.model import wilson_interval

EVENT_HORIZON = 60  # ruedas
# Ruedas sin que la regla se cumpla para contar una ocurrencia nueva (evita contar el
# mismo episodio varias veces y deja las ventanas de 60 ruedas casi sin solapamiento).
COOLDOWN = 60
RECENT_DAYS = 20
MIN_SECTOR_MEMBERS = 3
MIN_EVENT_SAMPLES = 5  # ocurrencias mínimas para reportar un sector
SENS_WEEKS = 156
MIN_SENS_WEEKS = 80


@dataclass(frozen=True)
class EventRule:
    key: str
    name: str
    category: str
    description: str
    series: tuple[str, ...]
    measure: str  # "change" (diferencia), "return" (variación %), "level"
    window: int
    threshold: float
    direction: int  # +1: dispara si medida >= umbral; -1: si <= umbral
    factor: str | None  # factor de sensibilidad asociado
    shock_sign: int = 1  # signo del shock sobre el factor


RULES: tuple[EventRule, ...] = (
    EventRule(
        "tasas_suba",
        "Suba de tasas largas en EE. UU.",
        "Tasas",
        "El rendimiento del Tesoro a 10 años subió 40 pb o más en 20 ruedas.",
        ("UST10Y",),
        "change",
        20,
        0.40,
        1,
        "UST10Y",
        1,
    ),
    EventRule(
        "tasas_baja",
        "Baja de tasas largas en EE. UU.",
        "Tasas",
        "El rendimiento del Tesoro a 10 años cayó 40 pb o más en 20 ruedas.",
        ("UST10Y",),
        "change",
        20,
        -0.40,
        -1,
        "UST10Y",
        -1,
    ),
    EventRule(
        "fed_suba",
        "Ciclo de suba de tasas cortas (Fed)",
        "Tasas",
        "La tasa a 3 meses subió 50 pb o más en 60 ruedas (anticipa o refleja subas de la Fed).",
        ("UST3M",),
        "change",
        60,
        0.50,
        1,
        "UST10Y",
        1,
    ),
    EventRule(
        "fed_baja",
        "Ciclo de recorte de tasas cortas (Fed)",
        "Tasas",
        "La tasa a 3 meses cayó 50 pb o más en 60 ruedas.",
        ("UST3M",),
        "change",
        60,
        -0.50,
        -1,
        "UST10Y",
        -1,
    ),
    EventRule(
        "petroleo_shock",
        "Shock alcista del petróleo",
        "Energía / geopolítica",
        "El Brent subió 15% o más en 20 ruedas (típico de conflictos o recortes de oferta).",
        ("BRENT",),
        "return",
        20,
        0.15,
        1,
        "WTI",
        1,
    ),
    EventRule(
        "petroleo_caida",
        "Derrumbe del petróleo",
        "Energía / geopolítica",
        "El Brent cayó 15% o más en 20 ruedas.",
        ("BRENT",),
        "return",
        20,
        -0.15,
        -1,
        "WTI",
        -1,
    ),
    EventRule(
        "estres",
        "Estrés de mercado (VIX alto)",
        "Riesgo",
        "El VIX cerró en 25 o más: el mercado descuenta volatilidad elevada.",
        ("VIX",),
        "level",
        1,
        25.0,
        1,
        "VIX",
        1,
    ),
    EventRule(
        "refugio_oro",
        "Búsqueda de refugio (oro)",
        "Riesgo",
        "El oro subió 7% o más en 20 ruedas (suele acompañar tensiones geopolíticas).",
        ("GOLD",),
        "return",
        20,
        0.07,
        1,
        "GOLD",
        1,
    ),
    EventRule(
        "dolar_fuerte",
        "Dólar global fuerte",
        "Monedas",
        "El índice dólar (DXY) subió 3% o más en 20 ruedas.",
        ("DXY",),
        "return",
        20,
        0.03,
        1,
        "DXY",
        1,
    ),
    EventRule(
        "dolar_debil",
        "Dólar global débil",
        "Monedas",
        "El índice dólar (DXY) cayó 3% o más en 20 ruedas.",
        ("DXY",),
        "return",
        20,
        -0.03,
        -1,
        "DXY",
        -1,
    ),
    EventRule(
        "granos_suba",
        "Suba fuerte de granos",
        "Clima / agro",
        "Soja, maíz y trigo subieron en promedio 10% o más en 20 ruedas "
        "(sequías, inundaciones u otros shocks de oferta).",
        ("SOY", "CORN", "WHEAT"),
        "return",
        20,
        0.10,
        1,
        "AGRO",
        1,
    ),
    EventRule(
        "granos_baja",
        "Caída fuerte de granos",
        "Clima / agro",
        "Soja, maíz y trigo cayeron en promedio 10% o más en 20 ruedas.",
        ("SOY", "CORN", "WHEAT"),
        "return",
        20,
        -0.10,
        -1,
        "AGRO",
        -1,
    ),
    EventRule(
        "gas_shock",
        "Shock del gas natural",
        "Clima / agro",
        "El gas natural subió 25% o más en 20 ruedas (olas de frío o calor, cortes de oferta).",
        ("NATGAS",),
        "return",
        20,
        0.25,
        1,
        None,
        1,
    ),
    EventRule(
        "cobre_suba",
        "Suba fuerte del cobre",
        "Metales",
        "El cobre subió 10% o más en 20 ruedas (demanda industrial, China).",
        ("COPPER",),
        "return",
        20,
        0.10,
        1,
        "COPPER",
        1,
    ),
)

# factor → (series, medida semanal, tamaño del shock de referencia, etiqueta)
FACTORS: dict[str, tuple[tuple[str, ...], str, float, str]] = {
    "UST10Y": (("UST10Y",), "change", 0.25, "+25 pb en la tasa a 10 años"),
    "WTI": (("WTI",), "return", 0.10, "+10% en el petróleo"),
    "VIX": (("VIX",), "change", 5.0, "+5 puntos de VIX"),
    "DXY": (("DXY",), "return", 0.02, "+2% en el índice dólar"),
    "GOLD": (("GOLD",), "return", 0.05, "+5% en el oro"),
    "AGRO": (("SOY", "CORN", "WHEAT"), "return", 0.05, "+5% en granos"),
    "COPPER": (("COPPER",), "return", 0.05, "+5% en el cobre"),
}


def _measure(macro: dict[str, pd.Series], series: tuple[str, ...], measure: str, window: int):
    parts = []
    for key in series:
        s = macro.get(key)
        if s is None or s.empty:
            return None
        s = s.sort_index()
        if measure == "change":
            parts.append(s - s.shift(window))
        elif measure == "return":
            parts.append(s / s.shift(window) - 1)
        else:
            parts.append(s)
    return pd.concat(parts, axis=1, sort=True).mean(axis=1, skipna=False).dropna()


def rule_stat(rule: EventRule, macro: dict[str, pd.Series]) -> pd.Series | None:
    return _measure(macro, rule.series, rule.measure, rule.window)


def fired(rule: EventRule, stat: pd.Series) -> pd.Series:
    return stat >= rule.threshold if rule.direction > 0 else stat <= rule.threshold


def onsets(flags: pd.Series, cooldown: int = COOLDOWN) -> pd.DatetimeIndex:
    """Primer día de cada episodio: la regla se cumple y no se cumplió en las
    `cooldown` ruedas previas."""
    f = flags.astype(bool)
    prev = f.shift(1, fill_value=False).astype(int).rolling(cooldown, min_periods=1).max()
    return pd.DatetimeIndex(f.index[f & (prev == 0)])


def _fmt_stat(rule: EventRule, v: float) -> str:
    if rule.measure == "return":
        return f"{v:+.1%}"
    if rule.measure == "change":
        return f"{v * 100:+.0f} pb" if rule.series[0].startswith("UST") else f"{v:+.2f}"
    return f"{v:.1f}"


def detect(macro: dict[str, pd.Series]) -> list[dict]:
    """Estado actual de cada regla."""
    out = []
    for rule in RULES:
        stat = rule_stat(rule, macro)
        if stat is None or stat.empty:
            continue
        flags = fired(rule, stat)
        last = float(stat.iloc[-1])
        recent = flags.iloc[-RECENT_DAYS:]
        if bool(flags.iloc[-1]):
            state = "activo"
        elif bool(recent.any()):
            state = "reciente"
        else:
            state = "inactivo"
        since = None
        if state != "inactivo":
            on = onsets(flags)
            since = str(on[-1].date()) if len(on) else None
        out.append(
            {
                "key": rule.key,
                "name": rule.name,
                "category": rule.category,
                "description": rule.description,
                "state": state,
                "since": since,
                "as_of": str(stat.index[-1].date()),
                "value": round(last, 4),
                "value_label": _fmt_stat(rule, last),
                "threshold_label": _fmt_stat(rule, rule.threshold),
                "occurrences": int(len(onsets(flags))),
                "factor": rule.factor,
            }
        )
    return out


def price_panel(closes: dict[str, pd.Series]) -> pd.DataFrame:
    if not closes:
        return pd.DataFrame()
    px = pd.DataFrame({t: s[~s.index.duplicated()] for t, s in closes.items()}).sort_index()
    return px.ffill(limit=5)


def event_study(
    macro: dict[str, pd.Series],
    closes: dict[str, pd.Series],
    sectors: dict[str, str],
    horizon: int = EVENT_HORIZON,
) -> dict[str, dict]:
    """Retorno de cada sector contra el universo en las `horizon` ruedas posteriores a cada
    ocurrencia histórica de cada regla. Descriptivo: muestras chicas, sin ajuste por
    comparaciones múltiples, por eso se reporta n e intervalo de confianza."""
    px = price_panel(closes)
    if px.empty:
        return {}
    fwd = px.shift(-horizon) / px - 1
    universe_fwd = fwd.median(axis=1)
    base_up = float((universe_fwd.dropna() > 0).mean()) if universe_fwd.notna().any() else None
    by_sector: dict[str, list[str]] = {}
    for t in px.columns:
        by_sector.setdefault(sectors.get(t) or "Sin clasificar", []).append(t)
    sector_fwd = pd.DataFrame(
        {
            s: fwd[m].median(axis=1).where(fwd[m].notna().sum(axis=1) >= MIN_SECTOR_MEMBERS)
            for s, m in by_sector.items()
        }
    )
    out: dict[str, dict] = {}
    for rule in RULES:
        stat = rule_stat(rule, macro)
        if stat is None or stat.empty:
            continue
        dates = []
        for d in onsets(fired(rule, stat)):
            pos = px.index.searchsorted(d, side="left")
            if pos < len(px.index) and pd.notna(universe_fwd.iloc[pos]):
                dates.append(px.index[pos])
        if not dates:
            out[rule.key] = {"n": 0, "dates": [], "universe": None, "sectors": []}
            continue
        u = universe_fwd.loc[dates]
        uni_hit = float((u > 0).mean())
        lo, hi = wilson_interval(uni_hit, len(u))
        rows = []
        for sector in sector_fwd.columns:
            ex = (sector_fwd.loc[dates, sector] - u).dropna()
            if sector == "Sin clasificar" or len(ex) < MIN_EVENT_SAMPLES:
                continue
            hit = float((ex > 0).mean())
            clo, chi = wilson_interval(hit, len(ex))
            rows.append(
                {
                    "sector": sector,
                    "n": int(len(ex)),
                    "mean_excess": round(float(ex.mean()), 4),
                    "median_excess": round(float(ex.median()), 4),
                    "hit_rate": round(hit, 4),
                    "ci_low": round(clo, 4),
                    "ci_high": round(chi, 4),
                    # Se destaca solo si el IC95 de "le fue mejor que al universo" excluye 50%.
                    "significant": bool(clo > 0.5 or chi < 0.5),
                }
            )
        rows.sort(key=lambda r: r["mean_excess"], reverse=True)
        out[rule.key] = {
            "n": len(dates),
            "dates": [str(d.date()) for d in dates],
            "universe": {
                "mean_return": round(float(u.mean()), 4),
                "hit_rate": round(uni_hit, 4),
                "ci_low": round(lo, 4),
                "ci_high": round(hi, 4),
                "base_rate": round(base_up, 4) if base_up is not None else None,
            },
            "sectors": rows,
        }
    return out


def _weekly_factor(macro: dict[str, pd.Series], factor: str) -> pd.Series | None:
    series, measure, _, _ = FACTORS[factor]
    weekly = {}
    for k in series:
        s = macro.get(k)
        if s is None or s.empty:
            return None
        weekly[k] = s.sort_index().resample("W-FRI").last()
    df = pd.DataFrame(weekly)
    moves = df.diff() if measure == "change" else df.pct_change(fill_method=None)
    return moves.mean(axis=1, skipna=False)


def sensitivities(
    macro: dict[str, pd.Series], closes: dict[str, pd.Series], weeks: int = SENS_WEEKS
) -> dict[str, dict[str, dict]]:
    """Beta univariada de los retornos semanales de cada activo frente a cada factor.

    `impact` es el movimiento promedio del activo ante el shock de referencia del factor
    (p. ej. +25 pb en la tasa a 10 años); `t` es su estadístico t."""
    factors = {f: _weekly_factor(macro, f) for f in FACTORS}
    out: dict[str, dict[str, dict]] = {}
    for t, s in closes.items():
        r = s.sort_index().resample("W-FRI").last().pct_change(fill_method=None)
        res: dict[str, dict] = {}
        for f, x in factors.items():
            if x is None:
                continue
            df = pd.concat([r, x], axis=1, keys=["y", "x"], sort=True).dropna().iloc[-weeks:]
            df = df[np.isfinite(df).all(axis=1)]
            n = len(df)
            if n < MIN_SENS_WEEKS or df["x"].var() <= 0:
                continue
            xv = df["x"] - df["x"].mean()
            yv = df["y"] - df["y"].mean()
            beta = float((xv * yv).sum() / (xv**2).sum())
            resid = yv - beta * xv
            se = math.sqrt(float((resid**2).sum()) / (n - 2) / float((xv**2).sum()))
            unit = FACTORS[f][2]
            res[f] = {
                "beta": round(beta, 4),
                "impact": round(beta * unit, 4),
                "t": round(beta / se, 2) if se > 0 else None,
                "corr": round(float(df["x"].corr(df["y"])), 3),
                "n_weeks": n,
            }
        if res:
            out[t] = res
    return out


def sector_sensitivities(
    sens: dict[str, dict[str, dict]], sectors: dict[str, str]
) -> dict[str, dict[str, dict]]:
    grouped: dict[str, dict[str, list[float]]] = {}
    for t, by_f in sens.items():
        sec = sectors.get(t) or "Sin clasificar"
        for f, v in by_f.items():
            grouped.setdefault(sec, {}).setdefault(f, []).append(v["impact"])
    return {
        sec: {
            f: {"impact": round(float(np.median(v)), 4), "n": len(v)}
            for f, v in by_f.items()
            if len(v) >= MIN_SECTOR_MEMBERS
        }
        for sec, by_f in grouped.items()
    }


def macro_snapshot(macro: dict[str, pd.Series], labels: dict[str, tuple[str, str]]) -> list[dict]:
    """Último valor y variaciones a 20 y 60 ruedas de cada serie."""
    rows = []
    for key, (label, unit) in labels.items():
        s = macro.get(key)
        if s is None or s.empty:
            continue
        s = s.sort_index()
        last = float(s.iloc[-1])

        def chg(n: int, s: pd.Series = s, last: float = last, unit: str = unit) -> float | None:
            if len(s) <= n:
                return None
            prev = float(s.iloc[-1 - n])
            return round(last - prev, 4) if unit == "pct" else round(last / prev - 1, 4)

        rows.append(
            {
                "key": key,
                "label": label,
                "unit": unit,
                "as_of": str(s.index[-1].date()),
                "value": round(last, 4),
                "change_20": chg(20),
                "change_60": chg(60),
                "spark": [
                    {"time": str(d.date()), "value": round(float(v), 4)}
                    for d, v in s.iloc[-250:].items()
                ],
            }
        )
    return rows


def _shock_label(rule: EventRule) -> str | None:
    if not rule.factor:
        return None
    label = FACTORS[rule.factor][3]
    return label if rule.shock_sign > 0 else "−" + label.removeprefix("+")


def asset_exposure(
    ticker: str,
    sector: str,
    active: list[dict],
    study: dict[str, dict],
    sens: dict[str, dict[str, dict]],
) -> list[dict]:
    """Cómo se comportó históricamente el activo y su sector ante cada evento vigente."""
    out = []
    for ev in active:
        if ev["state"] == "inactivo":
            continue
        rule = next(r for r in RULES if r.key == ev["key"])
        sector_row = next(
            (r for r in (study.get(rule.key) or {}).get("sectors", []) if r["sector"] == sector),
            None,
        )
        s = (sens.get(ticker) or {}).get(rule.factor or "")
        reaction = None
        if s:
            impact = s["impact"] * rule.shock_sign
            reaction = {
                "factor": rule.factor,
                "shock": _shock_label(rule),
                "impact": round(impact, 4),
                "t": s["t"],
                "significant": bool(s["t"] is not None and abs(s["t"]) >= 2),
            }
        tone = None
        if sector_row and sector_row["significant"]:
            tone = "favorable" if sector_row["mean_excess"] > 0 else "desfavorable"
        elif reaction and reaction["significant"]:
            tone = "favorable" if reaction["impact"] > 0 else "desfavorable"
        out.append(
            {
                "event": ev["key"],
                "name": ev["name"],
                "state": ev["state"],
                "sector_history": sector_row,
                "reaction": reaction,
                "tone": tone,
            }
        )
    return out
