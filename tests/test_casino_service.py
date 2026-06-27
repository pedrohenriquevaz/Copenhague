from __future__ import annotations

from pathlib import Path

import pytest

from app.models.casino import CoinSide, RaceMascot
from app.models.economy import EconomyTransactionType
from app.repositories.economy_repository import SQLiteEconomyRepository
from app.services.casino_service import (
    SLOT_SYMBOLS,
    CasinoService,
    CasinoValidationError,
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


async def test_coin_flip_debits_bet_and_pays_win(tmp_path: Path) -> None:
    repository = SQLiteEconomyRepository(tmp_path / "economy.db")
    await _seed_wallet(repository, balance=1000)
    service = CasinoService(
        repository,
        rng=FixedRng(choices=[CoinSide.CARA]),
        cooldown_seconds=0,
    )

    result = await service.play_coin_flip(
        guild_id=1,
        user_id=10,
        bet=100,
        choice="cara",
    )
    transactions = await repository.list_transactions(1, 10, limit=5)

    assert result.payout == 200
    assert result.profit == 100
    assert result.wallet.balance == 1100
    assert transactions[0].type is EconomyTransactionType.CASINO_PAYOUT
    assert transactions[1].type is EconomyTransactionType.CASINO_BET


async def test_dice_exact_number_pays_six_times(tmp_path: Path) -> None:
    repository = SQLiteEconomyRepository(tmp_path / "economy.db")
    await _seed_wallet(repository, balance=1000)
    service = CasinoService(
        repository,
        rng=FixedRng(numbers=[6]),
        cooldown_seconds=0,
    )

    result = await service.play_dice(
        guild_id=1,
        user_id=10,
        bet=100,
        mode="numero",
        value=6,
    )

    assert result.result_label == "6"
    assert result.payout == 600
    assert result.profit == 500
    assert result.wallet.balance == 1500


async def test_slot_triple_symbol_uses_paytable(tmp_path: Path) -> None:
    repository = SQLiteEconomyRepository(tmp_path / "economy.db")
    await _seed_wallet(repository, balance=1000)
    symbol = SLOT_SYMBOLS[-1]
    service = CasinoService(
        repository,
        rng=FixedRng(choices=[symbol, symbol, symbol]),
        cooldown_seconds=0,
    )

    result = await service.play_slot(guild_id=1, user_id=10, bet=10)

    assert result.result_label == "Triplo 7️⃣"
    assert result.detail_lines == ["Resultado: 7️⃣ | 7️⃣ | 7️⃣"]
    assert result.payout == 500
    assert result.profit == 490
    assert result.wallet.balance == 1490


async def test_roulette_green_pays_ten_times(tmp_path: Path) -> None:
    repository = SQLiteEconomyRepository(tmp_path / "economy.db")
    await _seed_wallet(repository, balance=1000)
    service = CasinoService(
        repository,
        rng=FixedRng(numbers=[1000]),
        cooldown_seconds=0,
    )

    result = await service.play_roulette(
        guild_id=1,
        user_id=10,
        bet=100,
        color="verde",
    )

    assert result.result_label == "Verde 🟩"
    assert result.payout == 1000
    assert result.profit == 900
    assert result.wallet.balance == 1900


async def test_roulette_black_loses_against_red(tmp_path: Path) -> None:
    repository = SQLiteEconomyRepository(tmp_path / "economy.db")
    await _seed_wallet(repository, balance=1000)
    service = CasinoService(
        repository,
        rng=FixedRng(numbers=[1]),
        cooldown_seconds=0,
    )

    result = await service.play_roulette(
        guild_id=1,
        user_id=10,
        bet=100,
        color="preto",
    )

    assert result.result_label == "Vermelho 🟥"
    assert result.payout == 0
    assert result.profit == -100
    assert result.wallet.balance == 900


async def test_mascot_race_win_pays_five_times(tmp_path: Path) -> None:
    repository = SQLiteEconomyRepository(tmp_path / "economy.db")
    await _seed_wallet(repository, balance=1000)
    service = CasinoService(
        repository,
        rng=FixedRng(choices=[RaceMascot.RAPOSA]),
        cooldown_seconds=0,
    )

    result = await service.play_mascot_race(
        guild_id=1,
        user_id=10,
        bet=100,
        mascot="raposa",
    )

    assert result.result_label == "Raposa"
    assert result.payout == 500
    assert result.profit == 400
    assert result.wallet.balance == 1400


async def test_duel_dice_debits_both_players_and_pays_pot(tmp_path: Path) -> None:
    repository = SQLiteEconomyRepository(tmp_path / "economy.db")
    await _seed_wallet(repository, user_id=10, balance=1000)
    await _seed_wallet(repository, user_id=20, balance=1000)
    service = CasinoService(
        repository,
        rng=FixedRng(numbers=[6, 2]),
        cooldown_seconds=0,
    )

    result = await service.resolve_duel(
        guild_id=1,
        challenger_id=10,
        challenged_id=20,
        bet=100,
        mode="dados",
    )

    assert result.winner_id == 10
    assert result.payout == 200
    assert result.challenger_wallet.balance == 1100
    assert result.challenged_wallet.balance == 900


async def test_duel_draw_refunds_both_players(tmp_path: Path) -> None:
    repository = SQLiteEconomyRepository(tmp_path / "economy.db")
    await _seed_wallet(repository, user_id=10, balance=1000)
    await _seed_wallet(repository, user_id=20, balance=1000)
    service = CasinoService(
        repository,
        rng=FixedRng(numbers=[4, 4]),
        cooldown_seconds=0,
    )

    result = await service.resolve_duel(
        guild_id=1,
        challenger_id=10,
        challenged_id=20,
        bet=100,
        mode="dados",
    )

    assert result.winner_id is None
    assert result.challenger_wallet.balance == 1000
    assert result.challenged_wallet.balance == 1000


async def test_duel_cooldown_blocks_recent_player(tmp_path: Path) -> None:
    repository = SQLiteEconomyRepository(tmp_path / "economy.db")
    await _seed_wallet(repository, user_id=10, balance=1000)
    await _seed_wallet(repository, user_id=20, balance=1000)
    await _seed_wallet(repository, user_id=30, balance=1000)
    service = CasinoService(
        repository,
        rng=FixedRng(numbers=[6, 2]),
        cooldown_seconds=60,
    )

    await service.resolve_duel(
        guild_id=1,
        challenger_id=10,
        challenged_id=20,
        bet=100,
        mode="dados",
    )

    with pytest.raises(CasinoValidationError, match="Aguarde"):
        await service.validate_duel_challenge(
            guild_id=1,
            challenger_id=10,
            challenged_id=30,
            bet=100,
            mode="dados",
        )


async def test_casino_user_stats_and_ranking(tmp_path: Path) -> None:
    repository = SQLiteEconomyRepository(tmp_path / "economy.db")
    await _seed_wallet(repository, user_id=10, balance=1000)
    await _seed_wallet(repository, user_id=20, balance=1000)
    service = CasinoService(
        repository,
        rng=FixedRng(choices=[CoinSide.CARA, CoinSide.COROA]),
        cooldown_seconds=0,
    )

    await service.play_coin_flip(guild_id=1, user_id=10, bet=100, choice="cara")
    await service.play_coin_flip(guild_id=1, user_id=20, bet=100, choice="cara")

    stats = await service.get_user_stats(1, 10)
    ranking = await service.list_profit_ranking(1)

    assert stats.total_games_played == 1
    assert stats.total_bet_amount == 100
    assert stats.total_payout_amount == 200
    assert stats.net_profit == 100
    assert ranking[0].user_id == 10
    assert ranking[0].net_profit == 100


async def test_casino_cooldown_blocks_repeated_game(tmp_path: Path) -> None:
    repository = SQLiteEconomyRepository(tmp_path / "economy.db")
    await _seed_wallet(repository, balance=1000)
    service = CasinoService(
        repository,
        rng=FixedRng(choices=[CoinSide.CARA, CoinSide.CARA]),
        cooldown_seconds=60,
    )

    await service.play_coin_flip(guild_id=1, user_id=10, bet=100, choice="cara")

    with pytest.raises(CasinoValidationError, match="Aguarde"):
        await service.play_coin_flip(guild_id=1, user_id=10, bet=100, choice="cara")


async def test_casino_history_returns_only_game_transactions(tmp_path: Path) -> None:
    repository = SQLiteEconomyRepository(tmp_path / "economy.db")
    await _seed_wallet(repository, balance=1000)
    service = CasinoService(
        repository,
        rng=FixedRng(choices=[CoinSide.COROA]),
        cooldown_seconds=0,
    )

    await service.play_coin_flip(guild_id=1, user_id=10, bet=100, choice="cara")
    history = await service.list_history(1, 10)

    assert len(history) == 1
    assert history[0].type is EconomyTransactionType.CASINO_BET
    assert history[0].metadata["game"] == "coin_flip"


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
