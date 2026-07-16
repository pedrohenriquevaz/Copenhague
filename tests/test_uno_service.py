from __future__ import annotations

import random
from io import BytesIO
from unittest.mock import AsyncMock

import discord
import pytest
from PIL import Image

from app.models.uno import (
    UnoCard,
    UnoColor,
    UnoGameStatus,
    UnoPlayer,
    UnoSession,
    UnoValue,
)
from app.services.economy_service import EconomyService
from app.services.uno_service import UnoService, UnoValidationError
from app.ui.uno_table_image import render_uno_table_image
from app.ui.uno_view import (
    HAND_PAGE_SIZE,
    UnoCardSelect,
    UnoHandView,
    _edit_uno_hand_handle,
    _register_uno_hand,
    refresh_open_uno_hands,
)
from tests.postgres_support import PostgresEconomyRepository, PostgresUnoRepository


def test_uno_deck_has_standard_108_cards() -> None:
    deck = UnoService.build_deck()

    assert len(deck) == 108
    assert len({card.id for card in deck}) == 108
    assert sum(card.value is UnoValue.WILD for card in deck) == 4
    assert sum(card.value is UnoValue.WILD_DRAW_FOUR for card in deck) == 4
    for color in UnoColor:
        assert (
            sum(card.color is color and card.value is UnoValue.ZERO for card in deck)
            == 1
        )


async def test_uno_lobby_join_and_start_deals_private_hands(tmp_path) -> None:
    repository = PostgresUnoRepository(tmp_path / "uno.pg")
    economy_repository = PostgresEconomyRepository(tmp_path / "uno.pg")
    economy = EconomyService(economy_repository)
    for user_id in (100, 200):
        await economy.give_points(
            guild_id=1,
            user_id=user_id,
            actor_id=999,
            amount=1000,
            reason="seed",
        )
    service = UnoService(repository, economy_repository, rng=random.Random(1))
    session = await service.create_lobby(
        guild_id=1,
        channel_id=10,
        created_by=100,
        title="Mesa de testes",
        stake=100,
    )
    session = await service.join_game(session.id or 0, 200)
    session = await service.start_game(session.id or 0, 100)

    assert session.status is UnoGameStatus.PLAYING
    assert set(session.economic_policy_snapshots) == {100, 200}
    persisted_session = await repository.get_game(session.id or 0)
    assert persisted_session is not None
    assert set(persisted_session.economic_policy_snapshots) == {100, 200}
    assert [len(player.hand) for player in session.players] == [7, 7]
    assert len(session.draw_pile) == 93
    assert len(session.discard_pile) == 1
    assert session.top_card is not None
    assert session.top_card.color is not None
    assert session.current_player is not None
    assert session.current_player.user_id == 100


