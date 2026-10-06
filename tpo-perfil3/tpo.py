#!/usr/bin/env python3
"""
TPO Teoría de Carteras — Perfil 3 (Inversor joven de alto riesgo / Tecnológico)
Gestión ALGORÍTMICA: el algoritmo decide armado, rebalanceos y alertas; el equipo
solo ejecuta en BymaLab las órdenes que se generan.

Comandos:
    python tpo.py armar         Cartera inicial (selección + frontera eficiente)
    python tpo.py rebalancear   Rebalanceo semanal (obligatorio por reglamento)
    python tpo.py alertas       Chequeo diario: stops, tendencia, desvíos
    python tpo.py confirmar     Registrar las órdenes ya ejecutadas en BymaLab
    python tpo.py estado        Valuación y métricas de la cartera actual

Agregar --demo a cualquier comando para correr con datos sintéticos (sin internet).
"""
import argparse
import csv
import json
import math
import shutil
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

import config as C

BASE = Path(__file__).resolve().parent
ESTADO = BASE / "estado" / "cartera.json"
SALIDAS = BASE / "salidas"
BITACORA = SALIDAS / "bitacora.md"
ULTIMAS_CSV = SALIDAS / "ultimas_ordenes.csv"
ULTIMAS_META = SALIDAS / "ultimas_ordenes.json"
ALERTA_ACTUAL = SALIDAS / "alerta_actual.md"
PRECIOS_MANUALES = BASE / "precios_manuales.csv"

COLUMNAS_ORDEN = ["ticker", "accion", "cantidad", "precio_ref_ars", "monto_estimado_ars",
                  "peso_actual", "peso_objetivo", "motivo",
                  "cantidad_ejecutada", "precio_ejecutado"]


# =============================================================================
# Datos de mercado
# =============================================================================
class Mercado:
    def __init__(self, usd, ars, rf, origen):
        self.usd = usd      # DataFrame de cierres ajustados en USD (tickers de EE.UU. + benchmark)
        self.ars = ars      # Series: último precio en pesos por ticker BYMA
        self.rf = rf        # Tasa libre de riesgo anual
        self.origen = origen
        self.fecha = usd.index[-1].date()


def _cierres(df):
    """yfinance devuelve columnas MultiIndex o simples según la versión."""
    x = df["Close"]
    return x.to_frame() if isinstance(x, pd.Series) else x


def mercado_real():
    import yfinance as yf

    tickers_us = sorted(set(C.UNIVERSO.values()) | {C.BENCHMARK})
    usd = _cierres(yf.download(tickers_us, period="2y", auto_adjust=True, progress=False))

    tickers_ba = [f"{t}.BA" for t in C.UNIVERSO]
    ars_df = _cierres(yf.download(tickers_ba, period="1mo", auto_adjust=False, progress=False))
    ars = ars_df.ffill().iloc[-1].dropna()
    ars.index = [str(t).removesuffix(".BA") for t in ars.index]

    rf = C.TASA_LIBRE_RIESGO
    try:
        irx = _cierres(yf.download("^IRX", period="1mo", progress=False)).iloc[:, 0].dropna()
        if len(irx):
            rf = float(irx.iloc[-1]) / 100
    except Exception:
        pass
    return Mercado(usd.dropna(how="all"), ars, rf, "Yahoo Finance")


def mercado_demo(semilla=7, dias=520):
    """Datos sintéticos (modelo de mercado de un factor) para probar sin internet."""
    rng = np.random.default_rng(semilla)
    fechas = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=dias)
    mkt = rng.normal(0.10 / 252, 0.18 / math.sqrt(252), dias)
    usd = {C.BENCHMARK: 100 * np.exp(np.cumsum(mkt))}
    for us in sorted(set(C.UNIVERSO.values())):
        beta = rng.uniform(0.5, 2.0)
        alfa = rng.normal(0, 0.15) / 252
        idio = rng.uniform(0.15, 0.45) / math.sqrt(252)
        r = alfa + beta * mkt + rng.normal(0, idio, dias)
        usd[us] = rng.uniform(20, 400) * np.exp(np.cumsum(r))
    usd = pd.DataFrame(usd, index=fechas)
    ccl = 1450.0
    ars = pd.Series({b: usd[u].iloc[-1] * ccl / rng.choice([1, 2, 5, 10, 20])
                     for b, u in C.UNIVERSO.items()})
    return Mercado(usd, ars, C.TASA_LIBRE_RIESGO, f"DEMO sintético (semilla {semilla})")


