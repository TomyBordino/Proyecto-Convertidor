"""Cliente HTTP compartido por los proveedores reales.

- Reintentos con backoff exponencial ante 429/5xx y errores de red.
- Rate limit mínimo por host (SEC EDGAR exige ≤ 10 req/s; BYMA y data912 son servicios
  gratuitos que conviene no saturar).
- Un 403/404 no se reintenta: suele ser política de red o símbolo inexistente.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from app.ingestion.providers.base import ProviderError, SourceUnavailableError

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}
DEFAULT_MIN_INTERVAL = 0.25  # segundos entre requests al mismo host


class HttpClient:
    def __init__(
        self,
        user_agent: str = "QuantBYMA/0.1",
        timeout: float = 20.0,
        retries: int = 3,
        min_interval: dict[str, float] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": user_agent, "Accept": "application/json, text/csv, */*"},
            follow_redirects=True,
            transport=transport,
        )
        self.retries = retries
        self.min_interval = min_interval or {}
        self._last_call: dict[str, float] = {}
        self._lock = threading.Lock()

    def _throttle(self, host: str) -> None:
        interval = self.min_interval.get(host, DEFAULT_MIN_INTERVAL)
        with self._lock:
            wait = self._last_call.get(host, 0.0) + interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_call[host] = time.monotonic()

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        host = urlparse(url).netloc
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            self._throttle(host)
            try:
                resp = self._client.request(method, url, **kwargs)
            except httpx.ProxyError as exc:
                # El proxy de salida rechazó el host (política de red): reintentar no sirve.
                raise SourceUnavailableError(
                    f"{method} {url} bloqueado por el proxy de red: {exc}"
                ) from exc
            except httpx.HTTPError as exc:  # timeouts, DNS, conexión cortada
                last_exc = exc
            else:
                if resp.status_code < 400:
                    return resp
                if resp.status_code not in RETRY_STATUS:
                    raise ProviderError(f"{method} {url} → HTTP {resp.status_code}")
                last_exc = ProviderError(f"{method} {url} → HTTP {resp.status_code}")
            if attempt < self.retries:
                time.sleep(min(2**attempt, 8))
        raise SourceUnavailableError(
            f"{method} {url} falló tras {self.retries + 1} intentos: {last_exc}"
        )

    def get_json(self, url: str, **kwargs: Any) -> Any:
        resp = self.request("GET", url, **kwargs)
        try:
            return resp.json()
        except ValueError as exc:
            raise ProviderError(f"Respuesta no JSON de {url}") from exc

    def get_text(self, url: str, **kwargs: Any) -> str:
        return self.request("GET", url, **kwargs).text
