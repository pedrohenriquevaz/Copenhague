from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


def utc_now() -> datetime:
    """Retorna o horario atual em UTC com timezone explicito."""

    return datetime.now(UTC)


def parse_datetime(value: str) -> datetime:
    """Converte uma string ISO 8601 em datetime consciente de fuso."""

    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def serialize_datetime(value: datetime) -> str:
    """Serializa datetime para ISO 8601 em UTC."""

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


@dataclass(slots=True)
class GiveawayRewardTier:
    """Configuracao de uma faixa de premio durante a criacao do evento."""

    reward_name: str
    reward_amount: int
    quantity: int


@dataclass(slots=True)
class GiveawayEventCreate:
    """Dados necessarios para persistir um novo evento."""

    title: str
    description: str
    created_by: int
    created_at: datetime
    total_codes: int
    max_redemptions: int | None = None
    notify_user_id: int | None = None
    embed_color: int | None = None
    expires_at: datetime | None = None


@dataclass(slots=True)
class GiveawayCodeSeed:
    """Codigo pronto para ser inserido na base."""

    code: str
    reward_name: str | None
    reward_amount: int | None


@dataclass(slots=True)
class GiveawayEvent:
    """Evento/campanha de distribuicao de codigos."""

    id: int
    title: str
    description: str
    channel_id: int | None
    message_id: int | None
    created_by: int
    created_at: datetime
    is_active: bool
    max_redemptions: int | None
    total_codes: int
    notify_user_id: int | None
    embed_color: int | None
    expires_at: datetime | None


@dataclass(slots=True)
class GiveawayCode:
    """Codigo HEX pertencente a um evento."""

    id: int
    event_id: int
    code: str
    reward_name: str | None
    reward_amount: int | None
    is_claimed: bool
    claimed_by: int | None
    claimed_at: datetime | None


@dataclass(slots=True)
class GiveawayClaim:
    """Registro de resgate de um usuario em um evento."""

    id: int
    event_id: int
    user_id: int
    code_id: int
    claimed_at: datetime
    reward_amount: int | None
    reward_name: str | None
    code: str


@dataclass(slots=True)
class GiveawayEventStats:
    """Resumo rapido do estado atual de um evento."""

    total_codes: int
    claimed_codes: int
    available_codes: int
    rewarded_codes: int


class GiveawayDrawStatus(StrEnum):
    """Estados possiveis de uma tentativa de resgate."""

    SUCCESS = "success"
    ALREADY_CLAIMED = "already_claimed"
    EVENT_NOT_FOUND = "event_not_found"
    EVENT_INACTIVE = "event_inactive"
    SOLD_OUT = "sold_out"


@dataclass(slots=True)
class GiveawayDrawResult:
    """Resultado completo de uma tentativa de sorteio."""

    status: GiveawayDrawStatus
    event: GiveawayEvent | None = None
    code: GiveawayCode | None = None
    claim: GiveawayClaim | None = None


@dataclass(slots=True)
class GiveawayCreationResult:
    """Resultado da criacao de um evento."""

    event: GiveawayEvent
    rewarded_codes: int
    reward_tiers: list[GiveawayRewardTier]


@dataclass(slots=True)
class GiveawayFinalizationResult:
    """Resultado do encerramento de um evento."""

    event: GiveawayEvent
    remaining_codes: list[GiveawayCode]
    winning_claims: list[GiveawayClaim]
