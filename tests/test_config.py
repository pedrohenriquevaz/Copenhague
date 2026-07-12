from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings


def test_settings_from_env_uses_required_and_default_values() -> None:
    settings = Settings.from_env({"DISCORD_TOKEN": "token"})

    assert settings.DISCORD_TOKEN == "token"
    assert settings.GUILD_IDS == ()
    assert settings.ENVIRONMENT == "development"
    assert settings.LOG_LEVEL == "INFO"
    assert settings.DATABASE_BACKEND == "sqlite"
    assert settings.GAME_PROGRESS_DB_BACKEND == "sqlite"
    assert settings.POSTGRES_SCHEMA == "copenhague"
    assert settings.POSTGRES_POOL_MIN_SIZE == 2
    assert settings.POSTGRES_POOL_MAX_SIZE == 10
    assert settings.ENABLE_MEMBERS_INTENT is False
    assert settings.ENABLE_MESSAGE_CONTENT_INTENT is False
    assert Path(settings.GIVEAWAY_DB_PATH) == Path("data/giveaways.sqlite3")
    assert Path(settings.BOLAO_DB_PATH) == Path("data/bot.db")
    assert Path(settings.MATCH_BET_DB_PATH) == Path("data/bot.db")
    assert Path(settings.GAME_PROGRESS_DB_PATH) == Path("data/bot.db")
    assert Path(settings.ECONOMY_DB_PATH) == Path("data/economy.sqlite3")


def test_settings_from_env_parses_optional_values() -> None:
    settings = Settings.from_env(
        {
            "DISCORD_TOKEN": "token",
            "GUILD_IDS": "123, 456,123",
            "ENVIRONMENT": "production",
            "LOG_LEVEL": "debug",
            "DATABASE_BACKEND": "postgres",
            "POSTGRES_DSN": "postgresql://user:pass@db:5432/app",
            "POSTGRES_SCHEMA": "custom_schema",
            "POSTGRES_POOL_MIN_SIZE": "3",
            "POSTGRES_POOL_MAX_SIZE": "12",
            "GAME_PROGRESS_DB_BACKEND": "postgres",
            "ENABLE_MEMBERS_INTENT": "true",
            "ENABLE_MESSAGE_CONTENT_INTENT": "1",
            "GIVEAWAY_DB_PATH": "custom.sqlite3",
            "BOLAO_DB_PATH": "custom_bolao.sqlite3",
            "MATCH_BET_DB_PATH": "custom_match_bets.sqlite3",
            "GAME_PROGRESS_DB_PATH": "custom_game_progress.sqlite3",
            "ECONOMY_DB_PATH": "custom_economy.sqlite3",
        }
    )

    assert settings.GUILD_IDS == (123, 456)
    assert settings.ENVIRONMENT == "production"
    assert settings.LOG_LEVEL == "DEBUG"
    assert settings.DATABASE_BACKEND == "postgres"
    assert settings.POSTGRES_DSN == "postgresql://user:pass@db:5432/app"
    assert settings.POSTGRES_SCHEMA == "custom_schema"
    assert settings.POSTGRES_POOL_MIN_SIZE == 3
    assert settings.POSTGRES_POOL_MAX_SIZE == 12
    assert settings.GAME_PROGRESS_DB_BACKEND == "postgres"
    assert settings.ENABLE_MEMBERS_INTENT is True
    assert settings.ENABLE_MESSAGE_CONTENT_INTENT is True
    assert settings.GIVEAWAY_DB_PATH == "custom.sqlite3"
    assert settings.BOLAO_DB_PATH == "custom_bolao.sqlite3"
    assert settings.MATCH_BET_DB_PATH == "custom_match_bets.sqlite3"
    assert settings.GAME_PROGRESS_DB_PATH == "custom_game_progress.sqlite3"
    assert settings.ECONOMY_DB_PATH == "custom_economy.sqlite3"


def test_settings_from_env_requires_token() -> None:
    with pytest.raises(ValueError, match="DISCORD_TOKEN"):
        Settings.from_env({})


def test_settings_from_env_accepts_legacy_guild_id() -> None:
    settings = Settings.from_env({"DISCORD_TOKEN": "token", "GUILD_ID": "123"})

    assert settings.GUILD_IDS == (123,)
