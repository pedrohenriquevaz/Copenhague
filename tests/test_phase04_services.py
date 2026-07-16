from __future__ import annotations

from pathlib import Path

import pytest

from app.models.casino import RaceMascot
from app.models.economy import EconomyTransactionType
from app.models.game_progress import CollectiveRaceBetStatus
from app.services.collective_race_service import (
    CollectiveRaceService,
    CollectiveRaceValidationError,
)
from app.services.economy_limits import current_daily_profit_window_start
from app.services.game_progress_service import DEFAULT_ACHIEVEMENTS, GameProgressService
from app.services.scratch_card_service import (
    SCRATCH_DAILY_PURCHASE_LIMIT,
    ScratchCardService,
    ScratchCardValidationError,
)
from tests.postgres_support import (
    PostgresEconomyRepository,
    PostgresGameProgressRepository,
)


class FixedRng:
    def __init__(
        self,
        *,
        choices: list[object] | None = None,
        numbers: list[int] | None = None,
    ) -> None:
        self.choices = choices or []
        self.numbers = numbers or []

    def choice(self, values):
        if self.choices:
            return self.choices.pop(0)
        return values[0]

    def randint(self, start: int, end: int) -> int:
        if self.numbers:
            return self.numbers.pop(0)
        return start


async def test_scratch_card_pays_winning_line_and_unlocks_achievement(
    tmp_path: Path,
) -> None:
    economy = PostgresEconomyRepository(tmp_path / "economy.db")
    progress_repository = PostgresGameProgressRepository(tmp_path / "progress.db")
    progress = GameProgressService(progress_repository, economy)
    service = ScratchCardService(
        economy,
        progress,
        rng=FixedRng(
            choices=[
                "🍒",
                "🍒",
                "🍒",
                "⭐",
                "💎",
                "🔔",
                "🍀",
                "7️⃣",
                "⭐",
            ]
        ),
    )
    await _seed_wallet(economy, balance=1000)

    result = await service.play(guild_id=1, user_id=10, tier="bronze")
    achievements = await progress.list_user_achievements(1, 10)

    assert result.winning_lines == ["Linha 1"]
    assert result.payout == 150
    assert result.wallet.balance == 1100
    assert {item.achievement.achievement_key for item in achievements} >= {
        "first_bet",
        "first_scratch",
        "first_win",
    }


async def test_scratch_card_jackpot_accumulates_and_can_be_claimed(
    tmp_path: Path,
) -> None:
    economy = PostgresEconomyRepository(tmp_path / "economy.db")
    progress_repository = PostgresGameProgressRepository(tmp_path / "progress.db")
    progress = GameProgressService(progress_repository, economy)
    service = ScratchCardService(
        economy,
        progress,
        rng=FixedRng(choices=["💎"] * 9),
    )
    await _seed_wallet(economy, balance=1000)
    await progress.add_scratch_jackpot(1, 100)

    result = await service.play(guild_id=1, user_id=10, tier="bronze")
    jackpot = await progress.get_scratch_jackpot(1)

    assert result.jackpot_won == 105
    assert result.payout == 1305
    assert jackpot.amount == 0


async def test_scratch_card_diamond_win_gate_can_turn_line_into_loss(
    tmp_path: Path,
) -> None:
    economy = PostgresEconomyRepository(tmp_path / "economy.db")
    progress_repository = PostgresGameProgressRepository(tmp_path / "progress.db")
    progress = GameProgressService(progress_repository, economy)
    service = ScratchCardService(
        economy,
        progress,
        rng=FixedRng(
            choices=[
                "ðŸ’",
                "ðŸ’",
                "ðŸ’",
                "â­",
                "ðŸ’Ž",
                "ðŸ””",
                "ðŸ€",
                "7ï¸âƒ£",
                "â­",
            ],
            numbers=[10_000],
        ),
    )
    await _seed_wallet(economy, balance=1000)

    result = await service.play(guild_id=1, user_id=10, tier="diamante")

    assert result.winning_lines == []
    assert result.payout == 0
    assert result.wallet.balance == 500


