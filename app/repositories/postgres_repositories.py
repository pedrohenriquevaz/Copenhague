from __future__ import annotations

import threading

from app.repositories.bolao_repository import SQLiteBolaoRepository
from app.repositories.economy_repository import SQLiteEconomyRepository
from app.repositories.form_repository import SQLiteFormRepository
from app.repositories.game_progress_repository import SQLiteGameProgressRepository
from app.repositories.giveaway_repository import SQLiteGiveawayRepository
from app.repositories.match_bet_repository import SQLiteMatchBetRepository
from app.repositories.postgres_database import (
    PostgresConnectionAdapter,
    PostgresDatabase,
)


class _PostgresRepositoryMixin:
    def _init_postgres(self, database: PostgresDatabase) -> None:
        self._database = database
        self._lock = threading.RLock()
        self._initialize_schema()

    def _connect(self) -> PostgresConnectionAdapter:
        return self._database.connection()


class PostgresEconomyRepository(_PostgresRepositoryMixin, SQLiteEconomyRepository):
    """PostgreSQL storage for economy, wallets, shop, activity and audit."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._init_postgres(database)


class PostgresGameProgressRepository(
    _PostgresRepositoryMixin,
    SQLiteGameProgressRepository,
):
    """PostgreSQL storage for achievements, jackpots and collective races."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._init_postgres(database)


class PostgresMatchBetRepository(_PostgresRepositoryMixin, SQLiteMatchBetRepository):
    """PostgreSQL storage for match bets."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._init_postgres(database)


class PostgresBolaoRepository(_PostgresRepositoryMixin, SQLiteBolaoRepository):
    """PostgreSQL storage for boloes."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._init_postgres(database)


class PostgresFormRepository(_PostgresRepositoryMixin, SQLiteFormRepository):
    """PostgreSQL storage for forms."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._init_postgres(database)


class PostgresGiveawayRepository(_PostgresRepositoryMixin, SQLiteGiveawayRepository):
    """PostgreSQL storage for giveaways."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._init_postgres(database)
