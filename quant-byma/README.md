# Quant BYMA

Plataforma de análisis técnico y fundamental para acciones argentinas (BYMA) y CEDEARs, con
normalización por CCL y un motor de scoring cuantitativo.

## Arquitectura

```
 Yahoo Finance (.BA + EE. UU.)  ─┐                     ┌─ /api/rankings, /api/screener/run
 Proveedor demo (sin red)       ─┼─▶ Ingesta (APScheduler) ─▶ PostgreSQL/TimescaleDB ─▶ FastAPI ─▶ Next.js
                                 │   precios BA/US, balances,   (SQLite en dev)          └─ /api/instruments/{t}/…
                                 └─▶ CCL implícito + snapshots de score
```

1. **Ingesta y normalización** — cada activo tiene su símbolo BYMA, su par en EE. UU. (subyacente o ADR) y su
   ratio. `CCL implícito = precio BA × ratio / precio US`; el CCL de mercado es la mediana ponderada por volumen
   tras descartar outliers por MAD (detecta ratios desactualizados). Los balances en ARS se pasan a USD: stocks
   al CCL de cierre, flujos al CCL promedio del ejercicio (también hay ajuste por CPI).
2. **Técnico** — SMA/EMA 20/50/200, RSI y ATR de Wilder, MACD 12/26/9, Bollinger 20/2; golden/death cross,
   breakouts de 55 ruedas con volumen y divergencias de RSI. Se analiza la serie en moneda dura (subyacente/ADR,
   o precio local / CCL si no hay par).
3. **Fundamental** — P/E, P/S, EV/EBITDA, P/B, ROE, ROIC, crecimiento de revenue, FCF yield, D/E,
   current ratio y Altman Z (no aplicado a financieras).
4. **Composite Score (0–100)** — técnico 40% (tendencia, RSI 40–60 con tendencia previa, MACD, %B, eventos),
   fundamental 35% (descuento vs histórico propio y vs sector, calidad, crecimiento, salud) y CCL 25%
   (desvío −5% → 100, +5% → 0). Los grupos sin datos se excluyen y se re-normalizan los pesos.
   Cada snapshot guarda el desglose por componente.
5. **Dashboard** — ranking con filtros y orden, vista por activo (velas ARS / USD CCL / subyacente con
   SMA, Bollinger, RSI y MACD; CCL implícito vs mercado; fundamentales; desglose del score), screener con
   filtros guardables y página de CCL.

## Puesta en marcha

```bash
cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
python -m app.scheduler --once --provider auto   # Yahoo si hay red, demo si no
uvicorn app.main:app --port 8000
cd ../frontend && npm install && npm run dev     # http://localhost:3000
```

Con `QB_SCHEDULER_ENABLED=true` la API corre la ingesta de lunes a viernes a las 18:15 (hora de Buenos Aires).

> El proveedor **demo** genera series sintéticas determinísticas (no son cotizaciones reales) para desarrollar
> y testear sin red. Los ratios de CEDEAR de `universe.py` son la referencia de carga inicial: verificalos contra
> BYMA. Nada de esto es recomendación de inversión.
