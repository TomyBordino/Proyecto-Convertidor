# Quant BYMA — guía para Claude

Plataforma de análisis cuantitativo para acciones BYMA y CEDEARs. Vive en `quant-byma/`,
aislada del sitio estático (ConvertiYa) que ocupa la raíz del repositorio.

## Estructura
- `backend/` — Python 3.11+, FastAPI, pandas/numpy, SQLAlchemy 2 (SQLite en dev, PostgreSQL/TimescaleDB en prod).
  - `app/ingestion/` — universo de tickers y ratios (`universe.py`), CCL implícito/mercado (`ccl.py`),
    normalización ARS→USD (`normalization.py`), proveedores `yahoo` y `demo` (`providers/`).
  - `app/analytics/` — `technical.py` (SMA/EMA/RSI/MACD/Bollinger/ATR), `patterns.py`, `fundamental.py`,
    `scoring.py` (Composite Score), `screener.py` (DSL de filtros).
  - `app/services/` — pipeline de ingesta y cálculo de snapshots; `app/api/` — rutas `/api/*`.
  - `app/db/timescale.sql` — hypertables, compresión y agregado continuo para producción.
- `frontend/` — Next.js 16 (App Router, `cacheComponents`), Tailwind v4, componentes estilo shadcn/ui
  escritos a mano en `src/components/ui`, lightweight-charts v5 y Recharts. Datos vía SWR en el cliente;
  `/api/*` se reescribe al backend (`BACKEND_URL`, default `http://localhost:8000`).

## Comandos
Backend (desde `quant-byma/backend`):
```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
python -m app.scheduler --once --provider demo   # ingesta (demo | yahoo | auto)
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
- Configuración por variables `QB_*` (ver `backend/app/config.py`).
- Toda función de ratio devuelve `None` si el dato falta o no tiene sentido económico; el scoring re-escala
  los componentes disponibles, nunca penaliza por falta de datos.
- Respuestas JSON sin NaN/Infinity (`_f()` en `services/analytics.py`).
- Next 16: accesos a `params`/`usePathname` van dentro de `<Suspense>`; leer `node_modules/next/dist/docs/` ante dudas.
- lightweight-charts solo acepta colores hex/rgb (no los tokens oklch) y se le fija `locale: "es-AR"`.
- Los ratios de CEDEAR en `universe.py` deben verificarse contra el listado oficial de BYMA.
