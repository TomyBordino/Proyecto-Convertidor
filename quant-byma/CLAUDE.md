# Quant BYMA — guía para Claude

Plataforma de análisis cuantitativo para acciones BYMA y CEDEARs. Vive en `quant-byma/`,
aislada del sitio estático (ConvertiYa) que ocupa la raíz del repositorio.

## Estructura
- `backend/` — Python 3.11+, FastAPI, pandas/numpy, SQLAlchemy 2 (SQLite en dev, PostgreSQL/TimescaleDB en prod).
  - `app/ingestion/` — universo de tickers y ratios (`universe.py`), CCL implícito/mercado (`ccl.py`),
    normalización ARS→USD (`normalization.py`), proveedores en `providers/`: `real.py` (cadena BYMA Data →
    data912 → Yahoo para BYMA; Tiingo → Stooq → Yahoo para EE. UU.; SEC EDGAR → FMP → Yahoo para balances;
    argentinadatos para CCL de referencia), `demo.py` (sintético, solo tests).
  - `app/ingestion/discovery.py` — universo desde el panel en vivo de data912, overrides de subyacente,
    estimación de ratios con precios reales e historia de cambios de ratio.
  - `app/analytics/` — `technical.py` (SMA/EMA/RSI/MACD/Bollinger/ATR), `patterns.py`, `fundamental.py`,
    `scoring.py` (Composite Score), `screener.py` (DSL de filtros), `regime.py` (etapas de Weinstein),
    `model.py` (panel point-in-time, puntaje de factores tendencia+valuación con pesos fijos,
    calibración isotónica walk-forward, compuerta de habilidad, evidencia).
  - `app/services/diagnosis.py` — etapa + momento fundamental + probabilidades por activo.
  - `app/services/` — pipeline de ingesta y cálculo de snapshots; `app/api/` — rutas `/api/*`.
  - `app/db/timescale.sql` — hypertables, compresión y agregado continuo para producción.
- `frontend/` — Next.js 16 (App Router, `cacheComponents`), Tailwind v4, componentes estilo shadcn/ui
  escritos a mano en `src/components/ui`, lightweight-charts v5 y Recharts. Datos vía SWR en el cliente;
  `/api/*` se reescribe al backend (`BACKEND_URL`, default `http://localhost:8000`).

## Comandos
Backend (desde `quant-byma/backend`):
```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
python -m app.scheduler --check                  # diagnóstico de cada fuente real
python -m app.scheduler --once                   # ingesta real (--provider real | yahoo | demo)
uvicorn app.main:app --reload --port 8000        # dev API
python -m pytest                                 # tests
ruff check . && ruff format --check . && mypy app   # lint + tipos
```
Frontend (desde `quant-byma/frontend`):
```bash
npm install
npm run dev      # http://localhost:3000
npm run build    # compila + typecheck
npm run lint     # eslint
npx tsc --noEmit
```
Base de datos de producción: `docker compose up -d db`, luego `QB_DATABASE_URL=postgresql+psycopg://quant:quant@localhost:5432/quant`,
correr una ingesta y `psql "$URL" -f backend/app/db/timescale.sql`.

## Convenciones
- Configuración por variables `QB_*` (ver `backend/app/config.py` y `backend/.env.example`).
- Nunca caer a datos sintéticos de forma implícita: `demo` solo con `--provider demo` o en tests.
- Los tests de proveedores usan `httpx.MockTransport` con payloads del formato de cada API.
- Fundamentales de ADRs: el precio del ADR se divide por el ratio (`per_share_close`) porque los 20-F
  informan acciones ordinarias.
- No reemplazar el puntaje de factores por un modelo ajustado sin mostrar que mejora AUC y Brier skill
  fuera de muestra (walk-forward) en la historia larga; con los datos actuales los ajustados no ganaron.
- Las probabilidades se reportan siempre con métricas fuera de muestra; nunca evaluar el modelo con datos
  usados para entrenarlo. Features solo con información disponible a la fecha (`test_no_lookahead_in_features`).
- Las fallas de red levantan `SourceUnavailableError` (cuentan para el circuit breaker); un símbolo
  inexistente levanta `ProviderError` (no cuenta).
- Toda función de ratio devuelve `None` si el dato falta o no tiene sentido económico; el scoring re-escala
  los componentes disponibles, nunca penaliza por falta de datos.
- Respuestas JSON sin NaN/Infinity (`_f()` en `services/analytics.py`).
- Next 16: accesos a `params`/`usePathname` van dentro de `<Suspense>`; leer `node_modules/next/dist/docs/` ante dudas.
- lightweight-charts solo acepta colores hex/rgb (no los tokens oklch) y se le fija `locale: "es-AR"`.
- Los ratios de CEDEAR en `universe.py` deben verificarse contra el listado oficial de BYMA.