def cargar_mercado(args):
    m = mercado_demo(args.semilla) if args.demo else mercado_real()
    # Precios manuales (p.ej. copiados de BymaLab) pisan a los descargados.
    if PRECIOS_MANUALES.exists():
        manual = pd.read_csv(PRECIOS_MANUALES)
        for _, fila in manual.iterrows():
            m.ars[str(fila["ticker"]).strip().upper()] = float(fila["precio_ars"])
    return m


# =============================================================================
# Estado de la cartera
# =============================================================================
def leer_estado():
    if ESTADO.exists():
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    return {"efectivo_ars": float(C.CAPITAL_INICIAL_ARS), "posiciones": {}, "pesos_objetivo": {}}


def guardar_estado(est):
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(est, indent=2, ensure_ascii=False), encoding="utf-8")


def valuar(est, mercado):
    """Devuelve (valor total, Series de valores por posición)."""
    valores = pd.Series({t: p["cantidad"] * float(mercado.ars.get(t, p["precio_compra_ars"]))
                         for t, p in est["posiciones"].items()}, dtype=float)
    return est["efectivo_ars"] + valores.sum(), valores


# =============================================================================
# Análisis: métricas, ranking y selección
# =============================================================================
def metricas(mercado):
    px = mercado.usd
    ret = px.pct_change().iloc[-C.VENTANA_DIAS:]
    mkt = ret[C.BENCHMARK]
    filas = {}
    for byma, us in C.UNIVERSO.items():
        if us not in px or byma not in mercado.ars.index:
            continue  # sin datos en USD o sin precio en pesos para dimensionar la orden
        serie = px[us].dropna()
        r = ret[us]
        par = pd.concat([r, mkt], axis=1).dropna()
        if len(par) < C.VENTANA_DIAS * 0.8:
            continue  # historia insuficiente
        beta = par.iloc[:, 0].cov(par.iloc[:, 1]) / par.iloc[:, 1].var()
        vol = r.std() * math.sqrt(252)
        mu = r.mean() * 252
        ini = serie.iloc[-253] if len(serie) > 253 else serie.iloc[0]
        filas[byma] = {
            "ticker_us": us,
            "beta": beta,
            "volatilidad": vol,
            "retorno_1a": serie.iloc[-1] / serie.iloc[-min(len(serie), 253)] - 1,
            "momentum": serie.iloc[-22] / ini - 1,           # 12-1 meses
            "sharpe": (mu - mercado.rf) / vol if vol > 0 else 0.0,
            "ret_20d": serie.iloc[-1] / serie.iloc[-21] - 1,
            "bajo_sma50": bool(serie.iloc[-1] < serie.iloc[-50:].mean()),
        }
    return pd.DataFrame(filas).T.infer_objects()


def _z(s):
    s = s.astype(float).clip(s.quantile(0.05), s.quantile(0.95))
    return (s - s.mean()) / s.std(ddof=0) if s.std(ddof=0) > 0 else s * 0


def rankear(met):
    eleg = met[met["beta"] >= C.BETA_MINIMA_ACTIVO].copy()
    if len(eleg) < C.N_ACTIVOS:  # si el filtro es muy estricto, completar con las Betas más altas
        eleg = met.sort_values("beta", ascending=False).head(max(C.N_ACTIVOS, len(eleg))).copy()
    eleg["score"] = sum(peso * _z(eleg[k]) for k, peso in C.PESO_SCORE.items())
    eleg = eleg.sort_values("score", ascending=False)
    eleg["rank"] = range(1, len(eleg) + 1)
    return eleg


def seleccionar(ranking, tenencias):
    """Top N por score, con histéresis para no rotar de más los activos ya en cartera."""
    if "veto" in ranking:
        ranking = ranking[~ranking["veto"]]
    mantener = [t for t in ranking.index
                if t in tenencias and ranking.at[t, "rank"] <= C.N_ACTIVOS + C.BUFFER_RANKING]
    mantener = mantener[:C.N_ACTIVOS]
    nuevos = [t for t in ranking.index if t not in mantener]
    return mantener + nuevos[:C.N_ACTIVOS - len(mantener)]


