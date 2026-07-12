from __future__ import annotations

from .bolao_repository import (
    BolaoRepositoryProtocol,
    SQLiteBolaoRepository,
)
from .economy_repository import SQLiteEconomyRepository
from .game_progress_repository import (
    GameProgressRepositoryProtocol,
    SQLiteGameProgressRepository,
)
from .giveaway_repository import (
    GiveawayRepositoryProtocol,
    SQLiteGiveawayRepository,
)
from .match_bet_repository import (
    MatchBetRepositoryProtocol,
    SQLiteMatchBetRepository,
)
from .postgres_game_progress_repository import PostgresGameProgressRepository
from .postgres_repositories import (
    PostgresBolaoRepository,
    PostgresEconomyRepository,
    PostgresFormRepository,
    PostgresGiveawayRepository,
    PostgresMatchBetRepository,
    PostgresTrucoRepository,
    PostgresUnoRepository,
)
from .truco_repository import SQLiteTrucoRepository, TrucoRepositoryProtocol
from .uno_repository import SQLiteUnoRepository, UnoRepositoryProtocol

__all__ = [
    "BolaoRepositoryProtocol",
    "GameProgressRepositoryProtocol",
    "GiveawayRepositoryProtocol",
    "MatchBetRepositoryProtocol",
    "SQLiteBolaoRepository",
    "SQLiteEconomyRepository",
    "SQLiteGameProgressRepository",
    "SQLiteGiveawayRepository",
    "SQLiteMatchBetRepository",
    "SQLiteTrucoRepository",
    "TrucoRepositoryProtocol",
    "SQLiteUnoRepository",
    "UnoRepositoryProtocol",
    "PostgresBolaoRepository",
    "PostgresEconomyRepository",
    "PostgresFormRepository",
    "PostgresGameProgressRepository",
    "PostgresGiveawayRepository",
    "PostgresMatchBetRepository",
    "PostgresTrucoRepository",
    "PostgresUnoRepository",
]
