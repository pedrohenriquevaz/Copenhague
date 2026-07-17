from __future__ import annotations

import asyncio
import logging
import random
import re
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from json import JSONDecodeError
from typing import Any
from urllib.parse import urlsplit

import aiohttp

from app.integrations.http_client import AsyncHttpClient

from .dto import (
    MlbbHeroPage,
    MlbbLoginResult,
    MlbbMatchDetails,
    MlbbMatchPage,
    MlbbPlayerProfile,
    MlbbPlayerStatsRaw,
)
from .errors import (
    MlbbAccountNotFoundError,
    MlbbAuthenticationError,
    MlbbInvalidResponseError,
    MlbbInvalidVerificationCodeError,
    MlbbProviderResponseError,
    MlbbRateLimitedError,
    MlbbSessionExpiredError,
    MlbbTimeoutError,
    MlbbUnavailableError,
    MlbbVerificationExpiredError,
)
from .mappers import (
    map_frequent_heroes,
    map_login,
    map_match_details,
    map_match_page,
    map_player_profile,
    map_player_stats,
    map_seasons,
)

logger = logging.getLogger(__name__)

_RETRYABLE_HTTP_STATUS = frozenset({429, 502, 503, 504})
_TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_AUTH_MESSAGE_MARKERS = (
    "unauthorized",
    "not authenticated",
    "jwt expired",
    "token expired",
    "session expired",
    "invalid jwt",
    "invalid token",
)
_VERIFICATION_EXPIRED_MARKERS = (
    "verification code expired",
    "expired verification",
    "vc expired",
)
_ACCOUNT_NOT_FOUND_MARKERS = (
    "account not found",
    "player not found",
    "user not found",
)


