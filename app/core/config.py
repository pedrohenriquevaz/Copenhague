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
    GUILD_ID: int | None
    ENVIRONMENT: str
    LOG_LEVEL: str
    ENABLE_MEMBERS_INTENT: bool
    ENABLE_MESSAGE_CONTENT_INTENT: bool
    GIVEAWAY_DB_PATH: str
    BOLAO_DB_PATH: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ

        token = env.get("DISCORD_TOKEN")
        if not token:
            raise ValueError("A variavel de ambiente DISCORD_TOKEN nao foi definida.")

        guild_id_raw = env.get("GUILD_ID")
        guild_id = int(guild_id_raw) if guild_id_raw else None

        return cls(
            DISCORD_TOKEN=token,
            GUILD_ID=guild_id,
            ENVIRONMENT=env.get("ENVIRONMENT", "development"),
            LOG_LEVEL=env.get("LOG_LEVEL", "INFO").upper(),
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
