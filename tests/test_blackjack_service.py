from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import discord
import pytest
from PIL import Image

from app.models.casino import (
    BlackjackCard,
    BlackjackOutcome,
    BlackjackSession,
    CardRank,
    CardSuit,
)
from app.models.economy import EconomyTransactionType
from app.models.guild_settings import GuildEconomySettings
from app.services.blackjack_service import (
    BlackjackService,
    BlackjackValidationError,
    calculate_hand_value,
)
from app.ui.blackjack_table_image import (
    BLACKJACK_TABLE_FILENAME,
    render_blackjack_table_image,
)
from app.ui.blackjack_view import BlackjackView, build_blackjack_embed
from tests.postgres_support import PostgresEconomyRepository


def card(rank: CardRank, suit: CardSuit = CardSuit.SPADES) -> BlackjackCard:
    return BlackjackCard(rank=rank, suit=suit)


def _blackjack_session() -> BlackjackSession:
    return BlackjackSession(guild_id=1, user_id=10, bet=100, deck=[])


def _settings() -> GuildEconomySettings:
    now = datetime.now(UTC)
    return GuildEconomySettings(
        guild_id=1,
        currency_name="pontos",
        voice_points_per_minute=2,
        message_points=1,
        activity_provider="native",
        economy_channel_id=None,
        shop_channel_id=None,
        staff_log_channel_id=None,
        min_voice_seconds_to_claim=60,
        min_messages_to_claim=1,
        ignore_afk_channel=True,
        ignore_bots=True,
        count_voice_when_alone=False,
        max_admin_grant_per_use=100000,
        casino_max_bet=1000,
        casino_daily_profit_limit=5000,
        economy_manager_role_id=None,
        created_at=now,
        updated_at=now,
    )


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


def test_blackjack_embed_uses_compact_table_layout() -> None:
    session = _blackjack_session()
    session.player_hand.add(card(CardRank.ACE, CardSuit.SPADES))
    session.player_hand.add(card(CardRank.KING, CardSuit.HEARTS))
    session.dealer_hand.add(card(CardRank.SIX, CardSuit.DIAMONDS))

    embed = build_blackjack_embed(
        session,
        _settings(),
        player_display_name="Copenhague",
        player_avatar_url="https://cdn.example.com/avatar.png",
    )

    assert embed.title == "♣ Blackjack"
    assert embed.description is not None
    assert "**Banca (6+?):**" in embed.description
    assert "`♦ 6` `? ?`" in embed.description
    assert "**Copenhague (21):**" in embed.description
    assert "`♠ A` `♥ K`" in embed.description
    assert embed.thumbnail.url == "https://cdn.example.com/avatar.png"
    assert embed.image.url == f"attachment://{BLACKJACK_TABLE_FILENAME}"


def test_blackjack_table_image_renders_png() -> None:
    session = _blackjack_session()
    session.player_hand.add(card(CardRank.ACE, CardSuit.SPADES))
    session.player_hand.add(card(CardRank.KING, CardSuit.HEARTS))
    session.dealer_hand.add(card(CardRank.SIX, CardSuit.DIAMONDS))

    image_bytes = render_blackjack_table_image(
        session,
        _settings(),
        player_display_name="Copenhague",
    )

    assert image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(BytesIO(image_bytes)) as image:
        assert image.size == (960, 640)
        assert image.mode == "RGB"


def test_blackjack_view_exposes_visual_buttons() -> None:
    active = BlackjackView(
        object(),  # type: ignore[arg-type]
        _blackjack_session(),
        _settings(),
    )
    labels = {
        item.label: item.disabled
        for item in active.children
        if isinstance(item, discord.ui.Button)
    }

    assert labels["Pedir carta"] is False
    assert labels["Split"] is True
    assert labels["Seguro"] is True
    assert labels["Começar nova partida"] is True

    finished_session = _blackjack_session()
    finished_session.outcome = BlackjackOutcome.PLAYER_WIN
    finished = BlackjackView(
        object(),  # type: ignore[arg-type]
        finished_session,
        _settings(),
    )
    finished_labels = {
        item.label: item.disabled
        for item in finished.children
        if isinstance(item, discord.ui.Button)
    }
    assert finished_labels["Pedir carta"] is True
    assert finished_labels["Começar nova partida"] is False


async def test_blackjack_natural_pays_two_and_half_times(tmp_path: Path) -> None:
    repository = PostgresEconomyRepository(tmp_path / "economy.db")
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
    repository = PostgresEconomyRepository(tmp_path / "economy.db")
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


async def test_blackjack_win_streak_bonus_multiplies_profit(
    tmp_path: Path,
) -> None:
    repository = PostgresEconomyRepository(tmp_path / "economy.db")
    await _seed_wallet(repository, balance=1000)
    decks = [
        [
            card(CardRank.KING),
            card(CardRank.NINE),
            card(CardRank.QUEEN),
            card(CardRank.SEVEN),
            card(CardRank.TWO),
        ],
        [
            card(CardRank.KING),
            card(CardRank.NINE),
            card(CardRank.QUEEN),
            card(CardRank.SEVEN),
            card(CardRank.TWO),
        ],
    ]
    service = BlackjackService(repository, deck_factory=lambda: decks.pop(0))

    first = await service.start_game(guild_id=1, user_id=10, bet=100)
    first = await service.stand(guild_id=1, user_id=10)
    second = await service.start_game(guild_id=1, user_id=10, bet=100)
    second = await service.stand(guild_id=1, user_id=10)
    wallet = await repository.get_wallet(1, 10)

    assert first.outcome is BlackjackOutcome.PLAYER_WIN
    assert first.payout == 200
    assert first.win_streak == 1
    assert second.outcome is BlackjackOutcome.PLAYER_WIN
    assert second.base_payout == 200
    assert second.streak_bonus == 10
    assert second.payout == 210
    assert second.win_streak == 2
    assert second.payout_multiplier_percent == 110
    assert wallet.balance == 1210


async def test_blackjack_blocks_duplicate_and_insufficient_balance(
    tmp_path: Path,
) -> None:
    repository = PostgresEconomyRepository(tmp_path / "economy.db")
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


async def test_blackjack_uses_configured_min_bet(tmp_path: Path) -> None:
    repository = PostgresEconomyRepository(tmp_path / "economy.db")
    await repository.update_guild_settings(1, {"casino_min_bet_blackjack": 75})
    await _seed_wallet(repository, balance=1000)
    service = BlackjackService(
        repository,
        deck_factory=lambda: [
            card(CardRank.FIVE),
            card(CardRank.NINE),
            card(CardRank.SIX),
            card(CardRank.SEVEN),
        ],
    )

    with pytest.raises(BlackjackValidationError, match="aposta mínima"):
        await service.start_game(guild_id=1, user_id=10, bet=50)


async def _seed_wallet(
    repository: PostgresEconomyRepository,
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
