from __future__ import annotations

import logging
from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from app.models.form import FormDefinition
from app.services.form_service import FormService, FormValidationError
from app.ui.form_views import DynamicFormView
from app.utils.embeds import build_form_embed, build_form_list_embed

logger = logging.getLogger(__name__)


class FormsCog(commands.Cog):
    """Comandos administrativos para formularios dinamicos."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.service = cast(FormService, bot.form_service)  # type: ignore[attr-defined]

    async def register_active_views(self) -> None:
        """Re-registra botoes persistentes dos formularios ativos."""

        forms = await self.service.list_active_forms()
        for form in forms:
            if form.message_id is None:
                continue

            self.bot.add_view(
                DynamicFormView(self.bot, form.id),
                message_id=form.message_id,
            )
            logger.info(
                "View persistente registrada para o formulario #%s (mensagem %s).",
                form.id,
                form.message_id,
            )

    @app_commands.command(
        name="form_create",
        description="Cria e publica um formulario dinamico no canal atual.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        titulo="Titulo do formulario.",
        descricao="Descricao exibida no embed do formulario.",
        canal_respostas="Canal onde as respostas serao enviadas.",
        perguntas=(
            "Formato: curta|Pergunta;combo|Pergunta|Opcao A,Opcao B;"
            "multipla|Pergunta|Opcao A,Opcao B"
        ),
    )
    async def form_create(
        self,
        interaction: discord.Interaction,
        titulo: str,
        descricao: str,
        canal_respostas: discord.TextChannel | discord.Thread,
        perguntas: str,
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
                "Nao foi possivel identificar o canal para publicar o formulario.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        await self._create_and_publish_form(
            interaction=interaction,
            target_channel=target_channel,
            title=titulo,
            description=descricao,
            response_channel=canal_respostas,
            questions_raw=perguntas,
        )

    async def _create_and_publish_form(
        self,
        *,
        interaction: discord.Interaction,
        target_channel,
        title: str,
        description: str,
        response_channel: discord.TextChannel | discord.Thread,
        questions_raw: str,
    ) -> None:
        try:
            form = await self.service.create_form(
                title=title,
                description=description,
                response_channel_id=response_channel.id,
                created_by=interaction.user.id,
                questions_raw=questions_raw,
            )
        except FormValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        view = DynamicFormView(self.bot, form.id)
        embed = build_form_embed(form)
        try:
            message = await target_channel.send(embed=embed, view=view)
        except discord.Forbidden:
            await self.service.close_form(form.id)
            await interaction.followup.send(
                "Nao tenho permissao para enviar mensagens nesse canal.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await self.service.close_form(form.id)
            await interaction.followup.send(
                "Ocorreu um erro ao publicar o formulario.",
                ephemeral=True,
            )
            return

        published = await self.service.publish_form(
            form.id,
            channel_id=target_channel.id,
            message_id=message.id,
        )
        self.bot.add_view(view, message_id=message.id)

        await interaction.followup.send(
            (
                f"Formulario criado com sucesso. ID: **{published.id}**\n"
                f"Mensagem: {message.jump_url}\n"
                f"Respostas: {response_channel.mention}"
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="form_close",
        description="Encerra um formulario existente.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(form_id="ID do formulario a encerrar.")
    async def form_close(
        self,
        interaction: discord.Interaction,
        form_id: int,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado dentro de um servidor.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            form = await self.service.close_form(form_id)
        except FormValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        await self._disable_public_message(form)
        await interaction.followup.send(
            f"Formulario **#{form.id}** encerrado com sucesso.",
            ephemeral=True,
        )

    @app_commands.command(
        name="form_list",
        description="Lista os formularios ativos.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def form_list(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado dentro de um servidor.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        forms = await self.service.list_active_forms()
        await interaction.followup.send(
            embed=build_form_list_embed(forms),
            ephemeral=True,
        )

    async def _disable_public_message(self, form: FormDefinition) -> None:
        if form.channel_id is None or form.message_id is None:
            return

        channel = self.bot.get_channel(form.channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(form.channel_id)
            except (discord.Forbidden, discord.HTTPException):
                logger.warning(
                    "Nao foi possivel localizar o canal do formulario %s.",
                    form.id,
                )
                return

        if not hasattr(channel, "fetch_message"):
            return

        try:
            message = await channel.fetch_message(form.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            logger.warning(
                "Nao foi possivel acessar a mensagem do formulario %s.",
                form.id,
            )
            return

        view = DynamicFormView(self.bot, form.id)
        view.answer_button.disabled = True
        try:
            await message.edit(embed=build_form_embed(form, closed=True), view=view)
        except discord.HTTPException:
            logger.exception(
                "Erro ao editar mensagem publica do formulario %s.",
                form.id,
            )

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        original_error = getattr(error, "original", error)

        if isinstance(original_error, FormValidationError):
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

        logger.exception("Erro inesperado no formulario: %s", error)
        message = "Ocorreu um erro inesperado ao executar o formulario."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    cog = FormsCog(bot)
    await bot.add_cog(cog)
    await cog.register_active_views()
