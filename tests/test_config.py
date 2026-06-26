from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings


def test_settings_from_env_uses_required_and_default_values() -> None:
    settings = Settings.from_env({"DISCORD_TOKEN": "token"})

    assert settings.DISCORD_TOKEN == "token"
    assert settings.GUILD_ID is None
    assert settings.ENVIRONMENT == "development"
    assert settings.LOG_LEVEL == "INFO"
    assert settings.ENABLE_MEMBERS_INTENT is False
    assert settings.ENABLE_MESSAGE_CONTENT_INTENT is False
    assert Path(settings.GIVEAWAY_DB_PATH) == Path("data/giveaways.sqlite3")
    assert Path(settings.BOLAO_DB_PATH) == Path("data/bot.db")
    assert Path(settings.ECONOMY_DB_PATH) == Path("data/economy.sqlite3")


def test_settings_from_env_parses_optional_values() -> None:
    settings = Settings.from_env(
        {
            "DISCORD_TOKEN": "token",
            "GUILD_ID": "123",
            "ENVIRONMENT": "production",
            "LOG_LEVEL": "debug",
            "ENABLE_MEMBERS_INTENT": "true",
            "ENABLE_MESSAGE_CONTENT_INTENT": "1",
            "GIVEAWAY_DB_PATH": "custom.sqlite3",
            "BOLAO_DB_PATH": "custom_bolao.sqlite3",
            "ECONOMY_DB_PATH": "custom_economy.sqlite3",
        }
    )

    assert settings.GUILD_ID == 123
    assert settings.ENVIRONMENT == "production"
    assert settings.LOG_LEVEL == "DEBUG"
    assert settings.ENABLE_MEMBERS_INTENT is True
    assert settings.ENABLE_MESSAGE_CONTENT_INTENT is True
    assert settings.GIVEAWAY_DB_PATH == "custom.sqlite3"
    assert settings.BOLAO_DB_PATH == "custom_bolao.sqlite3"
    assert settings.ECONOMY_DB_PATH == "custom_economy.sqlite3"


def test_settings_from_env_requires_token() -> None:
    with pytest.raises(ValueError, match="DISCORD_TOKEN"):
        Settings.from_env({})
