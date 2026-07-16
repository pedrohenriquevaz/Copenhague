from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from app.cogs.moderation.context import moderation_principal
from app.models.moderation import (
    ModerationLogChannelReference,
    ModerationPrincipal,
    ModerationRoleReference,
)
from app.services.moderation_service import (
    ModerationAuthorizationError,
    ModerationService,
    ModerationValidationError,
)

logger = logging.getLogger(__name__)


class ModerationConfigurationCog(commands.Cog):
    """Comandos administrativos da fundacao de moderacao."""

    moderation = app_commands.Group(
        name="moderation",
        description="Configura o modulo de moderacao.",
        default_permissions=discord.Permissions(manage_guild=True),
        guild_only=True,
    )
    role = app_commands.Group(
        name="role",
        description="Gerencia cargos autorizados.",
        parent=moderation,
    )
    log_channel = app_commands.Group(
        name="log-channel",
        description="Gerencia o canal de logs.",
        parent=moderation,
    )

    def __init__(self, bot: commands.Bot, service: ModerationService) -> None:
        self.bot = bot
        self._service = service

    def _context(
        self, interaction: discord.Interaction
    ) -> tuple[int, ModerationPrincipal]:
        if interaction.guild is None or not isinstance(
            interaction.user, discord.Member
        ):
            raise ModerationAuthorizationError(
                "Este comando so pode ser usado dentro de um servidor."
            )
        return interaction.guild.id, moderation_principal(interaction.user)

    async def _error(self, interaction: discord.Interaction, error: Exception) -> None:
        message = str(error)
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    async def _unexpected_error(
        self,
        interaction: discord.Interaction,
        *,
        operation: str,
    ) -> None:
        logger.exception(
            "moderation.config.command_failed guild_id=%s actor_id=%s operation=%s",
            interaction.guild.id if interaction.guild else None,
            interaction.user.id,
            operation,
        )
        await self._error(
            interaction,
            RuntimeError(
                "Nao foi possivel concluir a configuracao de moderacao agora."
            ),
        )

    @role.command(name="add", description="Autoriza um cargo para moderacao.")
    async def role_add(
        self, interaction: discord.Interaction, role: discord.Role
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            guild_id, actor = self._context(interaction)
            added = await self._service.add_authorized_role(
                guild_id,
                actor,
                ModerationRoleReference(
                    guild_id=role.guild.id,
                    role_id=role.id,
                    is_default=role.is_default(),
                ),
            )
            message = (
                f"Cargo {role.mention} autorizado para moderacao."
                if added
                else f"O cargo {role.mention} ja estava autorizado."
            )
            await interaction.followup.send(message, ephemeral=True)
        except (ModerationAuthorizationError, ModerationValidationError) as exc:
            await self._error(interaction, exc)
        except Exception:
            await self._unexpected_error(interaction, operation="role_add")

    @role.command(name="remove", description="Remove um cargo autorizado.")
    async def role_remove(
        self, interaction: discord.Interaction, role: discord.Role
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            guild_id, actor = self._context(interaction)
            removed = await self._service.remove_authorized_role(
                guild_id,
                actor,
                ModerationRoleReference(
                    guild_id=role.guild.id,
                    role_id=role.id,
                    is_default=role.is_default(),
                ),
            )
            message = (
                f"Cargo {role.mention} removido da moderacao."
                if removed
                else f"O cargo {role.mention} nao estava autorizado."
            )
            await interaction.followup.send(message, ephemeral=True)
        except (ModerationAuthorizationError, ModerationValidationError) as exc:
            await self._error(interaction, exc)
        except Exception:
            await self._unexpected_error(interaction, operation="role_remove")

    @role.command(name="list", description="Lista os cargos autorizados.")
    async def role_list(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            guild_id, actor = self._context(interaction)
            settings = await self._service.authorize_configuration(guild_id, actor)
            roles = [
                f"<@&{role_id}> (`{role_id}`)"
                for role_id in settings.authorized_role_ids
            ]
            if not roles:
                await interaction.followup.send(
                    "Nenhum cargo de moderacao foi configurado.", ephemeral=True
                )
            else:
                for chunk in self._chunk_lines(roles):
                    await interaction.followup.send(chunk, ephemeral=True)
        except (ModerationAuthorizationError, ModerationValidationError) as exc:
            await self._error(interaction, exc)
        except Exception:
            await self._unexpected_error(interaction, operation="role_list")

    @log_channel.command(name="set", description="Define o canal de logs.")
    async def log_channel_set(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            guild_id, actor = self._context(interaction)
            me = interaction.guild.me if interaction.guild else None
            if me is None:
                raise ModerationAuthorizationError(
                    "Nao foi possivel validar as permissoes do bot."
                )
            bot_permissions = channel.permissions_for(me)
            await self._service.set_log_channel(
                guild_id,
                actor,
                ModerationLogChannelReference(
                    guild_id=channel.guild.id,
                    channel_id=channel.id,
                    bot_can_view=bot_permissions.view_channel,
                    bot_can_send=bot_permissions.send_messages,
                    bot_can_embed=bot_permissions.embed_links,
                ),
            )
            await interaction.followup.send(
                f"Canal de logs definido como {channel.mention}.", ephemeral=True
            )
        except (ModerationAuthorizationError, ModerationValidationError) as exc:
            await self._error(interaction, exc)
        except Exception:
            await self._unexpected_error(interaction, operation="log_channel_set")

    @log_channel.command(name="show", description="Mostra o canal de logs.")
    async def log_channel_show(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            guild_id, actor = self._context(interaction)
            settings = await self._service.authorize_configuration(guild_id, actor)
            message = (
                f"Canal de logs atual: <#{settings.log_channel_id}>."
                if settings.log_channel_id
                else "Nenhum canal de logs foi configurado."
            )
            await interaction.followup.send(message, ephemeral=True)
        except (ModerationAuthorizationError, ModerationValidationError) as exc:
            await self._error(interaction, exc)
        except Exception:
            await self._unexpected_error(interaction, operation="log_channel_show")

    @log_channel.command(name="clear", description="Remove o canal de logs.")
    async def log_channel_clear(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            guild_id, actor = self._context(interaction)
            await self._service.set_log_channel(guild_id, actor, None)
            await interaction.followup.send(
                "Canal de logs de moderacao removido.", ephemeral=True
            )
        except (ModerationAuthorizationError, ModerationValidationError) as exc:
            await self._error(interaction, exc)
        except Exception:
            await self._unexpected_error(interaction, operation="log_channel_clear")

    @staticmethod
    def _chunk_lines(lines: list[str], *, limit: int = 1_900) -> list[str]:
        chunks: list[str] = []
        current: list[str] = []
        current_size = 0
        for line in lines:
            extra = len(line) + (1 if current else 0)
            if current and current_size + extra > limit:
                chunks.append("\n".join(current))
                current = []
                current_size = 0
                extra = len(line)
            current.append(line)
            current_size += extra
        if current:
            chunks.append("\n".join(current))
        return chunks


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModerationConfigurationCog(bot, bot.moderation_service))
