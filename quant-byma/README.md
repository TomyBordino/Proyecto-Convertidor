# Quant BYMA

Plataforma de análisis técnico y fundamental para acciones argentinas (BYMA) y CEDEARs, con
normalización por CCL y un motor de scoring cuantitativo.

## Arquitectura

```
 BYMA Data · data912 · Tiingo   ─┐                     ┌─ /api/rankings, /api/screener/run
 Stooq · SEC EDGAR · FMP · Yahoo ─┼─▶ Ingesta (APScheduler) ─▶ PostgreSQL/TimescaleDB ─▶ FastAPI ─▶ Next.js
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

## Universo

La ingesta descubre todas las especies con operaciones en BYMA desde el panel en vivo de data912
(~400 CEDEARs y ~70 acciones locales) además de los 42 activos "ancla" de `universe.py`.

- **Ratios de CEDEAR**: ninguna API pública accesible los publica, así que se deducen de precios
  reales: `ratio = CCL × precio_US / precio_BYMA` (mediana de 20 ruedas, redondeada al entero). Se
  acepta solo si la serie es estable (dispersión < 3%) y cae cerca de un entero; la confianza queda
  guardada en cada activo. Validado contra los 37 ratios curados: 37/37 coincidencias.
- **Cambios de ratio históricos** (p. ej. los cambios masivos de BYMA del 18/11/2022 y 25/01/2024)
  se detectan automáticamente y se usan para calcular CCL implícitos históricos correctos.
- **Subyacente**: mismo ticker en EE. UU. salvo los overrides de `discovery.py`; un mapeo incorrecto
  produce un ratio inestable y el activo queda inactivo con el motivo.
- La ingesta es incremental: si un activo ya tiene historia, solo baja las ruedas nuevas.

## Diagnóstico y probabilidades

Cada activo recibe:

1. **Momento técnico**: etapa de Weinstein (1 base · 2 tendencia alcista · 3 techo · 4 tendencia
   bajista, con la media de 30 semanas y su pendiente) y un submomento (pullback, sobreextendida,
   en máximos, rebote, sobrevendida…).
2. **Momento fundamental**: percentiles de valuación (P/E, P/S, P/B), calidad (ROE), crecimiento y
   endeudamiento contra su sector (o el universo si el sector tiene menos de 5 empresas).
3. **Probabilidad de cotizar más alto** en 20, 60 y 120 ruedas, de una regresión logística:
   - features sin mirar el futuro (los balances cuentan 100 días después del cierre);
   - validación walk-forward por año con embargo; todas las métricas son fuera de muestra;
   - calibración isotónica sobre esas predicciones;
   - evidencia por predicción: frecuencia de acierto de situaciones históricas con puntaje similar,
     intervalo de Wilson con n efectivo (ventanas superpuestas) y rango de retornos;
   - factores que explican cada probabilidad (coeficiente × valor estandarizado).
4. **Sesgo**: Favorable / Neutral / Desfavorable vs la tasa base, marcado como significativo cuando
   el intervalo de confianza de las situaciones similares excluye a la tasa base.

La página **Modelo** del dashboard muestra AUC, Brier skill score, calibración por decil, quintiles y
desempeño histórico por etapa.

## Fuentes de datos reales

El proveedor por defecto (`QB_DATA_PROVIDER=real`) combina fuentes con cadena de respaldo y
**nunca** usa datos sintéticos: si ninguna fuente responde, la ingesta aborta sin tocar la base.

| Dato | Fuente principal | Respaldo | Notas |
| --- | --- | --- | --- |
| Precios BYMA (ARS) | **BYMA Data** (`open.bymadata.com.ar`, oficial) | data912.com → Yahoo `.BA` | Plazo `24HS` configurable |
| Precios EE. UU. (USD) | **Tiingo** (con `QB_TIINGO_API_KEY`) | Yahoo (descarga en lote) → Stooq | Precios sin ajustar por dividendos |
| Balances | **SEC EDGAR** XBRL (10-K y 20-F, oficial) | FMP (con `QB_FMP_API_KEY`) → Yahoo | Requiere `QB_SEC_USER_AGENT` |
| CCL de referencia | argentinadatos.com | — | Valida el CCL calculado |

Las acciones locales sin ADR (TXAR, ALUA, COME, TRAN, BYMA) no tienen balances en una API estructurada
(la CNV publica PDFs): se analizan sin componente fundamental salvo que Yahoo lo provea.

Diagnóstico de conectividad: `python -m app.scheduler --check`.

Detalles de la integración:
- BYMA Data publica ~2 años de historia: el tramo anterior se completa con data912/Yahoo,
  reescalado al ajuste por splits de la fuente principal (data912 publica precios crudos).
- La API XBRL de la SEC a veces no incluye los estados de 20-F recientes; si el último
  ejercicio tiene más de 15 meses se agregan los posteriores de Yahoo en la misma moneda.
- Una fuente con 3 fallas seguidas se saltea por el resto de la corrida (circuit breaker).

### Validación con datos reales (rueda del 2026-10-16)

- 42/42 activos ingeridos, 115.313 ruedas, balances para los 40 que no son ETFs.
- CCL calculado 1.618,76 vs 1.615,75 publicado (argentinadatos): +0,19%; desvío absoluto
  medio 0,30% en 2026 y 0,78% en 2025.
- CCL implícito de los 42 activos dentro de ±0,8% del de mercado.
- La validación detectó y corrigió: SPY 60:1 (no 20:1), YPFD 10:1 tras su split local del
  2026-08-03 y el ticker de Disney en BYMA (DISN).

Dominios que tiene que permitir la red donde corra la ingesta:
`open.bymadata.com.ar`, `data912.com`, `api.tiingo.com`, `stooq.com`, `www.sec.gov`, `data.sec.gov`,
`financialmodelingprep.com`, `api.argentinadatos.com`, `query1.finance.yahoo.com`,
`query2.finance.yahoo.com`, `fc.yahoo.com`.

## Pendientes

Ver [PENDIENTES.md](PENDIENTES.md).

## Puesta en marcha

```bash
cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
cp .env.example .env                              # completar QB_SEC_USER_AGENT (y API keys opcionales)
python -m app.scheduler --check                   # verifica cada fuente
python -m app.scheduler --once                    # ingesta con datos reales
uvicorn app.main:app --port 8000
cd ../frontend && npm install && npm run dev     # http://localhost:3000
```

Con `QB_SCHEDULER_ENABLED=true` la API corre la ingesta de lunes a viernes a las 18:15 (hora de Buenos Aires).

> El proveedor **demo** (`--provider demo`) genera series sintéticas solo para tests; la interfaz muestra un
> aviso permanente cuando la base contiene esos datos. Los ratios de CEDEAR de `universe.py` son la referencia de carga inicial: verificalos contra
> BYMA. Nada de esto es recomendación de inversión.
