from __future__ import annotations

from typing import cast

import discord
from discord.ext import commands

from app.models.guild_settings import GuildEconomySettings
from app.models.match_bet import MatchBetMatch, MatchBetPlacementResult, MatchBetTeam
from app.services.match_bet_service import MatchBetService, MatchBetValidationError
from app.utils.embeds import format_points


def build_match_bet_embed(
    match: MatchBetMatch,
    settings: GuildEconomySettings,
    *,
    closed: bool = False,
) -> discord.Embed:
    color = (
        discord.Color.red() if closed or not match.is_active else discord.Color.gold()
    )
    embed = discord.Embed(title=match.title, color=color)
    if closed or not match.is_active:
        embed.description = _closed_description(match)
    else:
        embed.description = (
            "Escolha seu time nos botoes abaixo e informe o valor da aposta.\n"
            "Apostas multiplas sao permitidas. A odd da sua aposta fica travada "
            "no momento da confirmacao."
        )

    embed.add_field(
        name=match.team_1,
        value=f"Odd: **{MatchBetService.format_odd_bps(match.odd_team_1_bps)}**",
        inline=True,
    )
    embed.add_field(
        name=match.team_2,
        value=f"Odd: **{MatchBetService.format_odd_bps(match.odd_team_2_bps)}**",
        inline=True,
    )
    embed.add_field(
        name="Moeda",
        value=settings.currency_name,
        inline=True,
    )
    embed.set_footer(text=f"Bet #{match.id}")
    return embed


def build_match_bet_list_embed(
    matches: list[MatchBetMatch],
) -> discord.Embed:
    embed = discord.Embed(title="Bets ativas", color=discord.Color.gold())
    if not matches:
        embed.description = "Nenhuma partida de apostas ativa."
        return embed

    lines = []
    for match in matches:
        lines.append(
            f"**#{match.id}** {match.title}\n"
            f"{match.team_1}: {MatchBetService.format_odd_bps(match.odd_team_1_bps)} "
            f"| {match.team_2}: {MatchBetService.format_odd_bps(match.odd_team_2_bps)}"
        )
    embed.description = "\n\n".join(lines)
    return embed


def build_match_bet_confirmation_embed(
    result: MatchBetPlacementResult,
    settings: GuildEconomySettings,
) -> discord.Embed:
    ticket = result.ticket
    embed = discord.Embed(title="Aposta confirmada", color=discord.Color.green())
    embed.description = (
        f"Partida: **{result.match.title}**\n"
        f"Time: **{ticket.team_name_snapshot}**\n"
        f"Odd travada: **{MatchBetService.format_odd_bps(ticket.odd_bps)}**"
    )
    embed.add_field(
        name="Valor apostado",
        value=format_points(ticket.stake, settings.currency_name),
        inline=True,
    )
    embed.add_field(
        name="Retorno potencial",
        value=format_points(ticket.potential_payout, settings.currency_name),
        inline=True,
    )
    embed.add_field(
        name="Saldo atual",
        value=format_points(result.wallet.balance, settings.currency_name),
        inline=False,
    )
    embed.set_footer(text=f"Ticket #{ticket.id} | Bet #{result.match.id}")
    return embed


class MatchBetStakeModal(discord.ui.Modal):
    """Modal para informar o valor da aposta."""

    amount = discord.ui.TextInput(
        label="Valor da aposta",
        placeholder="Ex.: 100",
        min_length=1,
        max_length=10,
    )

    def __init__(
        self,
        bot: commands.Bot,
        match_id: int,
        team: MatchBetTeam,
    ) -> None:
        super().__init__(title="Confirmar aposta")
        self.bot = bot
        self.match_id = match_id
        self.team = team

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Esta aposta so pode ser feita em servidores.",
                ephemeral=True,
            )
            return

        try:
            stake = int(str(self.amount.value).strip())
        except ValueError:
            await interaction.response.send_message(
                "Informe um valor inteiro para a aposta.",
                ephemeral=True,
            )
            return

        service = cast(
            MatchBetService | None,
            getattr(self.bot, "match_bet_service", None),
        )
        if service is None:
            await interaction.response.send_message(
                "O sistema de bets nao esta disponivel agora.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        try:
            result = await service.place_bet(
                guild_id=interaction.guild.id,
                user_id=interaction.user.id,
                match_id=self.match_id,
                team=self.team.value,
                stake=stake,
            )
        except MatchBetValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        await interaction.followup.send(
            embed=build_match_bet_confirmation_embed(result, settings),
            ephemeral=True,
        )


class MatchBetButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"^match_bet:(?P<match_id>\d+):(?P<team>team_[12])$",
):
    """Botao persistente que abre o modal de aposta."""

    def __init__(
        self,
        bot: commands.Bot,
        match_id: int,
        team: MatchBetTeam,
        *,
        label: str,
        style: discord.ButtonStyle,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                label=label,
                style=style,
                custom_id=f"match_bet:{match_id}:{team.value}",
            )
        )
        self.bot = bot
        self.match_id = match_id
        self.team = team

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match,
    ) -> MatchBetButton:
        return cls(
            cast(commands.Bot, interaction.client),
            int(match.group("match_id")),
            MatchBetTeam(match.group("team")),
            label=item.label or "Apostar",
            style=item.style,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        service = cast(
            MatchBetService | None,
            getattr(self.bot, "match_bet_service", None),
        )
        if service is None:
            await interaction.response.send_message(
                "O sistema de bets nao esta disponivel agora.",
                ephemeral=True,
            )
            return

        match = await service.get_match(self.match_id)
        if match is None:
            await interaction.response.send_message(
                "Esta partida de apostas nao foi encontrada.",
                ephemeral=True,
            )
            return
        if not match.is_active:
            await interaction.response.send_message(
                "Esta partida ja foi encerrada.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            MatchBetStakeModal(self.bot, self.match_id, self.team)
        )


class MatchBetView(discord.ui.View):
    """Botoes publicos de uma sessao de bets."""

    def __init__(
        self,
        bot: commands.Bot,
        match: MatchBetMatch,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(timeout=None)
        team_1_button = MatchBetButton(
            bot,
            match.id,
            MatchBetTeam.TEAM_1,
            label=_button_label(match.team_1),
            style=discord.ButtonStyle.primary,
        )
        team_2_button = MatchBetButton(
            bot,
            match.id,
            MatchBetTeam.TEAM_2,
            label=_button_label(match.team_2),
            style=discord.ButtonStyle.secondary,
        )
        team_1_button.item.disabled = disabled
        team_2_button.item.disabled = disabled
        self.add_item(team_1_button)
        self.add_item(team_2_button)


def _button_label(team_name: str) -> str:
    return f"Apostar {team_name}"[:80]


def _closed_description(match: MatchBetMatch) -> str:
    if match.resolved_winner is MatchBetTeam.TEAM_1:
        return f"Partida encerrada. Vencedor: **{match.team_1}**."
    if match.resolved_winner is MatchBetTeam.TEAM_2:
        return f"Partida encerrada. Vencedor: **{match.team_2}**."
    return "Partida cancelada. Apostas devolvidas."
