from __future__ import annotations

from .bolao_repository import BolaoRepositoryProtocol
from .economy_protocol import EconomyRepositoryProtocol
from .game_progress_repository import GameProgressRepositoryProtocol
from .giveaway_repository import GiveawayRepositoryProtocol
from .match_bet_repository import MatchBetRepositoryProtocol
from .postgres_repositories import (
    PostgresBolaoRepository,
    PostgresEconomyRepository,
    PostgresFormRepository,
    PostgresGameProgressRepository,
    PostgresGiveawayRepository,
    PostgresMatchBetRepository,
    PostgresTrucoRepository,
    PostgresUnoRepository,
)
from .truco_repository import TrucoRepositoryProtocol
from .uno_repository import UnoRepositoryProtocol

__all__ = [
    "BolaoRepositoryProtocol",
    "EconomyRepositoryProtocol",
    "GameProgressRepositoryProtocol",
    "GiveawayRepositoryProtocol",
    "MatchBetRepositoryProtocol",
    "TrucoRepositoryProtocol",
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