# =============================================================================
# Optimización de Markowitz: cartera tangente (máximo Sharpe) y frontera
# =============================================================================
def insumos(mercado, sel, met):
    tick = [met.at[t, "ticker_us"] for t in sel]
    r = mercado.usd[tick].pct_change().iloc[-C.VENTANA_DIAS:].fillna(0)
    S = r.cov().values * 252
    S = (1 - C.SHRINK_COV) * S + C.SHRINK_COV * np.diag(np.diag(S))
    beta = met.loc[sel, "beta"].astype(float).values
    mu_hist = np.clip(r.mean().values * 252, -0.5, 1.0)
    mu_capm = mercado.rf + beta * C.PRIMA_MERCADO
    mu = C.MEZCLA_CAPM * mu_capm + (1 - C.MEZCLA_CAPM) * mu_hist
    return mu, S, beta


def _limites(n):
    invertido = 1 - C.EFECTIVO_MINIMO
    hi = max(C.PESO_MAX, invertido / n + 1e-6)
    lo = min(C.PESO_MIN, invertido / n - 1e-6)
    return invertido, [(lo, hi)] * n


def tangente(mu, S, beta, rf):
    n = len(mu)
    invertido, lim = _limites(n)
    w0 = np.full(n, invertido / n)
    obj = lambda w: -(w @ (mu - rf)) / math.sqrt(w @ S @ w)
    base = [{"type": "eq", "fun": lambda w: w.sum() - invertido}]
    con_beta = base + [{"type": "ineq", "fun": lambda w: w @ beta - C.BETA_MINIMA_CARTERA}]
    res = minimize(obj, w0, method="SLSQP", bounds=lim, constraints=con_beta,
                   options={"maxiter": 500, "ftol": 1e-10})
    aviso = ""
    if not res.success:
        res = minimize(obj, w0, method="SLSQP", bounds=lim, constraints=base,
                       options={"maxiter": 500, "ftol": 1e-10})
        aviso = "Restricción de Beta de cartera no factible: se optimizó sin ella."
    w = np.clip(res.x, 0, None)
    return w * invertido / w.sum(), aviso


def frontera(mu, S, puntos=25):
    n = len(mu)
    invertido, lim = _limites(n)
    w0 = np.full(n, invertido / n)
    suma = {"type": "eq", "fun": lambda w: w.sum() - invertido}
    # Rango factible con los límites de peso: desde la cartera de mínima varianza
    # hasta la de máximo retorno.
    w_min = minimize(lambda w: w @ S @ w, w0, method="SLSQP", bounds=lim, constraints=[suma]).x
    w_max = minimize(lambda w: -(w @ mu), w0, method="SLSQP", bounds=lim, constraints=[suma]).x
    salida = []
    for objetivo in np.linspace(w_min @ mu, w_max @ mu, puntos):
        res = minimize(lambda w: w @ S @ w, w0, method="SLSQP", bounds=lim,
                       constraints=[suma, {"type": "eq", "fun": lambda w, o=objetivo: w @ mu - o}])
        if res.success:
            salida.append((math.sqrt(res.x @ S @ res.x), float(res.x @ mu)))
    return salida


def guardar_frontera(pts, mu, S, sel, w, rf, sello):
    ruta = SALIDAS / f"frontera_{sello}.csv"
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["tipo", "nombre", "volatilidad", "retorno_esperado"])
        for v, r in pts:
            wr.writerow(["frontera", "", f"{v:.6f}", f"{r:.6f}"])
        for i, t in enumerate(sel):
            wr.writerow(["activo", t, f"{math.sqrt(S[i, i]):.6f}", f"{mu[i]:.6f}"])
        wr.writerow(["tangente", "cartera", f"{math.sqrt(w @ S @ w):.6f}", f"{w @ mu:.6f}"])
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 5))
        if pts:
            ax.plot([p[0] for p in pts], [p[1] for p in pts], label="Frontera eficiente")
        ax.scatter(np.sqrt(np.diag(S)), mu, s=18, label="Activos")
        for i, t in enumerate(sel):
            ax.annotate(t, (math.sqrt(S[i, i]), mu[i]), fontsize=7)
        vt, rt = math.sqrt(w @ S @ w), w @ mu
        ax.scatter([vt], [rt], marker="*", s=200, label="Cartera tangente")
        ax.plot([0, vt * 1.5], [rf, rf + (rt - rf) * 1.5], "--", lw=1, label="CML")
        ax.set_xlabel("Volatilidad anual")
        ax.set_ylabel("Retorno esperado anual")
        ax.legend()
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(SALIDAS / f"frontera_{sello}.png", dpi=130)
        plt.close(fig)
    except ImportError:
        pass
    return ruta


