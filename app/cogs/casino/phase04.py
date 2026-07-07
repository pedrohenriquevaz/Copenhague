from __future__ import annotations

import asyncio
import logging
from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from app.models.game_progress import CollectiveRaceSession
from app.services.collective_race_service import (
    CollectiveRaceService,
    CollectiveRaceValidationError,
)
from app.services.game_progress_service import (
    GameProgressService,
    GameProgressValidationError,
)
from app.services.scratch_card_service import (
    ScratchCardService,
    ScratchCardValidationError,
)
from app.ui.phase04_views import (
    CollectiveRaceButton,
    CollectiveRaceView,
    ScratchRevealView,
    build_achievements_embed,
    build_collective_race_embed,
    build_collective_race_result_embed,
    build_scratch_card_embed,
    build_seasonal_embed,
)
from app.utils.embeds import format_points

logger = logging.getLogger(__name__)


class CasinoPhase04Cog(commands.Cog):
    """Fase 0.4 do roadmap de jogos."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.scratch_service = cast(ScratchCardService, bot.scratch_card_service)  # type: ignore[attr-defined]
        self.race_service = cast(CollectiveRaceService, bot.collective_race_service)  # type: ignore[attr-defined]
        self.progress_service = cast(GameProgressService, bot.game_progress_service)  # type: ignore[attr-defined]

    async def register_active_views(self) -> None:
        self.bot.add_dynamic_items(CollectiveRaceButton)
        logger.info("Botoes dinamicos de corrida coletiva registrados.")

    @app_commands.command(
        name="raspadinha",
        description="Compre uma raspadinha virtual.",
    )
    @app_commands.guild_only()
    @app_commands.choices(
        tipo=[
            app_commands.Choice(name="Bronze - 50 pontos", value="bronze"),
            app_commands.Choice(name="Prata - 100 pontos", value="prata"),
            app_commands.Choice(name="Ouro - 250 pontos", value="ouro"),
            app_commands.Choice(name="Diamante - 500 pontos", value="diamante"),
        ]
    )
    async def raspadinha(
        self,
        interaction: discord.Interaction,
        tipo: str,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        try:
            result = await self.scratch_service.play(
                guild_id=interaction.guild.id,
                user_id=interaction.user.id,
                tier=tipo,
            )
        except ScratchCardValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        view = ScratchRevealView(result, settings)
        await interaction.followup.send(
            embed=build_scratch_card_embed(result, settings, revealed=False),
            view=view,
            ephemeral=True,
        )

    @app_commands.command(
        name="corrida_iniciar",
        description="Abre uma corrida coletiva de mascotes.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        duracao="Tempo da janela de apostas em segundos.",
        aposta="Valor fixo da aposta por usuario.",
    )
    async def corrida_iniciar(
        self,
        interaction: discord.Interaction,
        duracao: int,
        aposta: int,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return

        channel = interaction.channel
        if channel is None or not hasattr(channel, "send"):
            await interaction.response.send_message(
                "Nao consegui identificar o canal para publicar a corrida.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        try:
            race = await self.race_service.create_race(
                guild_id=interaction.guild.id,
                opened_by=interaction.user.id,
                stake=aposta,
                duration_seconds=duracao,
            )
        except CollectiveRaceValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        view = CollectiveRaceView(self.bot, race)
        try:
            message = await channel.send(
                embed=build_collective_race_embed(race, settings),
                view=view,
            )
        except discord.HTTPException:
            await self.race_service.finish_race(
                guild_id=interaction.guild.id,
                race_id=race.id,
                cancel=True,
            )
            await interaction.followup.send(
                "Nao consegui publicar a corrida neste canal.",
                ephemeral=True,
            )
            return

        published = await self.race_service.publish_race(
            race.id,
            channel_id=channel.id,
            message_id=message.id,
        )
        await message.edit(
            embed=build_collective_race_embed(published, settings),
            view=CollectiveRaceView(self.bot, published),
        )
        self._schedule_race_finish(published)
        await interaction.followup.send(
            f"Corrida coletiva criada. ID: **{published.id}**",
            ephemeral=True,
        )

    @app_commands.command(
        name="corrida_finalizar",
        description="Finaliza uma corrida coletiva manualmente.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.choices(
        vencedor=[
            app_commands.Choice(name="Sortear", value="sortear"),
            app_commands.Choice(name="Dragao", value="dragao"),
            app_commands.Choice(name="Lobo", value="lobo"),
            app_commands.Choice(name="Raposa", value="raposa"),
            app_commands.Choice(name="Tartaruga", value="tartaruga"),
            app_commands.Choice(name="Aguia", value="aguia"),
            app_commands.Choice(name="Gato", value="gato"),
            app_commands.Choice(name="Cancelar", value="cancelar"),
        ]
    )
    async def corrida_finalizar(
        self,
        interaction: discord.Interaction,
        corrida_id: int,
        vencedor: str = "sortear",
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            result = await self.race_service.finish_race(
                guild_id=interaction.guild.id,
                race_id=corrida_id,
                winner=None if vencedor == "sortear" else vencedor,
                cancel=vencedor == "cancelar",
            )
        except CollectiveRaceValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        await self._edit_race_message(result.race, closed=True)
        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        await interaction.followup.send(
            embed=build_collective_race_result_embed(result, settings),
            ephemeral=True,
        )
        await self._send_public_race_result(interaction, result.race.id)

    @app_commands.command(
        name="jackpot",
        description="Mostra o jackpot atual da raspadinha.",
    )
    @app_commands.guild_only()
    async def jackpot(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return

        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        jackpot = await self.progress_service.get_scratch_jackpot(interaction.guild.id)
        formatted_jackpot = format_points(jackpot.amount, settings.currency_name)
        await interaction.response.send_message(
            f"Jackpot da raspadinha: **{formatted_jackpot}**",
            ephemeral=True,
        )

    @app_commands.command(
        name="conquistas",
        description="Mostra conquistas de jogos.",
    )
    @app_commands.guild_only()
    async def conquistas(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return

        target = usuario or interaction.user
        achievements = await self.progress_service.list_user_achievements(
            interaction.guild.id,
            target.id,
        )
        await interaction.response.send_message(
            embed=build_achievements_embed(target.id, achievements),
            ephemeral=True,
        )

    @app_commands.command(
        name="evento_sazonal",
        description="Mostra o tema sazonal atual dos jogos.",
    )
    @app_commands.guild_only()
    async def evento_sazonal(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return

        setting = await self.progress_service.get_seasonal_theme(interaction.guild.id)
        await interaction.response.send_message(
            embed=build_seasonal_embed(setting),
            ephemeral=True,
        )

    @app_commands.command(
        name="evento_sazonal_definir",
        description="Define o tema sazonal dos jogos.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.choices(
        tema=[
            app_commands.Choice(name="Nenhum", value="none"),
            app_commands.Choice(name="Natal", value="natal"),
            app_commands.Choice(name="Halloween", value="halloween"),
            app_commands.Choice(name="Copa", value="copa"),
            app_commands.Choice(name="Anime", value="anime"),
            app_commands.Choice(name="Aniversario", value="aniversario"),
        ]
    )
    async def evento_sazonal_definir(
        self,
        interaction: discord.Interaction,
        tema: str,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return

        try:
            setting = await self.progress_service.set_seasonal_theme(
                interaction.guild.id,
                tema,
            )
        except GameProgressValidationError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        await interaction.response.send_message(
            embed=build_seasonal_embed(setting),
            ephemeral=True,
        )

    def _schedule_race_finish(self, race: CollectiveRaceSession) -> None:
        async def runner() -> None:
            await asyncio.sleep(
                max(1, int((race.closes_at - discord.utils.utcnow()).total_seconds()))
            )
            latest = await self.race_service.get_race(race.id)
            if latest is None or latest.status.value != "open":
                return
            try:
                result = await self.race_service.finish_race(
                    guild_id=latest.guild_id,
                    race_id=latest.id,
                )
            except CollectiveRaceValidationError:
                return
            await self._edit_race_message(result.race, closed=True)
            await self._send_race_result_to_channel(result.race.id)

        asyncio.create_task(runner())

    async def _edit_race_message(
        self,
        race: CollectiveRaceSession,
        *,
        closed: bool,
    ) -> None:
        if race.channel_id is None or race.message_id is None:
            return

        channel = self.bot.get_channel(race.channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(race.channel_id)
            except (discord.Forbidden, discord.HTTPException):
                return
        if not hasattr(channel, "fetch_message"):
            return

        try:
            message = await channel.fetch_message(race.message_id)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            return

        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            race.guild_id
        )
        try:
            await message.edit(
                embed=build_collective_race_embed(race, settings, closed=closed),
                view=CollectiveRaceView(self.bot, race, disabled=closed),
            )
        except discord.HTTPException:
            logger.exception("Erro ao editar corrida coletiva %s.", race.id)

    async def _send_public_race_result(
        self,
        interaction: discord.Interaction,
        race_id: int,
    ) -> None:
        channel = interaction.channel
        if channel is None or not hasattr(channel, "send"):
            return
        race = await self.race_service.get_race(race_id)
        if race is None:
            return
        try:
            await channel.send(_format_race_public_result(race))
        except discord.HTTPException:
            logger.exception("Erro ao anunciar corrida coletiva %s.", race.id)

    async def _send_race_result_to_channel(self, race_id: int) -> None:
        race = await self.race_service.get_race(race_id)
        if race is None or race.channel_id is None:
            return
        channel = self.bot.get_channel(race.channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(race.channel_id)
            except (discord.Forbidden, discord.HTTPException):
                return
        if not hasattr(channel, "send"):
            return
        try:
            await channel.send(_format_race_public_result(race))
        except discord.HTTPException:
            logger.exception("Erro ao anunciar corrida coletiva %s.", race.id)


def _format_race_public_result(race: CollectiveRaceSession) -> str:
    winner = race.winner.value.title() if race.winner else "Cancelada"
    return f"Corrida coletiva **#{race.id}** encerrada. Resultado: **{winner}**"


async def setup(bot: commands.Bot) -> None:
    cog = CasinoPhase04Cog(bot)
    await bot.add_cog(cog)
    await cog.register_active_views()
