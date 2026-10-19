"""Tarea programada de ingesta diaria y CLI (`python -m app.scheduler --once`)."""

from __future__ import annotations

import argparse
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import get_settings
from app.db.session import init_engine, session_factory
from app.ingestion.providers import build_provider
from app.services.ingestion import IngestionError, run_ingestion

log = logging.getLogger(__name__)


def check_sources() -> list[tuple[str, str, str]]:
    """Prueba cada fuente real con un símbolo conocido: (fuente, estado, detalle)."""
    from datetime import date, timedelta

    from app.ingestion.providers.real import RealDataProvider

    p = RealDataProvider.from_settings(get_settings())
    end = date.today()
    start = end - timedelta(days=30)
    results = []
    probes = [(src, "GGAL.BA") for src in p.local] + [(src, "AAPL") for src in p.us]
    for src, symbol in probes:
        try:
            df = src.history(symbol, start, end)
            status = "OK" if len(df) else "VACÍO"
            last = df.index.max().date() if len(df) else "—"
            results.append((src.name, status, f"{symbol}: {len(df)} ruedas, último {last}"))
        except Exception as exc:
            results.append((src.name, "FALLA", f"{symbol}: {exc}"[:200]))
    for fsrc in p.fund_sources:
        try:
            st = fsrc.fundamentals("AAPL")
            results.append((fsrc.name, "OK" if st else "VACÍO", f"AAPL: {len(st)} ejercicios"))
        except Exception as exc:
            results.append((fsrc.name, "FALLA", f"AAPL: {exc}"[:200]))
    if p.ccl_reference:
        try:
            ref = p.ccl_reference.ccl(start, end)
            results.append((p.ccl_reference.name, "OK", f"CCL: {len(ref)} días"))
        except Exception as exc:
            results.append((p.ccl_reference.name, "FALLA", str(exc)[:200]))
    return results


def ingest_job(provider_kind: str | None = None) -> dict:
    settings = get_settings()
    provider = build_provider(provider_kind or settings.data_provider)
    with session_factory()() as session:
        result = run_ingestion(
            session,
            provider,
            history_days=settings.history_days,
            us_history_start=settings.model_history_start,
        )
    log.info("Ingesta %s: %s", provider.name, {k: v for k, v in result.items() if k != "errors"})
    return result


def _scheduled_ingest() -> None:
    try:
        ingest_job()
    except IngestionError as exc:
        log.error("Ingesta programada abortada: %s", exc)


def start_scheduler() -> BackgroundScheduler:
    s = get_settings()
    scheduler = BackgroundScheduler(timezone="America/Argentina/Buenos_Aires")
    scheduler.add_job(
        _scheduled_ingest,
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
    parser.add_argument("--provider", choices=["real", "yahoo", "demo"], default=None)
    parser.add_argument("--check", action="store_true", help="Diagnosticar las fuentes reales")
    args = parser.parse_args()
    if args.check:
        for name, status, detail in check_sources():
            print(f"{status:6} {name:15} {detail}")
        return
    init_engine()
    if args.once:
        try:
            res = ingest_job(args.provider)
        except IngestionError as exc:
            log.error("%s", exc)
            raise SystemExit(1) from exc
        print({k: v for k, v in res.items() if k != "errors"})
        for e in res["errors"]:
            print("  -", e)
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