async def test_scratch_card_profit_pressure_reduces_win_gate(
    tmp_path: Path,
) -> None:
    economy = PostgresEconomyRepository(tmp_path / "economy.db")
    await economy.update_guild_settings(1, {"casino_daily_profit_limit": 5000})
    progress_repository = PostgresGameProgressRepository(tmp_path / "progress.db")
    progress = GameProgressService(progress_repository, economy)
    service = ScratchCardService(
        economy,
        progress,
        rng=FixedRng(
            choices=[
                "ðŸ’",
                "ðŸ’",
                "ðŸ’",
                "â­",
                "ðŸ’Ž",
                "ðŸ””",
                "ðŸ€",
                "7ï¸âƒ£",
                "â­",
            ],
            numbers=[9_000],
        ),
    )
    await _seed_wallet(economy, balance=30000)
    await economy.mutate_balance(
        guild_id=1,
        user_id=10,
        amount=-100,
        transaction_type=EconomyTransactionType.CASINO_BET,
        actor_id=None,
        reason="previous_bet",
        metadata={"game": "coin_flip", "bet": 100},
    )
    await economy.mutate_balance(
        guild_id=1,
        user_id=10,
        amount=3600,
        transaction_type=EconomyTransactionType.CASINO_PAYOUT,
        actor_id=None,
        reason="previous_payout",
        metadata={"game": "coin_flip", "bet": 100, "outcome": "WON"},
    )

    result = await service.play(guild_id=1, user_id=10, tier="bronze")

    assert result.winning_lines == []
    assert result.payout == 0
    assert result.wallet.balance == 33450


async def test_scratch_card_limits_daily_purchases_per_user(
    tmp_path: Path,
) -> None:
    economy = PostgresEconomyRepository(tmp_path / "economy.db")
    progress_repository = PostgresGameProgressRepository(tmp_path / "progress.db")
    progress = GameProgressService(progress_repository, economy)
    service = ScratchCardService(
        economy,
        progress,
        rng=FixedRng(),
    )
    await _seed_wallet(economy, balance=30000)

    for _ in range(SCRATCH_DAILY_PURCHASE_LIMIT):
        await service.play(guild_id=1, user_id=10, tier="bronze")

    wallet_before_block = await economy.get_wallet(1, 10)
    with pytest.raises(ScratchCardValidationError, match="limite diario"):
        await service.play(guild_id=1, user_id=10, tier="diamante")
    wallet_after_block = await economy.get_wallet(1, 10)
    purchases_today = await economy.count_user_scratch_card_purchases_since(
        1,
        10,
        current_daily_profit_window_start(),
    )

    assert purchases_today == SCRATCH_DAILY_PURCHASE_LIMIT
    assert wallet_after_block.balance == wallet_before_block.balance


async def test_scratch_card_daily_purchase_limit_can_be_disabled(
    tmp_path: Path,
) -> None:
    economy = PostgresEconomyRepository(tmp_path / "economy.db")
    await economy.update_guild_settings(1, {"casino_limiters_enabled": 0})
    progress_repository = PostgresGameProgressRepository(tmp_path / "progress.db")
    progress = GameProgressService(progress_repository, economy)
    service = ScratchCardService(
        economy,
        progress,
        rng=FixedRng(),
    )
    await _seed_wallet(economy, balance=30000)

    for _ in range(SCRATCH_DAILY_PURCHASE_LIMIT + 1):
        await service.play(guild_id=1, user_id=10, tier="bronze")

    purchases_today = await economy.count_user_scratch_card_purchases_since(
        1,
        10,
        current_daily_profit_window_start(),
    )

    assert purchases_today == SCRATCH_DAILY_PURCHASE_LIMIT + 1


async def test_scratch_card_uses_configured_min_bet(
    tmp_path: Path,
) -> None:
    economy = PostgresEconomyRepository(tmp_path / "economy.db")
    await economy.update_guild_settings(1, {"casino_min_bet_scratch_card": 100})
    progress_repository = PostgresGameProgressRepository(tmp_path / "progress.db")
    progress = GameProgressService(progress_repository, economy)
    service = ScratchCardService(economy, progress, rng=FixedRng())
    await _seed_wallet(economy, balance=1000)

    with pytest.raises(ScratchCardValidationError, match="aposta minima"):
        await service.play(guild_id=1, user_id=10, tier="bronze")


