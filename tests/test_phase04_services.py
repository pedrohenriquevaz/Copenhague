from __future__ import annotations

from pathlib import Path

from app.models.casino import RaceMascot
from app.models.economy import EconomyTransactionType
from app.models.game_progress import CollectiveRaceBetStatus
from app.repositories.economy_repository import SQLiteEconomyRepository
from app.repositories.game_progress_repository import SQLiteGameProgressRepository
from app.services.collective_race_service import CollectiveRaceService
from app.services.game_progress_service import GameProgressService
from app.services.scratch_card_service import ScratchCardService


class FixedRng:
    def __init__(
        self,
        *,
        choices: list[object] | None = None,
    ) -> None:
        self.choices = choices or []

    def choice(self, values):
        if self.choices:
            return self.choices.pop(0)
        return values[0]


async def test_scratch_card_pays_winning_line_and_unlocks_achievement(
    tmp_path: Path,
) -> None:
    economy = SQLiteEconomyRepository(tmp_path / "economy.db")
    progress_repository = SQLiteGameProgressRepository(tmp_path / "progress.db")
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
    economy = SQLiteEconomyRepository(tmp_path / "economy.db")
    progress_repository = SQLiteGameProgressRepository(tmp_path / "progress.db")
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


async def test_collective_race_pays_winners_and_marks_losers(tmp_path: Path) -> None:
    economy = SQLiteEconomyRepository(tmp_path / "economy.db")
    progress_repository = SQLiteGameProgressRepository(tmp_path / "progress.db")
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
    assert winner_wallet.balance == 1400
    assert loser_wallet.balance == 900


async def test_collective_race_cancel_refunds_bets(tmp_path: Path) -> None:
    economy = SQLiteEconomyRepository(tmp_path / "economy.db")
    progress_repository = SQLiteGameProgressRepository(tmp_path / "progress.db")
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
    assert wallet.balance == 1000


async def _seed_wallet(
    repository: SQLiteEconomyRepository,
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
