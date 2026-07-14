from __future__ import annotations

import threading

from app.repositories.bolao_repository import _BolaoRepositoryImplementation
from app.repositories.economy_repository import _EconomyRepositoryImplementation
from app.repositories.form_repository import _FormRepositoryImplementation
from app.repositories.game_progress_repository import (
    _GameProgressRepositoryImplementation,
)
from app.repositories.giveaway_repository import _GiveawayRepositoryImplementation
from app.repositories.match_bet_repository import _MatchBetRepositoryImplementation
from app.repositories.postgres_database import (
    PostgresConnectionAdapter,
    PostgresDatabase,
)
from app.repositories.truco_repository import _TrucoRepositoryImplementation
from app.repositories.uno_repository import _UnoRepositoryImplementation


class _PostgresRepositoryMixin:
    def _init_postgres(self, database: PostgresDatabase) -> None:
        self._database = database
        self._lock = threading.RLock()
        self._initialize_schema()

    def _connect(self) -> PostgresConnectionAdapter:
        return self._database.connection()


class PostgresEconomyRepository(
    _PostgresRepositoryMixin, _EconomyRepositoryImplementation
):
    """PostgreSQL storage for economy, wallets, shop, activity and audit."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._init_postgres(database)


class PostgresGameProgressRepository(
    _PostgresRepositoryMixin,
    _GameProgressRepositoryImplementation,
):
    """PostgreSQL storage for achievements, jackpots and collective races."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._init_postgres(database)


class PostgresMatchBetRepository(
    _PostgresRepositoryMixin, _MatchBetRepositoryImplementation
):
    """PostgreSQL storage for match bets."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._init_postgres(database)


class PostgresBolaoRepository(_PostgresRepositoryMixin, _BolaoRepositoryImplementation):
    """PostgreSQL storage for boloes."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._init_postgres(database)


class PostgresFormRepository(_PostgresRepositoryMixin, _FormRepositoryImplementation):
    """PostgreSQL storage for forms."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._init_postgres(database)


class PostgresGiveawayRepository(
    _PostgresRepositoryMixin, _GiveawayRepositoryImplementation
):
    """PostgreSQL storage for giveaways."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._init_postgres(database)


class PostgresTrucoRepository(_PostgresRepositoryMixin, _TrucoRepositoryImplementation):
    """PostgreSQL storage for Truco games."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._init_postgres(database)


class PostgresUnoRepository(_PostgresRepositoryMixin, _UnoRepositoryImplementation):
    """PostgreSQL storage for UNO games."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._init_postgres(database)
