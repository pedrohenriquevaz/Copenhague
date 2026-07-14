from __future__ import annotations

from typing import Any

from app.repositories.postgres_database import PostgresDatabase
from app.repositories.postgres_repositories import (
    PostgresBolaoRepository as _PostgresBolaoRepository,
)
from app.repositories.postgres_repositories import (
    PostgresEconomyRepository as _PostgresEconomyRepository,
)
from app.repositories.postgres_repositories import (
    PostgresFormRepository as _PostgresFormRepository,
)
from app.repositories.postgres_repositories import (
    PostgresGameProgressRepository as _PostgresGameProgressRepository,
)
from app.repositories.postgres_repositories import (
    PostgresGiveawayRepository as _PostgresGiveawayRepository,
)
from app.repositories.postgres_repositories import (
    PostgresMatchBetRepository as _PostgresMatchBetRepository,
)
from app.repositories.postgres_repositories import (
    PostgresTrucoRepository as _PostgresTrucoRepository,
)
from app.repositories.postgres_repositories import (
    PostgresUnoRepository as _PostgresUnoRepository,
)

_database: PostgresDatabase | None = None


def set_test_database(database: PostgresDatabase | None) -> None:
    global _database
    _database = database


def get_test_database() -> PostgresDatabase:
    if _database is None:
        raise RuntimeError("Fixture PostgreSQL de teste nao foi inicializada.")
    return _database


class _PathCompatibleTestRepository:
    def __init__(self, ignored_source: Any = None) -> None:
        del ignored_source
        super().__init__(get_test_database())  # type: ignore[misc]


class PostgresEconomyRepository(
    _PathCompatibleTestRepository, _PostgresEconomyRepository
):
    pass


class PostgresGameProgressRepository(
    _PathCompatibleTestRepository, _PostgresGameProgressRepository
):
    pass


class PostgresMatchBetRepository(
    _PathCompatibleTestRepository, _PostgresMatchBetRepository
):
    pass


class PostgresBolaoRepository(_PathCompatibleTestRepository, _PostgresBolaoRepository):
    pass


class PostgresFormRepository(_PathCompatibleTestRepository, _PostgresFormRepository):
    pass


class PostgresGiveawayRepository(
    _PathCompatibleTestRepository, _PostgresGiveawayRepository
):
    pass


class PostgresTrucoRepository(_PathCompatibleTestRepository, _PostgresTrucoRepository):
    pass


class PostgresUnoRepository(_PathCompatibleTestRepository, _PostgresUnoRepository):
    pass
