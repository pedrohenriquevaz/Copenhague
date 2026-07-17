from __future__ import annotations

import pytest

from app.core.config import Settings


def test_settings_from_env_uses_required_and_default_values() -> None:
    settings = Settings.from_env({"DISCORD_TOKEN": "token"})

    assert settings.DISCORD_TOKEN == "token"
    assert settings.GUILD_IDS == ()
    assert settings.ENVIRONMENT == "development"
    assert settings.LOG_LEVEL == "INFO"
    assert settings.NETWORK_LOG_LEVEL == "INFO"
    assert settings.ENABLE_NETWORK_ACCESS_LOG is True
    assert settings.DISCORD_INTERACTION_ACK_SECONDS == 2.5
    assert settings.HTTP_CONNECT_TIMEOUT_SECONDS == 3.0
    assert settings.HTTP_REQUEST_TIMEOUT_SECONDS == 15.0
    assert settings.HTTP_MAX_RETRIES == 2
    assert settings.MLBB_ENABLED is False
    assert settings.MLBB_API_BASE_URL == "https://mlbb.rone.dev/api"
    assert settings.MLBB_HTTP_TIMEOUT_SECONDS == 15.0
    assert settings.MLBB_MAX_CONCURRENT_REQUESTS == 10
    assert settings.MLBB_TOKEN_ENCRYPTION_KEYS == ()
    assert settings.MLBB_AUTH_TTL_SECONDS == 300
    assert settings.MLBB_SEND_VC_COOLDOWN_SECONDS == 60
    assert settings.MLBB_MAX_CONFIRM_ATTEMPTS == 5
    assert settings.MLBB_PROFILE_CACHE_TTL_SECONDS == 300
    assert settings.MLBB_STATS_CACHE_TTL_SECONDS == 120
    assert settings.MLBB_PROFILE_REFRESH_COOLDOWN_SECONDS == 30
    assert settings.POSTGRES_SCHEMA == "copenhague"
    assert settings.POSTGRES_POOL_MIN_SIZE == 2
    assert settings.POSTGRES_POOL_MAX_SIZE == 10
    assert settings.ECONOMIC_DIFFICULTY_THRESHOLD_BPS == 7_000
    assert settings.ENABLE_MEMBERS_INTENT is False
    assert settings.ENABLE_MESSAGE_CONTENT_INTENT is False


