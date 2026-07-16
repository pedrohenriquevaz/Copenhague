from __future__ import annotations

import random
from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import AsyncMock

import discord
import pytest
from PIL import Image

from app.models.truco import (
    TrucoCard,
    TrucoGameStatus,
    TrucoPlayedCard,
    TrucoPlayer,
    TrucoRank,
    TrucoSession,
    TrucoSuit,
    TrucoTeam,
)
from app.services.economy_service import EconomyService
from app.services.truco_service import TrucoService, TrucoValidationError
from app.ui.truco_table_image import render_truco_table_image
from app.ui.truco_view import (
    _edit_truco_hand_handle,
    _register_truco_hand,
    refresh_open_truco_hands,
)
from tests.postgres_support import PostgresEconomyRepository, PostgresTrucoRepository


async def test_truco_accepts_all_debits_stakes_and_splits_pot(tmp_path) -> None:
    economy_repository = PostgresEconomyRepository(tmp_path / "economy.pg")
    truco_repository = PostgresTrucoRepository(tmp_path / "economy.pg")
    economy = EconomyService(economy_repository)
    service = TrucoService(
        truco_repository,
        economy_repository,
        rng=random.Random(1),
    )
    for user_id in (10, 20, 30, 40):
        await economy.give_points(
            guild_id=1,
            user_id=user_id,
            actor_id=99,
            amount=1000,
            reason="seed",
        )

    session = await service.create_lobby(
        guild_id=1,
        channel_id=100,
        created_by=10,
        partner_id=30,
        opponent_1_id=20,
        opponent_2_id=40,
        stake=100,
    )

    for user_id in (10, 30, 20, 40):
        session = await service.accept_lobby(session.id or 0, user_id)

    assert session.status is TrucoGameStatus.PLAYING
    assert set(session.economic_policy_snapshots) == {10, 20, 30, 40}
    persisted_session = await truco_repository.get_game(session.id or 0)
    assert persisted_session is not None
    assert set(persisted_session.economic_policy_snapshots) == {10, 20, 30, 40}
    balances = {
        user_id: (await economy.get_wallet(1, user_id)).balance
        for user_id in (10, 20, 30, 40)
    }
    assert balances == {
        10: 900,
        20: 900,
        30: 900,
        40: 900,
    }

    while session.status is TrucoGameStatus.PLAYING:
        session = await service.run(session.id or 0, 20)

    assert session.winning_team is TrucoTeam.BLUE
    assert session.score_blue == 12
    assert session.score_red == 0
    assert session.zero_loss_announcement is not None
    balances = {
        user_id: (await economy.get_wallet(1, user_id)).balance
        for user_id in (10, 20, 30, 40)
    }
    assert balances == {
        10: 1150,
        20: 900,
        30: 1150,
        40: 900,
    }


async def test_truco_challenge_blocks_cards_until_acceptance(tmp_path) -> None:
    economy_repository = PostgresEconomyRepository(tmp_path / "economy.pg")
    truco_repository = PostgresTrucoRepository(tmp_path / "economy.pg")
    economy = EconomyService(economy_repository)
    service = TrucoService(
        truco_repository,
        economy_repository,
        rng=random.Random(2),
    )
    for user_id in (10, 20, 30, 40):
        await economy.give_points(
            guild_id=1,
            user_id=user_id,
            actor_id=99,
            amount=1000,
            reason="seed",
        )
    session = await service.create_lobby(
        guild_id=1,
        channel_id=100,
        created_by=10,
        partner_id=30,
        opponent_1_id=20,
        opponent_2_id=40,
        stake=100,
    )
    for user_id in (10, 30, 20, 40):
        session = await service.accept_lobby(session.id or 0, user_id)

    session = await service.request_truco(session.id or 0, 10)

    assert session.pending_challenge is not None
    assert session.pending_challenge.proposed_value == 3
    with pytest.raises(TrucoValidationError, match="pendente"):
        await service.play_card(
            game_id=session.id or 0,
            user_id=10,
            card_index=0,
        )

    session = await service.accept_truco(session.id or 0, 20)

    assert session.pending_challenge is None
    assert session.hand_value == 3


