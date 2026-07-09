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
    casino_max_bet: int
    casino_daily_profit_limit: int
    economy_manager_role_id: int | None
    created_at: datetime
    updated_at: datetime
    casino_min_bet_coin_flip: int = 1
    casino_min_bet_dice: int = 1
    casino_min_bet_slot: int = 1
    casino_min_bet_roulette: int = 1
    casino_min_bet_mascot_race: int = 1
    casino_min_bet_duel: int = 1
    casino_min_bet_blackjack: int = 1
    casino_min_bet_scratch_card: int = 1
    casino_min_bet_collective_race: int = 1
    casino_min_bet_match_bet: int = 1
    casino_limiters_enabled: bool = True
