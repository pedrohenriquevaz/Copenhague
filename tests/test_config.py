from __future__ import annotations

import pytest

from app.core.config import Settings


def test_settings_from_env_uses_required_and_default_values() -> None:
    settings = Settings.from_env({"DISCORD_TOKEN": "token"})

    assert settings.DISCORD_TOKEN == "token"
    assert settings.GUILD_ID is None
    assert settings.ENVIRONMENT == "development"
    assert settings.LOG_LEVEL == "INFO"


def test_settings_from_env_parses_optional_values() -> None:
    settings = Settings.from_env(
        {
            "DISCORD_TOKEN": "token",
            "GUILD_ID": "123",
            "ENVIRONMENT": "production",
            "LOG_LEVEL": "debug",
        }
    )

    assert settings.GUILD_ID == 123
    assert settings.ENVIRONMENT == "production"
    assert settings.LOG_LEVEL == "DEBUG"


def test_settings_from_env_requires_token() -> None:
    with pytest.raises(ValueError, match="DISCORD_TOKEN"):
        Settings.from_env({})
