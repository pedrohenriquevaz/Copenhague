from __future__ import annotations

from datetime import timedelta, timezone

from app.models.giveaway import utc_now
from app.models.guild_settings import GuildEconomySettings
from app.repositories.economy_protocol import EconomyRepositoryProtocol

DAILY_PROFIT_TIMEZONE = timezone(timedelta(hours=-3))
PROFIT_DIFFICULTY_ROLL_MAX = 10_000

DAILY_PROFIT_DIFFICULTY_STEPS: tuple[tuple[int, int], ...] = (
    (9_000, 5_000),
    (7_500, 3_500),
    (5_000, 2_000),
    (2_500, 750),
)


def current_daily_profit_window_start():
    local_now = utc_now().astimezone(DAILY_PROFIT_TIMEZONE)
    return local_now.replace(hour=0, minute=0, second=0, microsecond=0)


def calculate_daily_profit_difficulty_bps(
    current_profit: int,
    settings: GuildEconomySettings,
) -> int:
    if (
        not settings.casino_limiters_enabled
        or settings.casino_daily_profit_limit <= 0
        or current_profit <= 0
    ):
        return 0

    profit_ratio_bps = (
        current_profit * PROFIT_DIFFICULTY_ROLL_MAX
    ) // settings.casino_daily_profit_limit
    for threshold_bps, difficulty_bps in DAILY_PROFIT_DIFFICULTY_STEPS:
        if profit_ratio_bps >= threshold_bps:
            return difficulty_bps
    return 0


def apply_daily_profit_difficulty_to_probability(
    probability_bps: int,
    difficulty_bps: int,
) -> int:
    if probability_bps <= 0:
        return 0
    if difficulty_bps <= 0:
        return min(probability_bps, PROFIT_DIFFICULTY_ROLL_MAX)

    remaining_bps = max(0, PROFIT_DIFFICULTY_ROLL_MAX - difficulty_bps)
    adjusted = (probability_bps * remaining_bps) // PROFIT_DIFFICULTY_ROLL_MAX
    return max(1, min(adjusted, PROFIT_DIFFICULTY_ROLL_MAX))


async def apply_daily_casino_profit_cap(
    repository: EconomyRepositoryProtocol,
    settings: GuildEconomySettings,
    *,
    guild_id: int,
    user_id: int,
    stake: int,
    payout: int,
) -> int:
    if (
        not settings.casino_limiters_enabled
        or settings.casino_daily_profit_limit <= 0
        or payout <= 0
        or payout <= stake
    ):
        return payout

    current_profit = await repository.get_user_casino_profit_since(
        guild_id,
        user_id,
        current_daily_profit_window_start(),
    )
    remaining_payout = settings.casino_daily_profit_limit - current_profit
    return max(0, min(payout, remaining_payout))
