from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.guild_settings import GuildEconomySettings
from app.services.economic_tier_service import EconomicTierService
from app.services.economy_limits import (
    EconomicDifficultyPolicyName,
    EconomicDifficultyPolicyService,
    apply_daily_casino_profit_cap,
    current_daily_profit_window_start,
    deserialize_economic_difficulty_decision,
    select_economic_difficulty_policy,
    serialize_economic_difficulty_decision,
)


def _settings(*, enabled: bool = True, limit: int = 10_000) -> GuildEconomySettings:
    now = datetime.now(UTC)
    return GuildEconomySettings(
        guild_id=1,
        currency_name="moedas",
        voice_points_per_minute=1,
        message_points=1,
        activity_provider="native",
        economy_channel_id=None,
        shop_channel_id=None,
        staff_log_channel_id=None,
        min_voice_seconds_to_claim=1,
        min_messages_to_claim=1,
        ignore_afk_channel=True,
        ignore_bots=True,
        count_voice_when_alone=False,
        max_admin_grant_per_use=100_000,
        casino_max_bet=10_000,
        casino_daily_profit_limit=limit,
        economy_manager_role_id=None,
        created_at=now,
        updated_at=now,
        casino_limiters_enabled=enabled,
    )


def _repository(*, balance: int, profit: int) -> SimpleNamespace:
    return SimpleNamespace(
        get_wallet=AsyncMock(return_value=SimpleNamespace(balance=balance)),
        get_user_casino_profit_since=AsyncMock(return_value=profit),
    )


@pytest.mark.parametrize("balance", [0, 5_000, 5_001, 25_000])
async def test_first_two_tiers_are_exempt_regardless_of_profit(balance: int) -> None:
    repository = _repository(balance=balance, profit=999_999)

    decision = await select_economic_difficulty_policy(
        repository, _settings(), guild_id=1, user_id=10, game="coin_flip"
    )

    assert decision.policy is EconomicDifficultyPolicyName.EXEMPT
    assert decision.difficulty_bps == 0
    assert decision.daily_profit == 0
    assert decision.daily_profit_evaluated is False
    repository.get_user_casino_profit_since.assert_not_awaited()


async def test_disabled_limiters_do_not_read_daily_profit() -> None:
    repository = _repository(balance=100_000, profit=999_999)

    decision = await select_economic_difficulty_policy(
        repository,
        _settings(enabled=False),
        guild_id=1,
        user_id=10,
        game="dice",
    )

    assert decision.policy is EconomicDifficultyPolicyName.DISABLED
    assert decision.tier is None
    assert decision.daily_profit_evaluated is False
    repository.get_wallet.assert_not_awaited()
    repository.get_user_casino_profit_since.assert_not_awaited()


@pytest.mark.parametrize(
    ("profit", "policy", "difficulty_bps"),
    [
        (6_999, EconomicDifficultyPolicyName.STANDARD, 0),
        (7_000, EconomicDifficultyPolicyName.INCREASED, 3_500),
        (8_000, EconomicDifficultyPolicyName.INCREASED, 3_500),
        (12_000, EconomicDifficultyPolicyName.SEVERE, 5_000),
    ],
)
async def test_threshold_at_6999_7000_and_above_100_percent(
    profit: int,
    policy: EconomicDifficultyPolicyName,
    difficulty_bps: int,
) -> None:
    decision = await select_economic_difficulty_policy(
        _repository(balance=100_000, profit=profit),
        _settings(),
        guild_id=1,
        user_id=10,
        game="slot",
    )

    assert decision.profit_ratio_bps == profit
    assert decision.policy is policy
    assert decision.difficulty_bps == difficulty_bps


@pytest.mark.parametrize("limit", [0, -1])
async def test_zero_or_negative_limit_disables_policy_safely(limit: int) -> None:
    repository = _repository(balance=100_000, profit=10_000)

    decision = await select_economic_difficulty_policy(
        repository, _settings(limit=limit), guild_id=1, user_id=10, game="roulette"
    )

    assert decision.policy is EconomicDifficultyPolicyName.INVALID_LIMIT
    assert decision.difficulty_bps == 0
    assert decision.profit_cap_applies is False
    assert decision.purchase_limit_applies is True
    repository.get_user_casino_profit_since.assert_not_awaited()


async def test_refund_or_negative_daily_profit_does_not_add_difficulty() -> None:
    decision = await select_economic_difficulty_policy(
        _repository(balance=100_000, profit=-500),
        _settings(),
        guild_id=1,
        user_id=10,
        game="scratch_card",
    )

    assert decision.policy is EconomicDifficultyPolicyName.STANDARD
    assert decision.profit_ratio_bps == 0
    assert decision.difficulty_bps == 0


