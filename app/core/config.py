from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(slots=True)
class Settings:
    DISCORD_TOKEN: str
    GUILD_IDS: tuple[int, ...]
    ENVIRONMENT: str
    LOG_LEVEL: str
    DATABASE_BACKEND: str
    POSTGRES_DSN: str
    POSTGRES_SCHEMA: str
    POSTGRES_POOL_MIN_SIZE: int
    POSTGRES_POOL_MAX_SIZE: int
    GAME_PROGRESS_DB_BACKEND: str
    ENABLE_MEMBERS_INTENT: bool
    ENABLE_MESSAGE_CONTENT_INTENT: bool
    GIVEAWAY_DB_PATH: str
    BOLAO_DB_PATH: str
    MATCH_BET_DB_PATH: str
    GAME_PROGRESS_DB_PATH: str
    FORM_DB_PATH: str
    ECONOMY_DB_PATH: str

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
            DATABASE_BACKEND=env.get("DATABASE_BACKEND", "sqlite").strip().lower(),
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
            GAME_PROGRESS_DB_BACKEND=env.get(
                "GAME_PROGRESS_DB_BACKEND",
                env.get("DATABASE_BACKEND", "sqlite"),
            )
            .strip()
            .lower(),
            ENABLE_MEMBERS_INTENT=_get_bool(env, "ENABLE_MEMBERS_INTENT", False),
            ENABLE_MESSAGE_CONTENT_INTENT=_get_bool(
                env,
                "ENABLE_MESSAGE_CONTENT_INTENT",
                False,
            ),
            GIVEAWAY_DB_PATH=env.get(
                "GIVEAWAY_DB_PATH",
                str(Path("data") / "giveaways.sqlite3"),
            ),
            BOLAO_DB_PATH=env.get(
                "BOLAO_DB_PATH",
                str(Path("data") / "bot.db"),
            ),
            MATCH_BET_DB_PATH=env.get(
                "MATCH_BET_DB_PATH",
                str(Path("data") / "bot.db"),
            ),
            GAME_PROGRESS_DB_PATH=env.get(
                "GAME_PROGRESS_DB_PATH",
                str(Path("data") / "bot.db"),
            ),
            FORM_DB_PATH=env.get(
                "FORM_DB_PATH",
                str(Path("data") / "bot.db"),
            ),
            ECONOMY_DB_PATH=env.get(
                "ECONOMY_DB_PATH",
                str(Path("data") / "economy.sqlite3"),
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
        raise ValueError("GUILD_IDS deve conter apenas IDs positivos separados por virgula.")
    return guild_ids
