from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import aiohttp

from .errors import (
    ExternalApiAuthenticationError,
    ExternalApiRateLimitedError,
    ExternalApiResponseError,
    ExternalApiTimeoutError,
    ExternalApiUnavailableError,
)
from .network_logging import build_http_trace_config
from .timeout_policy import DiscordOrchestratedTimeoutPolicy

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = frozenset({500, 502, 503, 504})
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    data: Any


class AsyncHttpClient:
    """Cliente HTTP compartilhado para providers externos futuros."""

    def __init__(
        self,
        policy: DiscordOrchestratedTimeoutPolicy,
        *,
        user_agent: str = "CopenhagueBot/1.0",
        access_log_enabled: bool = True,
    ) -> None:
        self._policy = policy
        self._user_agent = user_agent
        self._access_log_enabled = access_log_enabled
        self._session: aiohttp.ClientSession | None = None

    async def open(self) -> None:
        if self._session is not None and not self._session.closed:
            return
        timeout = aiohttp.ClientTimeout(
            total=self._policy.request_seconds,
            connect=self._policy.connect_seconds,
        )
        trace = build_http_trace_config(enabled=self._access_log_enabled)
        self._session = aiohttp.ClientSession(
            timeout=timeout,
            headers={"User-Agent": self._user_agent},
            trace_configs=[trace] if trace is not None else [],
        )

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def request_json(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str | int | float] | None = None,
        json: Any = None,
    ) -> HttpResponse:
        await self.open()
        if self._session is None:
            raise RuntimeError("Cliente HTTP nao inicializado.")

        normalized_method = method.upper()
        attempts = (
            self._policy.max_retries + 1
            if normalized_method in _IDEMPOTENT_METHODS
            else 1
        )
        for attempt in range(attempts):
            try:
                async with self._session.request(
                    normalized_method,
                    url,
                    headers=headers,
                    params=params,
                    json=json,
                ) as response:
                    if response.status in {401, 403}:
                        raise ExternalApiAuthenticationError(
                            "O provedor recusou as credenciais."
                        )
                    if response.status == 429:
                        retry_after = _parse_retry_after(response.headers)
                        raise ExternalApiRateLimitedError(
                            "O provedor limitou temporariamente as requisicoes.",
                            retry_after=retry_after,
                        )
                    if response.status in _RETRYABLE_STATUS and attempt + 1 < attempts:
                        await asyncio.sleep(1 + attempt * 2)
                        continue
                    if response.status >= 500:
                        raise ExternalApiUnavailableError(
                            f"O provedor retornou HTTP {response.status}."
                        )
                    if response.status >= 400:
                        raise ExternalApiResponseError(
                            f"O provedor retornou HTTP {response.status}.",
                            status=response.status,
                        )
                    data = await response.json(content_type=None)
                    return HttpResponse(response.status, dict(response.headers), data)
            except TimeoutError as exc:
                raise ExternalApiTimeoutError(
                    "O provedor excedeu o timeout configurado."
                ) from exc
            except aiohttp.ClientError as exc:
                if attempt + 1 < attempts:
                    await asyncio.sleep(1 + attempt * 2)
                    continue
                raise ExternalApiUnavailableError(
                    "Falha de rede ao acessar o provedor."
                ) from exc
        raise ExternalApiUnavailableError("O provedor nao respondeu.")


def _parse_retry_after(headers: Mapping[str, str]) -> float | None:
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None
