from __future__ import annotations

from app.models.activity import ActivityStats
from app.repositories.economy_protocol import EconomyRepositoryProtocol


class NativeActivityProvider:
    """Provider nativo baseado nos eventos capturados pelo proprio bot."""

    source = "native"

    def __init__(self, repository: EconomyRepositoryProtocol) -> None:
        self._repository = repository

    async def get_user_stats(self, guild_id: int, user_id: int) -> ActivityStats:
        return await self._repository.get_activity_stats(guild_id, user_id)
