"""
Parámetros del algoritmo — Perfil 3: Inversor joven de alto riesgo / Tecnológico.

Todo lo que define el comportamiento del algoritmo vive en este archivo.
La "intervención humana" permitida por el reglamento es definir estas reglas
ANTES de empezar; durante la simulación no se tocan (si se tocan, dejarlo
registrado en la bitácora y justificarlo en el informe).
"""

# --- Capital y costos -------------------------------------------------------
CAPITAL_INICIAL_ARS = 100_000_000   # Ajustar al saldo inicial real de BymaLab
COMISION = 0.006                    # Comisión + derechos estimados por operación (0,6%)
EFECTIVO_MINIMO = 0.02              # Liquidez mínima que se deja sin invertir (2%)

# --- Universo de inversión ---------------------------------------------------
# ticker BYMA -> ticker en EE.UU. (subyacente del CEDEAR o ADR de la acción local).
# El análisis (retornos, beta, covarianzas) se hace en USD con el ticker de EE.UU.
# para que la devaluación del peso no "infle" los rendimientos; las cantidades
# a operar se calculan con el precio en pesos de BYMA (<ticker>.BA en Yahoo).
UNIVERSO = {
    # CEDEARs tecnológicos / growth
    "NVDA": "NVDA", "AMD": "AMD", "AVGO": "AVGO", "TSM": "TSM", "MU": "MU",
    "QCOM": "QCOM", "AAPL": "AAPL", "MSFT": "MSFT", "GOOGL": "GOOGL",
    "AMZN": "AMZN", "META": "META", "NFLX": "NFLX", "TSLA": "TSLA",
    "MELI": "MELI", "PLTR": "PLTR", "SHOP": "SHOP", "UBER": "UBER",
    "COIN": "COIN", "MSTR": "MSTR", "CRM": "CRM", "ADBE": "ADBE",
    "ORCL": "ORCL", "PYPL": "PYPL", "SPOT": "SPOT", "NU": "NU",
    # ETFs (CEDEARs)
    "QQQ": "QQQ", "ARKK": "ARKK",
    # Acciones argentinas (ADR en EE.UU.) — alta volatilidad local
    "GGAL": "GGAL", "YPFD": "YPF", "PAMP": "PAM", "BMA": "BMA", "VIST": "VIST",
    "TGSU2": "TGS", "CEPU": "CEPU", "SUPV": "SUPV", "BBAR": "BBAR",
}

BENCHMARK = "SPY"          # Cartera de mercado para medir la Beta
TASA_LIBRE_RIESGO = 0.04   # Se usa si no se puede descargar la tasa de T-Bills (^IRX)
PRIMA_MERCADO = 0.055      # Prima de riesgo de mercado (CAPM) anual

# --- Selección de activos (alta Beta + momentum) -----------------------------
VENTANA_DIAS = 252          # 1 año de ruedas para beta, volatilidad y covarianzas
BETA_MINIMA_ACTIVO = 1.0    # Filtro: solo activos con Beta >= 1 vs SPY
N_ACTIVOS = 10              # Cantidad de activos en cartera
BUFFER_RANKING = 3          # Un activo ya en cartera se mantiene si rankea dentro de N + BUFFER
PESO_SCORE = {              # Ponderación del score de ranking (z-scores)
    "momentum": 0.45,       # Retorno 12 meses excluyendo el último mes (12-1)
    "beta": 0.30,           # Beta vs SPY
    "sharpe": 0.25,         # Sharpe histórico 1 año
}

# --- Optimización (frontera eficiente / cartera tangente) --------------------
PESO_MIN = 0.04             # Peso mínimo por activo seleccionado
PESO_MAX = 0.20             # Peso máximo por activo (control de concentración)
BETA_MINIMA_CARTERA = 1.2   # Restricción: la cartera completa debe tener Beta >= 1.2
SHRINK_COV = 0.30           # Contracción de la matriz de covarianzas hacia la diagonal
MEZCLA_CAPM = 0.5           # Retorno esperado = 50% CAPM + 50% histórico (reduce sobreajuste)

# --- Rebalanceo semanal ------------------------------------------------------
BANDA_REBALANCEO = 0.02     # Se opera un activo si su peso se desvía > 2 p.p. del objetivo
MONTO_MINIMO_ORDEN = 0.005  # No se generan órdenes menores al 0,5% de la cartera

# --- Alertas diarias ---------------------------------------------------------
STOP_TRAILING = 0.15        # Venta total si el activo cae 15% (en USD) desde su máximo desde la compra
CAIDA_TENDENCIA = 0.10      # Reducir 50% si cae >10% en 20 ruedas Y cotiza bajo su media de 50
DESVIO_ALERTA = 0.05        # Alerta de rebalanceo anticipado si un peso se desvía > 5 p.p.
DRAWDOWN_CARTERA = 0.12     # Alerta general si la cartera cae 12% desde su máximo

# --- Capa de IA: análisis de noticias con un modelo de lenguaje ---------------
USAR_NOTICIAS = True          # Si es False (o falta ANTHROPIC_API_KEY) se usa solo el ranking cuantitativo
MODELO_IA = "claude-opus-5-5"
N_CANDIDATOS_NOTICIAS = 18    # Se analizan los 18 mejores del ranking cuantitativo + los que ya están en cartera
DIAS_NOTICIAS = 10            # Antigüedad máxima de las noticias consideradas
MAX_BUSQUEDAS_WEB = 20        # Límite de búsquedas web por corrida (controla costo)
PESO_NOTICIAS = 0.5           # score_final = score_cuant + 0,5 × sentimiento × confianza
VETO_NOTICIAS = -0.6          # Si sentimiento × confianza <= -0,6 el activo queda excluido
