from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv()


@dataclass(slots=True)
class Settings:
    DISCORD_TOKEN: str
    GUILD_IDS: tuple[int, ...]
    ENVIRONMENT: str
    LOG_LEVEL: str
    NETWORK_LOG_LEVEL: str
    ENABLE_NETWORK_ACCESS_LOG: bool
    DISCORD_INTERACTION_ACK_SECONDS: float
    HTTP_CONNECT_TIMEOUT_SECONDS: float
    HTTP_REQUEST_TIMEOUT_SECONDS: float
    HTTP_MAX_RETRIES: int
    MLBB_ENABLED: bool
    MLBB_API_BASE_URL: str
    MLBB_HTTP_TIMEOUT_SECONDS: float
    MLBB_MAX_CONCURRENT_REQUESTS: int
    MLBB_TOKEN_ENCRYPTION_KEYS: tuple[str, ...]
    MLBB_AUTH_TTL_SECONDS: int
    MLBB_SEND_VC_COOLDOWN_SECONDS: int
    MLBB_MAX_CONFIRM_ATTEMPTS: int
    MLBB_PROFILE_CACHE_TTL_SECONDS: int
    MLBB_STATS_CACHE_TTL_SECONDS: int
    MLBB_PROFILE_REFRESH_COOLDOWN_SECONDS: int
    POSTGRES_DSN: str
    POSTGRES_SCHEMA: str
    POSTGRES_POOL_MIN_SIZE: int
    POSTGRES_POOL_MAX_SIZE: int
    ECONOMIC_DIFFICULTY_THRESHOLD_BPS: int
    ENABLE_MEMBERS_INTENT: bool
    ENABLE_MESSAGE_CONTENT_INTENT: bool

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ

        token = env.get("DISCORD_TOKEN")
        if not token:
            raise ValueError("A variavel de ambiente DISCORD_TOKEN nao foi definida.")

        guild_ids = _get_guild_ids(env)

        return cls(
            DISCORD_TOKEN=token,
            GUILD_IDS=guild_ids,
            ENVIRONMENT=env.get("ENVIRONMENT", "development"),
            LOG_LEVEL=env.get("LOG_LEVEL", "INFO").upper(),
            NETWORK_LOG_LEVEL=env.get("NETWORK_LOG_LEVEL", "INFO").upper(),
            ENABLE_NETWORK_ACCESS_LOG=_get_bool(env, "ENABLE_NETWORK_ACCESS_LOG", True),
            DISCORD_INTERACTION_ACK_SECONDS=_get_positive_float(
                env, "DISCORD_INTERACTION_ACK_SECONDS", 2.5
            ),
            HTTP_CONNECT_TIMEOUT_SECONDS=_get_positive_float(
                env, "HTTP_CONNECT_TIMEOUT_SECONDS", 3.0
            ),
            HTTP_REQUEST_TIMEOUT_SECONDS=_get_positive_float(
                env, "HTTP_REQUEST_TIMEOUT_SECONDS", 15.0
            ),
            HTTP_MAX_RETRIES=max(0, int(env.get("HTTP_MAX_RETRIES", "2"))),
            MLBB_ENABLED=_get_bool(env, "MLBB_ENABLED", False),
            MLBB_API_BASE_URL=_get_http_base_url(
                env,
                "MLBB_API_BASE_URL",
                "https://mlbb.rone.dev/api",
            ),
            MLBB_HTTP_TIMEOUT_SECONDS=_get_positive_float(
                env,
                "MLBB_HTTP_TIMEOUT_SECONDS",
                15.0,
            ),
            MLBB_MAX_CONCURRENT_REQUESTS=_get_positive_int(
                env,
                "MLBB_MAX_CONCURRENT_REQUESTS",
                10,
            ),
            MLBB_TOKEN_ENCRYPTION_KEYS=tuple(
                key.strip()
                for key in env.get("MLBB_TOKEN_ENCRYPTION_KEYS", "").split(",")
                if key.strip()
            ),
            MLBB_AUTH_TTL_SECONDS=_get_bounded_int(
                env,
                "MLBB_AUTH_TTL_SECONDS",
                300,
                minimum=1,
                maximum=300,
            ),
            MLBB_SEND_VC_COOLDOWN_SECONDS=_get_positive_int(
                env,
                "MLBB_SEND_VC_COOLDOWN_SECONDS",
                60,
            ),
            MLBB_MAX_CONFIRM_ATTEMPTS=_get_positive_int(
                env,
                "MLBB_MAX_CONFIRM_ATTEMPTS",
                5,
            ),
            MLBB_PROFILE_CACHE_TTL_SECONDS=_get_positive_int(
                env,
                "MLBB_PROFILE_CACHE_TTL_SECONDS",
                300,
            ),
            MLBB_STATS_CACHE_TTL_SECONDS=_get_positive_int(
                env,
                "MLBB_STATS_CACHE_TTL_SECONDS",
                120,
            ),
            MLBB_PROFILE_REFRESH_COOLDOWN_SECONDS=_get_positive_int(
                env,
                "MLBB_PROFILE_REFRESH_COOLDOWN_SECONDS",
                30,
            ),
            POSTGRES_DSN=env.get(
                "POSTGRES_DSN",
                "postgresql://copenhague:copenhague@postgres:5432/copenhague",
            ),
            POSTGRES_SCHEMA=env.get("POSTGRES_SCHEMA", "copenhague"),
            POSTGRES_POOL_MIN_SIZE=max(
                1,
                int(env.get("POSTGRES_POOL_MIN_SIZE", "2")),
            ),
            POSTGRES_POOL_MAX_SIZE=max(
                1,
                int(env.get("POSTGRES_POOL_MAX_SIZE", "10")),
            ),
            ECONOMIC_DIFFICULTY_THRESHOLD_BPS=_get_bounded_int(
                env,
                "ECONOMIC_DIFFICULTY_THRESHOLD_BPS",
                7_000,
                minimum=1,
                maximum=8_999,
            ),
            ENABLE_MEMBERS_INTENT=_get_bool(env, "ENABLE_MEMBERS_INTENT", False),
            ENABLE_MESSAGE_CONTENT_INTENT=_get_bool(
                env,
                "ENABLE_MESSAGE_CONTENT_INTENT",
                False,
            ),
        )


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()