# =============================================================================
# Generación de órdenes
# =============================================================================
def generar_ordenes(est, mercado, objetivo, motivos, forzar_una=False, solo=None):
    """
    objetivo: dict ticker -> peso objetivo sobre el valor total de la cartera.
    solo: si se indica, solo se consideran esos tickers (usado por las alertas).
    """
    total, valores = valuar(est, mercado)
    actual = (valores / total).to_dict()
    tickers = sorted(set(actual) | set(objetivo))
    if solo is not None:
        tickers = [t for t in tickers if t in solo]

    candidatas = []
    for t in tickers:
        pa, po = actual.get(t, 0.0), objetivo.get(t, 0.0)
        precio = float(mercado.ars[t])
        tenida = est["posiciones"].get(t, {}).get("cantidad", 0)
        dif = po - pa
        cierre = po == 0 and tenida > 0
        cantidad = tenida if cierre else int(abs(dif) * total // precio)
        if dif < 0:
            cantidad = min(cantidad, tenida)
        candidatas.append({"ticker": t, "accion": "VENDER" if dif < 0 else "COMPRAR",
                           "cantidad": cantidad, "precio": precio, "pa": pa, "po": po,
                           "dif": dif, "cierre": cierre,
                           "motivo": motivos.get(t, "Rebalanceo a peso objetivo")})

    ordenes = [c for c in candidatas if c["cantidad"] > 0 and (
        c["cierre"] or (abs(c["dif"]) > C.BANDA_REBALANCEO
                        and abs(c["dif"]) >= C.MONTO_MINIMO_ORDEN)
        or (solo is not None and abs(c["dif"]) >= C.MONTO_MINIMO_ORDEN))]

    if not ordenes and forzar_una:
        # El reglamento exige rebalancear todas las semanas: se ajusta el mayor desvío.
        posibles = sorted((c for c in candidatas if c["cantidad"] > 0),
                          key=lambda c: abs(c["dif"]), reverse=True)
        if posibles:
            posibles[0]["motivo"] += " (ajuste táctico semanal: ningún desvío superó la banda)"
            ordenes = posibles[:1]

    # Primero ventas, luego compras limitadas por el efectivo disponible.
    ventas = [o for o in ordenes if o["accion"] == "VENDER"]
    compras = sorted((o for o in ordenes if o["accion"] == "COMPRAR"),
                     key=lambda o: o["dif"], reverse=True)
    disponible = (est["efectivo_ars"]
                  + sum(o["cantidad"] * o["precio"] for o in ventas) * (1 - C.COMISION)
                  - C.EFECTIVO_MINIMO * total * 0.5)
    costo = sum(o["cantidad"] * o["precio"] for o in compras) * (1 + C.COMISION)
    if compras and costo > disponible:
        escala = max(disponible, 0) / costo
        for o in compras:
            o["cantidad"] = int(o["cantidad"] * escala)
        compras = [o for o in compras if o["cantidad"] > 0]

    return [{
        "ticker": o["ticker"], "accion": o["accion"], "cantidad": o["cantidad"],
        "precio_ref_ars": round(o["precio"], 2),
        "monto_estimado_ars": round(o["cantidad"] * o["precio"], 2),
        "peso_actual": f"{o['pa']:.2%}", "peso_objetivo": f"{o['po']:.2%}",
        "motivo": o["motivo"], "cantidad_ejecutada": "", "precio_ejecutado": "",
    } for o in ventas + compras]


def publicar_ordenes(ordenes, tipo, pesos_objetivo, sello):
    SALIDAS.mkdir(exist_ok=True)
    ruta = SALIDAS / f"ordenes_{sello}_{tipo}.csv"
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=COLUMNAS_ORDEN)
        wr.writeheader()
        wr.writerows(ordenes)
    shutil.copy(ruta, ULTIMAS_CSV)
    ULTIMAS_META.write_text(json.dumps({"tipo": tipo, "sello": sello, "archivo": ruta.name,
                                        "pesos_objetivo": pesos_objetivo}, indent=2),
                            encoding="utf-8")
    return ruta


