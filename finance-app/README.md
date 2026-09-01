# Finanzas.ai

App de finanzas con cotizaciones de Wall Street y Argentina, ratios financieros
por empresa, y una sección de Análisis con IA que proyecta valuaciones futuras.

Es un proyecto separado del convertidor de archivos de este repositorio: vive en
`finance-app/` con su propio backend y frontend, sin compartir código ni deploy.

## Arquitectura

```
finance-app/
├── backend/   # API en Node/Express + TypeScript
└── frontend/  # SPA en React + Vite + TypeScript + Tailwind
```

El backend existe porque las claves de proveedores de datos/IA no deben quedar
expuestas en el navegador, y porque cachear y normalizar cotizaciones de dos
mercados distintos es más simple del lado del servidor.

### Backend (`finance-app/backend`)

- **Cotizaciones de EE.UU.**: [`yahoo-finance2`](https://www.npmjs.com/package/yahoo-finance2)
  (API no oficial de Yahoo Finance, sin necesidad de API key).
- **Cotizaciones de Argentina**: [`data912.com`](https://data912.com) (API pública
  de BYMA/CEDEARs sin autenticación) como fuente primaria, con fallback automático
  a Yahoo Finance (sufijo `.BA`) si data912 no responde o cambia su formato.
  Ver el comentario al inicio de `src/services/providers/arProvider.ts`: como
  data912 no tiene documentación oficial estable, el parseo es defensivo.
- **Ratios financieros**: se derivan de los mismos datos de cada proveedor
  (P/E, P/B, P/S, ROE, ROA, márgenes, deuda/patrimonio, crecimiento, beta, etc.).
  La lista completa con etiquetas y descripciones vive en `src/services/ratios.ts`.
- **Análisis con IA** (`src/services/valuation.ts`): estima un CAGR histórico
  con una regresión log-lineal sobre el precio de cierre, y proyecta 3 escenarios
  (conservador / base / optimista) a `N` años. La narrativa que acompaña la
  proyección se genera por reglas (`HeuristicNarrativeProvider`) por defecto, y
  automáticamente pasa a usar un modelo real de Anthropic
  (`AnthropicNarrativeProvider`, en `src/services/ai/narrativeProvider.ts`) si
  configurás `ANTHROPIC_API_KEY` — con fallback a la versión heurística si la
  llamada al modelo falla.

### Frontend (`finance-app/frontend`)

- Dashboard con watchlist por defecto + buscador, separado por mercado
  (`/us` y `/ar`).
- Vista de detalle por ticker con precio y tabla de ratios (`/:market/:symbol`).
- Sección de Análisis con IA con formulario de supuestos (horizonte, crecimiento,
  tasa de referencia) y gráfico de escenarios (`/:market/:symbol/analisis`).

## Cómo correrlo localmente

```bash
# Backend
cd finance-app/backend
cp .env.example .env
npm install
npm run dev        # http://localhost:4000

# Frontend (en otra terminal)
cd finance-app/frontend
cp .env.example .env.local
npm install
npm run dev         # http://localhost:5173
```

## Variables de entorno

**Backend** (`finance-app/backend/.env`, ver `.env.example`):

| Variable | Requerida | Descripción |
|---|---|---|
| `PORT` | No | Puerto del servidor (default `4000`). |
| `CORS_ORIGIN` | No | Origen permitido para CORS (default `http://localhost:5173`). |
| `ANTHROPIC_API_KEY` | No | Si se define, la narrativa del análisis la genera un modelo de Anthropic real. |
| `ANTHROPIC_MODEL` | No | Modelo a usar (default `claude-sonnet-5`). |
| `DATA912_BASE_URL` | No | Override de la URL base de data912, por si cambia. |

**Frontend** (`finance-app/frontend/.env.local`, ver `.env.example`):

| Variable | Requerida | Descripción |
|---|---|---|
| `VITE_API_BASE_URL` | No | URL del backend (default `http://localhost:4000`). |

No se necesita ninguna API key para levantar la app: todo funciona con
proveedores gratuitos/sin autenticación por defecto.

## Testing

```bash
cd finance-app/backend
npm test         # vitest — cubre el motor de proyección (CAGR, escenarios, clamping)
npm run typecheck
npm run build

cd finance-app/frontend
npm run build     # incluye typecheck (tsc -b) + build de Vite
```

## Limitaciones conocidas / próximos pasos

- **Cotizaciones no oficiales**: tanto `yahoo-finance2` como data912 son APIs
  no oficiales y sin SLA. Yahoo puede exigir un flujo de cookies/crumb que
  algunos entornos de red restringidos (proxies corporativos, ciertos hosting
  serverless) bloquean — si ves el error *"No set-cookie header present in
  Yahoo's response"*, es ese flujo fallando por la red, no un bug de la app.
  Para producción seria, migrar a un proveedor pago (Alpha Vantage, Finnhub,
  IOL, etc.) sólo implica escribir un nuevo `QuoteProvider` (ver
  `src/services/providers/quoteProvider.ts`) sin tocar rutas ni frontend.
- **Fundamentals en Argentina**: muchas acciones y la mayoría de los CEDEARs
  locales no tienen ratios propios cargados en Yahoo bajo el sufijo `.BA`; en
  esos casos la tabla de ratios muestra "N/D" en vez de romper.
  Cotizaciones y ratios de Wall Street sí normalizan bien.
- **Análisis con IA**: el motor de proyección es un ejercicio cuantitativo
  (tendencia histórica + escenarios), no una predicción real de mercado — el
  disclaimer se muestra siempre en la UI. Con `ANTHROPIC_API_KEY` configurada,
  la narrativa la redacta un LLM real en vez del generador por reglas.
- **Sin persistencia**: no hay login, portfolios guardados ni base de datos
  todavía. La cache es en memoria (se pierde al reiniciar el backend).
