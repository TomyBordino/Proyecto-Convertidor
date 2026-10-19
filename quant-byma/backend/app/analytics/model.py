"""Modelo probabilístico: P(precio en USD más alto dentro de H ruedas).

El puntaje es un modelo de factores con pesos fijos (sin parámetros ajustados), porque en
la validación con datos reales los modelos ajustados (logística, gradient boosting) no le
ganaron a la tasa base fuera de muestra, mientras que los factores clásicos sí:

    tendencia  = promedio de percentiles (por fecha) de pendiente de la SMA200, momentum
                 12-1 meses, distancia a la SMA200 y distancia al máximo de 52 semanas
    valuación  = promedio de percentiles de earnings, book, FCF y sales yield
    puntaje    = 50% tendencia + 50% valuación (solo tendencia si no hay balances)

Tendencia y valuación se compensan: el momentum falla en los rebotes posteriores a las
crisis, justo cuando la valuación funciona ("Value and Momentum Everywhere", Asness,
Moskowitz y Pedersen, 2013).

Probabilidad: calibración isotónica del puntaje contra la frecuencia observada de suba.
Validación walk-forward: cada año se califica con una calibración ajustada solo con años
anteriores (con embargo de H ruedas), y todas las métricas reportadas son de esas
predicciones fuera de muestra. Si un horizonte no supera a la tasa base (Brier skill ≤ 0
o AUC < MIN_AUC) se marca "sin ventaja demostrada" y se informa la tasa base.

Las features usan solo información disponible a cada fecha: cada balance se considera
conocido FILING_LAG_DAYS días después del cierre del ejercicio.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

from app.analytics.regime import stage_series
from app.analytics.technical import bollinger, rsi, sma

HORIZONS = (20, 60, 120)
STEP = 5  # una muestra por semana y activo
FILING_LAG_DAYS = 100
MIN_TRAIN_SAMPLES = 2000
MIN_TRAIN_YEARS = 2
MIN_AUC = 0.51

TREND_FACTORS = ("slope_200", "mom_12_1", "dist_sma200", "dd_252")
VALUE_FACTORS = ("r_earnings_yield", "r_book_yield", "r_fcf_yield", "r_sales_yield")
TREND_WEIGHT = 0.5

TECH_FEATURES = {
    "mom_20": "Retorno del último mes",
    "mom_60": "Retorno de los últimos 3 meses",
    "mom_12_1": "Momentum 12 meses (sin el último)",
    "dist_sma50": "Distancia a la media de 50 ruedas",
    "dist_sma200": "Distancia a la media de 200 ruedas",
    "slope_200": "Pendiente de la media de 200 ruedas",
    "rsi14": "RSI 14",
    "bb_pct_b": "Posición en bandas de Bollinger",
    "vol_60": "Volatilidad de 3 meses",
    "dd_252": "Distancia al máximo de 52 semanas",
    "volume_trend": "Volumen reciente vs promedio",
}
STAGE_FEATURES = {f"stage_{i}": f"Etapa {i}" for i in (1, 2, 3, 4)}
FUND_FEATURES = {
    "r_earnings_yield": "Barata por P/E (percentil)",
    "r_sales_yield": "Barata por P/S (percentil)",
    "r_book_yield": "Barata por P/B (percentil)",
    "r_fcf_yield": "Rendimiento de flujo de caja (percentil)",
    "r_roe": "Rentabilidad ROE (percentil)",
    "r_growth": "Crecimiento de ventas (percentil)",
    "r_low_leverage": "Bajo endeudamiento (percentil)",
    "has_fundamentals": "Tiene balances publicados",
}
FEATURES = {
    **TECH_FEATURES,
    **STAGE_FEATURES,
    **FUND_FEATURES,
    "slope_200": "Tendencia: pendiente de la media de 200",
    "mom_12_1": "Tendencia: momentum 12 meses (sin el último)",
    "dist_sma200": "Tendencia: distancia a la media de 200",
    "dd_252": "Tendencia: cercanía al máximo de 52 semanas",
    "r_earnings_yield": "Valuación: barata por P/E",
    "r_book_yield": "Valuación: barata por P/B",
    "r_fcf_yield": "Valuación: rendimiento de flujo de caja",
    "r_sales_yield": "Valuación: barata por P/S",
}
FEATURE_NAMES = list(FEATURES)


# ------------------------------------------------------------------ features


def technical_features(close: pd.Series, volume: pd.Series | None = None) -> pd.DataFrame:
    close = close.astype(float)
    logret = np.log(close).diff()
    sma50, sma200 = sma(close, 50), sma(close, 200)
    out = pd.DataFrame(index=close.index)
    out["mom_20"] = close / close.shift(20) - 1
    out["mom_60"] = close / close.shift(60) - 1
    out["mom_12_1"] = close.shift(21) / close.shift(252) - 1
    out["dist_sma50"] = close / sma50 - 1
    out["dist_sma200"] = close / sma200 - 1
    out["slope_200"] = sma200 / sma200.shift(60) - 1
    out["rsi14"] = rsi(close, 14)
    out["bb_pct_b"] = bollinger(close).percent_b.clip(-1, 2)
    out["vol_60"] = logret.rolling(60).std() * math.sqrt(252)
    out["dd_252"] = close / close.rolling(252, min_periods=60).max() - 1
    if volume is not None and (volume > 0).any():
        v = volume.replace(0, np.nan)
        out["volume_trend"] = np.log(v.rolling(20).mean() / v.rolling(120).mean())
    else:
        out["volume_trend"] = 0.0
    stages = stage_series(close)
    for i in (1, 2, 3, 4):
        out[f"stage_{i}"] = (stages == i).astype(float).where(stages.notna())
    out["stage"] = stages
    return out


def forward_returns(close: pd.Series, horizons=HORIZONS) -> pd.DataFrame:
    return pd.DataFrame({f"fwd_{h}": close.shift(-h) / close - 1 for h in horizons})


def point_in_time_fundamentals(
    dates: pd.DatetimeIndex, statements: list, price_per_share: pd.Series
) -> pd.DataFrame:
    """Valores fundamentales conocidos en cada fecha (balance publicado + precio del día)."""
    cols = ["earnings_yield", "sales_yield", "book_yield", "fcf_yield", "roe", "growth", "lev"]
    if not statements:
        return pd.DataFrame(np.nan, index=dates, columns=cols)
    rows, prev_rev = [], None
    for s in statements:
        fcf = None
        if s.operating_cash_flow is not None and s.capex is not None:
            fcf = s.operating_cash_flow - abs(s.capex)
        growth = None
        if s.revenue and prev_rev and prev_rev > 0:
            growth = s.revenue / prev_rev - 1
        prev_rev = s.revenue
        rows.append(
            {
                "available": pd.Timestamp(s.period_end) + pd.Timedelta(days=FILING_LAG_DAYS),
                "ni": s.net_income,
                "rev": s.revenue,
                "eq": s.equity,
                "fcf": fcf,
                "shares": s.shares_outstanding,
                "growth": growth,
                "lev": (s.total_debt / s.equity) if s.total_debt is not None and s.equity else None,
                "roe": (s.net_income / s.equity) if s.net_income is not None and s.equity else None,
            }
        )
    st = pd.DataFrame(rows).sort_values("available")
    st["available"] = st["available"].astype("datetime64[ns]")
    for c in st.columns.drop("available"):
        st[c] = pd.to_numeric(st[c], errors="coerce")
    base = pd.DataFrame({"date": pd.DatetimeIndex(dates).astype("datetime64[ns]")})
    base = base.sort_values("date")
    merged = pd.merge_asof(base, st, left_on="date", right_on="available").set_index("date")
    px = price_per_share.reindex(merged.index).ffill()
    mcap = px * merged["shares"]
    mcap = mcap.where(mcap > 0)
    out = pd.DataFrame(index=merged.index)
    out["earnings_yield"] = merged["ni"] / mcap
    out["sales_yield"] = merged["rev"] / mcap
    out["book_yield"] = merged["eq"] / mcap
    out["fcf_yield"] = merged["fcf"] / mcap
    out["roe"] = merged["roe"]
    out["growth"] = merged["growth"]
    out["lev"] = merged["lev"]
    out.index = pd.DatetimeIndex(dates).sort_values()
    return out.reindex(dates)


@dataclass
class AssetInput:
    ticker: str
    close: pd.Series  # serie de análisis en USD
    volume: pd.Series | None
    statements: list = field(default_factory=list)  # balances en USD
    price_per_share: pd.Series | None = None


def build_panel(assets: list[AssetInput], step: int = STEP) -> pd.DataFrame:
    """Panel (fecha, ticker) con features, etapa y retornos futuros."""
    frames = []
    for a in assets:
        close = a.close.dropna()
        close = close[close > 0]
        if len(close) < 260:
            continue
        tech = technical_features(
            close, a.volume.reindex(close.index) if a.volume is not None else None
        )
        fwd = forward_returns(close)
        fund = point_in_time_fundamentals(
            close.index, a.statements, a.price_per_share if a.price_per_share is not None else close
        )
        df = pd.concat([tech, fwd, fund], axis=1)
        # Muestreo semanal alineado a la última rueda (que siempre queda incluida).
        keep = np.arange(len(df) - 1, -1, -step)[::-1]
        df = df.iloc[keep]
        df["ticker"] = a.ticker
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    panel = pd.concat(frames)
    panel.index.name = "date"
    panel = panel.reset_index()
    # Percentiles de corte transversal por fecha (solo entre activos con dato).
    ranks = {
        "r_earnings_yield": ("earnings_yield", True),
        "r_sales_yield": ("sales_yield", True),
        "r_book_yield": ("book_yield", True),
        "r_fcf_yield": ("fcf_yield", True),
        "r_roe": ("roe", True),
        "r_growth": ("growth", True),
        "r_low_leverage": ("lev", False),
    }
    for col, (src, ascending) in ranks.items():
        vals = panel[src] if ascending else -panel[src]
        panel[col] = vals.groupby(panel["date"]).rank(pct=True)
    panel["has_fundamentals"] = panel["earnings_yield"].notna().astype(float)
    for col in ranks:
        panel[col] = panel[col].fillna(0.5)
    for f in TREND_FACTORS:
        panel[f"q_{f}"] = panel[f].groupby(panel["date"]).rank(pct=True)
    panel["trend_score"] = panel[[f"q_{f}" for f in TREND_FACTORS]].mean(axis=1)
    value = panel[list(VALUE_FACTORS)].mean(axis=1)
    has = panel["has_fundamentals"] > 0
    panel["value_score"] = value.where(has)
    panel["score"] = panel["trend_score"].where(
        ~has, TREND_WEIGHT * panel["trend_score"] + (1 - TREND_WEIGHT) * value
    )
    return panel


# --------------------------------------------------------------------- modelo


def wilson_interval(p: float, n: float, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 1.0
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, center - half), min(1.0, center + half)


@dataclass
class HorizonModel:
    horizon: int
    report: dict
    calibrator: IsotonicRegression | None = None
    oos: pd.DataFrame | None = None  # predicciones fuera de muestra (score, prob, y, fwd)
    has_skill: bool = False


def _calibration_table(p: np.ndarray, y: np.ndarray, bins: int = 10) -> list[dict]:
    edges = np.unique(np.quantile(p, np.linspace(0, 1, bins + 1)))
    idx = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, len(edges) - 2)
    out = []
    for b in range(len(edges) - 1):
        m = idx == b
        if m.sum() == 0:
            continue
        out.append(
            {
                "pred": round(float(p[m].mean()), 4),
                "observed": round(float(y[m].mean()), 4),
                "n": int(m.sum()),
            }
        )
    return out


def _isotonic() -> IsotonicRegression:
    return IsotonicRegression(out_of_bounds="clip", y_min=0.02, y_max=0.98, increasing=True)


def train_horizon(panel: pd.DataFrame, horizon: int) -> HorizonModel:
    target = f"fwd_{horizon}"
    data = panel.dropna(subset=["score", "stage", target]).copy()
    data["y"] = (data[target] > 0).astype(int)
    report: dict = {
        "horizon": horizon,
        "n_samples": int(len(data)),
        "method": "factores con pesos fijos + calibración isotónica walk-forward",
        "weights": {
            "trend": TREND_WEIGHT,
            "value": 1 - TREND_WEIGHT,
            "trend_factors": list(TREND_FACTORS),
            "value_factors": list(VALUE_FACTORS),
        },
    }
    if len(data) < MIN_TRAIN_SAMPLES or data["y"].nunique() < 2:
        report["status"] = f"muestras insuficientes ({len(data)})"
        return HorizonModel(horizon, report)

    years = sorted(data["date"].dt.year.unique())
    embargo = pd.Timedelta(days=int(horizon * 1.5) + 7)  # ruedas → días corridos
    parts, by_year = [], []
    for y in years[MIN_TRAIN_YEARS:]:
        test = data[data["date"].dt.year == y]
        train = data[data["date"] < pd.Timestamp(year=y, month=1, day=1) - embargo]
        if len(train) < MIN_TRAIN_SAMPLES or train["y"].nunique() < 2 or test.empty:
            continue
        iso = _isotonic().fit(train["score"], train["y"])
        part = test[["date", "ticker", "stage", "score", "y", target]].copy()
        part["prob"] = iso.predict(test["score"])
        part["train_base"] = train["y"].mean()
        parts.append(part)
        if test["y"].nunique() == 2:
            by_year.append(
                {
                    "year": int(y),
                    "auc": round(float(roc_auc_score(test["y"], test["score"])), 4),
                    "base_rate": round(float(test["y"].mean()), 4),
                    "n": int(len(test)),
                }
            )
    if not parts:
        report["status"] = "historia insuficiente para validación walk-forward"
        return HorizonModel(horizon, report)

    oos = pd.concat(parts).rename(columns={target: "fwd"})
    y_oos = oos["y"].to_numpy()
    brier = brier_score_loss(y_oos, oos["prob"])
    brier_base = brier_score_loss(y_oos, oos["train_base"])
    auc = float(roc_auc_score(y_oos, oos["score"]))
    skill = float(1 - brier / brier_base)
    has_skill = skill > 0 and auc >= MIN_AUC
    q = pd.qcut(oos["score"].rank(method="first"), 5, labels=False)
    top, bottom = oos[q == 4], oos[q == 0]
    report.update(
        {
            "status": "ok",
            "has_skill": has_skill,
            "oos_samples": int(len(oos)),
            "oos_effective": round(len(oos) * STEP / horizon),
            "oos_years": sorted(int(v) for v in oos["date"].dt.year.unique()),
            "base_rate": round(float(data["y"].mean()), 4),
            "auc": round(auc, 4),
            "brier": round(float(brier), 5),
            "brier_base": round(float(brier_base), 5),
            "brier_skill": round(skill, 4),
            "years_auc_above_half": sum(1 for r in by_year if r["auc"] > 0.5),
            "by_year": by_year,
            "top_quintile_hit": round(float(top["y"].mean()), 4),
            "bottom_quintile_hit": round(float(bottom["y"].mean()), 4),
            "top_quintile_median_return": round(float(top["fwd"].median()), 4),
            "bottom_quintile_median_return": round(float(bottom["fwd"].median()), 4),
            "calibration": _calibration_table(oos["prob"].to_numpy(), y_oos),
        }
    )
    # Calibración final con toda la historia etiquetada.
    calibrator = _isotonic().fit(data["score"], data["y"])
    return HorizonModel(horizon, report, calibrator, oos, has_skill)


def stage_statistics(panel: pd.DataFrame, horizon: int) -> list[dict]:
    target = f"fwd_{horizon}"
    data = panel.dropna(subset=["stage", target])
    out = []
    for st, g in data.groupby("stage"):
        hit = float((g[target] > 0).mean())
        n_eff = len(g) * STEP / horizon
        lo, hi = wilson_interval(hit, n_eff)
        out.append(
            {
                "stage": int(st),
                "hit_rate": round(hit, 4),
                "ci_low": round(lo, 4),
                "ci_high": round(hi, 4),
                "n": int(len(g)),
                "n_effective": round(n_eff),
                "median_return": round(float(g[target].median()), 4),
                "p25_return": round(float(g[target].quantile(0.25)), 4),
                "p75_return": round(float(g[target].quantile(0.75)), 4),
            }
        )
    return out


def _drivers(row: pd.Series) -> list[dict]:
    """Aporte de cada factor al puntaje: peso × (percentil − 0,5)."""
    has_value = row.get("has_fundamentals", 0) > 0
    w_trend = TREND_WEIGHT if has_value else 1.0
    out = []
    for f in TREND_FACTORS:
        v = row.get(f"q_{f}")
        if v is not None and np.isfinite(v):
            out.append((f, float(v), w_trend / len(TREND_FACTORS) * (float(v) - 0.5)))
    if has_value:
        for f in VALUE_FACTORS:
            v = row.get(f)
            if v is not None and np.isfinite(v):
                out.append(
                    (f, float(v), (1 - TREND_WEIGHT) / len(VALUE_FACTORS) * (float(v) - 0.5))
                )
    return [
        {"feature": f, "label": FEATURES.get(f, f), "value": round(v, 4), "impact": round(i, 4)}
        for f, v, i in sorted(out, key=lambda x: -abs(x[2]))
    ]


def predict(hm: HorizonModel, rows: pd.DataFrame) -> list[dict | None]:
    """Probabilidad calibrada, evidencia histórica y factores que la explican."""
    if hm.calibrator is None or hm.oos is None:
        return [None] * len(rows)
    base = hm.report.get("base_rate")
    oos = hm.oos
    out: list[dict | None] = []
    for _, row in rows.iterrows():
        score = row.get("score")
        if score is None or not np.isfinite(score):
            out.append(None)
            continue
        if hm.has_skill or base is None:
            prob = float(hm.calibrator.predict([score])[0])
        else:
            prob = float(base)  # sin ventaja demostrada: la mejor estimación es la tasa base
        # Situaciones similares: muestras fuera de muestra con puntaje cercano.
        window = 0.01
        similar = oos[(oos["score"] - score).abs() <= window]
        while len(similar) < 300 and window < 0.1:
            window += 0.01
            similar = oos[(oos["score"] - score).abs() <= window]
        n = len(similar)
        hit = float(similar["y"].mean()) if n else float("nan")
        n_eff = n * STEP / hm.horizon
        lo, hi = wilson_interval(hit, n_eff) if n else (0.0, 1.0)
        drivers = _drivers(row)
        out.append(
            {
                "horizon": hm.horizon,
                "probability": round(prob, 4),
                "score": round(float(score), 4),
                "has_skill": hm.has_skill,
                "base_rate": base,
                "similar": {
                    "hit_rate": round(hit, 4) if n else None,
                    "ci_low": round(lo, 4),
                    "ci_high": round(hi, 4),
                    "n": int(n),
                    "n_effective": round(n_eff),
                    "median_return": _f(similar["fwd"].median()) if n else None,
                    "p25_return": _f(similar["fwd"].quantile(0.25)) if n else None,
                    "p75_return": _f(similar["fwd"].quantile(0.75)) if n else None,
                },
                "drivers_up": [d for d in drivers if d["impact"] > 0.005][:4],
                "drivers_down": [d for d in drivers if d["impact"] < -0.005][:4],
            }
        )
    return out


def _f(x: object) -> float | None:
    try:
        v = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return round(v, 4) if math.isfinite(v) else None