async def test_admin_force_cancel_refunds_active_game_once(tmp_path) -> None:
    economy_repository = PostgresEconomyRepository(tmp_path / "economy.pg")
    truco_repository = PostgresTrucoRepository(tmp_path / "economy.pg")
    economy = EconomyService(economy_repository)
    service = TrucoService(
        truco_repository,
        economy_repository,
        rng=random.Random(3),
    )
    for user_id in (10, 20, 30, 40):
        await economy.give_points(
            guild_id=1,
            user_id=user_id,
            actor_id=99,
            amount=1000,
            reason="seed",
        )
    session = await service.create_lobby(
        guild_id=1,
        channel_id=100,
        created_by=10,
        partner_id=30,
        opponent_1_id=20,
        opponent_2_id=40,
        stake=100,
    )
    for user_id in (10, 20, 30, 40):
        session = await service.accept_lobby(session.id or 0, user_id)

    cancelled = await service.force_cancel_active_games(
        guild_id=1,
        target_user_id=20,
        actor_id=99,
        reason="Mensagem da mesa foi apagada.",
    )

    assert len(cancelled) == 1
    assert cancelled[0].status is TrucoGameStatus.CANCELLED
    for user_id in (10, 20, 30, 40):
        assert (await economy.get_wallet(1, user_id)).balance == 1000

    with pytest.raises(TrucoValidationError, match="não participa"):
        await service.force_cancel_active_games(
            guild_id=1,
            target_user_id=20,
            actor_id=99,
            reason="Tentativa repetida.",
        )


