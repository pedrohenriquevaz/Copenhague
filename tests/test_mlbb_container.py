from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.core import container as container_module
from app.core.config import Settings
from app.core.container import AppContainer


class DummyRepository:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass


@pytest.fixture(autouse=True)
def stub_postgres_repositories(monkeypatch: pytest.MonkeyPatch) -> None:
    repository_names = (
        "PostgresEconomyRepository",
        "PostgresModerationRepository",
        "PostgresGameProgressRepository",
        "PostgresMatchBetRepository",
        "PostgresTrucoRepository",
        "PostgresUnoRepository",
        "PostgresGiveawayRepository",
        "PostgresBolaoRepository",
        "PostgresFormRepository",
        "PostgresMlbbRepository",
    )
    for name in repository_names:
        monkeypatch.setattr(container_module, name, DummyRepository)


def test_container_composes_single_mlbb_client_and_auth_dependencies() -> None:
    settings = Settings.from_env(
        {
            "DISCORD_TOKEN": "discord-token-ficticio",
            "MLBB_ENABLED": "true",
            "MLBB_TOKEN_ENCRYPTION_KEYS": Fernet.generate_key().decode("ascii"),
        }
    )

    container = AppContainer.build(settings)

    assert container.mlbb_auth_service.enabled is True
    assert container.mlbb_auth_service._client is container.mlbb_client
    assert container.mlbb_auth_service._repository is container.mlbb_repository
    assert container.mlbb_auth_service._token_cipher is container.mlbb_token_cipher
    assert (
        container.mlbb_auth_service._cache_invalidator is container.mlbb_cache_service
    )
    assert container.mlbb_profile_service._client is container.mlbb_client
    assert container.mlbb_profile_service._repository is container.mlbb_repository
    assert container.mlbb_profile_service._token_cipher is container.mlbb_token_cipher
    assert container.mlbb_profile_service._cache is container.mlbb_cache_service


def test_disabled_mlbb_ignores_dormant_invalid_key_during_startup() -> None:
    settings = Settings.from_env(
        {
            "DISCORD_TOKEN": "discord-token-ficticio",
            "MLBB_ENABLED": "false",
            "MLBB_TOKEN_ENCRYPTION_KEYS": "chave-invalida",
        }
    )

    container = AppContainer.build(settings)

    assert container.mlbb_auth_service.enabled is False
    assert container.mlbb_profile_service.enabled is False
    assert container.mlbb_token_cipher.configured is False
