"""Ingesta en segundo plano disparada desde la web.

Una ingesta tarda minutos: correrla dentro del request hace que el proxy de Next corte la
conexión ("Internal Server Error") aunque la ingesta siga. Acá se lanza en un hilo y la web
consulta el estado.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict[str, Any] = {"running": False, "started_at": None, "finished_at": None, "error": None}


def status() -> dict[str, Any]:
    with _lock:
        return dict(_state)


def start(job: Callable[[], dict]) -> bool:
    """Lanza `job` si no hay otra ingesta corriendo. Devuelve False si ya había una."""
    with _lock:
        if _state["running"]:
            return False
        _state.update(
            running=True, started_at=datetime.now(UTC).isoformat(), finished_at=None, error=None
        )

    def run() -> None:
        error = None
        try:
            job()
        except Exception as exc:  # se informa en /api/ingest/status
            log.exception("Ingesta desde la web")
            error = str(exc)[:500]
        with _lock:
            _state.update(running=False, finished_at=datetime.now(UTC).isoformat(), error=error)

    threading.Thread(target=run, name="ingesta-web", daemon=True).start()
    return True
