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
]