async def test_exempt_tier_payout_is_never_capped() -> None:
    payout = await apply_daily_casino_profit_cap(
        _repository(balance=25_000, profit=20_000),
        _settings(),
        guild_id=1,
        user_id=10,
        stake=100,
        payout=1_000,
        game="uno",
    )

    assert payout == 1_000


async def test_third_tier_payout_remains_safely_capped() -> None:
    payout = await apply_daily_casino_profit_cap(
        _repository(balance=25_001, profit=9_500),
        _settings(),
        guild_id=1,
        user_id=10,
        stake=100,
        payout=1_000,
        game="uno",
    )

    assert payout == 500


def test_daily_window_turns_over_at_midnight_in_economic_timezone() -> None:
    before_midnight = datetime(2026, 7, 15, 2, 59, tzinfo=UTC)
    after_midnight = datetime(2026, 7, 15, 3, 0, tzinfo=UTC)

    before = current_daily_profit_window_start(now=before_midnight)
    after = current_daily_profit_window_start(now=after_midnight)

    assert before.date().isoformat() == "2026-07-14"
    assert after.date().isoformat() == "2026-07-15"
    assert after - before == timedelta(days=1)


async def test_policy_writes_structured_debug_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("DEBUG", logger="app.services.economy_limits"):
        await select_economic_difficulty_policy(
            _repository(balance=100_000, profit=7_000),
            _settings(),
            guild_id=1,
            user_id=42,
            game="coin_flip",
        )

    assert "user_id=42" in caplog.text
    assert "tier=tycoon" in caplog.text
    assert "daily_profit=7000" in caplog.text
    assert "daily_limit=10000" in caplog.text
    assert "ratio_bps=7000" in caplog.text
    assert "policy=increased" in caplog.text
    assert "game=coin_flip" in caplog.text


async def test_increased_threshold_is_configurable() -> None:
    repository = _repository(balance=100_000, profit=6_500)
    service = EconomicDifficultyPolicyService(
        repository,
        EconomicTierService(),
        increased_threshold_bps=6_500,
    )

    decision = await service.select(_settings(), guild_id=1, user_id=10, game="dice")

    assert decision.policy is EconomicDifficultyPolicyName.INCREASED
    assert decision.profit_ratio_bps == 6_500


@pytest.mark.parametrize("enabled", [True, False])
async def test_policy_snapshot_round_trip_preserves_decision(enabled: bool) -> None:
    decision = await select_economic_difficulty_policy(
        _repository(balance=100_000, profit=7_000),
        _settings(enabled=enabled),
        guild_id=1,
        user_id=10,
        game="coin_flip",
    )

    restored = deserialize_economic_difficulty_decision(
        serialize_economic_difficulty_decision(decision)
    )

    assert restored == decision


def test_policy_snapshot_rejects_invalid_version_and_boolean() -> None:
    decision = SimpleNamespace(
        tier=None,
        daily_profit=0,
        daily_limit=10_000,
        profit_ratio_bps=0,
        difficulty_bps=0,
        policy=EconomicDifficultyPolicyName.DISABLED,
        window_start=datetime.now(UTC),
        daily_profit_evaluated=False,
    )
    snapshot = serialize_economic_difficulty_decision(decision)

    with pytest.raises(ValueError, match="Versao"):
        deserialize_economic_difficulty_decision({**snapshot, "version": 999})
    with pytest.raises(ValueError, match="daily_profit_evaluated"):
        deserialize_economic_difficulty_decision(
            {**snapshot, "daily_profit_evaluated": "false"}
        )


async def test_settlement_delegates_economic_timezone_to_atomic_repository() -> None:
    repository = _repository(balance=100_000, profit=7_000)
    service = EconomicDifficultyPolicyService(repository, EconomicTierService())
    decision = await service.select(
        _settings(), guild_id=1, user_id=10, game="coin_flip"
    )
    next_day = decision.window_start + timedelta(days=1)
    repository.settle_casino_payout = AsyncMock(
        return_value=SimpleNamespace(
            daily_profit_before=0,
            requested_payout=200,
            paid_payout=200,
            profit_window_start=next_day,
            idempotent_replay=False,
        )
    )

    await service.settle_payout(
        decision,
        guild_id=1,
        user_id=10,
        stake=100,
        payout=200,
        transaction_type=SimpleNamespace(),
        reason="test",
        metadata={"game": "coin_flip"},
    )

    assert (
        repository.settle_casino_payout.await_args.kwargs[
            "profit_timezone_offset_minutes"
        ]
        == -180
    )
