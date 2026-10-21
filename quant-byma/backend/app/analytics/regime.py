"""Etapa de mercado de cada activo (análisis de etapas de Weinstein) y submomento.

La media de 30 semanas (≈150 ruedas) y su pendiente definen la etapa:

    Etapa 1 · Base / acumulación     media plana luego de una caída
    Etapa 2 · Tendencia alcista      precio sobre la media y media en alza
    Etapa 3 · Techo / distribución   media plana luego de una suba, o el precio perfora
                                     una media que todavía sube
    Etapa 4 · Tendencia bajista      precio bajo la media y media en baja

El submomento matiza la etapa con osciladores de corto plazo (pullback, sobreextensión,
rebote, ruptura de máximos).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.analytics.technical import rsi, sma

STAGE_MA = 150
SLOPE_LOOKBACK = 20
# Pendiente mínima (variación de la media en 20 ruedas) para considerarla en alza/baja.
SLOPE_THRESHOLD = 0.01
MEMORY = 120  # ruedas hacia atrás para recordar la última etapa direccional

STAGES = {
    1: (
        "Base / acumulación",
        "La media de 30 semanas se aplanó después de una caída: "
        "el precio lateraliza y la presión vendedora se agotó.",
    ),
    2: (
        "Tendencia alcista",
        "Precio sobre una media de 30 semanas en alza: la fase en "
        "la que históricamente se concentran las subas.",
    ),
    3: (
        "Techo / distribución",
        "La media dejó de subir o el precio la perforó: la tendencia alcista pierde fuerza.",
    ),
    4: (
        "Tendencia bajista",
        "Precio bajo una media de 30 semanas en baja: la fase con peor desempeño histórico.",
    ),
}


def stage_series(close: pd.Series) -> pd.Series:
    """Etapa (1–4) en cada rueda, usando solo información disponible a esa fecha."""
    ma = sma(close, STAGE_MA)
    slope = ma / ma.shift(SLOPE_LOOKBACK) - 1
    above = close > ma
    up = slope > SLOPE_THRESHOLD
    down = slope < -SLOPE_THRESHOLD

    direction = pd.Series(np.nan, index=close.index)
    direction[above & up] = 2
    direction[~above & down] = 4
    last_dir = direction.ffill(limit=MEMORY)

    stage = direction.copy()
    flat_or_mixed = stage.isna() & ma.notna()
    # Sin dirección clara: base si venía cayendo, techo si venía subiendo.
    stage[flat_or_mixed & (last_dir == 4)] = 1
    stage[flat_or_mixed & (last_dir == 2)] = 3
    # Precio sobre una media que baja: intento de salida de la base.
    stage[flat_or_mixed & last_dir.isna() & above] = 1
    # Precio bajo una media que sube: se pierde la tendencia.
    stage[flat_or_mixed & last_dir.isna() & ~above] = 3
    return stage.where(ma.notna())


@dataclass
class Regime:
    stage: int | None
    stage_name: str | None
    stage_description: str | None
    substate: str | None
    substate_description: str | None
    stage_since: str | None  # fecha ISO desde la que rige la etapa actual
    days_in_stage: int | None


def substate(close: pd.Series, stage: int | None) -> tuple[str | None, str | None]:
    if stage is None or len(close) < 60:
        return None, None
    r = float(rsi(close, 14).iloc[-1])
    last = float(close.iloc[-1])
    sma20 = float(sma(close, 20).iloc[-1])
    sma50 = float(sma(close, 50).iloc[-1])
    high_252 = float(close.iloc[-252:].max())
    dist50 = last / sma50 - 1
    if stage == 2:
        if r > 72 or dist50 > 0.15:
            return "Sobreextendida", (
                f"RSI {r:.0f} y {dist50:+.0%} sobre la media de 50: suba fuerte que suele "
                "corregir o consolidar antes de seguir."
            )
        if last >= high_252 * 0.995:
            return "En máximos", "Cotiza en máximos de 52 semanas dentro de la tendencia alcista."
        if last < sma20 or r < 45:
            return "Pullback", (
                f"Corrección dentro de la tendencia (RSI {r:.0f}): retroceso hacia sus medias "
                "sin perder la estructura alcista."
            )
        return "Avance", "Tendencia alcista en curso sin extremos de corto plazo."
    if stage == 4:
        if r < 30:
            return "Sobrevendida", f"RSI {r:.0f}: caída extendida, con rebotes técnicos posibles."
        if last > sma50:
            return "Rebote", "Rebota sobre su media de 50 ruedas dentro de una tendencia bajista."
        return "Caída", "Tendencia bajista en curso."
    if stage == 1:
        if last > sma50 and dist50 > 0:
            return "Intentando salir", "Opera sobre la media de 50 dentro de la base."
        return "Lateral", "Rango lateral, sin tendencia definida."
    if last < sma50:
        return "Perdiendo soporte", "Perforó su media de 50 ruedas luego de la suba."
    return "Lateral alto", "Consolida cerca de máximos sin nuevo impulso."


def current_regime(close: pd.Series) -> Regime:
    st = stage_series(close).dropna()
    if st.empty:
        return Regime(None, None, None, None, None, None, None)
    stage = int(st.iloc[-1])
    changes = st[st != st.shift()]
    since = changes.index[-1]
    days = int((st.index >= since).sum())
    name, desc = STAGES[stage]
    sub, sub_desc = substate(close, stage)
    return Regime(stage, name, desc, sub, sub_desc, since.date().isoformat(), days)