async def test_collective_race_pays_winners_and_marks_losers(tmp_path: Path) -> None:
    economy = PostgresEconomyRepository(tmp_path / "economy.db")
    progress_repository = PostgresGameProgressRepository(tmp_path / "progress.db")
    progress = GameProgressService(progress_repository, economy)
    service = CollectiveRaceService(progress_repository, economy, progress)
    await _seed_wallet(economy, user_id=10, balance=1000)
    await _seed_wallet(economy, user_id=20, balance=1000)
    race = await service.create_race(
        guild_id=1,
        opened_by=99,
        stake=100,
        duration_seconds=60,
    )

    await service.place_bet(guild_id=1, user_id=10, race_id=race.id, mascot="dragao")
    await service.place_bet(guild_id=1, user_id=20, race_id=race.id, mascot="lobo")
    result = await service.finish_race(
        guild_id=1,
        race_id=race.id,
        winner="dragao",
    )
    winner_wallet = await economy.get_wallet(1, 10)
    loser_wallet = await economy.get_wallet(1, 20)

    assert result.winner is RaceMascot.DRAGAO
    assert result.winning_bets == 1
    assert result.lost_bets == 1
    assert result.total_paid == 500
    assert winner_wallet.balance == 1500
    assert loser_wallet.balance == 950


async def test_collective_race_persists_pre_debit_policy_snapshot(
    tmp_path: Path,
) -> None:
    economy = PostgresEconomyRepository(tmp_path / "economy.db")
    await economy.update_guild_settings(1, {"casino_daily_profit_limit": 30})
    progress_repository = PostgresGameProgressRepository(tmp_path / "progress.db")
    progress = GameProgressService(progress_repository, economy)
    service = CollectiveRaceService(progress_repository, economy, progress)
    await _seed_wallet(economy, balance=25_001)
    race = await service.create_race(
        guild_id=1,
        opened_by=99,
        stake=100,
        duration_seconds=60,
    )

    placement = await service.place_bet(
        guild_id=1,
        user_id=10,
        race_id=race.id,
        mascot="dragao",
    )
    reloaded_repository = PostgresGameProgressRepository(tmp_path / "progress.db")
    reloaded_progress = GameProgressService(reloaded_repository, economy)
    reloaded_service = CollectiveRaceService(
        reloaded_repository,
        economy,
        reloaded_progress,
    )
    result = await reloaded_service.finish_race(
        guild_id=1,
        race_id=race.id,
        winner="dragao",
    )
    balance_after_first_finish = (await economy.get_wallet(1, 10)).balance
    payout_transactions = [
        transaction
        for transaction in await economy.list_transactions(1, 10, limit=20)
        if transaction.reason == "collective_race_payout"
    ]
    await reloaded_service.finish_race(
        guild_id=1,
        race_id=race.id,
        winner="dragao",
    )

    assert placement.bet.economic_policy_snapshot is not None
    assert placement.bet.economic_policy_snapshot["tier"]["identifier"] == (
        "prosperous"
    )
    assert result.total_paid == 130
    assert len(payout_transactions) == 1
    assert payout_transactions[0].amount == 130
    assert payout_transactions[0].metadata["payout"] == 130
    assert (await economy.get_wallet(1, 10)).balance == balance_after_first_finish


async def test_collective_race_cancel_refunds_bets(tmp_path: Path) -> None:
    economy = PostgresEconomyRepository(tmp_path / "economy.db")
    progress_repository = PostgresGameProgressRepository(tmp_path / "progress.db")
    progress = GameProgressService(progress_repository, economy)
    service = CollectiveRaceService(progress_repository, economy, progress)
    await _seed_wallet(economy, balance=1000)
    race = await service.create_race(
        guild_id=1,
        opened_by=99,
        stake=100,
        duration_seconds=60,
    )

    await service.place_bet(guild_id=1, user_id=10, race_id=race.id, mascot="dragao")
    result = await service.finish_race(guild_id=1, race_id=race.id, cancel=True)
    wallet = await economy.get_wallet(1, 10)

    assert result.refunded_bets == 1
    assert result.bets[0].status is CollectiveRaceBetStatus.REFUNDED
    assert result.total_refunded == 100
    assert wallet.balance == 1025


