from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.models.economy import UserWallet


class MatchBetTeam(StrEnum):
    """Lados possiveis de uma aposta em partida."""

    TEAM_1 = "team_1"
    TEAM_2 = "team_2"


class MatchBetTicketStatus(StrEnum):
    """Estados financeiros de uma aposta registrada."""

    OPEN = "open"
    WON = "won"
    LOST = "lost"
    REFUNDED = "refunded"


@dataclass(slots=True)
class MatchBetCreate:
    """Dados necessarios para criar uma sessao de apostas."""

    guild_id: int
    title: str
    team_1: str
    team_2: str
    odd_team_1_bps: int
    odd_team_2_bps: int
    created_by: int
    created_at: datetime


@dataclass(slots=True)
class MatchBetMatch:
    """Sessao publica de apostas para uma partida."""

    id: int
    guild_id: int
    title: str
    team_1: str
    team_2: str
    odd_team_1_bps: int
    odd_team_2_bps: int
    channel_id: int | None
    message_id: int | None
    created_by: int
    created_at: datetime
    is_active: bool
    resolved_winner: MatchBetTeam | None
    resolved_at: datetime | None


@dataclass(slots=True)
class MatchBetTicketCreate:
    """Aposta individual feita por um usuario."""

    match_id: int
    guild_id: int
    user_id: int
    team: MatchBetTeam
    team_name_snapshot: str
    stake: int
    odd_bps: int
    potential_payout: int
    debit_transaction_id: int
    created_at: datetime


@dataclass(slots=True)
class MatchBetTicket:
    """Ticket persistido de uma aposta individual."""

    id: int
    match_id: int
    guild_id: int
    user_id: int
    team: MatchBetTeam
    team_name_snapshot: str
    stake: int
    odd_bps: int
    potential_payout: int
    status: MatchBetTicketStatus
    debit_transaction_id: int | None
    payout_transaction_id: int | None
    created_at: datetime
    settled_at: datetime | None


@dataclass(slots=True)
class MatchBetPlacementResult:
    """Resultado de uma aposta aceita."""

    match: MatchBetMatch
    ticket: MatchBetTicket
    wallet: UserWallet


@dataclass(slots=True)
class MatchBetSettlementResult:
    """Resumo do encerramento de uma partida de apostas."""

    match: MatchBetMatch
    tickets: list[MatchBetTicket]
    winning_tickets: int
    lost_tickets: int
    refunded_tickets: int
    total_paid: int
    total_refunded: int
    total_cashback: int = 0