class MlbbClient:
    """Client defensivo que compartilha a ClientSession do AppContainer."""

    def __init__(
        self,
        http_client: AsyncHttpClient,
        *,
        base_url: str,
        timeout_seconds: float = 15.0,
        max_concurrent_requests: int = 10,
        max_retries: int = 2,
        user_agent: str = "CopenhagueBot/1.0 MLBBIntegration",
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self._http_client = http_client
        self._base_url = _normalize_base_url(base_url)
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds precisa ser maior que zero.")
        if max_concurrent_requests <= 0:
            raise ValueError("max_concurrent_requests precisa ser maior que zero.")
        if not 0 <= max_retries <= 2:
            raise ValueError("max_retries precisa ficar entre zero e dois.")
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._semaphore = asyncio.Semaphore(max_concurrent_requests)
        self._max_retries = max_retries
        self._user_agent = user_agent
        self._sleep = sleep
        self._jitter = jitter

    async def send_verification_code(
        self,
        *,
        role_id: int,
        zone_id: int,
    ) -> None:
        _require_positive_int(role_id, "role_id")
        _require_positive_int(zone_id, "zone_id")
        await self._request(
            "POST",
            "/user/auth/send-vc",
            json_body={"role_id": role_id, "zone_id": zone_id},
            operation="send_verification_code",
        )

    async def login(
        self,
        *,
        role_id: int,
        zone_id: int,
        verification_code: str,
    ) -> MlbbLoginResult:
        _require_positive_int(role_id, "role_id")
        _require_positive_int(zone_id, "zone_id")
        if not verification_code.strip():
            raise ValueError("verification_code nao pode ficar vazio.")
        payload = await self._request(
            "POST",
            "/user/auth/login",
            json_body={
                "role_id": role_id,
                "zone_id": zone_id,
                "vc": verification_code,
            },
            operation="login",
        )
        return map_login(payload)

    async def logout(self, *, jwt: str) -> None:
        await self._request(
            "POST",
            "/user/auth/logout",
            jwt=_require_jwt(jwt),
            operation="logout",
        )

    async def get_user_info(self, *, jwt: str) -> MlbbPlayerProfile:
        payload = await self._request(
            "GET",
            "/user/info",
            jwt=_require_jwt(jwt),
            params={"lang": "pt"},
            operation="get_user_info",
        )
        return map_player_profile(payload)

    async def get_user_stats(self, *, jwt: str) -> MlbbPlayerStatsRaw:
        payload = await self._request(
            "GET",
            "/user/stats",
            jwt=_require_jwt(jwt),
            params={"lang": "pt"},
            operation="get_user_stats",
        )
        return map_player_stats(payload)

    async def get_seasons(self, *, jwt: str) -> tuple[int, ...]:
        payload = await self._request(
            "GET",
            "/user/season",
            jwt=_require_jwt(jwt),
            params={"lang": "pt"},
            operation="get_seasons",
        )
        return map_seasons(payload)

    async def get_matches(
        self,
        *,
        jwt: str,
        season_id: int,
        limit: int,
        cursor: int | str | None = None,
    ) -> MlbbMatchPage:
        _require_positive_int(season_id, "season_id")
        _require_positive_int(limit, "limit")
        params: dict[str, int | str] = {
            "sid": season_id,
            "limit": limit,
            "lang": "pt",
        }
        if cursor is not None:
            params["last_cursor"] = _normalize_cursor(cursor)
        payload = await self._request(
            "GET",
            "/user/matches",
            jwt=_require_jwt(jwt),
            params=params,
            operation="get_matches",
        )
        return map_match_page(payload)

    async def get_match_details(
        self,
        *,
        jwt: str,
        season_id: int,
        match_id: int | str,
    ) -> MlbbMatchDetails:
        _require_positive_int(season_id, "season_id")
        normalized_match_id = _normalize_match_id(match_id)
        payload = await self._request(
            "GET",
            f"/user/matches/{normalized_match_id}",
            jwt=_require_jwt(jwt),
            params={"sid": season_id, "lang": "pt"},
            operation="get_match_details",
        )
        return map_match_details(
            payload,
            season_id=season_id,
            match_id=normalized_match_id,
        )

    async def get_frequent_heroes(
        self,
        *,
        jwt: str,
        season_id: int,
        limit: int,
        cursor: int | str | None = None,
    ) -> MlbbHeroPage:
        _require_positive_int(season_id, "season_id")
        _require_positive_int(limit, "limit")
        params: dict[str, int | str] = {
            "sid": season_id,
            "limit": limit,
            "lang": "pt",
        }
        if cursor is not None:
            params["last_cursor"] = _normalize_cursor(cursor)
        payload = await self._request(
            "GET",
            "/user/heroes/frequent",
            jwt=_require_jwt(jwt),
            params=params,
            operation="get_frequent_heroes",
        )
        return map_frequent_heroes(payload)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        jwt: str | None = None,
        params: Mapping[str, int | str] | None = None,
        json_body: Mapping[str, object] | None = None,
        operation: str,
    ) -> Mapping[str, Any]:
        normalized_method = method.upper()
        attempts = self._max_retries + 1 if normalized_method == "GET" else 1
        session = await self._http_client.get_session()
        for attempt in range(attempts):
            try:
                payload = await self._request_once(
                    session,
                    normalized_method,
                    path,
                    jwt=jwt,
                    params=params,
                    json_body=json_body,
                )
                return self._validate_envelope(
                    payload,
                    operation=operation,
                    authenticated=jwt is not None,
                )
            except _RetryableHttpError as exc:
                if attempt + 1 >= attempts:
                    if exc.status == 429:
                        raise MlbbRateLimitedError(
                            retry_after=exc.retry_after
                        ) from None
                    raise MlbbUnavailableError(
                        "A MLBB Public Data API esta temporariamente indisponivel."
                    ) from None
                await self._retry_delay(
                    attempt,
                    operation=operation,
                    reason=f"http_{exc.status}",
                    retry_after=exc.retry_after,
                )
            except TimeoutError as exc:
                if attempt + 1 >= attempts:
                    raise MlbbTimeoutError(
                        "A MLBB Public Data API excedeu o timeout configurado."
                    ) from exc
                await self._retry_delay(
                    attempt,
                    operation=operation,
                    reason="timeout",
                )
            except aiohttp.ClientError as exc:
                if attempt + 1 >= attempts:
                    raise MlbbUnavailableError(
                        "Falha de rede ao acessar a MLBB Public Data API."
                    ) from exc
                await self._retry_delay(
                    attempt,
                    operation=operation,
                    reason="network",
                )
        raise MlbbUnavailableError("A MLBB Public Data API nao respondeu.")

    async def _request_once(
        self,
        session: aiohttp.ClientSession,
        method: str,
        path: str,
        *,
        jwt: str | None,
        params: Mapping[str, int | str] | None,
        json_body: Mapping[str, object] | None,
    ) -> object:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": self._user_agent,
        }
        if jwt is not None:
            headers["Authorization"] = f"Bearer {jwt}"

        async with self._semaphore:
            async with session.request(
                method,
                f"{self._base_url}{path}",
                headers=headers,
                params=params,
                json=json_body,
                timeout=self._timeout,
            ) as response:
                retry_after = _parse_retry_after(response.headers)
                if response.status in _RETRYABLE_HTTP_STATUS:
                    raise _RetryableHttpError(response.status, retry_after)
                if response.status in {401, 403}:
                    if jwt is not None:
                        raise MlbbSessionExpiredError(
                            "A sessao MLBB foi recusada ou expirou."
                        )
                    raise MlbbAuthenticationError(
                        "A MLBB Public Data API recusou a autenticacao."
                    )
                if response.status >= 500:
                    raise MlbbUnavailableError(
                        "A MLBB Public Data API esta temporariamente indisponivel."
                    )
                if response.status >= 400:
                    raise MlbbInvalidResponseError(
                        "A MLBB Public Data API recusou a requisicao.",
                        status=response.status,
                    )
                try:
                    return await response.json(content_type=None)
                except (JSONDecodeError, aiohttp.ContentTypeError, ValueError) as exc:
                    raise MlbbInvalidResponseError(
                        "A MLBB Public Data API retornou JSON invalido.",
                        status=response.status,
                    ) from exc

    def _validate_envelope(
        self,
        payload: object,
        *,
        operation: str,
        authenticated: bool,
    ) -> Mapping[str, Any]:
        if not isinstance(payload, Mapping):
            raise MlbbInvalidResponseError(
                "A resposta da MLBB Public Data API nao e um objeto JSON."
            )
        trace_id = _safe_trace_id(payload.get("traceID"))
        if trace_id is not None:
            logger.info(
                "mlbb.response operation=%s trace_id=%s",
                operation,
                trace_id,
            )

        code = payload.get("code")
        if isinstance(code, bool) or not isinstance(code, int):
            raise MlbbInvalidResponseError(
                "A resposta da MLBB Public Data API nao possui code valido.",
                trace_id=trace_id,
            )
        if code == 0:
            return payload

        upstream_message = _upstream_message(payload)
        if operation == "login":
            if _contains_marker(upstream_message, _VERIFICATION_EXPIRED_MARKERS):
                raise MlbbVerificationExpiredError(
                    "O codigo de verificacao MLBB expirou."
                )
            raise MlbbInvalidVerificationCodeError(
                "O codigo de verificacao MLBB foi recusado."
            )
        if authenticated and _contains_marker(
            upstream_message,
            _AUTH_MESSAGE_MARKERS,
        ):
            raise MlbbSessionExpiredError("A sessao MLBB foi recusada ou expirou.")
        if operation == "send_verification_code" and _contains_marker(
            upstream_message,
            _ACCOUNT_NOT_FOUND_MARKERS,
        ):
            raise MlbbAccountNotFoundError("A conta MLBB informada nao foi encontrada.")
        raise MlbbProviderResponseError(
            external_code=code,
            trace_id=trace_id,
        )

    async def _retry_delay(
        self,
        attempt: int,
        *,
        operation: str,
        reason: str,
        retry_after: float | None = None,
    ) -> None:
        delay = (
            retry_after
            if retry_after is not None
            else (0.25 * (2**attempt)) + self._jitter(0.0, 0.1)
        )
        logger.warning(
            "mlbb.request.retry operation=%s reason=%s attempt=%s",
            operation,
            reason,
            attempt + 1,
        )
        await self._sleep(max(0.0, delay))


