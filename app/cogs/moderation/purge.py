from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from app.cogs.moderation.context import moderation_principal
from app.models.moderation import ModerationActionType
from app.services.moderation_service import (
    ModerationAuthorizationError,
    ModerationService,
    ModerationValidationError,
)

logger = logging.getLogger(__name__)


class PurgeCog(commands.Cog):
    """Comando de limpeza de mensagens."""

    def __init__(self, bot: commands.Bot, service: ModerationService) -> None:
        self.bot = bot
        self._service = service

    @app_commands.command(
        name="purge",
        description="Remove mensagens recentes do canal atual.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(
        manage_messages=True,
        read_message_history=True,
    )
    @app_commands.describe(
        amount="Quantidade de mensagens para remover, de 1 a 100.",
        reason="Motivo opcional da limpeza.",
    )
    async def purge_messages(
        self,
        interaction: discord.Interaction,
        amount: int,
        reason: str | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return

        if amount < 1 or amount > 100:
            await interaction.response.send_message(
                "Informe uma quantidade entre 1 e 100 mensagens.",
                ephemeral=True,
            )
            return

        try:
            normalized_reason = self._service.normalize_case_reason(
                reason or f"Purge executado por {interaction.user}"
            )
        except ModerationValidationError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        channel = interaction.channel
        me = interaction.guild.me
        if (
            channel is None
            or not hasattr(channel, "purge")
            or not hasattr(channel, "permissions_for")
            or me is None
            or not isinstance(interaction.user, discord.Member)
        ):
            await interaction.response.send_message(
                "Este canal nao permite limpeza de mensagens.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await self._service.authorize_action(
                interaction.guild.id,
                moderation_principal(
                    interaction.user,
                    permissions=channel.permissions_for(interaction.user),
                ),
                None,
                moderation_principal(me, permissions=channel.permissions_for(me)),
                action_type=ModerationActionType.PURGE,
            )
        except (ModerationAuthorizationError, ModerationValidationError) as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except Exception:
            logger.exception(
                "moderation.authorization_failed guild_id=%s action=PURGE "
                "moderator_user_id=%s channel_id=%s",
                interaction.guild.id,
                interaction.user.id,
                channel.id,
            )
            await interaction.followup.send(
                "Nao foi possivel validar a autorizacao de moderacao agora.",
                ephemeral=True,
            )
            return

        try:
            deleted = await channel.purge(
                limit=amount,
                reason=normalized_reason[:512],
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "Nao tenho permissao para apagar mensagens neste canal.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                "Nao consegui apagar as mensagens solicitadas.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"Limpeza concluida. Mensagens removidas: **{len(deleted)}**.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PurgeCog(bot, bot.moderation_service))