# =============================================================================
# Salida: consola y bitácora
# =============================================================================
def tabla_md(df, fmt=None):
    fmt = fmt or {}
    cols = list(df.columns)
    lineas = ["| " + " | ".join(["ticker"] + cols) + " |",
              "|" + "---|" * (len(cols) + 1)]
    for idx, fila in df.iterrows():
        celdas = [fmt.get(c, "{}").format(fila[c]) for c in cols]
        lineas.append("| " + " | ".join([str(idx)] + celdas) + " |")
    return "\n".join(lineas)


def tabla_ordenes(ordenes):
    if not ordenes:
        return "_Sin órdenes._"
    df = pd.DataFrame(ordenes).set_index("ticker")[
        ["accion", "cantidad", "precio_ref_ars", "monto_estimado_ars",
         "peso_actual", "peso_objetivo", "motivo"]]
    return tabla_md(df, {"precio_ref_ars": "{:,.2f}", "monto_estimado_ars": "{:,.0f}"})


def bitacora(titulo, cuerpo):
    SALIDAS.mkdir(exist_ok=True)
    nuevo = not BITACORA.exists()
    with open(BITACORA, "a", encoding="utf-8") as f:
        if nuevo:
            f.write("# Bitácora del algoritmo — Perfil 3 (Gestión algorítmica)\n\n"
                    "Registro automático de cada decisión del algoritmo.\n")
        f.write(f"\n## {datetime.now():%Y-%m-%d %H:%M} — {titulo}\n\n{cuerpo}\n")


# =============================================================================
# Capa de IA (noticias)
# =============================================================================
def capa_noticias(args, ranking, est, sello):
    """Ajusta el ranking con el sentimiento de noticias. Devuelve (ranking, texto para bitácora)."""
    if args.sin_noticias or not C.USAR_NOTICIAS:
        return ranking, "### Noticias (IA)\n\n_Desactivado: ranking solo cuantitativo._\n"
    import noticias

    candidatos = list(ranking.index[:C.N_CANDIDATOS_NOTICIAS])
    candidatos += [t for t in est["posiciones"] if t in ranking.index and t not in candidatos]
    print(f"Analizando noticias de {len(candidatos)} activos con {C.MODELO_IA}...")
    evaluaciones, error = noticias.evaluar_noticias(
        {t: ranking.at[t, "ticker_us"] for t in candidatos})
    if not evaluaciones:
        aviso = error or "El modelo no devolvió evaluaciones."
        print(f"AVISO: {aviso} Se sigue con el ranking cuantitativo.")
        return ranking, f"### Noticias (IA)\n\n_No disponible ({aviso}) — ranking solo cuantitativo._\n"

    (SALIDAS / f"noticias_{sello}.json").write_text(
        json.dumps(evaluaciones, indent=2, ensure_ascii=False), encoding="utf-8")
    ajustado = noticias.ajustar_ranking(ranking, evaluaciones)
    filas = pd.DataFrame({
        "sentimiento": [e["sentimiento"] for e in evaluaciones.values()],
        "confianza": [e["confianza"] for e in evaluaciones.values()],
        "veto": ["SÍ" if ajustado.at[t, "veto"] else "" for t in evaluaciones],
        "resumen": [e["resumen"] for e in evaluaciones.values()],
    }, index=list(evaluaciones)).sort_values("sentimiento")
    texto = (f"### Noticias (IA: {C.MODELO_IA})\n\n"
             f"Ajuste: score += {C.PESO_NOTICIAS} × sentimiento × confianza; "
             f"veto si sentimiento × confianza <= {C.VETO_NOTICIAS}. "
             f"Fuentes completas en `noticias_{sello}.json`.\n\n"
             + tabla_md(filas, {"sentimiento": "{:+.2f}", "confianza": "{:.2f}"}) + "\n")
    return ajustado, texto


