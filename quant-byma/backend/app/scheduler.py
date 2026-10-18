"""Tarea programada de ingesta diaria y CLI (`python -m app.scheduler --once`)."""

from __future__ import annotations

import argparse
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import get_settings
from app.db.session import init_engine, session_factory
from app.ingestion.providers import build_provider
from app.services.ingestion import run_ingestion

log = logging.getLogger(__name__)


def ingest_job(provider_kind: str | None = None) -> dict:
    settings = get_settings()
    provider = build_provider(provider_kind or settings.data_provider)
    with session_factory()() as session:
        result = run_ingestion(session, provider, history_days=settings.history_days)
    log.info("Ingesta %s: %s", provider.name, {k: v for k, v in result.items() if k != "errors"})
    return result


def start_scheduler() -> BackgroundScheduler:
    s = get_settings()
    scheduler = BackgroundScheduler(timezone="America/Argentina/Buenos_Aires")
    scheduler.add_job(
        ingest_job,
        "cron",
        day_of_week="mon-fri",
        hour=s.refresh_hour,
        minute=s.refresh_minute,
        id="daily_ingest",
        replace_existing=True,
    )
    scheduler.start()
    return scheduler


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Ingesta de datos Quant BYMA")
    parser.add_argument("--once", action="store_true", help="Ejecutar una ingesta y salir")
    parser.add_argument("--provider", choices=["auto", "yahoo", "demo"], default=None)
    args = parser.parse_args()
    init_engine()
    if args.once:
        res = ingest_job(args.provider)
        print({k: v for k, v in res.items() if k != "errors"}, "errores:", len(res["errors"]))
        return
    import time

    start_scheduler()
    log.info("Scheduler iniciado (Ctrl+C para salir)")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