async def test_collective_race_duplicate_rollback_does_not_consume_cancel_refund_key(
    tmp_path: Path,
) -> None:
    economy = PostgresEconomyRepository(tmp_path / "economy.db")
    progress_repository = PostgresGameProgressRepository(tmp_path / "progress.db")
    progress = GameProgressService(progress_repository, economy)
    service = CollectiveRaceService(progress_repository, economy, progress)
    await _seed_wallet(economy, balance=1000)
    race = await service.create_race(
        guild_id=1,
        opened_by=99,
        stake=100,
        duration_seconds=60,
    )
    placement = await service.place_bet(
        guild_id=1,
        user_id=10,
        race_id=race.id,
        mascot="dragao",
    )
    balance_after_first_bet = (await economy.get_wallet(1, 10)).balance

    with pytest.raises(CollectiveRaceValidationError, match="ja apostou"):
        await service.place_bet(
            guild_id=1,
            user_id=10,
            race_id=race.id,
            mascot="lobo",
        )

    assert (await economy.get_wallet(1, 10)).balance == balance_after_first_bet
    settlement = await service.finish_race(
        guild_id=1,
        race_id=race.id,
        cancel=True,
    )
    refunds = [
        transaction
        for transaction in await economy.list_transactions(1, 10, limit=20)
        if transaction.type is EconomyTransactionType.REFUND
        and transaction.reason == "collective_race_refund"
    ]
    refund_keys = {transaction.idempotency_key for transaction in refunds}

    assert settlement.total_refunded == 100
    assert (await economy.get_wallet(1, 10)).balance == balance_after_first_bet + 100
    assert len(refunds) == 2
    assert f"collective_race:bet:{placement.bet.id}:refund" in refund_keys
    assert any(
        key is not None and key.startswith("collective_race:transaction:")
        for key in refund_keys
    )


async def test_collective_race_uses_configured_min_bet(tmp_path: Path) -> None:
    economy = PostgresEconomyRepository(tmp_path / "economy.db")
    await economy.update_guild_settings(1, {"casino_min_bet_collective_race": 150})
    progress_repository = PostgresGameProgressRepository(tmp_path / "progress.db")
    progress = GameProgressService(progress_repository, economy)
    service = CollectiveRaceService(progress_repository, economy, progress)

    with pytest.raises(CollectiveRaceValidationError, match="aposta minima"):
        await service.create_race(
            guild_id=1,
            opened_by=99,
            stake=100,
            duration_seconds=60,
        )


async def test_game_progress_admin_summary(tmp_path: Path) -> None:
    economy = PostgresEconomyRepository(tmp_path / "economy.db")
    progress_repository = PostgresGameProgressRepository(tmp_path / "progress.db")
    progress = GameProgressService(progress_repository, economy)
    service = CollectiveRaceService(progress_repository, economy, progress)
    await _seed_wallet(economy, balance=1000)
    race = await service.create_race(
        guild_id=1,
        opened_by=99,
        stake=100,
        duration_seconds=60,
    )

    await service.place_bet(guild_id=1, user_id=10, race_id=race.id, mascot="dragao")
    await progress.unlock(1, 10, "first_bet")
    summary = await progress_repository.get_admin_summary(1)

    assert summary["total_races"] == 1
    assert summary["open_races"] == 1
    assert summary["race_bets"] == 1
    assert summary["race_stake"] == 100
    assert summary["unlocked_achievements"] >= 1


async def test_game_progress_reset_user_profile_clears_user_data(
    tmp_path: Path,
) -> None:
    economy = PostgresEconomyRepository(tmp_path / "economy.db")
    progress_repository = PostgresGameProgressRepository(tmp_path / "progress.db")
    progress = GameProgressService(progress_repository, economy)
    service = CollectiveRaceService(progress_repository, economy, progress)
    await _seed_wallet(economy, balance=1000)
    race = await service.create_race(
        guild_id=1,
        opened_by=99,
        stake=100,
        duration_seconds=60,
    )

    await service.place_bet(guild_id=1, user_id=10, race_id=race.id, mascot="dragao")
    await progress.unlock(1, 10, "first_win")

    counts = await progress_repository.reset_user_profile(1, 10)
    achievements = await progress.list_user_achievements(1, 10)
    summary = await progress_repository.get_admin_summary(1)

    assert counts["achievements"] == 2
    assert counts["collective_race_bets"] == 1
    assert achievements == []
    assert summary["race_bets"] == 0
    assert summary["unlocked_achievements"] == 0


async def test_default_achievements_include_gradual_rewards() -> None:
    rewards = {
        achievement.achievement_key: achievement.reward_points
        for achievement in DEFAULT_ACHIEVEMENTS
    }

    assert len(DEFAULT_ACHIEVEMENTS) == 30
    assert rewards["first_bet"] == 25
    assert rewards["big_win_5k"] == 300
    assert rewards["duel_king"] == 500
    assert rewards["scratch_jackpot"] == 750