# =============================================================================
# Comandos
# =============================================================================
def cmd_optimizar(args, tipo):
    mercado = cargar_mercado(args)
    est = leer_estado()
    if tipo == "armado" and est["posiciones"] and not args.forzar:
        sys.exit("Ya hay posiciones cargadas. Usá 'rebalancear' (o 'armar --forzar').")

    met = metricas(mercado)
    ranking = rankear(met)
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    ranking, texto_ia = capa_noticias(args, ranking, est, sello)
    sel = seleccionar(ranking, est["posiciones"])
    mu, S, beta = insumos(mercado, sel, met)
    w, aviso = tangente(mu, S, beta, mercado.rf)
    pesos = {t: float(p) for t, p in zip(sel, w)}

    vol = math.sqrt(w @ S @ w)
    ret = float(w @ mu + (1 - w.sum()) * mercado.rf)
    beta_c = float(w @ beta)
    sharpe = (ret - mercado.rf) / vol

    vetados = set(ranking.index[ranking["veto"]]) if "veto" in ranking else set()
    motivos = {t: ("Sale de cartera: veto por noticias negativas (IA)" if t in vetados
                   else "Sale de cartera: perdió ranking (momentum/beta/sharpe/noticias)")
               for t in est["posiciones"] if t not in pesos}
    motivos.update({t: "Ingresa a cartera: top del ranking" for t in pesos
                    if t not in est["posiciones"]})
    ordenes = generar_ordenes(est, mercado, pesos, motivos, forzar_una=(tipo == "rebalanceo"))
    ruta = publicar_ordenes(ordenes, tipo, pesos, sello)
    ruta_f = guardar_frontera(frontera(mu, S), mu, S, sel, w, mercado.rf, sello)

    cartera = pd.DataFrame({
        "peso": w, "retorno_esp": mu, "volatilidad": np.sqrt(np.diag(S)), "beta": beta,
        "rank": ranking.loc[sel, "rank"].values}, index=sel).sort_values("peso", ascending=False)
    cols = ["beta", "momentum", "sharpe", "volatilidad"]
    cols += ["score_cuant", "noticias"] if "noticias" in ranking else []
    top = ranking.head(C.N_ACTIVOS + C.BUFFER_RANKING + 2)[cols + ["score", "rank"]]

    resumen = (
        f"- Datos: {mercado.origen}, cierre {mercado.fecha}; tasa libre de riesgo {mercado.rf:.2%}\n"
        f"- Universo analizado: {len(met)} activos; elegibles por Beta >= {C.BETA_MINIMA_ACTIVO}: "
        f"{int((met['beta'] >= C.BETA_MINIMA_ACTIVO).sum())}\n"
        f"- **Cartera tangente**: retorno esperado {ret:.2%}, volatilidad {vol:.2%}, "
        f"Sharpe {sharpe:.2f}, Beta {beta_c:.2f}, efectivo {1 - w.sum():.1%}\n"
        + (f"- AVISO: {aviso}\n" if aviso else "")
    )
    cuerpo = (resumen
              + "\n### Ranking (selección por score)\n\n"
              + tabla_md(top, {"beta": "{:.2f}", "momentum": "{:.1%}", "sharpe": "{:.2f}",
                               "volatilidad": "{:.1%}", "score_cuant": "{:.2f}",
                               "noticias": "{:+.2f}", "score": "{:.2f}", "rank": "{:.0f}"})
              + "\n\n" + texto_ia
              + "\n### Pesos objetivo\n\n"
              + tabla_md(cartera, {"peso": "{:.1%}", "retorno_esp": "{:.1%}",
                                   "volatilidad": "{:.1%}", "beta": "{:.2f}", "rank": "{:.0f}"})
              + "\n\n### Órdenes a ejecutar en BymaLab\n\n" + tabla_ordenes(ordenes)
              + f"\n\nArchivos: `{ruta.name}`, `{ruta_f.name}`\n")
    bitacora("Armado inicial" if tipo == "armado" else "Rebalanceo semanal", cuerpo)
    print(cuerpo)
    print(f"\n>>> Ejecutá las órdenes en BymaLab, completá (si difieren) cantidad/precio "
          f"ejecutado en {ULTIMAS_CSV.relative_to(BASE)} y corré: python tpo.py confirmar")


