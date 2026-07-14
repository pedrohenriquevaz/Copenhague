from __future__ import annotations

import logging
import re
from time import perf_counter
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit

import aiohttp

logger = logging.getLogger("app.network.access")

_SENSITIVE_PATH_PATTERNS = (
    re.compile(r"(/webhooks/\d+/)[^/]+", re.IGNORECASE),
    re.compile(r"(/interactions/\d+/)[^/]+", re.IGNORECASE),
)


def sanitize_url(url: object) -> str:
    """Remove credenciais, query string e tokens conhecidos antes do log."""

    parsed = urlsplit(str(url))
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    path = parsed.path
    for pattern in _SENSITIVE_PATH_PATTERNS:
        path = pattern.sub(r"\1<redacted>", path)
    return urlunsplit((parsed.scheme, host, path, "", ""))


def build_http_trace_config(*, enabled: bool = True) -> aiohttp.TraceConfig | None:
    if not enabled:
        return None

    trace = aiohttp.TraceConfig()

    async def on_request_start(
        session: aiohttp.ClientSession,
        context: SimpleNamespace,
        params: aiohttp.TraceRequestStartParams,
    ) -> None:
        del session
        context.started_at = perf_counter()
        context.safe_url = sanitize_url(params.url)
        logger.debug(
            "network.request.start method=%s url=%s", params.method, context.safe_url
        )

    async def on_request_end(
        session: aiohttp.ClientSession,
        context: SimpleNamespace,
        params: aiohttp.TraceRequestEndParams,
    ) -> None:
        del session
        elapsed_ms = (perf_counter() - context.started_at) * 1000
        logger.info(
            "network.request.end method=%s url=%s status=%s duration_ms=%.2f",
            params.method,
            context.safe_url,
            params.response.status,
            elapsed_ms,
        )

    async def on_request_exception(
        session: aiohttp.ClientSession,
        context: SimpleNamespace,
        params: aiohttp.TraceRequestExceptionParams,
    ) -> None:
        del session
        elapsed_ms = (perf_counter() - context.started_at) * 1000
        logger.warning(
            "network.request.error method=%s url=%s duration_ms=%.2f error=%s",
            params.method,
            context.safe_url,
            elapsed_ms,
            type(params.exception).__name__,
        )

    trace.on_request_start.append(on_request_start)
    trace.on_request_end.append(on_request_end)
    trace.on_request_exception.append(on_request_exception)
    return trace
