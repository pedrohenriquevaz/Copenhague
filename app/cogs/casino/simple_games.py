from __future__ import annotations

from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from app.models.casino import CasinoGameResult, CasinoUserStats
from app.models.economy import EconomyTransaction
from app.models.guild_settings import GuildEconomySettings
from app.services.casino_service import CasinoService, CasinoValidationError
from app.ui.duel_view import DuelChallengeView, build_duel_invite_embed
from app.utils.embeds import format_points


class CasinoGamesCog(commands.Cog):
    """Jogos instantaneos do arcade de pontos."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.service = cast(CasinoService, bot.casino_service)  # type: ignore[attr-defined]

    @app_commands.command(
        name="cara_coroa",
        description="Aposte pontos em Cara ou Coroa.",
    )
    @app_commands.guild_only()
    @app_commands.choices(
        escolha=[
            app_commands.Choice(name="Cara", value="cara"),
            app_commands.Choice(name="Coroa", value="coroa"),
        ]
    )
    async def cara_coroa(
        self,
        interaction: discord.Interaction,
        aposta: int,
        escolha: str,
    ) -> None:
        if not await self._validate_interaction(interaction):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = await self._get_settings(interaction)
        try:
            result = await self.service.play_coin_flip(
                guild_id=interaction.guild.id,  # type: ignore[union-attr]
                user_id=interaction.user.id,
                bet=aposta,
                choice=escolha,
            )
        except CasinoValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        await interaction.followup.send(
            embed=build_casino_result_embed(result, settings),
            ephemeral=True,
        )

    @app_commands.command(
        name="dado",
        description="Aposte pontos em um dado de 6 lados.",
    )
    @app_commands.guild_only()
    @app_commands.choices(
        modo=[
            app_commands.Choice(name="Numero exato", value="numero"),
            app_commands.Choice(name="Par", value="par"),
            app_commands.Choice(name="Impar", value="impar"),
            app_commands.Choice(name="Maior que 3", value="maior"),
            app_commands.Choice(name="Menor ou igual a 3", value="menor"),
        ]
    )
    async def dado(
        self,
        interaction: discord.Interaction,
        aposta: int,
        modo: str,
        valor: int | None = None,
    ) -> None:
        if not await self._validate_interaction(interaction):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = await self._get_settings(interaction)
        try:
            result = await self.service.play_dice(
                guild_id=interaction.guild.id,  # type: ignore[union-attr]
                user_id=interaction.user.id,
                bet=aposta,
                mode=modo,
                value=valor,
            )
        except CasinoValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        await interaction.followup.send(
            embed=build_casino_result_embed(result, settings),
            ephemeral=True,
        )

    @app_commands.command(name="slot", description="Aposte pontos na Slot Machine.")
    @app_commands.guild_only()
    async def slot(self, interaction: discord.Interaction, aposta: int) -> None:
        if not await self._validate_interaction(interaction):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = await self._get_settings(interaction)
        try:
            result = await self.service.play_slot(
                guild_id=interaction.guild.id,  # type: ignore[union-attr]
                user_id=interaction.user.id,
                bet=aposta,
            )
        except CasinoValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        await interaction.followup.send(
            embed=build_casino_result_embed(result, settings),
            ephemeral=True,
        )

    @app_commands.command(name="roleta", description="Aposte pontos na roleta.")
    @app_commands.guild_only()
    @app_commands.choices(
        cor=[
            app_commands.Choice(name="Vermelho", value="vermelho"),
            app_commands.Choice(name="Preto", value="preto"),
            app_commands.Choice(name="Verde", value="verde"),
        ]
    )
    async def roleta(
        self,
        interaction: discord.Interaction,
        aposta: int,
        cor: str,
    ) -> None:
        if not await self._validate_interaction(interaction):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = await self._get_settings(interaction)
        try:
            result = await self.service.play_roulette(
                guild_id=interaction.guild.id,  # type: ignore[union-attr]
                user_id=interaction.user.id,
                bet=aposta,
                color=cor,
            )
        except CasinoValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        await interaction.followup.send(
            embed=build_casino_result_embed(result, settings),
            ephemeral=True,
        )

    @app_commands.command(
        name="duelo",
        description="Desafie outro usuario para apostar pontos.",
    )
    @app_commands.guild_only()
    @app_commands.choices(
        modo=[
            app_commands.Choice(name="Sorte", value="sorte"),
            app_commands.Choice(name="Dados", value="dados"),
        ]
    )
    async def duelo(
        self,
        interaction: discord.Interaction,
        desafiar: discord.Member,
        aposta: int,
        modo: str,
    ) -> None:
        if not await self._validate_interaction(interaction):
            return
        if desafiar.bot:
            await interaction.response.send_message(
                "Voce nao pode desafiar bots.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = await self._get_settings(interaction)
        try:
            duel_mode = await self.service.validate_duel_challenge(
                guild_id=interaction.guild.id,  # type: ignore[union-attr]
                challenger_id=interaction.user.id,
                challenged_id=desafiar.id,
                bet=aposta,
                mode=modo,
            )
        except CasinoValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        view = DuelChallengeView(
            self.bot,
            guild_id=interaction.guild.id,  # type: ignore[union-attr]
            challenger_id=interaction.user.id,
            challenged_id=desafiar.id,
            bet=aposta,
            mode=duel_mode,
            settings=settings,
        )
        embed = build_duel_invite_embed(
            challenger=interaction.user,
            challenged=desafiar,
            bet=aposta,
            mode=duel_mode,
            settings=settings,
        )
        if interaction.channel is None:
            await interaction.followup.send(
                "Nao consegui identificar o canal para publicar o duelo.",
                ephemeral=True,
            )
            return

        try:
            message = await interaction.channel.send(embed=embed, view=view)
        except discord.HTTPException:
            await interaction.followup.send(
                "Nao consegui publicar o duelo neste canal.",
                ephemeral=True,
            )
            return

        view.message = message
        await interaction.followup.send(
            "Desafio criado.",
            ephemeral=True,
        )

    @app_commands.command(
        name="corrida",
        description="Aposte em uma corrida individual de mascotes.",
    )
    @app_commands.guild_only()
    @app_commands.choices(
        mascote=[
            app_commands.Choice(name="Dragao", value="dragao"),
            app_commands.Choice(name="Lobo", value="lobo"),
            app_commands.Choice(name="Raposa", value="raposa"),
            app_commands.Choice(name="Tartaruga", value="tartaruga"),
            app_commands.Choice(name="Aguia", value="aguia"),
            app_commands.Choice(name="Gato", value="gato"),
        ]
    )
    async def corrida(
        self,
        interaction: discord.Interaction,
        aposta: int,
        mascote: str,
    ) -> None:
        if not await self._validate_interaction(interaction):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = await self._get_settings(interaction)
        try:
            result = await self.service.play_mascot_race(
                guild_id=interaction.guild.id,  # type: ignore[union-attr]
                user_id=interaction.user.id,
                bet=aposta,
                mascot=mascote,
            )
        except CasinoValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        await interaction.followup.send(
            embed=build_casino_result_embed(result, settings),
            ephemeral=True,
        )

    @app_commands.command(
        name="jogos_perfil",
        description="Mostra suas estatisticas de jogos.",
    )
    @app_commands.guild_only()
    async def jogos_perfil(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member | None = None,
    ) -> None:
        if not await self._validate_interaction(interaction):
            return

        target = usuario or interaction.user
        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = await self._get_settings(interaction)
        stats = await self.service.get_user_stats(
            interaction.guild.id,  # type: ignore[union-attr]
            target.id,
        )
        await interaction.followup.send(
            embed=build_casino_profile_embed(stats, settings),
            ephemeral=True,
        )

    @app_commands.command(
        name="jogos_ranking",
        description="Mostra o ranking de lucro em jogos.",
    )
    @app_commands.guild_only()
    async def jogos_ranking(self, interaction: discord.Interaction) -> None:
        if not await self._validate_interaction(interaction):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = await self._get_settings(interaction)
        ranking = await self.service.list_profit_ranking(
            interaction.guild.id,  # type: ignore[union-attr]
        )
        await interaction.followup.send(
            embed=build_casino_ranking_embed(ranking, settings),
            ephemeral=True,
        )

    @app_commands.command(
        name="jogos_historico",
        description="Mostra seu historico recente de apostas.",
    )
    @app_commands.guild_only()
    async def jogos_historico(self, interaction: discord.Interaction) -> None:
        if not await self._validate_interaction(interaction):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = await self._get_settings(interaction)
        transactions = await self.service.list_history(
            interaction.guild.id,  # type: ignore[union-attr]
            interaction.user.id,
        )
        await interaction.followup.send(
            embed=build_casino_history_embed(transactions, settings),
            ephemeral=True,
        )

    async def _validate_interaction(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return False

        if interaction.user.bot:
            await interaction.response.send_message(
                "Bots nao podem jogar no arcade.",
                ephemeral=True,
            )
            return False

        return True

    async def _get_settings(
        self,
        interaction: discord.Interaction,
    ) -> GuildEconomySettings:
        return await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id  # type: ignore[union-attr]
        )


def build_casino_result_embed(
    result: CasinoGameResult,
    settings: GuildEconomySettings,
) -> discord.Embed:
    color = discord.Color.green() if result.payout > result.bet else discord.Color.red()
    if result.payout == result.bet:
        color = discord.Color.blurple()

    embed = discord.Embed(title=result.title, color=color)
    embed.description = _format_result_message(result)
    for line in result.detail_lines:
        name, _, value = line.partition(":")
        embed.add_field(name=name, value=value.strip() or "-", inline=True)

    embed.add_field(
        name="Aposta",
        value=format_points(result.bet, settings.currency_name),
        inline=True,
    )
    embed.add_field(
        name="Retorno",
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
    return embed


def build_casino_history_embed(
    transactions: list[EconomyTransaction],
    settings: GuildEconomySettings,
) -> discord.Embed:
    embed = discord.Embed(title="Historico de jogos", color=discord.Color.gold())
    if not transactions:
        embed.description = "Nenhuma aposta registrada ainda."
        return embed

    lines = []
    for transaction in transactions:
        game = transaction.metadata.get("game", "jogo")
        sign = "+" if transaction.amount > 0 else ""
        lines.append(
            f"`{sign}{format_points(transaction.amount, settings.currency_name)}` "
            f"| {game} | {transaction.type.value}"
        )
    embed.description = "\n".join(lines)
    return embed


def build_casino_profile_embed(
    stats: CasinoUserStats,
    settings: GuildEconomySettings,
) -> discord.Embed:
    embed = discord.Embed(title="Perfil de jogos", color=discord.Color.gold())
    embed.description = f"Estatisticas de <@{stats.user_id}>"
    embed.add_field(name="Partidas", value=str(stats.total_games_played), inline=True)
    embed.add_field(
        name="Total apostado",
        value=format_points(stats.total_bet_amount, settings.currency_name),
        inline=True,
    )
    embed.add_field(
        name="Total recebido",
        value=format_points(stats.total_payout_amount, settings.currency_name),
        inline=True,
    )
    embed.add_field(
        name="Lucro liquido",
        value=_format_profit(stats.net_profit, settings),
        inline=True,
    )
    embed.add_field(
        name="Maior vitoria",
        value=format_points(stats.biggest_win, settings.currency_name),
        inline=True,
    )
    embed.add_field(
        name="Maior aposta perdida",
        value=format_points(stats.biggest_loss, settings.currency_name),
        inline=True,
    )
    return embed


def build_casino_ranking_embed(
    ranking: list[CasinoUserStats],
    settings: GuildEconomySettings,
) -> discord.Embed:
    embed = discord.Embed(title="Ranking de jogos", color=discord.Color.gold())
    if not ranking:
        embed.description = "Nenhuma aposta registrada ainda."
        return embed

    lines = []
    for index, stats in enumerate(ranking, start=1):
        lines.append(
            f"**#{index}** <@{stats.user_id}> - "
            f"{_format_profit(stats.net_profit, settings)} "
            f"({stats.total_games_played} partida(s))"
        )
    embed.description = "\n".join(lines)
    return embed


def _format_result_message(result: CasinoGameResult) -> str:
    if result.payout > result.bet:
        return f"Voce venceu! Resultado: **{result.result_label}**"
    if result.payout > 0:
        return f"Quase. Resultado: **{result.result_label}**"
    return f"Voce perdeu. Resultado: **{result.result_label}**"


def _format_profit(
    profit: int,
    settings: GuildEconomySettings,
) -> str:
    prefix = "+" if profit > 0 else ""
    return f"{prefix}{format_points(profit, settings.currency_name)}"


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CasinoGamesCog(bot))