def test_settings_from_env_parses_optional_values() -> None:
    settings = Settings.from_env(
        {
            "DISCORD_TOKEN": "token",
            "GUILD_IDS": "123, 456,123",
            "ENVIRONMENT": "production",
            "LOG_LEVEL": "debug",
            "NETWORK_LOG_LEVEL": "debug",
            "ENABLE_NETWORK_ACCESS_LOG": "false",
            "DISCORD_INTERACTION_ACK_SECONDS": "2",
            "HTTP_CONNECT_TIMEOUT_SECONDS": "4",
            "HTTP_REQUEST_TIMEOUT_SECONDS": "20",
            "HTTP_MAX_RETRIES": "4",
            "MLBB_ENABLED": "true",
            "MLBB_API_BASE_URL": "https://mlbb.example.test/api/",
            "MLBB_HTTP_TIMEOUT_SECONDS": "12",
            "MLBB_MAX_CONCURRENT_REQUESTS": "7",
            "MLBB_TOKEN_ENCRYPTION_KEYS": "key-a, key-b",
            "MLBB_AUTH_TTL_SECONDS": "240",
            "MLBB_SEND_VC_COOLDOWN_SECONDS": "90",
            "MLBB_MAX_CONFIRM_ATTEMPTS": "4",
            "MLBB_PROFILE_CACHE_TTL_SECONDS": "240",
            "MLBB_STATS_CACHE_TTL_SECONDS": "90",
            "MLBB_PROFILE_REFRESH_COOLDOWN_SECONDS": "45",
            "POSTGRES_DSN": "postgresql://user:pass@db:5432/app",
            "POSTGRES_SCHEMA": "custom_schema",
            "POSTGRES_POOL_MIN_SIZE": "3",
            "POSTGRES_POOL_MAX_SIZE": "12",
            "ECONOMIC_DIFFICULTY_THRESHOLD_BPS": "6500",
            "ENABLE_MEMBERS_INTENT": "true",
            "ENABLE_MESSAGE_CONTENT_INTENT": "1",
        }
    )

    assert settings.GUILD_IDS == (123, 456)
    assert settings.ENVIRONMENT == "production"
    assert settings.LOG_LEVEL == "DEBUG"
    assert settings.NETWORK_LOG_LEVEL == "DEBUG"
    assert settings.ENABLE_NETWORK_ACCESS_LOG is False
    assert settings.DISCORD_INTERACTION_ACK_SECONDS == 2.0
    assert settings.HTTP_CONNECT_TIMEOUT_SECONDS == 4.0
    assert settings.HTTP_REQUEST_TIMEOUT_SECONDS == 20.0
    assert settings.HTTP_MAX_RETRIES == 4
    assert settings.MLBB_ENABLED is True
    assert settings.MLBB_API_BASE_URL == "https://mlbb.example.test/api"
    assert settings.MLBB_HTTP_TIMEOUT_SECONDS == 12.0
    assert settings.MLBB_MAX_CONCURRENT_REQUESTS == 7
    assert settings.MLBB_TOKEN_ENCRYPTION_KEYS == ("key-a", "key-b")
    assert settings.MLBB_AUTH_TTL_SECONDS == 240
    assert settings.MLBB_SEND_VC_COOLDOWN_SECONDS == 90
    assert settings.MLBB_MAX_CONFIRM_ATTEMPTS == 4
    assert settings.MLBB_PROFILE_CACHE_TTL_SECONDS == 240
    assert settings.MLBB_STATS_CACHE_TTL_SECONDS == 90
    assert settings.MLBB_PROFILE_REFRESH_COOLDOWN_SECONDS == 45
    assert settings.POSTGRES_DSN == "postgresql://user:pass@db:5432/app"
    assert settings.POSTGRES_SCHEMA == "custom_schema"
    assert settings.POSTGRES_POOL_MIN_SIZE == 3
    assert settings.POSTGRES_POOL_MAX_SIZE == 12
    assert settings.ECONOMIC_DIFFICULTY_THRESHOLD_BPS == 6_500
    assert settings.ENABLE_MEMBERS_INTENT is True
    assert settings.ENABLE_MESSAGE_CONTENT_INTENT is True


def test_settings_from_env_requires_token() -> None:
    with pytest.raises(ValueError, match="DISCORD_TOKEN"):
        Settings.from_env({})


def test_settings_from_env_accepts_legacy_guild_id() -> None:
    settings = Settings.from_env({"DISCORD_TOKEN": "token", "GUILD_ID": "123"})

    assert settings.GUILD_IDS == (123,)


@pytest.mark.parametrize("value", ["0", "9000"])
def test_settings_rejects_invalid_economic_threshold(value: str) -> None:
    with pytest.raises(ValueError, match="ECONOMIC_DIFFICULTY_THRESHOLD_BPS"):
        Settings.from_env(
            {
                "DISCORD_TOKEN": "token",
                "ECONOMIC_DIFFICULTY_THRESHOLD_BPS": value,
            }
        )


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("MLBB_API_BASE_URL", "not-a-url"),
        ("MLBB_HTTP_TIMEOUT_SECONDS", "0"),
        ("MLBB_MAX_CONCURRENT_REQUESTS", "0"),
        ("MLBB_AUTH_TTL_SECONDS", "301"),
        ("MLBB_SEND_VC_COOLDOWN_SECONDS", "0"),
        ("MLBB_MAX_CONFIRM_ATTEMPTS", "0"),
        ("MLBB_PROFILE_CACHE_TTL_SECONDS", "0"),
        ("MLBB_STATS_CACHE_TTL_SECONDS", "0"),
        ("MLBB_PROFILE_REFRESH_COOLDOWN_SECONDS", "0"),
    ],
)
def test_settings_rejects_invalid_mlbb_configuration(key: str, value: str) -> None:
    with pytest.raises(ValueError, match=key):
        Settings.from_env({"DISCORD_TOKEN": "token", key: value})
