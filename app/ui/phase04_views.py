from __future__ import annotations

from typing import cast

import discord
from discord.ext import commands

from app.models.casino import RaceMascot
from app.models.game_progress import (
    CollectiveRacePlacementResult,
    CollectiveRaceSession,
    CollectiveRaceSettlementResult,
    ScratchCardResult,
    SeasonalSetting,
    UserGameAchievement,
)
from app.models.guild_settings import GuildEconomySettings
from app.services.collective_race_service import (
    CollectiveRaceService,
    CollectiveRaceValidationError,
)
from app.utils.embeds import format_points

RACE_MASCOT_EMOJIS = {
    RaceMascot.DRAGAO: "🐉",
    RaceMascot.LOBO: "🐺",
    RaceMascot.RAPOSA: "🦊",
    RaceMascot.TARTARUGA: "🐢",
    RaceMascot.AGUIA: "🦅",
    RaceMascot.GATO: "🐱",
}

RACE_MASCOT_LABELS = {
    RaceMascot.DRAGAO: "Dragao",
    RaceMascot.LOBO: "Lobo",
    RaceMascot.RAPOSA: "Raposa",
    RaceMascot.TARTARUGA: "Tartaruga",
    RaceMascot.AGUIA: "Aguia",
    RaceMascot.GATO: "Gato",
}


def build_scratch_card_embed(
    result: ScratchCardResult,
    settings: GuildEconomySettings,
    *,
    revealed: bool,
) -> discord.Embed:
    color = discord.Color.green() if result.payout > 0 else discord.Color.gold()
    embed = discord.Embed(title=f"Raspadinha {result.tier_label}", color=color)
    embed.description = _format_scratch_grid(result.grid, revealed=revealed)
    if not revealed:
        embed.add_field(
            name="Status",
            value="Raspadinha comprada. Clique para revelar.",
            inline=False,
        )
        embed.add_field(
            name="Custo",
            value=format_points(result.cost, settings.currency_name),
            inline=True,
        )
        return embed

    message = "Sem combinacao vencedora."
    if result.winning_lines:
        message = "Combinacao: " + ", ".join(result.winning_lines)
    if result.jackpot_won > 0:
        message += "\nJackpot encontrado!"

    embed.add_field(name="Resultado", value=message, inline=False)
    embed.add_field(
        name="Premio",
        value=format_points(result.payout, settings.currency_name),
        inline=True,
    )
    embed.add_field(
        name="Lucro",
        value=_format_profit(result.profit, settings),
        inline=True,
    )
    embed.add_field(
        name="Saldo atual",
        value=format_points(result.wallet.balance, settings.currency_name),
        inline=False,
    )
    if result.seasonal_theme.value != "none":
        embed.set_footer(text=f"Tema sazonal: {result.seasonal_theme.value}")
    return embed


def build_collective_race_embed(
    race: CollectiveRaceSession,
    settings: GuildEconomySettings,
    *,
    closed: bool = False,
) -> discord.Embed:
    color = (
        discord.Color.red()
        if closed or race.status.value != "open"
        else discord.Color.gold()
    )
    embed = discord.Embed(title="Corrida Coletiva de Mascotes", color=color)
    if closed or race.status.value != "open":
        winner = _format_mascot(race.winner) if race.winner else "Cancelada"
        embed.description = f"Corrida encerrada. Resultado: **{winner}**"
    else:
        embed.description = (
            "Escolha um mascote nos botoes abaixo.\n"
            "Cada usuario pode apostar uma vez nesta corrida."
        )
    embed.add_field(
        name="Aposta",
        value=format_points(race.stake, settings.currency_name),
        inline=True,
    )
    embed.add_field(
        name="Pagamento",
        value=f"5x ({format_points(race.stake * 5, settings.currency_name)})",
        inline=True,
    )
    embed.add_field(
        name="Fecha em",
        value=discord.utils.format_dt(race.closes_at, style="R"),
        inline=True,
    )
    embed.add_field(
        name="Mascotes",
        value="\n".join(_format_mascot(mascot) for mascot in RaceMascot),
        inline=False,
    )
    embed.set_footer(text=f"Corrida #{race.id}")
    return embed


def build_collective_race_confirmation_embed(
    result: CollectiveRacePlacementResult,
    settings: GuildEconomySettings,
) -> discord.Embed:
    embed = discord.Embed(title="Aposta registrada", color=discord.Color.green())
    embed.description = (
        f"Corrida: **#{result.race.id}**\n"
        f"Mascote: **{_format_mascot(result.bet.mascot)}**"
    )
    embed.add_field(
        name="Valor",
        value=format_points(result.bet.stake, settings.currency_name),
        inline=True,
    )
    embed.add_field(
        name="Retorno potencial",
        value=format_points(result.bet.potential_payout, settings.currency_name),
        inline=True,
    )
    embed.add_field(
        name="Saldo atual",
        value=format_points(result.wallet.balance, settings.currency_name),
        inline=False,
    )
    return embed


