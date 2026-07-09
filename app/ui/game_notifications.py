from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import discord

from app.models.guild_settings import GuildEconomySettings
from app.utils.embeds import format_points

LOSS_NOTIFICATION_THRESHOLD = 500
MAX_GROUPED_LINES = 10


@dataclass(frozen=True, slots=True)
class GameOutcomeNotice:
    """Resultado financeiro a ser anunciado publicamente."""

    user_id: int
    stake: int
    payout: int
    win_streak: int = 0
    multiplier_percent: int = 100

    @property
    def profit(self) -> int:
        return self.payout - self.stake

    @property
    def loss(self) -> int:
        return max(0, self.stake - self.payout)

    @property
    def is_win(self) -> bool:
        return self.payout > self.stake

    @property
    def is_expressive_loss(self) -> bool:
        return self.loss > LOSS_NOTIFICATION_THRESHOLD


async def announce_game_result(
    interaction: discord.Interaction,
    *,
    user_id: int,
    game_name: str,
    stake: int,
    payout: int,
    settings: GuildEconomySettings,
    win_streak: int = 0,
    multiplier_percent: int = 100,
) -> None:
    """Anuncia vitorias e derrotas expressivas no canal da interacao."""

    channel = interaction.channel
    await announce_game_result_to_channel(
        channel,
        user_id=user_id,
        game_name=game_name,
        stake=stake,
        payout=payout,
        settings=settings,
        win_streak=win_streak,
        multiplier_percent=multiplier_percent,
    )


async def announce_game_result_to_channel(
    channel: discord.abc.Messageable | None,
    *,
    user_id: int,
    game_name: str,
    stake: int,
    payout: int,
    settings: GuildEconomySettings,
    win_streak: int = 0,
    multiplier_percent: int = 100,
) -> None:
    """Anuncia um unico resultado se ele for relevante para o chat."""

    if channel is None or not hasattr(channel, "send"):
        return

    notice = GameOutcomeNotice(
        user_id=user_id,
        stake=stake,
        payout=payout,
        win_streak=win_streak,
        multiplier_percent=multiplier_percent,
    )
    message = _format_single_notice(notice, game_name, settings)
    if message is None:
        return

    try:
        await channel.send(message)
    except discord.HTTPException:
        return


async def announce_grouped_game_results(
    channel: discord.abc.Messageable | None,
    *,
    game_name: str,
    settings: GuildEconomySettings,
    notices: Iterable[GameOutcomeNotice],
) -> None:
    """Agrupa anuncios de jogos coletivos para evitar excesso de mensagens."""

    if channel is None or not hasattr(channel, "send"):
        return

    wins = [notice for notice in notices if notice.is_win]
    losses = [notice for notice in notices if notice.is_expressive_loss]
    messages = [
        _format_grouped_wins(wins, game_name, settings),
        _format_grouped_losses(losses, game_name, settings),
    ]
    for message in messages:
        if message is None:
            continue
        try:
            await channel.send(message)
        except discord.HTTPException:
            continue


def _format_single_notice(
    notice: GameOutcomeNotice,
    game_name: str,
    settings: GuildEconomySettings,
) -> str | None:
    if notice.is_win:
        streak_text = _format_streak_text(notice)
        return (
            "🎉 "
            f"<@{notice.user_id}> acabou de ganhar "
            f"{format_points(notice.payout, settings.currency_name)} "
            f"em {game_name}!{streak_text}"
        )
    if notice.is_expressive_loss:
        return (
            "⚠️ "
            f"<@{notice.user_id}> acabou de perder "
            f"{format_points(notice.loss, settings.currency_name)} "
            f"em {game_name}."
        )
    return None


def _format_grouped_wins(
    notices: list[GameOutcomeNotice],
    game_name: str,
    settings: GuildEconomySettings,
) -> str | None:
    if not notices:
        return None
    lines = [
        f"<@{notice.user_id}> ganhou "
        f"**{format_points(notice.payout, settings.currency_name)}**"
        for notice in notices[:MAX_GROUPED_LINES]
    ]
    return _format_grouped_message("🎉", f"Vitorias em {game_name}", lines, notices)


def _format_grouped_losses(
    notices: list[GameOutcomeNotice],
    game_name: str,
    settings: GuildEconomySettings,
) -> str | None:
    if not notices:
        return None
    lines = [
        f"<@{notice.user_id}> perdeu "
        f"**{format_points(notice.loss, settings.currency_name)}**"
        for notice in notices[:MAX_GROUPED_LINES]
    ]
    return _format_grouped_message(
        "⚠️",
        f"Derrotas expressivas em {game_name}",
        lines,
        notices,
    )


def _format_grouped_message(
    icon: str,
    title: str,
    lines: list[str],
    notices: list[GameOutcomeNotice],
) -> str:
    remaining = len(notices) - len(lines)
    suffix = f"\n...e mais {remaining} resultado(s)." if remaining > 0 else ""
    return f"{icon} **{title}**\n" + "\n".join(lines) + suffix


def _format_streak_text(notice: GameOutcomeNotice) -> str:
    if notice.win_streak <= 1:
        return ""
    multiplier = f"{notice.multiplier_percent / 100:.2f}x"
    return f" Winstreak: **{notice.win_streak}** " f"| multiplicador **{multiplier}**."