async def test_configure_achievement_reward_persists_after_default_sync(
    tmp_path: Path,
) -> None:
    economy = PostgresEconomyRepository(tmp_path / "economy.db")
    progress_repository = PostgresGameProgressRepository(tmp_path / "progress.db")
    progress = GameProgressService(progress_repository, economy)

    await progress.ensure_default_achievements(1)
    configured = await progress.configure_achievement_reward(1, "first_bet", 777)
    await progress.ensure_default_achievements(1)
    unlocked = await progress.unlock(1, 10, "first_bet")
    wallet = await economy.get_wallet(1, 10)

    assert configured.reward_points == 777
    assert unlocked is not None
    assert unlocked.achievement.reward_points == 777
    assert wallet.balance == 777


async def test_game_progress_unlocks_milestones_from_transactions(
    tmp_path: Path,
) -> None:
    economy = PostgresEconomyRepository(tmp_path / "economy.db")
    progress_repository = PostgresGameProgressRepository(tmp_path / "progress.db")
    progress = GameProgressService(progress_repository, economy)
    await _seed_wallet(economy, balance=6000)
    await economy.mutate_balance(
        guild_id=1,
        user_id=10,
        amount=-100,
        transaction_type=EconomyTransactionType.CASINO_BET,
        actor_id=None,
        reason="coin_flip_bet",
        metadata={"game": "coin_flip", "bet": 100},
    )
    await economy.mutate_balance(
        guild_id=1,
        user_id=10,
        amount=5000,
        transaction_type=EconomyTransactionType.CASINO_PAYOUT,
        actor_id=None,
        reason="coin_flip_payout",
        metadata={"game": "coin_flip", "bet": 100, "outcome": "WON"},
    )

    unlocked = await progress.evaluate_user_milestones(1, 10)
    keys = {item.achievement.achievement_key for item in unlocked}
    wallet = await economy.get_wallet(1, 10)

    assert keys >= {"points_10k", "big_win_1k", "big_win_5k"}
    assert wallet.balance == 11_400


async def test_list_user_achievements_pays_unpaid_existing_reward_once(
    tmp_path: Path,
) -> None:
    economy = PostgresEconomyRepository(tmp_path / "economy.db")
    progress_repository = PostgresGameProgressRepository(tmp_path / "progress.db")
    progress = GameProgressService(progress_repository, economy)

    await progress.ensure_default_achievements(1)
    unlocked, is_new = await progress_repository.unlock_achievement(
        1,
        10,
        "first_bet",
    )

    assert unlocked is not None
    assert is_new is True
    assert (await economy.get_wallet(1, 10)).balance == 0

    achievements = await progress.list_user_achievements(1, 10)
    wallet_after_first_list = await economy.get_wallet(1, 10)
    await progress.list_user_achievements(1, 10)
    wallet_after_second_list = await economy.get_wallet(1, 10)

    assert {item.achievement.achievement_key for item in achievements} >= {"first_bet"}
    assert wallet_after_first_list.balance == 25
    assert wallet_after_second_list.balance == 25


async def test_list_user_achievements_does_not_double_pay_old_reward_transaction(
    tmp_path: Path,
) -> None:
    economy = PostgresEconomyRepository(tmp_path / "economy.db")
    progress_repository = PostgresGameProgressRepository(tmp_path / "progress.db")
    progress = GameProgressService(progress_repository, economy)

    await progress.ensure_default_achievements(1)
    await progress_repository.unlock_achievement(1, 10, "first_bet")
    await economy.mutate_balance(
        guild_id=1,
        user_id=10,
        amount=100,
        transaction_type=EconomyTransactionType.SYSTEM_ADJUSTMENT,
        actor_id=None,
        reason="achievement_reward",
        metadata={"achievement_key": "first_bet"},
    )

    await progress.list_user_achievements(1, 10)
    wallet = await economy.get_wallet(1, 10)

    assert wallet.balance == 100


async def _seed_wallet(
    repository: PostgresEconomyRepository,
    *,
    user_id: int = 10,
    balance: int,
) -> None:
    await repository.mutate_balance(
        guild_id=1,
        user_id=user_id,
        amount=balance,
        transaction_type=EconomyTransactionType.SYSTEM_ADJUSTMENT,
        actor_id=None,
        reason="test_seed",
        metadata={"source": "test"},
    )
