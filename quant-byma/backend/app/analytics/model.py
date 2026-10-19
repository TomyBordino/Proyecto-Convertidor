"""Modelo probabilístico: P(precio en USD más alto dentro de H ruedas).

Diseño (pensado para que la probabilidad sea verificable, no una opinión):

1. Panel de muestras (activo, fecha) cada `STEP` ruedas con features que usan solo
   información disponible a esa fecha: momentum, posición vs medias, osciladores,
   volatilidad, etapa de Weinstein y fundamentales "point in time" (cada balance se
   considera conocido `FILING_LAG_DAYS` días después del cierre del ejercicio).
   Los fundamentales se convierten a percentiles de corte transversal por fecha.
2. Etiqueta: retorno en USD a H ruedas > 0.
3. Validación walk-forward: para cada año Y se entrena con muestras previas a Y (con un
   embargo de H ruedas para que ninguna etiqueta del entrenamiento mire dentro de Y) y se
   predice Y. Todas las métricas reportadas son fuera de muestra.
4. Calibración isotónica ajustada sobre esas predicciones fuera de muestra: un 60%
   significa "en el pasado, de cada 10 situaciones con este puntaje, ~6 subieron".
5. Evidencia por predicción: frecuencia histórica de acierto de situaciones con puntaje
   similar, intervalo de Wilson con tamaño de muestra efectivo (las ventanas de H ruedas
   se superponen, así que n_efectivo = n × STEP / H).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.analytics.regime import stage_series
from app.analytics.technical import bollinger, rsi, sma

HORIZONS = (20, 60, 120)
STEP = 5  # una muestra por semana y activo
FILING_LAG_DAYS = 100
MIN_TRAIN_SAMPLES = 2000
MIN_TRAIN_YEARS = 2

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
FEATURES = {**TECH_FEATURES, **STAGE_FEATURES, **FUND_FEATURES}
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
    return panel


# --------------------------------------------------------------------- modelo


def wilson_interval(p: float, n: float, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 1.0
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def _winsor_bounds(X: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    return X.quantile(0.01), X.quantile(0.99)


def _make_model() -> object:
    return make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=1000))


def _design(panel: pd.DataFrame, bounds: tuple[pd.Series, pd.Series]) -> pd.DataFrame:
    X = panel[FEATURE_NAMES].astype(float)
    tech = list(TECH_FEATURES)
    X[tech] = X[tech].clip(bounds[0][tech], bounds[1][tech], axis=1)
    return X.fillna(0.0)


@dataclass
class HorizonModel:
    horizon: int
    report: dict
    model: object | None = None
    bounds: tuple[pd.Series, pd.Series] | None = None
    calibrator: IsotonicRegression | None = None
    oos: pd.DataFrame | None = None  # predicciones fuera de muestra (raw, y, fwd)


def _calibration_table(p: np.ndarray, y: np.ndarray, bins: int = 10) -> list[dict]:
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    edges[0], edges[-1] = 0.0, 1.0
    idx = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, bins - 1)
    out = []
    for b in range(bins):
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


def train_horizon(panel: pd.DataFrame, horizon: int) -> HorizonModel:
    target = f"fwd_{horizon}"
    tech = list(TECH_FEATURES)
    data = panel.dropna(subset=[*tech, "stage", target]).copy()
    data["y"] = (data[target] > 0).astype(int)
    report: dict = {"horizon": horizon, "n_samples": int(len(data))}
    if len(data) < MIN_TRAIN_SAMPLES or data["y"].nunique() < 2:
        report["status"] = f"muestras insuficientes ({len(data)})"
        return HorizonModel(horizon, report)

    years = sorted(data["date"].dt.year.unique())
    embargo = pd.Timedelta(days=int(horizon * 1.5) + 7)  # ruedas → días corridos
    oos_parts = []
    for y in years[MIN_TRAIN_YEARS:]:
        test = data[data["date"].dt.year == y]
        train = data[data["date"] < pd.Timestamp(year=y, month=1, day=1) - embargo]
        if len(train) < MIN_TRAIN_SAMPLES or train["y"].nunique() < 2 or test.empty:
            continue
        bounds = _winsor_bounds(train[tech])
        model = _make_model()
        model.fit(_design(train, bounds), train["y"])  # type: ignore[attr-defined]
        raw = model.predict_proba(_design(test, bounds))[:, 1]  # type: ignore[attr-defined]
        part = test[["date", "ticker", "stage", "y", target]].copy()
        part["raw"] = raw
        part["train_base"] = train["y"].mean()
        oos_parts.append(part)

    if not oos_parts:
        report["status"] = "historia insuficiente para validación walk-forward"
        return HorizonModel(horizon, report)
    oos = pd.concat(oos_parts).rename(columns={target: "fwd"})
    y_oos, p_oos = oos["y"].to_numpy(), oos["raw"].to_numpy()

    calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.01, y_max=0.99)
    calibrator.fit(p_oos, y_oos)

    brier = brier_score_loss(y_oos, p_oos)
    brier_base = brier_score_loss(y_oos, oos["train_base"].to_numpy())
    q = pd.qcut(oos["raw"].rank(method="first"), 5, labels=False)
    top, bottom = oos[q == 4], oos[q == 0]
    report.update(
        {
            "status": "ok",
            "oos_samples": int(len(oos)),
            "oos_effective": round(len(oos) * STEP / horizon),
            "oos_years": sorted(int(v) for v in oos["date"].dt.year.unique()),
            "base_rate": round(float(y_oos.mean()), 4),
            "auc": round(float(roc_auc_score(y_oos, p_oos)), 4),
            "brier": round(float(brier), 5),
            "brier_base": round(float(brier_base), 5),
            "brier_skill": round(float(1 - brier / brier_base), 4),
            "top_quintile_hit": round(float(top["y"].mean()), 4),
            "bottom_quintile_hit": round(float(bottom["y"].mean()), 4),
            "top_quintile_median_return": round(float(top["fwd"].median()), 4),
            "bottom_quintile_median_return": round(float(bottom["fwd"].median()), 4),
            "calibration": _calibration_table(p_oos, y_oos),
        }
    )

    # Modelo final: todo lo etiquetado (las etiquetas ya excluyen el futuro no observado).
    bounds = _winsor_bounds(data[tech])
    model = _make_model()
    model.fit(_design(data, bounds), data["y"])  # type: ignore[attr-defined]
    lr = model.steps[-1][1]  # type: ignore[attr-defined]
    report["coefficients"] = {
        f: round(float(c), 4) for f, c in zip(FEATURE_NAMES, lr.coef_[0], strict=True)
    }
    return HorizonModel(horizon, report, model, bounds, calibrator, oos)


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


def predict(hm: HorizonModel, rows: pd.DataFrame, top_k: int = 3) -> list[dict | None]:
    """Probabilidad calibrada, evidencia histórica y factores que la explican."""
    if hm.model is None or hm.bounds is None or hm.calibrator is None or hm.oos is None:
        return [None] * len(rows)
    X = _design(rows, hm.bounds)
    raw = hm.model.predict_proba(X)[:, 1]  # type: ignore[attr-defined]
    cal = hm.calibrator.predict(raw)
    scaler, lr = hm.model.steps[0][1], hm.model.steps[1][1]  # type: ignore[attr-defined]
    z = (X.to_numpy() - scaler.mean_) / scaler.scale_
    contrib = z * lr.coef_[0]
    oos = hm.oos
    out: list[dict | None] = []
    for i in range(len(rows)):
        # Situaciones similares: predicciones fuera de muestra con puntaje cercano.
        window = 0.03
        similar = oos[(oos["raw"] - raw[i]).abs() <= window]
        while len(similar) < 200 and window < 0.2:
            window += 0.02
            similar = oos[(oos["raw"] - raw[i]).abs() <= window]
        hit = float(similar["y"].mean()) if len(similar) else float("nan")
        n_eff = len(similar) * STEP / hm.horizon
        lo, hi = wilson_interval(hit, n_eff) if len(similar) else (0.0, 1.0)
        order = np.argsort(contrib[i])
        drivers = [
            {
                "feature": FEATURE_NAMES[j],
                "label": FEATURES[FEATURE_NAMES[j]],
                "value": _f(rows.iloc[i][FEATURE_NAMES[j]]),
                "impact": round(float(contrib[i, j]), 4),
            }
            for j in [*order[::-1][:top_k], *order[:top_k]]
            if abs(contrib[i, j]) > 0.01
        ]
        out.append(
            {
                "horizon": hm.horizon,
                "probability": round(float(cal[i]), 4),
                "raw_score": round(float(raw[i]), 4),
                "base_rate": hm.report.get("base_rate"),
                "similar": {
                    "hit_rate": round(hit, 4) if len(similar) else None,
                    "ci_low": round(lo, 4),
                    "ci_high": round(hi, 4),
                    "n": int(len(similar)),
                    "n_effective": round(n_eff),
                    "median_return": _f(similar["fwd"].median()) if len(similar) else None,
                    "p25_return": _f(similar["fwd"].quantile(0.25)) if len(similar) else None,
                    "p75_return": _f(similar["fwd"].quantile(0.75)) if len(similar) else None,
                },
                "drivers_up": [d for d in drivers if d["impact"] > 0],
                "drivers_down": [d for d in drivers if d["impact"] < 0],
            }
        )
    return out


def _f(x: object) -> float | None:
    try:
        v = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return round(v, 4) if math.isfinite(v) else None
