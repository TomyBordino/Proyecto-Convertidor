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
3. **Probabilidad de cotizar más alto** en 20, 60 y 120 ruedas:
   - **Puntaje de factores con pesos fijos**: 50% tendencia (percentiles de pendiente de la SMA200,
     momentum 12-1, distancia a la SMA200 y al máximo anual) + 50% valuación (earnings, book, FCF y
     sales yield) cuando hay balances. Se eligió así porque con datos reales los modelos ajustados
     (logística y gradient boosting con 26 variables) no le ganaron a la tasa base fuera de muestra,
     y los factores clásicos sí (ver "Validación del modelo").
   - **Calibración isotónica walk-forward**: cada año se califica con una calibración ajustada solo
     con años anteriores; todas las métricas son fuera de muestra.
   - **Compuerta de habilidad**: si un horizonte no supera a la tasa base (Brier skill ≤ 0 o
     AUC < 0,51) se informa la tasa base con la leyenda "sin ventaja demostrada".
   - Historia de entrenamiento: 22 años de los subyacentes en EE. UU. (desde 2004) y balances SEC
     desde 2009, usados "point in time" (cada balance cuenta 100 días después del cierre).
   - Evidencia por predicción: frecuencia de acierto de situaciones con puntaje similar, intervalo
     de Wilson con n efectivo (ventanas superpuestas) y rango de retornos.
4. **Sesgo**: Favorable / Neutral / Desfavorable vs la tasa base, marcado como significativo cuando
   el intervalo de confianza de las situaciones similares excluye a la tasa base.

La página **Modelo** del dashboard muestra AUC, Brier skill score, calibración por decil, quintiles y
desempeño histórico por etapa.

### Validación del modelo (datos reales, 2004–2026, 414 activos)

Métricas fuera de muestra (walk-forward por año, con embargo):

| Horizonte | Tasa base | AUC | Brier skill | Años con AUC > 0,5 | Decil 1 vs deciles 5–8 |
| --- | --- | --- | --- | --- | --- |
| 20 ruedas | 54,8% | 0,519 | +0,0013 | 16/21 | 49% vs ~56–57% |
| 60 ruedas | 57,6% | 0,526 | +0,0027 | 15/21 | 49% vs ~60% |
| 120 ruedas | 60,0% | 0,539 | +0,0050 | 16/21 | 49% vs ~62–64% |

**Superar al universo** (rendir más que la mediana en el mismo período): con la misma validación
dio AUC 0,510 / 0,514 / 0,524 y Brier skill ≤ 0,0003, por debajo del mínimo de 0,0005 exigido, así
que se informa la tasa base (50%) con la leyenda "sin ventaja demostrada". El efecto existe en el
decil más débil (42–46% de las veces supera a la mediana) pero no alcanza para una probabilidad útil.

La tabla muestra además el **percentil del puntaje** (0–100), que desempata activos con la misma
probabilidad calibrada (la calibración agrupa en escalones donde la historia no distingue).

Antes de llegar a este modelo se probaron, con la misma validación, una regresión logística y
gradient boosting con 26 variables (AUC 0,51 y Brier skill negativo con 6 años de datos; con 22
años, el objetivo absoluto dio AUC < 0,5). La ventaja es moderada y está sobre todo en evitar los
activos peor puntuados. Los múltiplos históricos usan acciones ajustadas por splits: sin ese ajuste
las empresas que luego hicieron splits parecían baratas en el pasado (información del futuro).

## Eventos y noticias (capa de contexto)

Página **Eventos**, tarjeta "Eventos y noticias" en cada activo y columna *Contexto* en el ranking.
Nada de esta capa modifica el puntaje ni las probabilidades.

- **Eventos macro medidos** (`app/analytics/events.py`): 14 reglas sobre series reales de Yahoo
  (Tesoro 10 años y 3 meses, VIX, WTI/Brent, oro, DXY, soja/maíz/trigo, gas, cobre), por ejemplo
  "Tesoro 10 años +40 pb en 20 ruedas" o "Brent +15% en 20 ruedas". Para cada regla vigente se muestra
  el **estudio de eventos**: retorno de cada sector contra el universo en las 60 ruedas siguientes a
  cada ocurrencia desde 2004 (episodios separados por 60 ruedas), con % de veces que le ganó, IC95 y n.
  También se muestra la **sensibilidad** de cada activo y sector a cada factor (beta semanal de 3 años).
- **Noticias** (`app/services/news_ai.py`): titulares de Yahoo Finance por activo (los 120 de más
  volumen) y por tema (tasas, guerra/sanciones, petróleo/OPEP, clima, aranceles, China, Argentina,
  regulación). Claude clasifica cada titular con salida estructurada (JSON Schema): relevancia, tipo
  de evento, y sectores/activos afectados con dirección, magnitud, confianza y horizonte. Los destinos
  fuera del universo se descartan. La presión por activo es la suma de dirección × magnitud × confianza
  con vida media de 5 días; las noticias del sector pesan la mitad.
- Requiere `ANTHROPIC_API_KEY` en `backend/.env` (modelo `claude-opus-5-5`, `QB_NEWS_MODEL`). Sin clave,
  los titulares se muestran sin clasificar. Si Claude declina un lote, se reintenta automáticamente en
  el modelo de respaldo de Anthropic (`fallbacks="default"`).
- **¿Por qué no entra al modelo?** Se probó agregar VIX, Δ tasa 10 años, Brent, DXY, pendiente de la
  curva y las 14 reglas a la probabilidad calibrada, con la misma validación walk-forward. El AUC subió
  (0,511 → 0,526 a 20 ruedas) pero el Brier skill pasó a ser negativo en los tres horizontes (−0,026 /
  −0,032 / −0,109): los regímenes macro no se repiten lo suficiente como para calibrar con ellos.

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

### Windows, sin consola

Doble clic en **`Iniciar QuantBYMA.bat`** (carpeta `quant-byma`). La primera vez instala dependencias,
compila la web y crea el acceso directo **Quant BYMA** en el escritorio; después abre el navegador en
http://localhost:3000. Backend y web quedan corriendo en segundo plano (registros en `logs/`), con la
actualización automática de las 18:15 activada; si los datos tienen más de 20 horas, se actualizan solos
en segundo plano al abrir.

- **`Detener QuantBYMA.bat`**: cierra todo.
- **`Actualizar QuantBYMA.bat`**: baja la última versión del código (`git pull`), recompila y vuelve a abrir.

### Manual

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
