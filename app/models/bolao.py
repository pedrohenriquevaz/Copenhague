from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


@dataclass(slots=True)
class BolaoEventCreate:
    """Dados necessarios para criar um bolao."""

    title: str
    description: str
    prize: str
    team_1: str
    team_2: str
    created_by: int
    receiver_user_id: int
    created_at: datetime


@dataclass(slots=True)
class BolaoEvent:
    """Evento de bolao publicado ou pronto para publicacao."""

    id: int
    title: str
    description: str
    prize: str
    team_1: str
    team_2: str
    channel_id: int | None
    message_id: int | None
    created_by: int
    receiver_user_id: int
    created_at: datetime
    is_active: bool


@dataclass(slots=True)
class BolaoGuess:
    """Palpite de placar de um participante."""

    id: int
    bolao_id: int
    user_id: int
    score_team_1: int
    score_team_2: int
    created_at: datetime


class BolaoGuessStatus(StrEnum):
    """Estados possiveis ao tentar registrar um palpite."""

    SUCCESS = "success"
    ALREADY_GUESSED = "already_guessed"
    EVENT_NOT_FOUND = "event_not_found"
    EVENT_CLOSED = "event_closed"


@dataclass(slots=True)
class BolaoGuessResult:
    """Resultado completo da tentativa de palpite."""

    status: BolaoGuessStatus
    event: BolaoEvent | None = None
    guess: BolaoGuess | None = None
