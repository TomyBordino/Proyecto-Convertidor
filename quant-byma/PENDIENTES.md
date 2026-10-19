# Pendientes

Estado al 2026-10-18, después de validar la ingesta con datos reales (ver README → "Validación").

## Configuración (requieren acción del usuario)

- [ ] **Identificador para SEC EDGAR**: cargar `QB_SEC_USER_AGENT="Nombre Apellido email@dominio"`.
      La ingesta funciona con el valor genérico, pero la política de acceso de la SEC pide
      un contacto real.
- [ ] **API key de Tiingo** (`QB_TIINGO_API_KEY`, plan gratuito): Stooq rechaza conexiones desde
      el entorno cloud, así que hoy los precios de EE. UU. vienen de Yahoo (último respaldo).
- [ ] **API key de Anthropic** (`ANTHROPIC_API_KEY` en `backend/.env`): habilita la interpretación de
      titulares con Claude. Costo estimado: ~US$1–2 la primera corrida (≈800 titulares) y menos
      después, porque solo se clasifican los titulares nuevos.
- [ ] **API key de FMP** (`QB_FMP_API_KEY`, opcional): respaldo de balances antes de Yahoo.
- [ ] **Ratios de CEDEAR**: los ~300 ratios del universo descubierto se estiman con precios reales
      (37/37 coincidencias contra los curados). Conviene contrastarlos con el listado oficial de
      BYMA/Comafi cuando haya una fuente accesible; los de confianza baja quedan inactivos.

## Datos

- [ ] **YPF**: cuando YPF publique un 20-F con las acciones posteriores al split local de
      agosto 2026, cambiar `reported_shares_per_unit=1` por `10` en `universe.py`.
- [ ] **Balances bajo NIC 29** (ADRs argentinos en ARS): hoy los flujos se convierten con el CCL
      promedio del ejercicio, pero vienen reexpresados a moneda de cierre. Convertirlos con el
      CCL de cierre sería más preciso.
- [ ] **Locales sin ADR** (TXAR, ALUA, COME, TRAN, BYMA): sus balances dependen solo de Yahoo.
      Evaluar otra fuente (la CNV publica PDFs, no una API).
- [ ] **EV/EBITDA faltante** en algunos emisores IFRS (GLOB, BABA, YPF) que no informan
      amortizaciones con los conceptos XBRL mapeados.
- [ ] **Cambios de ratio de CEDEAR en la historia**: el CCL implícito histórico de cada activo se
      calcula con el ratio actual. La mediana de mercado es robusta (filtro MAD), pero el
      gráfico por activo puede mostrar saltos antes de un cambio de ratio si la fuente no
      publica la serie ajustada.

## Eventos

- [ ] Más fuentes de noticias: Google News, GDELT, FRED (tasas/inflación oficiales) y BCRA están
      bloqueadas por la política de red del entorno; habilitarlas daría cobertura en español y
      series oficiales. Evaluar también los 8-K de la SEC (hechos relevantes por empresa).
- [ ] Validar fuera de muestra la presión de noticias como factor cuando haya meses de historial
      clasificado (hoy solo se acumula desde la primera corrida).

## Modelo

- [ ] Evaluar features adicionales: revisiones de estimaciones de analistas, sorpresas de
      resultados, flujo de CEDEARs (volumen anómalo en BYMA), tasa real y riesgo país.
- [ ] Probar modelos no lineales (gradient boosting) contra la logística con la misma validación
      walk-forward; adoptarlos solo si mejoran AUC y calibración fuera de muestra.
- [ ] Objetivo relativo (superar al universo/al SPY) además de "subir en USD".

## Infraestructura

- [ ] **Publicar online** (decidido para más adelante): web en Netlify y backend + PostgreSQL + ingesta
      diaria en Railway (la ingesta necesita varios GB de RAM y minutos de ejecución; Netlify solo no
      alcanza). Con usuario y contraseña, y con las acciones que gastan (actualizar datos, clasificar
      noticias con Claude) protegidas. Hoy se usa el lanzador local (`Iniciar QuantBYMA.bat`).

- [ ] **TimescaleDB**: probar `docker compose up -d db` + `app/db/timescale.sql` (no se ejecutó;
      el entorno de desarrollo no tenía Docker).
- [ ] **Deploy**: hoy corre solo en local. Falta definir hosting (backend + DB + scheduler
      diario y frontend).
- [ ] **CI**: agregar un workflow que corra pytest, ruff, mypy, eslint y `next build` en cada PR.
