from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class EconomyTransactionType(StrEnum):
    """Tipos imutaveis de movimentacao de pontos."""

    ACTIVITY_CONVERSION = "ACTIVITY_CONVERSION"
    ADMIN_GIVE = "ADMIN_GIVE"
    ADMIN_REMOVE = "ADMIN_REMOVE"
    SHOP_PURCHASE = "SHOP_PURCHASE"
    CASINO_BET = "CASINO_BET"
    CASINO_PAYOUT = "CASINO_PAYOUT"
    MATCH_BET = "MATCH_BET"
    MATCH_BET_PAYOUT = "MATCH_BET_PAYOUT"
    BOT_REWARD = "BOT_REWARD"
    REFUND = "REFUND"
    SYSTEM_ADJUSTMENT = "SYSTEM_ADJUSTMENT"
    USER_TRANSFER = "USER_TRANSFER"
    LEVEL_UPGRADE = "LEVEL_UPGRADE"


@dataclass(slots=True)
class UserWallet:
    """Carteira de pontos de um usuario em uma guild."""

    guild_id: int
    user_id: int
    balance: int
    total_earned: int
    total_spent: int
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class EconomyTransaction:
    """Registro imutavel de uma alteracao de saldo."""

    id: int
    guild_id: int
    user_id: int
    actor_id: int | None
    type: EconomyTransactionType
    amount: int
    balance_before: int
    balance_after: int
    reason: str | None
    metadata: dict[str, Any]
    created_at: datetime


@dataclass(slots=True)
class ActivityClaimCursor:
    """Cursor que impede converter a mesma atividade duas vezes."""

    guild_id: int
    user_id: int
    claimed_voice_seconds: int
    claimed_messages: int
    last_claimed_at: datetime | None
    last_source: str | None


@dataclass(slots=True)
class BalanceMutationResult:
    """Resultado de uma mudanca atomica de saldo."""

    wallet: UserWallet
    transaction: EconomyTransaction


@dataclass(slots=True)
class UserTransferResult:
    """Resultado de uma transferencia de pontos entre usuarios."""

    sender_wallet: UserWallet
    receiver_wallet: UserWallet
    sender_transaction: EconomyTransaction
    receiver_transaction: EconomyTransaction
    amount: int


@dataclass(slots=True)
class BotRewardClaimResult:
    """Resultado de um resgate de recompensa do painel do bot."""

    wallet: UserWallet
    transaction: EconomyTransaction
    reward_key: str
    amount: int


@dataclass(slots=True)
class ActivityConversionResult:
    """Resumo de uma conversao sob demanda."""

    wallet: UserWallet
    transaction: EconomyTransaction | None
    voice_seconds_delta: int
    messages_delta: int
    voice_points: int
    message_points: int
    total_points: int
    source: str


@dataclass(slots=True)
class UserGameProgressSummary:
    """Resumo acumulado usado para liberar conquistas de jogos."""

    wallet: UserWallet
    total_games_played: int
    total_wins: int
    total_wagered: int
    total_payout: int
    net_profit: int
    biggest_win: int
    duel_games: int
    duel_wins: int
    collective_race_wins: int
    scratch_plays: int
    scratch_wins: int
    blackjack_best_streak: int


@dataclass(slots=True)
class UserProfileResetResult:
    """Resumo dos dados economicos removidos ao resetar um perfil."""

    wallet_before: UserWallet | None
    deleted_transactions: int
    deleted_reward_claims: int
    deleted_activity_cursors: int
    deleted_message_stats: int
    deleted_voice_sessions: int
    deleted_purchases: int
    deleted_wallets: int
    deleted_level_upgrades: int = 0
