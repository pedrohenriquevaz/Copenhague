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
    CREDIT_CASHBACK = "CREDIT_CASHBACK"
    SAVINGS_DEPOSIT = "SAVINGS_DEPOSIT"
    SAVINGS_WITHDRAW = "SAVINGS_WITHDRAW"


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
class CreditProtectionState:
    """Estado de saves e derrotas seguidas de um usuario."""

    guild_id: int
    user_id: int
    saves: int
    lose_streak: int
    updated_at: datetime


@dataclass(slots=True)
class CreditProtectionResult:
    """Resultado da avaliacao de protecao apos um jogo."""

    state: CreditProtectionState
    wallet: UserWallet | None = None
    transaction: EconomyTransaction | None = None
    cashback_amount: int = 0
    cashback_percent: int = 0
    save_consumed: bool = False
    triggered_streak: int = 0


@dataclass(slots=True)
class CreditProtectionAdjustmentResult:
    """Resultado de um ajuste administrativo de saves."""

    before: CreditProtectionState
    after: CreditProtectionState
    delta: int


@dataclass(slots=True)
class SavingsAccount:
    """Saldo separado de poupanca de um usuario."""

    guild_id: int
    user_id: int
    balance: int
    total_interest_earned: int
    last_interest_at: datetime
    locked_until: datetime | None
    updated_at: datetime


@dataclass(slots=True)
class SavingsOverview:
    """Visao de carteira e poupanca do usuario."""

    wallet: UserWallet
    account: SavingsAccount
    daily_interest_bps: int
    max_deposit: int
    interest_applied: int = 0


@dataclass(slots=True)
class SavingsOperationResult:
    """Resultado de deposito ou saque da poupanca."""

    overview: SavingsOverview
    transaction: EconomyTransaction
    amount: int
    interest_applied: int = 0


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
    deleted_credit_protection: int = 0
    deleted_savings_accounts: int = 0
