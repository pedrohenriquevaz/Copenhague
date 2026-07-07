from __future__ import annotations

import logging
from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from app.models.match_bet import MatchBetMatch, MatchBetSettlementResult, MatchBetTeam
from app.services.match_bet_service import MatchBetService, MatchBetValidationError
from app.ui.match_bet_views import (
    MatchBetButton,
    MatchBetView,
    build_match_bet_embed,
    build_match_bet_list_embed,
)
from app.utils.embeds import format_points

logger = logging.getLogger(__name__)


class MatchBetCog(commands.Cog):
    """Comandos para apostas saudaveis em partidas do servidor."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.service = cast(MatchBetService, bot.match_bet_service)  # type: ignore[attr-defined]

    async def register_active_views(self) -> None:
        self.bot.add_dynamic_items(MatchBetButton)
        logger.info("Botoes dinamicos de bets registrados.")

    @app_commands.command(
        name="bet_criar",
        description="Cria uma sessao de apostas para uma partida.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        canal="Canal onde a embed de apostas sera publicada.",
        titulo="Titulo da partida.",
        time_1="Primeiro time.",
        time_2="Segundo time.",
        odd_time_1="Odd inicial do primeiro time. Ex.: 1.87",
        odd_time_2="Odd inicial do segundo time. Ex.: 1.98",
    )
    async def bet_criar(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
        titulo: str,
        time_1: str,
        time_2: str,
        odd_time_1: str,
        odd_time_2: str,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado dentro de um servidor.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        try:
            match = await self.service.create_match(
                guild_id=interaction.guild.id,
                title=titulo,
                team_1=time_1,
                team_2=time_2,
                odd_team_1=odd_time_1,
                odd_team_2=odd_time_2,
                created_by=interaction.user.id,
            )
        except MatchBetValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        view = MatchBetView(self.bot, match)
        try:
            message = await canal.send(
                embed=build_match_bet_embed(match, settings),
                view=view,
            )
        except discord.Forbidden:
            await self.service.settle_match(
                guild_id=interaction.guild.id,
                match_id=match.id,
                winner="cancelar",
            )
            await interaction.followup.send(
                "Nao tenho permissao para publicar a bet nesse canal.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await self.service.settle_match(
                guild_id=interaction.guild.id,
                match_id=match.id,
                winner="cancelar",
            )
            await interaction.followup.send(
                "Nao consegui publicar a embed de apostas.",
                ephemeral=True,
            )
            return

        published = await self.service.publish_match(
            match.id,
            channel_id=canal.id,
            message_id=message.id,
        )
        await message.edit(embed=build_match_bet_embed(published, settings), view=view)

        await interaction.followup.send(
            (
                f"Bet criada com sucesso. ID: **{published.id}**\n"
                f"Mensagem: {message.jump_url}"
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="bet_odds",
        description="Altera as odds de uma partida ativa.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        bet_id="ID da sessao de apostas.",
        odd_time_1="Nova odd do primeiro time.",
        odd_time_2="Nova odd do segundo time.",
    )
    async def bet_odds(
        self,
        interaction: discord.Interaction,
        bet_id: int,
        odd_time_1: str,
        odd_time_2: str,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado dentro de um servidor.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            match = await self.service.update_odds(
                guild_id=interaction.guild.id,
                match_id=bet_id,
                odd_team_1=odd_time_1,
                odd_team_2=odd_time_2,
            )
        except MatchBetValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        await self._edit_public_message(match)
        await self._send_odds_update(interaction, match)
        await interaction.followup.send(
            "Odds atualizadas com sucesso.",
            ephemeral=True,
        )

    @app_commands.command(
        name="bet_encerrar",
        description="Encerra uma bet e paga os vencedores.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.choices(
        vencedor=[
            app_commands.Choice(name="Time 1", value="team_1"),
            app_commands.Choice(name="Time 2", value="team_2"),
            app_commands.Choice(name="Cancelar e devolver", value="cancelar"),
        ]
    )
    @app_commands.describe(
        bet_id="ID da sessao de apostas.",
        vencedor="Resultado final da partida.",
    )
    async def bet_encerrar(
        self,
        interaction: discord.Interaction,
        bet_id: int,
        vencedor: str,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado dentro de um servidor.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            result = await self.service.settle_match(
                guild_id=interaction.guild.id,
                match_id=bet_id,
                winner=vencedor,
            )
        except MatchBetValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        await self._edit_public_message(result.match, closed=True)
        await interaction.followup.send(
            self._format_settlement_summary(result),
            ephemeral=True,
        )

        channel = interaction.channel
        if channel is not None and hasattr(channel, "send"):
            try:
                await channel.send(self._format_public_settlement(result))
            except discord.HTTPException:
                logger.exception("Erro ao publicar resumo da bet %s.", bet_id)

    @app_commands.command(
        name="bet_listar",
        description="Lista as bets ativas.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def bet_listar(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado dentro de um servidor.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        matches = await self.service.list_active_matches(interaction.guild.id)
        await interaction.followup.send(
            embed=build_match_bet_list_embed(matches),
            ephemeral=True,
        )

    async def _edit_public_message(
        self,
        match: MatchBetMatch,
        *,
        closed: bool = False,
    ) -> None:
        if match.channel_id is None or match.message_id is None:
            return

        channel = self.bot.get_channel(match.channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(match.channel_id)
            except (discord.Forbidden, discord.HTTPException):
                logger.warning(
                    "Nao foi possivel localizar o canal da bet %s.", match.id
                )
                return

        if not hasattr(channel, "fetch_message"):
            return

        try:
            message = await channel.fetch_message(match.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            logger.warning("Nao foi possivel acessar a mensagem da bet %s.", match.id)
            return

        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            match.guild_id
        )
        view = MatchBetView(self.bot, match, disabled=closed or not match.is_active)
        try:
            await message.edit(
                embed=build_match_bet_embed(match, settings, closed=closed),
                view=view,
            )
        except discord.HTTPException:
            logger.exception("Erro ao editar mensagem publica da bet %s.", match.id)

    async def _send_odds_update(
        self,
        interaction: discord.Interaction,
        match: MatchBetMatch,
    ) -> None:
        channel = interaction.channel
        if channel is None or not hasattr(channel, "send"):
            return

        message = (
            f"🌟 Odds para a partida **{match.title}**\n"
            f"{match.team_1}: {MatchBetService.format_odd_bps(match.odd_team_1_bps)}\n"
            f"{match.team_2}: {MatchBetService.format_odd_bps(match.odd_team_2_bps)}"
        )
        try:
            await channel.send(message)
        except discord.HTTPException:
            logger.exception(
                "Erro ao publicar atualizacao de odds da bet %s.", match.id
            )

    def _format_settlement_summary(
        self,
        result: MatchBetSettlementResult,
    ) -> str:
        return (
            f"Bet **#{result.match.id}** encerrada.\n"
            f"Tickets vencedores: **{result.winning_tickets}**\n"
            f"Tickets perdedores: **{result.lost_tickets}**\n"
            f"Tickets devolvidos: **{result.refunded_tickets}**\n"
            f"Total pago: **{result.total_paid} pontos**\n"
            f"Total devolvido: **{result.total_refunded} pontos**"
        )

    def _format_public_settlement(
        self,
        result: MatchBetSettlementResult,
    ) -> str:
        match = result.match
        if match.resolved_winner is MatchBetTeam.TEAM_1:
            winner = match.team_1
        elif match.resolved_winner is MatchBetTeam.TEAM_2:
            winner = match.team_2
        else:
            winner = "Cancelada"

        return (
            f"Bet **#{match.id} - {match.title}** encerrada.\n"
            f"Resultado: **{winner}**\n"
            f"Pagamentos: {format_points(result.total_paid)} | "
            f"Devolvidos: {format_points(result.total_refunded)}"
        )

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        original_error = getattr(error, "original", error)

        if isinstance(original_error, MatchBetValidationError):
            if interaction.response.is_done():
                await interaction.followup.send(str(original_error), ephemeral=True)
            else:
                await interaction.response.send_message(
                    str(original_error),
                    ephemeral=True,
                )
            return

        if isinstance(
            error,
            (app_commands.MissingPermissions, app_commands.CheckFailure),
        ):
            message = "Voce nao tem permissao para executar este comando."
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
            return

        logger.exception("Erro inesperado no sistema de bets: %s", error)
        message = "Ocorreu um erro inesperado ao executar o sistema de bets."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    cog = MatchBetCog(bot)
    await bot.add_cog(cog)
    await cog.register_active_views()
