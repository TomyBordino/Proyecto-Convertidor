from datetime import date
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="QB_", extra="ignore")

    # SQLite para desarrollo local; en producción usar
    # postgresql+psycopg://user:pass@host:5432/quant (TimescaleDB, ver app/db/timescale.sql)
    database_url: str = "sqlite:///./quant.db"

    # real: fuentes reales con cadena de respaldo (ver app/ingestion/providers/real.py).
    # demo: series sintéticas, solo para tests/desarrollo sin red. Nunca se usa por defecto.
    data_provider: Literal["real", "yahoo", "demo"] = "real"
    # SEC EDGAR exige identificarse: "Nombre Apellido email@dominio".
    sec_user_agent: str = "QuantBYMA/0.1 (configurar QB_SEC_USER_AGENT)"
    tiingo_api_key: str = ""
    fmp_api_key: str = ""
    yahoo_fallback: bool = True
    # Plazo de liquidación de las series de BYMA Data ("24HS" desde la migración a T+1).
    byma_settlement: str = "24HS"
    history_days: int = 2200  # ~6 años de historia en BYMA
    # Historia de los subyacentes en EE. UU. para entrenar y validar el modelo (22+ años).
    model_history_start: date = date(2004, 1, 1)

    # Ingesta diaria (hora Buenos Aires) luego del cierre de BYMA (17:00).
    scheduler_enabled: bool = False
    refresh_hour: int = 18
    refresh_minute: int = 15

    # Capa de eventos: titulares interpretados con Claude. Sin clave, las noticias se
    # muestran sin clasificar y los eventos macro (series de mercado) siguen funcionando.
    anthropic_api_key: str = Field(
        default="", validation_alias=AliasChoices("ANTHROPIC_API_KEY", "QB_ANTHROPIC_API_KEY")
    )
    news_model: str = "claude-opus-5-5"
    news_enabled: bool = True
    # Activos (por volumen operado) cuyos titulares se buscan en cada corrida.
    news_max_tickers: int = 120
    news_lookback_days: int = 14

    # Panel histórico para el backtest (se regenera en cada ingesta).
    panel_cache_path: str = "./panel_cache.pkl"

    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
