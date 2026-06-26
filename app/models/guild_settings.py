from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class GuildEconomySettings:
    """Configuracoes de economia por servidor."""

    guild_id: int
    currency_name: str
    voice_points_per_minute: int
    message_points: int
    activity_provider: str
    economy_channel_id: int | None
    shop_channel_id: int | None
    staff_log_channel_id: int | None
    min_voice_seconds_to_claim: int
    min_messages_to_claim: int
    ignore_afk_channel: bool
    ignore_bots: bool
    count_voice_when_alone: bool
    max_admin_grant_per_use: int
    economy_manager_role_id: int | None
    created_at: datetime
    updated_at: datetime
