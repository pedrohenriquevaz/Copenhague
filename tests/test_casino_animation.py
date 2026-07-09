from __future__ import annotations

from app.models.casino import CasinoGameType, DuelMode
from app.ui.casino_animation import (
    blackjack_animation,
    build_casino_animation_embed,
    casino_animation_for_game,
    coin_flip_animation,
    duel_animation,
)


def test_roulette_animation_has_multiple_frames() -> None:
    animation = casino_animation_for_game(CasinoGameType.ROULETTE)
    embed = build_casino_animation_embed(animation)

    assert animation.title == "Roleta girando"
    assert len(animation.frames) >= 3
    assert embed.title == "Roleta girando"
    assert animation.frames[0] in (embed.description or "")


def test_coin_flip_animation_lands_on_result() -> None:
    animation = coin_flip_animation("Coroa")
    embed = build_casino_animation_embed(
        animation,
        frame_index=len(animation.frames) - 1,
    )

    assert animation.title == "Moeda no ar"
    assert "Coroa" in animation.frames[-1]
    assert "Cara" not in animation.frames[-1]
    assert animation.settle_seconds >= 1.0
    assert "Coroa" in (embed.description or "")


def test_duel_dice_animation_uses_dice_frames() -> None:
    animation = duel_animation(DuelMode.DADOS)

    assert animation.title == "Duelo de dados"
    assert any("🎲" in frame for frame in animation.frames)


def test_blackjack_action_animation_changes_title() -> None:
    animation = blackjack_animation("stand")

    assert animation.title == "Banca jogando"
    assert len(animation.frames) >= 2
