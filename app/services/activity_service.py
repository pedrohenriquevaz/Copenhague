from __future__ import annotations

from app.models.activity import ActivityStats
from app.models.economy import ActivityConversionResult
from app.repositories.economy_repository import SQLiteEconomyRepository


class ActivityServiceError(Exception):
    """Erro base do sistema de atividade."""


class ActivityValidationError(ActivityServiceError):
    """Erro de validacao de atividade."""


class ActivityService:
    """Orquestra tracking nativo e conversao sob demanda."""

    def __init__(self, repository: SQLiteEconomyRepository) -> None:
        self._repository = repository

    async def record_message(
        self,
        *,
        guild_id: int,
        channel_id: int,
        user_id: int,
        is_bot: bool,
    ) -> None:
        settings = await self._repository.get_guild_settings(guild_id)
        if settings.ignore_bots and is_bot:
            return

        await self._repository.record_message_activity(
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
        )

    async def start_voice_session(
        self,
        *,
        guild_id: int,
        user_id: int,
        channel_id: int,
        is_bot: bool,
    ) -> None:
        settings = await self._repository.get_guild_settings(guild_id)
        if settings.ignore_bots and is_bot:
            return
        await self._repository.start_voice_session(
            guild_id=guild_id,
            user_id=user_id,
            channel_id=channel_id,
        )

    async def close_voice_sessions(
        self,
        *,
        guild_id: int,
        user_id: int,
        is_bot: bool,
        invalid_reason: str | None = None,
    ) -> None:
        settings = await self._repository.get_guild_settings(guild_id)
        if settings.ignore_bots and is_bot:
            return
        await self._repository.close_voice_sessions(
            guild_id=guild_id,
            user_id=user_id,
            invalid_reason=invalid_reason,
        )

    async def get_stats(self, guild_id: int, user_id: int) -> ActivityStats:
        return await self._repository.get_activity_stats(guild_id, user_id)

    async def convert_activity(
        self,
        *,
        guild_id: int,
        user_id: int,
    ) -> ActivityConversionResult:
        stats = await self.get_stats(guild_id, user_id)
        return await self._repository.convert_activity(stats=stats, actor_id=user_id)
