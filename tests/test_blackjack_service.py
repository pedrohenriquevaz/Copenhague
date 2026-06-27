from __future__ import annotations

from pathlib import Path

import pytest

from app.models.casino import BlackjackCard, BlackjackOutcome, CardRank, CardSuit
from app.models.economy import EconomyTransactionType
from app.repositories.economy_repository import SQLiteEconomyRepository
from app.services.blackjack_service import (
    BlackjackService,
    BlackjackValidationError,
    calculate_hand_value,
)


def card(rank: CardRank, suit: CardSuit = CardSuit.SPADES) -> BlackjackCard:
    return BlackjackCard(rank=rank, suit=suit)


def test_calculates_blackjack_hand_with_flexible_aces() -> None:
    assert card(CardRank.SEVEN, CardSuit.HEARTS).display == "7"
    assert (
        calculate_hand_value(
            [
                card(CardRank.ACE),
                card(CardRank.NINE),
                card(CardRank.ACE),
            ]
        )
        == 21
    )
    assert (
        calculate_hand_value(
            [
                card(CardRank.ACE),
                card(CardRank.KING),
            ]
        )
        == 21
    )
    assert (
        calculate_hand_value(
            [
                card(CardRank.KING),
                card(CardRank.QUEEN),
                card(CardRank.TWO),
            ]
        )
        == 22
    )


async def test_blackjack_natural_pays_two_and_half_times(tmp_path: Path) -> None:
    repository = SQLiteEconomyRepository(tmp_path / "economy.db")
    await _seed_wallet(repository, balance=1000)
    service = BlackjackService(
        repository,
        deck_factory=lambda: [
            card(CardRank.ACE),
            card(CardRank.NINE),
            card(CardRank.KING),
            card(CardRank.SEVEN),
        ],
    )

    session = await service.start_game(guild_id=1, user_id=10, bet=100)
    wallet = await repository.get_wallet(1, 10)
    transactions = await repository.list_transactions(1, 10, limit=5)

    assert session.outcome is BlackjackOutcome.PLAYER_BLACKJACK
    assert session.payout == 250
    assert wallet.balance == 1150
    assert transactions[0].type is EconomyTransactionType.CASINO_PAYOUT
    assert transactions[1].type is EconomyTransactionType.CASINO_BET


async def test_blackjack_double_down_debits_extra_bet_and_pays_win(
    tmp_path: Path,
) -> None:
    repository = SQLiteEconomyRepository(tmp_path / "economy.db")
    await _seed_wallet(repository, balance=1000)
    service = BlackjackService(
        repository,
        deck_factory=lambda: [
            card(CardRank.FIVE),
            card(CardRank.NINE),
            card(CardRank.SIX),
            card(CardRank.KING),
            card(CardRank.SEVEN),
            card(CardRank.FOUR),
        ],
    )

    started = await service.start_game(guild_id=1, user_id=10, bet=100)
    assert len(started.dealer_hand.cards) == 1
    session = await service.double_down(guild_id=1, user_id=10)
    wallet = await repository.get_wallet(1, 10)

    assert session.outcome is BlackjackOutcome.PLAYER_WIN
    assert session.bet == 200
    assert session.payout == 400
    assert wallet.balance == 1200


async def test_blackjack_blocks_duplicate_and_insufficient_balance(
    tmp_path: Path,
) -> None:
    repository = SQLiteEconomyRepository(tmp_path / "economy.db")
    await _seed_wallet(repository, balance=50)
    service = BlackjackService(
        repository,
        deck_factory=lambda: [
            card(CardRank.FIVE),
            card(CardRank.NINE),
            card(CardRank.SIX),
            card(CardRank.SEVEN),
        ],
    )

    with pytest.raises(BlackjackValidationError, match="Saldo insuficiente"):
        await service.start_game(guild_id=1, user_id=10, bet=100)

    await service.start_game(guild_id=1, user_id=10, bet=10)
    with pytest.raises(BlackjackValidationError, match="em andamento"):
        await service.start_game(guild_id=1, user_id=10, bet=10)


async def _seed_wallet(
    repository: SQLiteEconomyRepository,
    *,
    balance: int,
) -> None:
    await repository.mutate_balance(
        guild_id=1,
        user_id=10,
        amount=balance,
        transaction_type=EconomyTransactionType.SYSTEM_ADJUSTMENT,
        actor_id=None,
        reason="test_seed",
        metadata={"source": "test"},
    )
