from __future__ import annotations

from typing import Protocol

from app.models.moderation import (
    ModerationCase,
    ModerationCaseCreate,
    ModerationSettings,
)


class ModerationRepositoryProtocol(Protocol):
    async def get_settings(self, guild_id: int) -> ModerationSettings: ...
    async def add_authorized_role(self, guild_id: int, role_id: int) -> bool: ...
    async def remove_authorized_role(self, guild_id: int, role_id: int) -> bool: ...
    async def set_log_channel(
        self, guild_id: int, channel_id: int | None
    ) -> ModerationSettings: ...
    async def create_case(self, case: ModerationCaseCreate) -> ModerationCase: ...
    async def get_case(self, guild_id: int, case_id: int) -> ModerationCase | None: ...