def cmd_alertas(args):
    mercado = cargar_mercado(args)
    est = leer_estado()
    if ALERTA_ACTUAL.exists():
        ALERTA_ACTUAL.unlink()
    if not est["posiciones"]:
        print("Sin posiciones: no hay alertas que evaluar.")
        return

    total, valores = valuar(est, mercado)
    objetivo = dict(est.get("pesos_objetivo", {}))
    alertas, motivos, afectados = [], {}, set()

    for t, pos in est["posiciones"].items():
        us = C.UNIVERSO.get(t)
        if us not in mercado.usd:
            continue
        serie = mercado.usd[us].dropna()
        desde = serie[serie.index >= pd.Timestamp(pos["fecha_entrada"])]
        desde = desde if len(desde) else serie.iloc[-1:]
        caida = desde.iloc[-1] / desde.max() - 1
        ret20 = serie.iloc[-1] / serie.iloc[-21] - 1
        bajo_sma = serie.iloc[-1] < serie.iloc[-50:].mean()

        if caida <= -C.STOP_TRAILING:
            objetivo[t] = 0.0
            motivos[t] = f"STOP: cae {caida:.1%} (USD) desde su máximo desde la compra"
        elif ret20 <= -C.CAIDA_TENDENCIA and bajo_sma:
            objetivo[t] = objetivo.get(t, 0) / 2
            motivos[t] = f"TENDENCIA: {ret20:.1%} en 20 ruedas y bajo su media de 50 → reducir 50%"
        else:
            desvio = valores[t] / total - objetivo.get(t, 0)
            if desvio > C.DESVIO_ALERTA:
                motivos[t] = f"DESVÍO: sobrepondera {desvio:+.1%} vs objetivo → toma de ganancia"
            elif desvio < -C.DESVIO_ALERTA:
                motivos[t] = f"DESVÍO: subpondera {desvio:+.1%} vs objetivo"
            else:
                continue
        afectados.add(t)
        alertas.append(f"- **{t}**: {motivos[t]}")

    # Drawdown de la cartera actual (en USD) desde la primera compra.
    inicio = min(pd.Timestamp(p["fecha_entrada"]) for p in est["posiciones"].values())
    hist = sum(mercado.usd[C.UNIVERSO[t]] * p["cantidad"]
               for t, p in est["posiciones"].items() if C.UNIVERSO.get(t) in mercado.usd)
    hist = hist[hist.index >= inicio].dropna()
    dd = hist.iloc[-1] / hist.max() - 1 if len(hist) else 0.0
    if dd <= -C.DRAWDOWN_CARTERA:
        alertas.append(f"- **CARTERA**: drawdown de {dd:.1%} desde su máximo. Perfil agresivo de "
                       f"largo plazo: no se vende por esta regla, pero se adelanta el rebalanceo "
                       f"(correr `python tpo.py rebalancear`).")

    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"Datos: {mercado.origen}, cierre {mercado.fecha}. Valor cartera: $ {total:,.0f} "
          f"| Drawdown: {dd:.1%}")
    if not alertas:
        print("Sin alertas hoy.")
        return

    ordenes = generar_ordenes(est, mercado, objetivo, motivos, solo=afectados)
    if ordenes:
        publicar_ordenes(ordenes, "alerta", objetivo, sello)
    cuerpo = ("\n".join(alertas) + "\n\n### Órdenes generadas\n\n" + tabla_ordenes(ordenes)
              + ("\n\nEjecutarlas en BymaLab y correr `python tpo.py confirmar`.\n" if ordenes else "\n"))
    bitacora("ALERTA", cuerpo)
    ALERTA_ACTUAL.write_text(f"# Alerta del algoritmo — {mercado.fecha}\n\n{cuerpo}",
                             encoding="utf-8")
    print(cuerpo)


