from __future__ import annotations

import logging
from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from app.models.bolao import BolaoEvent
from app.services.bolao_service import BolaoService, BolaoValidationError
from app.ui.bolao_views import BolaoGuessView
from app.utils.embeds import build_bolao_event_embed, build_bolao_list_embed

logger = logging.getLogger(__name__)


class BolaoCog(commands.Cog):
    """Comandos administrativos do bolao de placar."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.service = cast(BolaoService, bot.bolao_service)  # type: ignore[attr-defined]

    async def register_active_views(self) -> None:
        """Re-registra botoes persistentes dos boloes ativos publicados."""

        events = await self.service.list_active_events()
        for event in events:
            if event.message_id is None:
                continue

            self.bot.add_view(
                BolaoGuessView(self.bot, event.id),
                message_id=event.message_id,
            )
            logger.info(
                "View persistente registrada para o bolao #%s (mensagem %s).",
                event.id,
                event.message_id,
            )

    @app_commands.command(
        name="bolao_create",
        description="Cria e publica um bolao de placar no canal atual.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        titulo="Titulo do bolao.",
        descricao="Descricao exibida no anuncio do bolao.",
        premio="Premiacao ou pool prize.",
        time_1="Primeiro time do jogo.",
        time_2="Segundo time do jogo.",
        responsavel="Usuario que recebera os palpites por DM.",
    )
    async def bolao_create(
        self,
        interaction: discord.Interaction,
        titulo: str,
        descricao: str,
        premio: str,
        time_1: str,
        time_2: str,
        responsavel: discord.User,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado dentro de um servidor.",
                ephemeral=True,
            )
            return

        target_channel = interaction.channel
        if target_channel is None or not hasattr(target_channel, "send"):
            await interaction.response.send_message(
                "Nao foi possivel identificar o canal para publicar o bolao.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            event = await self.service.create_event(
                title=titulo,
                description=descricao,
                prize=premio,
                team_1=time_1,
                team_2=time_2,
                created_by=interaction.user.id,
                receiver_user_id=responsavel.id,
            )
        except BolaoValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        view = BolaoGuessView(self.bot, event.id)
        embed = build_bolao_event_embed(event)
        try:
            message = await target_channel.send(embed=embed, view=view)
        except discord.Forbidden:
            await self.service.close_event(event.id)
            await interaction.followup.send(
                "Nao tenho permissao para enviar mensagens nesse canal.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await self.service.close_event(event.id)
            await interaction.followup.send(
                "Ocorreu um erro ao publicar o bolao.",
                ephemeral=True,
            )
            return

        published = await self.service.publish_event(
            event.id,
            channel_id=target_channel.id,
            message_id=message.id,
        )
        self.bot.add_view(view, message_id=message.id)

        await interaction.followup.send(
            (
                f"Bolao criado com sucesso. ID: **{published.id}**\n"
                f"Mensagem: {message.jump_url}\n"
                f"Responsavel pelos palpites: {responsavel.mention}"
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="bolao_close",
        description="Encerra um bolao existente.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        bolao_id="ID do bolao a encerrar.",
        message_id="ID da mensagem publicada do bolao.",
    )
    async def bolao_close(
        self,
        interaction: discord.Interaction,
        bolao_id: str | None = None,
        message_id: str | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado dentro de um servidor.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            event = await self._resolve_event(bolao_id, message_id)
            closed_event = await self.service.close_event(event.id)
        except BolaoValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        await self._disable_public_message(closed_event)
        await interaction.followup.send(
            f"Bolao **#{closed_event.id}** encerrado com sucesso.",
            ephemeral=True,
        )

    @app_commands.command(
        name="bolao_list",
        description="Lista os boloes ativos.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def bolao_list(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado dentro de um servidor.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        events = await self.service.list_active_events()
        await interaction.followup.send(
            embed=build_bolao_list_embed(events),
            ephemeral=True,
        )

    async def _resolve_event(
        self,
        bolao_id: str | None,
        message_id: str | None,
    ) -> BolaoEvent:
        if bolao_id is None and message_id is None:
            raise BolaoValidationError("Informe o ID do bolao ou o ID da mensagem.")

        if bolao_id is not None:
            try:
                parsed_bolao_id = int(bolao_id)
            except ValueError as exc:
                raise BolaoValidationError("O ID do bolao precisa ser numerico.") from exc

            event = await self.service.get_event(parsed_bolao_id)
            if event is None:
                raise BolaoValidationError("Nao encontrei um bolao com esse ID.")
            return event

        assert message_id is not None
        try:
            parsed_message_id = int(message_id)
        except ValueError as exc:
            raise BolaoValidationError("O ID da mensagem precisa ser numerico.") from exc

        event = await self.service.get_event_by_message_id(parsed_message_id)
        if event is None:
            raise BolaoValidationError("Nao encontrei um bolao com essa mensagem.")
        return event

    async def _disable_public_message(self, event: BolaoEvent) -> None:
        if event.channel_id is None or event.message_id is None:
            return

        channel = self.bot.get_channel(event.channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(event.channel_id)
            except (discord.Forbidden, discord.HTTPException):
                logger.warning(
                    "Nao foi possivel localizar o canal do bolao %s.",
                    event.id,
                )
                return

        if not hasattr(channel, "fetch_message"):
            return

        try:
            message = await channel.fetch_message(event.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            logger.warning(
                "Nao foi possivel acessar a mensagem do bolao %s.",
                event.id,
            )
            return

        view = BolaoGuessView(self.bot, event.id)
        view.guess_button.disabled = True
        try:
            await message.edit(
                embed=build_bolao_event_embed(event, closed=True),
                view=view,
            )
        except discord.HTTPException:
            logger.exception("Erro ao editar mensagem publica do bolao %s.", event.id)

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        original_error = getattr(error, "original", error)

        if isinstance(original_error, BolaoValidationError):
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

        logger.exception("Erro inesperado no bolao: %s", error)
        message = "Ocorreu um erro inesperado ao executar o bolao."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    cog = BolaoCog(bot)
    await bot.add_cog(cog)
    await cog.register_active_views()