async def test_truco_partial_start_failure_retry_and_cancel_use_distinct_refunds(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    economy_repository = PostgresEconomyRepository(tmp_path / "economy.pg")
    truco_repository = PostgresTrucoRepository(tmp_path / "economy.pg")
    economy = EconomyService(economy_repository)
    service = TrucoService(
        truco_repository,
        economy_repository,
        rng=random.Random(4),
    )
    for user_id in (10, 20, 30, 40):
        await economy.give_points(
            guild_id=1,
            user_id=user_id,
            actor_id=99,
            amount=1000,
            reason="seed",
        )
    session = await service.create_lobby(
        guild_id=1,
        channel_id=100,
        created_by=10,
        partner_id=30,
        opponent_1_id=20,
        opponent_2_id=40,
        stake=100,
    )
    for user_id in (10, 30, 20):
        session = await service.accept_lobby(session.id or 0, user_id)

    original_mutate_balance = economy_repository.mutate_balance
    stake_attempts = 0

    async def flaky_mutate_balance(**kwargs):
        nonlocal stake_attempts
        if kwargs.get("reason") == "truco_stake":
            stake_attempts += 1
            if stake_attempts == 4:
                raise RuntimeError("falha inesperada simulada")
        return await original_mutate_balance(**kwargs)

    monkeypatch.setattr(economy_repository, "mutate_balance", flaky_mutate_balance)

    with pytest.raises(RuntimeError, match="inesperada simulada"):
        await service.accept_lobby(session.id or 0, 40)

    assert {
        user_id: (await economy.get_wallet(1, user_id)).balance
        for user_id in (10, 20, 30, 40)
    } == {10: 1000, 20: 1000, 30: 1000, 40: 1000}

    session = await service.accept_lobby(session.id or 0, 40)
    assert session.status is TrucoGameStatus.PLAYING
    session = await service.cancel_game(session.id or 0, 10)
    assert session.status is TrucoGameStatus.CANCELLED
    assert {
        user_id: (await economy.get_wallet(1, user_id)).balance
        for user_id in (10, 20, 30, 40)
    } == {10: 1000, 20: 1000, 30: 1000, 40: 1000}

    refunds = [
        transaction
        for transaction in await economy_repository.list_transactions(1, 10, limit=20)
        if transaction.reason in {"truco_failed_start", "truco_cancel_refund"}
    ]
    assert {transaction.reason for transaction in refunds} == {
        "truco_failed_start",
        "truco_cancel_refund",
    }
    assert len({transaction.idempotency_key for transaction in refunds}) == 2


async def test_truco_pve_pays_two_times_stake_to_human_winner(tmp_path) -> None:
    database = tmp_path / "economy.pg"
    economy_repository = PostgresEconomyRepository(database)
    truco_repository = PostgresTrucoRepository(database)
    economy = EconomyService(economy_repository)
    await economy.give_points(
        guild_id=1,
        user_id=10,
        actor_id=99,
        amount=1000,
        reason="seed",
    )
    service = TrucoService(
        truco_repository,
        economy_repository,
        rng=random.Random(8),
    )
    session = await service.create_pve_game(
        guild_id=1,
        channel_id=100,
        created_by=10,
        stake=100,
    )

    while session.status is TrucoGameStatus.PLAYING:
        session = await service.run(session.id or 0, service.MACHINE_USER_ID)

    assert session.winning_team is TrucoTeam.BLUE
    assert (await economy.get_wallet(1, 10)).balance == 1100


async def test_truco_machine_plays_its_turn_automatically(tmp_path) -> None:
    database = tmp_path / "economy.pg"
    economy_repository = PostgresEconomyRepository(database)
    truco_repository = PostgresTrucoRepository(database)
    economy = EconomyService(economy_repository)
    await economy.give_points(
        guild_id=1,
        user_id=10,
        actor_id=99,
        amount=1000,
        reason="seed",
    )
    service = TrucoService(
        truco_repository,
        economy_repository,
        rng=random.Random(18),
    )
    session = await service.create_pve_game(
        guild_id=1,
        channel_id=100,
        created_by=10,
        stake=100,
    )
    session.current_turn_user_id = service.MACHINE_USER_ID
    session.hands[service.MACHINE_USER_ID] = [
        TrucoCard(TrucoRank.FOUR, TrucoSuit.OUROS),
        TrucoCard(TrucoRank.FIVE, TrucoSuit.COPAS),
    ]
    session = await truco_repository.update_game(session)

    session = await service.play_machine_turns(session.id or 0)

    assert session.current_turn_user_id == 10
    assert any(card.user_id == service.MACHINE_USER_ID for card in session.played_cards)


async def test_truco_pve_preserves_completed_round_until_reveal_finishes(
    tmp_path,
) -> None:
    database = tmp_path / "economy.pg"
    economy_repository = PostgresEconomyRepository(database)
    truco_repository = PostgresTrucoRepository(database)
    economy = EconomyService(economy_repository)
    await economy.give_points(
        guild_id=1,
        user_id=10,
        actor_id=99,
        amount=1000,
        reason="seed",
    )
    service = TrucoService(
        truco_repository,
        economy_repository,
        rng=random.Random(22),
    )
    session = await service.create_pve_game(
        guild_id=1,
        channel_id=100,
        created_by=10,
        stake=100,
    )
    session.current_turn_user_id = 10
    session.vira = TrucoCard(TrucoRank.FOUR, TrucoSuit.COPAS)
    session.manilha_rank = TrucoRank.FIVE
    session.hands = {
        10: [TrucoCard(TrucoRank.FOUR, TrucoSuit.OUROS)],
        service.MACHINE_USER_ID: [TrucoCard(TrucoRank.THREE, TrucoSuit.BASTOS)],
    }
    session = await truco_repository.update_game(session)

    session = await service.play_card(
        game_id=session.id or 0,
        user_id=10,
        card_index=0,
    )
    session = await service.play_machine_turns(session.id or 0)

    reveal = session.last_round_reveal
    assert reveal is not None
    assert session.round_reveal_pending is True
    assert reveal.hand_number == 1
    assert reveal.round_number == 1
    assert reveal.winner is TrucoTeam.RED
    assert reveal.winner_user_id == service.MACHINE_USER_ID
    assert reveal.score_blue_before == 0
    assert reveal.score_red_before == 0
    assert reveal.round_wins_blue == 0
    assert reveal.round_wins_red == 1
    assert [played.user_id for played in reveal.cards] == [
        10,
        service.MACHINE_USER_ID,
    ]

    unchanged = await service.play_machine_turns(session.id or 0)
    assert unchanged.to_dict() == session.to_dict()
    with pytest.raises(TrucoValidationError, match="apresentação"):
        await service.play_card(
            game_id=session.id or 0,
            user_id=service.MACHINE_USER_ID,
            card_index=0,
        )

    session = await service.consume_round_reveal(session.id or 0, reveal.key)
    assert session.round_reveal_pending is False
    assert session.last_round_reveal is not None


def test_closed_card_loses_to_any_open_card(tmp_path) -> None:
    economy_repository = PostgresEconomyRepository(tmp_path / "economy.pg")
    truco_repository = PostgresTrucoRepository(tmp_path / "economy.pg")
    service = TrucoService(truco_repository, economy_repository)
    now = datetime.now(UTC)
    session = TrucoSession(
        id=1,
        guild_id=1,
        channel_id=1,
        message_id=None,
        created_by=10,
        stake=100,
        status=TrucoGameStatus.PLAYING,
        players=[],
        manilha_rank=TrucoRank.FIVE,
    )
    closed_three = TrucoPlayedCard(
        user_id=10,
        card=TrucoCard(TrucoRank.THREE, TrucoSuit.BASTOS),
        round_number=1,
        play_order=1,
        is_closed=True,
        played_at=now,
    )
    open_four = TrucoPlayedCard(
        user_id=20,
        card=TrucoCard(TrucoRank.FOUR, TrucoSuit.OUROS),
        round_number=1,
        play_order=2,
        is_closed=False,
        played_at=now,
    )

    assert service._compare_played_cards(session, closed_three, open_four) < 0


async def test_truco_table_image_renders_public_game_state(tmp_path) -> None:
    economy_repository = PostgresEconomyRepository(tmp_path / "economy.pg")
    settings = await economy_repository.get_guild_settings(1)
    now = datetime.now(UTC)
    session = TrucoSession(
        id=1,
        guild_id=1,
        channel_id=1,
        message_id=2,
        created_by=10,
        stake=100,
        status=TrucoGameStatus.PLAYING,
        players=[
            TrucoPlayer(10, TrucoTeam.BLUE, 0, True),
            TrucoPlayer(20, TrucoTeam.RED, 1, True),
            TrucoPlayer(30, TrucoTeam.BLUE, 2, True),
            TrucoPlayer(40, TrucoTeam.RED, 3, True),
        ],
        score_blue=6,
        score_red=3,
        hand_value=3,
        current_turn_user_id=20,
        vira=TrucoCard(TrucoRank.FOUR, TrucoSuit.COPAS),
        manilha_rank=TrucoRank.FIVE,
        played_cards=[
            TrucoPlayedCard(
                user_id=10,
                card=TrucoCard(TrucoRank.THREE, TrucoSuit.BASTOS),
                round_number=1,
                play_order=1,
                is_closed=False,
                played_at=now,
            )
        ],
    )

    image_bytes = render_truco_table_image(
        session,
        settings,
        display_names={
            10: "Ana",
            20: "Bruno",
            30: "Carla",
            40: "Diego",
        },
    )
    image = Image.open(BytesIO(image_bytes))

    assert image.size == (960, 640)
    assert image.mode == "RGB"
    assert len(image_bytes) > 10_000


async def test_truco_table_image_renders_completed_round_reveal(tmp_path) -> None:
    economy_repository = PostgresEconomyRepository(tmp_path / "economy.pg")
    truco_repository = PostgresTrucoRepository(tmp_path / "economy.pg")
    economy = EconomyService(economy_repository)
    await economy.give_points(
        guild_id=1,
        user_id=10,
        actor_id=99,
        amount=1000,
        reason="seed",
    )
    settings = await economy_repository.get_guild_settings(1)
    service = TrucoService(
        truco_repository,
        economy_repository,
        rng=random.Random(23),
    )
    session = await service.create_pve_game(
        guild_id=1,
        channel_id=100,
        created_by=10,
        stake=100,
    )
    session.current_turn_user_id = 10
    session.vira = TrucoCard(TrucoRank.FOUR, TrucoSuit.COPAS)
    session.manilha_rank = TrucoRank.FIVE
    session.hands = {
        10: [TrucoCard(TrucoRank.FOUR, TrucoSuit.OUROS)],
        service.MACHINE_USER_ID: [TrucoCard(TrucoRank.THREE, TrucoSuit.BASTOS)],
    }
    session = await truco_repository.update_game(session)
    session = await service.play_card(
        game_id=session.id or 0,
        user_id=10,
        card_index=0,
    )
    session = await service.play_machine_turns(session.id or 0)

    image_bytes = render_truco_table_image(
        session,
        settings,
        display_names={10: "Jogador", service.MACHINE_USER_ID: "Máquina"},
        reveal_round=True,
    )
    image = Image.open(BytesIO(image_bytes))

    assert image.size == (960, 640)
    assert image.mode == "RGB"
    assert len(image_bytes) > 10_000


async def test_open_truco_hand_is_refreshed_for_new_hand(tmp_path) -> None:
    repository = PostgresEconomyRepository(tmp_path / "economy.pg")
    settings = await repository.get_guild_settings(1)
    session = TrucoSession(
        id=88,
        guild_id=1,
        channel_id=1,
        message_id=2,
        created_by=10,
        stake=100,
        status=TrucoGameStatus.PLAYING,
        players=[
            TrucoPlayer(10, TrucoTeam.BLUE, 0, True),
            TrucoPlayer(20, TrucoTeam.RED, 1, True),
        ],
        hands={10: [TrucoCard(TrucoRank.REI, TrucoSuit.COPAS)]},
        current_turn_user_id=10,
    )
    message = _FakeWebhookMessage()
    _register_truco_hand(88, 10, message)  # type: ignore[arg-type]

    await refresh_open_truco_hands(  # type: ignore[arg-type]
        object(),
        session,
        settings,
    )

    assert message.edits
    assert "Rei de Copas" in message.edits[-1]["embed"].description


async def test_truco_ephemeral_hand_uses_interaction_edit_route() -> None:
    interaction = AsyncMock(spec=discord.Interaction)
    embed = discord.Embed(title="Mão atualizada")

    await _edit_truco_hand_handle(interaction, embed, None)

    interaction.edit_original_response.assert_awaited_once_with(
        embed=embed,
        view=None,
    )


class _FakeWebhookMessage:
    def __init__(self) -> None:
        self.edits: list[dict[str, object]] = []

    async def edit(self, **kwargs) -> None:
        self.edits.append(kwargs)