def cmd_confirmar(args):
    if not ULTIMAS_CSV.exists():
        sys.exit("No hay órdenes pendientes de confirmar.")
    meta = json.loads(ULTIMAS_META.read_text(encoding="utf-8"))
    est = leer_estado()
    hoy = datetime.now().strftime("%Y-%m-%d")
    filas = list(csv.DictReader(open(ULTIMAS_CSV, encoding="utf-8")))
    ejecutadas = []
    for f in filas:
        t = f["ticker"]
        cant = int(float(f["cantidad_ejecutada"] or f["cantidad"]))
        precio = float(f["precio_ejecutado"] or f["precio_ref_ars"])
        if cant <= 0:
            continue
        pos = est["posiciones"].get(t)
        if f["accion"] == "COMPRAR":
            est["efectivo_ars"] -= cant * precio * (1 + C.COMISION)
            if pos:
                nueva = pos["cantidad"] + cant
                pos["precio_compra_ars"] = (pos["precio_compra_ars"] * pos["cantidad"]
                                            + precio * cant) / nueva
                pos["cantidad"] = nueva
            else:
                est["posiciones"][t] = {"cantidad": cant, "precio_compra_ars": precio,
                                        "fecha_entrada": hoy}
        else:
            if not pos:
                print(f"AVISO: venta de {t} sin posición registrada; se ignora.")
                continue
            cant = min(cant, pos["cantidad"])
            est["efectivo_ars"] += cant * precio * (1 - C.COMISION)
            pos["cantidad"] -= cant
            if pos["cantidad"] == 0:
                del est["posiciones"][t]
        ejecutadas.append(f"- {f['accion']} {cant} {t} a $ {precio:,.2f}")

    est["pesos_objetivo"] = {t: p for t, p in meta["pesos_objetivo"].items()
                             if p > 0 and (t in est["posiciones"] or meta["tipo"] != "alerta")}
    est["ultima_operacion"] = {"fecha": hoy, "tipo": meta["tipo"], "archivo": meta["archivo"]}
    if est["efectivo_ars"] < 0:
        print(f"AVISO: el efectivo quedó negativo ($ {est['efectivo_ars']:,.0f}). "
              f"Revisá cantidades/precios ejecutados.")
    guardar_estado(est)
    ULTIMAS_CSV.unlink()
    ULTIMAS_META.unlink()
    texto = "\n".join(ejecutadas) or "- (ninguna orden ejecutada)"
    bitacora(f"Confirmación de ejecución ({meta['tipo']})",
             texto + f"\n\nEfectivo resultante: $ {est['efectivo_ars']:,.0f}")
    print(texto)
    print(f"Estado actualizado en {ESTADO.relative_to(BASE)}")


def cmd_estado(args):
    mercado = cargar_mercado(args)
    est = leer_estado()
    total, valores = valuar(est, mercado)
    print(f"Datos: {mercado.origen}, cierre {mercado.fecha}")
    print(f"Valor total: $ {total:,.0f}  |  Efectivo: $ {est['efectivo_ars']:,.0f}  |  "
          f"Resultado vs capital inicial: {total / C.CAPITAL_INICIAL_ARS - 1:+.2%}")
    if not est["posiciones"]:
        return
    met = metricas(mercado)
    df = pd.DataFrame({
        "cantidad": [p["cantidad"] for p in est["posiciones"].values()],
        "precio_compra": [p["precio_compra_ars"] for p in est["posiciones"].values()],
        "precio_actual": [float(mercado.ars.get(t, np.nan)) for t in est["posiciones"]],
        "peso": [valores[t] / total for t in est["posiciones"]],
        "objetivo": [est.get("pesos_objetivo", {}).get(t, 0) for t in est["posiciones"]],
        "beta": [met["beta"].get(t, np.nan) for t in est["posiciones"]],
    }, index=list(est["posiciones"]))
    df["resultado"] = df["precio_actual"] / df["precio_compra"] - 1
    print(tabla_md(df, {"precio_compra": "{:,.2f}", "precio_actual": "{:,.2f}", "peso": "{:.1%}",
                        "objetivo": "{:.1%}", "beta": "{:.2f}", "resultado": "{:+.1%}"}))
    print(f"\nBeta de la cartera: {(df['peso'] * df['beta']).sum():.2f}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("comando", choices=["armar", "rebalancear", "alertas", "confirmar", "estado"])
    p.add_argument("--demo", action="store_true", help="usar datos sintéticos (sin internet)")
    p.add_argument("--semilla", type=int, default=7, help="semilla de los datos demo")
    p.add_argument("--forzar", action="store_true", help="permitir 'armar' con posiciones")
    p.add_argument("--sin-noticias", action="store_true",
                   help="no usar la capa de IA de noticias (solo ranking cuantitativo)")
    args = p.parse_args()
    SALIDAS.mkdir(exist_ok=True)
    {"armar": lambda a: cmd_optimizar(a, "armado"),
     "rebalancear": lambda a: cmd_optimizar(a, "rebalanceo"),
     "alertas": cmd_alertas, "confirmar": cmd_confirmar, "estado": cmd_estado}[args.comando](args)


if __name__ == "__main__":
    main()