async def test_uno_partial_start_failure_retry_and_cancel_use_distinct_refunds(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = PostgresUnoRepository(tmp_path / "uno.pg")
    economy_repository = PostgresEconomyRepository(tmp_path / "uno.pg")
    economy = EconomyService(economy_repository)
    for user_id in (100, 200):
        await economy.give_points(
            guild_id=1,
            user_id=user_id,
            actor_id=999,
            amount=1000,
            reason="seed",
        )
    service = UnoService(repository, economy_repository, rng=random.Random(2))
    session = await service.create_lobby(
        guild_id=1,
        channel_id=10,
        created_by=100,
        title="Mesa com retry",
        stake=100,
    )
    session = await service.join_game(session.id or 0, 200)

    original_mutate_balance = economy_repository.mutate_balance
    stake_attempts = 0

    async def flaky_mutate_balance(**kwargs):
        nonlocal stake_attempts
        if kwargs.get("reason") == "uno_stake":
            stake_attempts += 1
            if stake_attempts == 2:
                raise RuntimeError("falha inesperada simulada")
        return await original_mutate_balance(**kwargs)

    monkeypatch.setattr(economy_repository, "mutate_balance", flaky_mutate_balance)

    with pytest.raises(RuntimeError, match="inesperada simulada"):
        await service.start_game(session.id or 0, 100)

    assert (await economy.get_wallet(1, 100)).balance == 1000
    assert (await economy.get_wallet(1, 200)).balance == 1000

    session = await service.start_game(session.id or 0, 100)
    assert session.status is UnoGameStatus.PLAYING
    session = await service.cancel_game(session.id or 0, 100)
    assert session.status is UnoGameStatus.CANCELLED
    assert (await economy.get_wallet(1, 100)).balance == 1000
    assert (await economy.get_wallet(1, 200)).balance == 1000

    refunds = [
        transaction
        for transaction in await economy_repository.list_transactions(1, 100, limit=20)
        if transaction.reason in {"uno_failed_start", "uno_cancel_refund"}
    ]
    assert {transaction.reason for transaction in refunds} == {
        "uno_failed_start",
        "uno_cancel_refund",
    }
    assert len({transaction.idempotency_key for transaction in refunds}) == 2


async def test_uno_rejects_player_outside_turn(tmp_path) -> None:
    repository, service, session = await _started_game(tmp_path)
    card = session.players[1].hand[0]

    with pytest.raises(UnoValidationError, match="não é sua vez"):
        await service.play_card(
            game_id=session.id or 0,
            user_id=200,
            card_id=card.id,
        )


async def test_draw_two_penalizes_and_skips_next_player(tmp_path) -> None:
    repository, service, session = await _started_game(tmp_path)
    draw_two = UnoCard(1001, UnoColor.RED, UnoValue.DRAW_TWO)
    session.players[0].hand = [
        draw_two,
        UnoCard(1002, UnoColor.BLUE, UnoValue.ONE),
    ]
    session.players[1].hand = [UnoCard(1003, UnoColor.GREEN, UnoValue.TWO)]
    session.discard_pile = [UnoCard(1004, UnoColor.RED, UnoValue.FIVE)]
    session.current_color = UnoColor.RED
    before = len(session.players[1].hand)
    session = await repository.update_game(session)

    session = await service.play_card(
        game_id=session.id or 0,
        user_id=100,
        card_id=draw_two.id,
    )

    assert len(session.players[1].hand) == before + 2
    assert session.current_player is not None
    assert session.current_player.user_id == 100
    assert "perdeu a vez" in session.last_action


async def test_wild_draw_four_changes_color_and_skips_target(tmp_path) -> None:
    repository, service, session = await _started_game(tmp_path)
    wild = UnoCard(1101, None, UnoValue.WILD_DRAW_FOUR)
    session.players[0].hand = [
        wild,
        UnoCard(1102, UnoColor.BLUE, UnoValue.ONE),
    ]
    session.players[1].hand = [UnoCard(1103, UnoColor.GREEN, UnoValue.TWO)]
    session.discard_pile = [UnoCard(1104, UnoColor.RED, UnoValue.FIVE)]
    session.current_color = UnoColor.RED
    before = len(session.players[1].hand)
    session = await repository.update_game(session)

    session = await service.play_card(
        game_id=session.id or 0,
        user_id=100,
        card_id=wild.id,
        chosen_color=UnoColor.GREEN,
    )

    assert session.current_color is UnoColor.GREEN
    assert len(session.players[1].hand) == before + 4
    assert session.current_player is not None
    assert session.current_player.user_id == 100


async def test_playable_drawn_card_can_be_played_or_passed(tmp_path) -> None:
    repository, service, session = await _started_game(tmp_path)
    drawn = UnoCard(1201, UnoColor.RED, UnoValue.SEVEN)
    session.players[0].hand = [UnoCard(1202, UnoColor.BLUE, UnoValue.ONE)]
    session.discard_pile = [UnoCard(1203, UnoColor.RED, UnoValue.FIVE)]
    session.current_color = UnoColor.RED
    session.draw_pile.append(drawn)
    session = await repository.update_game(session)

    session = await service.draw_card(session.id or 0, 100)

    assert session.drawn_card_id == drawn.id
    assert session.current_player is not None
    assert session.current_player.user_id == 100

    session = await service.pass_turn(session.id or 0, 100)

    assert session.drawn_card_id is None
    assert session.current_player is not None
    assert session.current_player.user_id == 200


async def test_unplayable_drawn_card_automatically_passes(tmp_path) -> None:
    repository, service, session = await _started_game(tmp_path)
    drawn = UnoCard(1251, UnoColor.BLUE, UnoValue.NINE)
    session.discard_pile = [UnoCard(1252, UnoColor.RED, UnoValue.FIVE)]
    session.current_color = UnoColor.RED
    session.draw_pile.append(drawn)
    session = await repository.update_game(session)

    session = await service.draw_card(session.id or 0, 100)

    assert session.drawn_card_id is None
    assert session.current_player is not None
    assert session.current_player.user_id == 200


async def test_reverse_and_skip_follow_two_player_rules(tmp_path) -> None:
    repository, service, session = await _started_game(tmp_path)
    reverse = UnoCard(1271, UnoColor.RED, UnoValue.REVERSE)
    session.players[0].hand = [
        reverse,
        UnoCard(1272, UnoColor.BLUE, UnoValue.ONE),
    ]
    session.discard_pile = [UnoCard(1273, UnoColor.RED, UnoValue.FIVE)]
    session.current_color = UnoColor.RED
    session = await repository.update_game(session)

    session = await service.play_card(
        game_id=session.id or 0,
        user_id=100,
        card_id=reverse.id,
    )

    assert session.direction == -1
    assert session.current_player is not None
    assert session.current_player.user_id == 100


async def test_draw_pile_recycles_discard_without_moving_top_card(tmp_path) -> None:
    repository, service, session = await _started_game(tmp_path)
    old_discard = UnoCard(1281, UnoColor.BLUE, UnoValue.THREE)
    top = UnoCard(1282, UnoColor.RED, UnoValue.FIVE)
    session.draw_pile = []
    session.discard_pile = [old_discard, top]
    session.current_color = UnoColor.RED
    session = await repository.update_game(session)

    session = await service.draw_card(session.id or 0, 100)

    assert session.top_card == top
    assert old_discard in session.players[0].hand


async def test_uno_finishes_when_player_uses_last_card(tmp_path) -> None:
    repository, service, session = await _started_game(tmp_path)
    winner = UnoCard(1301, UnoColor.YELLOW, UnoValue.NINE)
    session.players[0].hand = [winner]
    session.discard_pile = [UnoCard(1302, UnoColor.YELLOW, UnoValue.FIVE)]
    session.current_color = UnoColor.YELLOW
    session = await repository.update_game(session)

    session = await service.play_card(
        game_id=session.id or 0,
        user_id=100,
        card_id=winner.id,
    )

    assert session.status is UnoGameStatus.FINISHED
    assert session.winner_user_id == 100
    assert session.players[0].hand == []
    economy = EconomyService(PostgresEconomyRepository(tmp_path / "uno.pg"))
    assert (await economy.get_wallet(1, 100)).balance == 1150
    assert (await economy.get_wallet(1, 200)).balance == 900


async def test_uno_pve_pays_two_times_stake_to_human_winner(tmp_path) -> None:
    database = tmp_path / "uno.pg"
    repository = PostgresUnoRepository(database)
    economy_repository = PostgresEconomyRepository(database)
    economy = EconomyService(economy_repository)
    await economy.give_points(
        guild_id=1,
        user_id=100,
        actor_id=999,
        amount=1000,
        reason="seed",
    )
    service = UnoService(repository, economy_repository, rng=random.Random(12))
    session = await service.create_pve_game(
        guild_id=1,
        channel_id=10,
        created_by=100,
        title="UNO contra a máquina",
        stake=100,
    )
    winner = UnoCard(1401, UnoColor.YELLOW, UnoValue.NINE)
    session.players[0].hand = [winner]
    session.discard_pile = [UnoCard(1402, UnoColor.YELLOW, UnoValue.FIVE)]
    session.current_color = UnoColor.YELLOW
    session.current_player_index = 0
    session = await repository.update_game(session)

    session = await service.play_card(
        game_id=session.id or 0,
        user_id=100,
        card_id=winner.id,
    )

    assert session.status is UnoGameStatus.FINISHED
    assert (await economy.get_wallet(1, 100)).balance == 1100


async def test_uno_machine_plays_without_reading_human_hand(tmp_path) -> None:
    database = tmp_path / "uno.pg"
    repository = PostgresUnoRepository(database)
    economy_repository = PostgresEconomyRepository(database)
    economy = EconomyService(economy_repository)
    await economy.give_points(
        guild_id=1,
        user_id=100,
        actor_id=999,
        amount=1000,
        reason="seed",
    )
    service = UnoService(repository, economy_repository, rng=random.Random(14))
    session = await service.create_pve_game(
        guild_id=1,
        channel_id=10,
        created_by=100,
        title="Máquina",
        stake=100,
    )
    machine = session.players[1]
    machine.hand = [
        UnoCard(1501, UnoColor.RED, UnoValue.SEVEN),
        UnoCard(1502, UnoColor.BLUE, UnoValue.ONE),
    ]
    session.discard_pile = [UnoCard(1503, UnoColor.RED, UnoValue.FIVE)]
    session.current_color = UnoColor.RED
    session.current_player_index = 1
    session = await repository.update_game(session)

    session = await service.play_machine_turns(session.id or 0)

    assert session.current_player is not None
    assert session.current_player.user_id == 100
    assert session.top_card == UnoCard(1501, UnoColor.RED, UnoValue.SEVEN)


def test_uno_public_table_renders_without_player_hands() -> None:
    session = UnoSession(
        id=1,
        guild_id=1,
        channel_id=10,
        message_id=20,
        title="UNO da Comunidade",
        created_by=100,
        status=UnoGameStatus.PLAYING,
        players=[
            UnoPlayer(100, [UnoCard(1, UnoColor.RED, UnoValue.ONE)] * 5),
            UnoPlayer(200, [UnoCard(2, UnoColor.BLUE, UnoValue.TWO)] * 3),
        ],
        draw_pile=[UnoCard(3, UnoColor.GREEN, UnoValue.THREE)] * 40,
        discard_pile=[UnoCard(4, UnoColor.YELLOW, UnoValue.SEVEN)],
        current_color=UnoColor.YELLOW,
    )

    image_bytes = render_uno_table_image(
        session,
        display_names={100: "Ana", 200: "Bruno"},
    )
    image = Image.open(BytesIO(image_bytes))

    assert image.size == (960, 640)
    assert image.mode == "RGB"
    assert len(image_bytes) > 10_000


async def test_private_hand_uses_select_menu_pagination() -> None:
    cards = [
        UnoCard(index, UnoColor.RED, UnoValue.ONE)
        for index in range(1, HAND_PAGE_SIZE + 7)
    ]
    session = UnoSession(
        id=1,
        guild_id=1,
        channel_id=10,
        message_id=20,
        title="Mesa",
        created_by=100,
        status=UnoGameStatus.PLAYING,
        players=[UnoPlayer(100, cards), UnoPlayer(200)],
        current_color=UnoColor.RED,
    )

    first_page = UnoHandView(object(), session, 100, page=0)  # type: ignore[arg-type]
    second_page = UnoHandView(object(), session, 100, page=1)  # type: ignore[arg-type]
    first_select = next(
        item for item in first_page.children if isinstance(item, UnoCardSelect)
    )
    second_select = next(
        item for item in second_page.children if isinstance(item, UnoCardSelect)
    )

    assert len(first_select.options) == HAND_PAGE_SIZE
    assert len(second_select.options) == 6


async def test_open_uno_hand_is_refreshed_automatically() -> None:
    session = UnoSession(
        id=77,
        guild_id=1,
        channel_id=10,
        message_id=20,
        title="Mesa",
        created_by=100,
        status=UnoGameStatus.PLAYING,
        players=[UnoPlayer(100), UnoPlayer(200)],
        current_color=UnoColor.RED,
    )
    message = _FakeWebhookMessage()
    _register_uno_hand(77, 100, message)  # type: ignore[arg-type]
    session.players[0].hand = [UnoCard(1, UnoColor.RED, UnoValue.SEVEN)]

    await refresh_open_uno_hands(object(), session)  # type: ignore[arg-type]

    assert message.edits
    assert "🔴 7" in message.edits[-1]["embed"].description


async def test_uno_ephemeral_hand_uses_interaction_edit_route() -> None:
    interaction = AsyncMock(spec=discord.Interaction)
    embed = discord.Embed(title="Mão atualizada")

    await _edit_uno_hand_handle(interaction, embed, None)

    interaction.edit_original_response.assert_awaited_once_with(
        embed=embed,
        view=None,
    )


async def _started_game(tmp_path):
    repository = PostgresUnoRepository(tmp_path / "uno.pg")
    economy_repository = PostgresEconomyRepository(tmp_path / "uno.pg")
    economy = EconomyService(economy_repository)
    for user_id in (100, 200):
        await economy.give_points(
            guild_id=1,
            user_id=user_id,
            actor_id=999,
            amount=1000,
            reason="seed",
        )
    service = UnoService(repository, economy_repository, rng=random.Random(9))
    session = await service.create_lobby(
        guild_id=1,
        channel_id=10,
        created_by=100,
        title="Mesa",
        stake=100,
    )
    session = await service.join_game(session.id or 0, 200)
    session = await service.start_game(session.id or 0, 100)
    return repository, service, session


class _FakeWebhookMessage:
    def __init__(self) -> None:
        self.edits: list[dict[str, object]] = []

    async def edit(self, **kwargs) -> None:
        self.edits.append(kwargs)
