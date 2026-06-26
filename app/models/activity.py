from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class ActivityStats:
    """Estatisticas acumuladas retornadas por um provider."""

    guild_id: int
    user_id: int
    total_voice_seconds: int
    total_messages: int
    source: str
    fetched_at: datetime


@dataclass(slots=True)
class NativeVoiceSession:
    """Sessao de voz registrada pelo provider nativo."""

    id: int
    guild_id: int
    user_id: int
    channel_id: int
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: int | None
    is_valid: bool
    invalid_reason: str | None
