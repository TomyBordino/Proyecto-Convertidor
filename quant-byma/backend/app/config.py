from functools import lru_cache
from typing import Literal

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
    history_days: int = 2200  # ~6 años: 5 balances anuales con precio

    # Ingesta diaria (hora Buenos Aires) luego del cierre de BYMA (17:00).
    scheduler_enabled: bool = False
    refresh_hour: int = 18
    refresh_minute: int = 15

    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
