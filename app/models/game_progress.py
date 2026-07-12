from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.models.casino import RaceMascot
from app.models.economy import UserWallet


class SeasonalTheme(StrEnum):
    """Temas sazonais aplicaveis aos jogos da fase 0.4."""

    NONE = "none"
    NATAL = "natal"
    HALLOWEEN = "halloween"
    COPA = "copa"
    ANIME = "anime"
    ANIVERSARIO = "aniversario"


class ScratchCardTier(StrEnum):
    """Tipos de raspadinha disponiveis."""

    BRONZE = "bronze"
    PRATA = "prata"
    OURO = "ouro"
    DIAMANTE = "diamante"


class CollectiveRaceStatus(StrEnum):
    """Estados de uma corrida coletiva."""

    OPEN = "open"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class CollectiveRaceBetStatus(StrEnum):
    """Estados financeiros das apostas da corrida coletiva."""

    OPEN = "open"
    WON = "won"
    LOST = "lost"
    REFUNDED = "refunded"


@dataclass(frozen=True, slots=True)
class ScratchCardTierConfig:
    """Configuracao financeira de uma raspadinha."""

    tier: ScratchCardTier
    label: str
    cost: int
    line_multiplier: int


@dataclass(slots=True)
class ScratchCardResult:
    """Resultado de uma raspadinha comprada."""

    guild_id: int
    user_id: int
    tier: ScratchCardTier
    tier_label: str
    cost: int
    grid: list[list[str]]
    winning_lines: list[str]
    payout: int
    jackpot_won: int
    seasonal_theme: SeasonalTheme
    wallet: UserWallet
    cashback: int = 0

    @property
    def profit(self) -> int:
        return self.payout + self.cashback - self.cost


@dataclass(slots=True)
class GameAchievement:
    """Conquista configuravel por servidor."""

    guild_id: int
    achievement_key: str
    name: str
    description: str
    reward_points: int
    badge_emoji: str | None
    is_active: bool
    created_at: datetime


@dataclass(slots=True)
class UserGameAchievement:
    """Conquista desbloqueada por um usuario."""

    guild_id: int
    user_id: int
    achievement: GameAchievement
    unlocked_at: datetime


@dataclass(slots=True)
class JackpotState:
    """Valor acumulado de um jackpot por servidor."""

    guild_id: int
    jackpot_key: str
    amount: int
    updated_at: datetime


@dataclass(slots=True)
class SeasonalSetting:
    """Tema sazonal ativo por servidor."""

    guild_id: int
    theme: SeasonalTheme
    updated_at: datetime


@dataclass(slots=True)
class CollectiveRaceCreate:
    """Dados para criar uma corrida coletiva."""

    guild_id: int
    channel_id: int | None
    message_id: int | None
    stake: int
    opened_by: int
    opened_at: datetime
    closes_at: datetime


@dataclass(slots=True)
class CollectiveRaceSession:
    """Sessao publica de corrida coletiva."""

    id: int
    guild_id: int
    channel_id: int | None
    message_id: int | None
    stake: int
    status: CollectiveRaceStatus
    opened_by: int
    opened_at: datetime
    closes_at: datetime
    winner: RaceMascot | None
    finished_at: datetime | None


@dataclass(slots=True)
class CollectiveRaceBetCreate:
    """Aposta individual em uma corrida coletiva."""

    race_id: int
    guild_id: int
    user_id: int
    mascot: RaceMascot
    stake: int
    potential_payout: int
    debit_transaction_id: int
    created_at: datetime


@dataclass(slots=True)
class CollectiveRaceBet:
    """Aposta persistida da corrida coletiva."""

    id: int
    race_id: int
    guild_id: int
    user_id: int
    mascot: RaceMascot
    stake: int
    potential_payout: int
    status: CollectiveRaceBetStatus
    debit_transaction_id: int | None
    payout_transaction_id: int | None
    created_at: datetime
    settled_at: datetime | None


@dataclass(slots=True)
class CollectiveRacePlacementResult:
    """Resultado de uma aposta aceita na corrida coletiva."""

    race: CollectiveRaceSession
    bet: CollectiveRaceBet
    wallet: UserWallet


@dataclass(slots=True)
class CollectiveRaceSettlementResult:
    """Resumo do fechamento de uma corrida coletiva."""

    race: CollectiveRaceSession
    bets: list[CollectiveRaceBet]
    winner: RaceMascot | None
    winning_bets: int
    lost_bets: int
    refunded_bets: int
    total_paid: int
    total_refunded: int
    total_cashback: int = 0
