from __future__ import annotations

import asyncio
from dataclasses import dataclass

import discord

from app.models.casino import CasinoGameType, DuelMode


@dataclass(frozen=True, slots=True)
class CasinoAnimation:
    """Sequencia curta de frames para criar sensacao de movimento no Discord."""

    title: str
    frames: tuple[str, ...]
    footer: str = "Aguarde o resultado..."
    color_value: int = 0xF1C40F
    delay_seconds: float = 0.45


def casino_animation_for_game(game_type: CasinoGameType) -> CasinoAnimation:
    animations = {
        CasinoGameType.COIN_FLIP: CasinoAnimation(
            title="Moeda no ar",
            frames=(
                "🪙   `cara`",
                "  🪙 `girando`",
                "`coroa`   🪙",
                "  🪙 `girando`",
            ),
        ),
        CasinoGameType.DICE: CasinoAnimation(
            title="Dados rolando",
            frames=(
                "🎲  ⚀",
                "⚁  🎲",
                "🎲  ⚄",
                "⚅  🎲",
            ),
        ),
        CasinoGameType.SLOT: CasinoAnimation(
            title="Slot girando",
            frames=(
                "🎰  🍒 | 🍋 | 🍇",
                "🎰  🔔 | ⭐ | 💎",
                "🎰  🍇 | 🔔 | 7️⃣",
                "🎰  💎 | 🍒 | ⭐",
            ),
        ),
        CasinoGameType.ROULETTE: CasinoAnimation(
            title="Roleta girando",
            frames=(
                "🔴  ⚫  🟢  ⚫",
                "⚫  🟢  ⚫  🔴",
                "🟢  ⚫  🔴  ⚫",
                "⚫  🔴  ⚫  🟢",
            ),
        ),
        CasinoGameType.MASCOT_RACE: CasinoAnimation(
            title="Corrida em andamento",
            frames=(
                "🐉━━ 🐺━ 🦊━━━",
                "🐉━━━ 🐺━━ 🦊━",
                "🐉━ 🐺━━━ 🦊━━",
                "🐉━━ 🐺━━━ 🦊━━━",
            ),
        ),
    }
    return animations.get(
        game_type,
        CasinoAnimation(
            title="Cassino em movimento",
            frames=("✨", "✨ ✨", "✨ ✨ ✨"),
        ),
    )


def blackjack_animation(action: str = "deal") -> CasinoAnimation:
    labels = {
        "deal": "Distribuindo cartas",
        "hit": "Puxando carta",
        "stand": "Banca jogando",
        "double": "Dobrar aposta",
    }
    frames = {
        "deal": ("🂠  🂠", "🂡  🂠", "🂡  🂫", "🂡  🂫  🂠"),
        "hit": ("🂠", "🂠  →", "🂠  →  🂡"),
        "stand": ("Banca: 🂠", "Banca: 🂠 🂠", "Banca: 🂠 🂠 🂠"),
        "double": ("💰 + 🂠", "💰💰 + 🂠", "💰💰 + 🂡"),
    }
    return CasinoAnimation(
        title=labels.get(action, "BlackJack em andamento"),
        frames=frames.get(action, frames["deal"]),
    )


def duel_animation(mode: DuelMode) -> CasinoAnimation:
    if mode is DuelMode.DADOS:
        return CasinoAnimation(
            title="Duelo de dados",
            frames=(
                "🎲     🎲",
                "  ⚀   ⚄",
                "⚃     ⚁",
                "  ⚅   ⚂",
            ),
        )
    return CasinoAnimation(
        title="Duelo de sorte",
        frames=(
            "✨ Desafiante     Desafiado",
            "Desafiante     ✨ Desafiado",
            "Desafiante     Desafiado ✨",
        ),
    )


def build_casino_animation_embed(
    animation: CasinoAnimation,
    *,
    frame_index: int = 0,
) -> discord.Embed:
    frame = animation.frames[frame_index % len(animation.frames)]
    embed = discord.Embed(
        title=animation.title,
        description=f"{frame}\n\n{animation.footer}",
        color=discord.Color(animation.color_value),
    )
    return embed


async def play_casino_animation(
    message: discord.Message | discord.WebhookMessage,
    animation: CasinoAnimation,
) -> None:
    for frame_index in range(1, len(animation.frames)):
        await asyncio.sleep(animation.delay_seconds)
        try:
            await message.edit(
                embed=build_casino_animation_embed(
                    animation,
                    frame_index=frame_index,
                )
            )
        except discord.HTTPException:
            return
