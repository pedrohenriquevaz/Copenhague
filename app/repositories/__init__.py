from __future__ import annotations

from .bolao_repository import (
    BolaoRepositoryProtocol,
    SQLiteBolaoRepository,
)
from .giveaway_repository import (
    GiveawayRepositoryProtocol,
    SQLiteGiveawayRepository,
)

__all__ = [
    "BolaoRepositoryProtocol",
    "GiveawayRepositoryProtocol",
    "SQLiteBolaoRepository",
    "SQLiteGiveawayRepository",
]
