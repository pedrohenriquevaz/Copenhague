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
    REFUND = "REFUND"
    SYSTEM_ADJUSTMENT = "SYSTEM_ADJUSTMENT"


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