def build_collective_race_result_embed(
    result: CollectiveRaceSettlementResult,
    settings: GuildEconomySettings,
) -> discord.Embed:
    embed = discord.Embed(
        title="Resultado da Corrida Coletiva", color=discord.Color.green()
    )
    embed.description = (
        f"Vencedor: **{_format_mascot(result.winner)}**"
        if result.winner
        else "Corrida cancelada."
    )
    embed.add_field(
        name="Apostas vencedoras", value=str(result.winning_bets), inline=True
    )
    embed.add_field(name="Apostas perdidas", value=str(result.lost_bets), inline=True)
    embed.add_field(
        name="Devolvidas",
        value=str(result.refunded_bets),
        inline=True,
    )
    embed.add_field(
        name="Total pago",
        value=format_points(result.total_paid, settings.currency_name),
        inline=True,
    )
    embed.add_field(
        name="Total devolvido",
        value=format_points(result.total_refunded, settings.currency_name),
        inline=True,
    )
    return embed


def build_achievements_embed(
    user_id: int,
    achievements: list[UserGameAchievement],
) -> discord.Embed:
    embed = discord.Embed(title="Conquistas", color=discord.Color.gold())
    embed.description = f"Conquistas de <@{user_id}>"
    if not achievements:
        embed.add_field(
            name="Nenhuma conquista ainda",
            value="Jogue uma raspadinha ou entre em uma corrida coletiva.",
            inline=False,
        )
        return embed

    lines = []
    for unlocked in achievements:
        achievement = unlocked.achievement
        badge = f"{achievement.badge_emoji} " if achievement.badge_emoji else ""
        lines.append(f"{badge}**{achievement.name}** - {achievement.description}")
    embed.add_field(name="Desbloqueadas", value="\n".join(lines), inline=False)
    return embed


def build_seasonal_embed(setting: SeasonalSetting) -> discord.Embed:
    embed = discord.Embed(title="Evento Sazonal", color=discord.Color.gold())
    embed.description = f"Tema atual: **{setting.theme.value}**"
    embed.set_footer(text="O tema afeta os simbolos da raspadinha.")
    return embed


class ScratchRevealView(discord.ui.View):
    """Botao para revelar uma raspadinha ja comprada."""

    def __init__(
        self,
        result: ScratchCardResult,
        settings: GuildEconomySettings,
    ) -> None:
        super().__init__(timeout=120)
        self.result = result
        self.settings = settings

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.result.user_id:
            await interaction.response.send_message(
                "Essa raspadinha pertence a outro usuario.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Revelar raspadinha", style=discord.ButtonStyle.primary)
    async def reveal(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        button.disabled = True
        await interaction.response.edit_message(
            embed=build_scratch_card_embed(self.result, self.settings, revealed=True),
            view=self,
        )


class CollectiveRaceButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"^collective_race:(?P<race_id>\d+):(?P<mascot>[a-z_]+)$",
):
    """Botao persistente para apostar em uma corrida coletiva."""

    def __init__(
        self,
        bot: commands.Bot,
        race_id: int,
        mascot: RaceMascot,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                label=_format_mascot(mascot),
                style=discord.ButtonStyle.secondary,
                custom_id=f"collective_race:{race_id}:{mascot.value}",
            )
        )
        self.bot = bot
        self.race_id = race_id
        self.mascot = mascot

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
    ) -> CollectiveRaceButton:
        return cls(
            cast(commands.Bot, interaction.client),
            int(match.group("race_id")),
            RaceMascot(match.group("mascot")),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "A corrida coletiva so funciona em servidores.",
                ephemeral=True,
            )
            return

        service = cast(
            CollectiveRaceService | None,
            getattr(self.bot, "collective_race_service", None),
        )
        if service is None:
            await interaction.response.send_message(
                "O sistema de corrida coletiva nao esta disponivel agora.",
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
                race_id=self.race_id,
                mascot=self.mascot.value,
            )
        except CollectiveRaceValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        await interaction.followup.send(
            embed=build_collective_race_confirmation_embed(result, settings),
            ephemeral=True,
        )


class CollectiveRaceView(discord.ui.View):
    """View publica de apostas da corrida coletiva."""

    def __init__(
        self,
        bot: commands.Bot,
        race: CollectiveRaceSession,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(timeout=None)
        for mascot in RaceMascot:
            button = CollectiveRaceButton(bot, race.id, mascot)
            button.item.disabled = disabled
            self.add_item(button)


def _format_scratch_grid(grid: list[list[str]], *, revealed: bool) -> str:
    if not revealed:
        return "\n".join(["|| ? || || ? || || ? ||" for _ in range(3)])
    return "\n".join(" ".join(row) for row in grid)


def _format_mascot(mascot: RaceMascot | None) -> str:
    if mascot is None:
        return "Sem vencedor"
    return f"{RACE_MASCOT_EMOJIS[mascot]} {RACE_MASCOT_LABELS[mascot]}"


def _format_profit(
    profit: int,
    settings: GuildEconomySettings,
) -> str:
    prefix = "+" if profit > 0 else ""
    return f"{prefix}{format_points(profit, settings.currency_name)}"
