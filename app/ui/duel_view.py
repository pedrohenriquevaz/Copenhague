from __future__ import annotations

from typing import cast

import discord
from discord.ext import commands

from app.models.casino import DuelMode, DuelResult
from app.models.guild_settings import GuildEconomySettings
from app.services.casino_service import CasinoService, CasinoValidationError
from app.utils.embeds import format_points


def build_duel_invite_embed(
    *,
    challenger: discord.User | discord.Member,
    challenged: discord.User | discord.Member,
    bet: int,
    mode: DuelMode,
    settings: GuildEconomySettings,
) -> discord.Embed:
    embed = discord.Embed(title="Duelo", color=discord.Color.orange())
    embed.description = (
        f"{challenger.mention} desafiou {challenged.mention}.\n"
        f"Aposta de cada um: **{format_points(bet, settings.currency_name)}**\n"
        f"Pote total: **{format_points(bet * 2, settings.currency_name)}**\n"
        f"Modo: **{_format_duel_mode(mode)}**"
    )
    return embed


def build_duel_result_embed(
    result: DuelResult,
    settings: GuildEconomySettings,
) -> discord.Embed:
    color = (
        discord.Color.blurple() if result.winner_id is None else discord.Color.green()
    )
    embed = discord.Embed(title="Resultado do Duelo", color=color)
    if result.winner_id is None:
        embed.description = "O duelo empatou. As apostas foram devolvidas."
    else:
        embed.description = (
            f"Vencedor: <@{result.winner_id}>\n"
            f"Premio: **{format_points(result.payout, settings.currency_name)}**"
        )

    for line in result.detail_lines:
        name, _, value = line.partition(":")
        embed.add_field(name=name, value=value.strip() or "-", inline=True)

    embed.add_field(
        name="Aposta",
        value=format_points(result.bet, settings.currency_name),
        inline=True,
    )
    embed.add_field(
        name="Saldo desafiante",
        value=format_points(result.challenger_wallet.balance, settings.currency_name),
        inline=True,
    )
    embed.add_field(
        name="Saldo desafiado",
        value=format_points(result.challenged_wallet.balance, settings.currency_name),
        inline=True,
    )
    return embed


class DuelChallengeView(discord.ui.View):
    """Botoes publicos para aceitar ou recusar duelo."""

    def __init__(
        self,
        bot: commands.Bot,
        *,
        guild_id: int,
        challenger_id: int,
        challenged_id: int,
        bet: int,
        mode: DuelMode,
        settings: GuildEconomySettings,
    ) -> None:
        super().__init__(timeout=60)
        self.bot = bot
        self.guild_id = guild_id
        self.challenger_id = challenger_id
        self.challenged_id = challenged_id
        self.bet = bet
        self.mode = mode
        self.settings = settings
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or interaction.guild.id != self.guild_id:
            await interaction.response.send_message(
                "Esse duelo nao pertence a este servidor.",
                ephemeral=True,
            )
            return False
        if interaction.user.id != self.challenged_id:
            await interaction.response.send_message(
                "Apenas o usuario desafiado pode responder esse duelo.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Aceitar duelo", style=discord.ButtonStyle.success)
    async def accept(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        service = cast(CasinoService, self.bot.casino_service)  # type: ignore[attr-defined]
        try:
            result = await service.resolve_duel(
                guild_id=self.guild_id,
                challenger_id=self.challenger_id,
                challenged_id=self.challenged_id,
                bet=self.bet,
                mode=self.mode.value,
            )
        except CasinoValidationError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        self._disable_buttons()
        await interaction.response.edit_message(
            embed=build_duel_result_embed(result, self.settings),
            view=self,
        )

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.secondary)
    async def decline(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        self._disable_buttons()
        embed = discord.Embed(
            title="Duelo recusado",
            description=f"<@{self.challenged_id}> recusou o desafio.",
            color=discord.Color.red(),
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self) -> None:
        self._disable_buttons()
        if self.message is None:
            return

        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            return

    def _disable_buttons(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True


def _format_duel_mode(mode: DuelMode) -> str:
    if mode is DuelMode.SORTE:
        return "Sorte"
    return "Dados"
