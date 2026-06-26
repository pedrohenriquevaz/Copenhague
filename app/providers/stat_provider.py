from __future__ import annotations

from typing import Protocol

from app.models.activity import ActivityStats


class StatProvider(Protocol):
    """Interface para fontes de estatisticas de atividade."""

    async def get_user_stats(self, guild_id: int, user_id: int) -> ActivityStats: ...