def _get_bool(
    environ: Mapping[str, str],
    key: str,
    default: bool,
) -> bool:
    value = environ.get(key)
    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_positive_float(
    environ: Mapping[str, str],
    key: str,
    default: float,
) -> float:
    value = float(environ.get(key, str(default)))
    if value <= 0:
        raise ValueError(f"{key} precisa ser maior que zero.")
    return value


def _get_bounded_int(
    environ: Mapping[str, str],
    key: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    value = int(environ.get(key, str(default)))
    if not minimum <= value <= maximum:
        raise ValueError(f"{key} precisa ficar entre {minimum} e {maximum}.")
    return value


def _get_positive_int(
    environ: Mapping[str, str],
    key: str,
    default: int,
) -> int:
    value = int(environ.get(key, str(default)))
    if value <= 0:
        raise ValueError(f"${key} precisa ser maior que zero.")
    return value


def _get_http_base_url(
    environ: Mapping[str, str],
    key: str,
    default: str,
) -> str:
    value = environ.get(key, default).strip().rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"${key} precisa ser uma URL HTTP valida.")
    if parsed.query or parsed.fragment:
        raise ValueError(f"${key} nao pode conter query string ou fragmento.")
    return value


def _get_guild_ids(environ: Mapping[str, str]) -> tuple[int, ...]:
    """Retorna servidores usados somente para sincronizacao rapida de comandos."""
    raw = environ.get("GUILD_IDS", "").strip()
    if not raw:
        # Compatibilidade com instalacoes que ainda usam a variavel singular.
        raw = environ.get("GUILD_ID", "").strip()
    if not raw:
        return ()

    guild_ids = tuple(dict.fromkeys(int(value.strip()) for value in raw.split(",")))
    if any(guild_id <= 0 for guild_id in guild_ids):
        raise ValueError(
            "GUILD_IDS deve conter apenas IDs positivos separados por virgula."
        )
    return guild_ids