class _RetryableHttpError(Exception):
    def __init__(self, status: int, retry_after: float | None) -> None:
        super().__init__(status)
        self.status = status
        self.retry_after = retry_after


def _normalize_base_url(base_url: str) -> str:
    value = base_url.strip().rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base_url precisa ser uma URL HTTP valida.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("base_url nao pode conter credenciais, query ou fragmento.")
    return value


def _require_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} precisa ser um inteiro positivo.")


def _require_jwt(jwt: str) -> str:
    if not isinstance(jwt, str) or not jwt.strip():
        raise ValueError("jwt nao pode ficar vazio.")
    return jwt.strip()


def _normalize_match_id(match_id: int | str) -> str:
    if isinstance(match_id, bool) or not isinstance(match_id, (int, str)):
        raise ValueError("match_id precisa ser numerico.")
    value = str(match_id).strip()
    if not value.isdigit() or int(value) <= 0:
        raise ValueError("match_id precisa ser numerico e positivo.")
    return value


def _normalize_cursor(cursor: int | str) -> str:
    if isinstance(cursor, bool) or not isinstance(cursor, (int, str)):
        raise ValueError("cursor possui tipo invalido.")
    value = str(cursor).strip()
    if not value:
        raise ValueError("cursor nao pode ficar vazio.")
    return value


def _parse_retry_after(headers: Mapping[str, str]) -> float | None:
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())


def _safe_trace_id(value: object) -> str | None:
    if not isinstance(value, str) or not _TRACE_ID_PATTERN.fullmatch(value):
        return None
    return value


def _upstream_message(payload: Mapping[str, Any]) -> str:
    for field_name in ("message", "msg"):
        value = payload.get(field_name)
        if isinstance(value, str):
            return value.casefold()
    return ""


def _contains_marker(message: str, markers: tuple[str, ...]) -> bool:
    return any(marker in message for marker in markers)
