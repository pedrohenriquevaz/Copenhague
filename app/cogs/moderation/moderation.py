from __future__ import annotations

import logging
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from app.cogs.moderation.context import moderation_principal
from app.models.moderation import (
    ModerationActionType,
    ModerationCase,
    ModerationCaseCreate,
    ModerationCaseStatus,
)
from app.services.moderation_service import (
    MAX_MUTE_DURATION_MINUTES,
    ModerationAuthorizationError,
    ModerationService,
    ModerationValidationError,
)

logger = logging.getLogger(__name__)

_ACTION_LABELS: dict[ModerationActionType, str] = {
    ModerationActionType.BAN: "Banimento",
    ModerationActionType.KICK: "Expulsão",
    ModerationActionType.MUTE: "Mute",
    ModerationActionType.WARN: "Advertência",
}


class ModerationCog(commands.Cog):
    """Comandos de punição que reutilizam a autorização central."""

    def __init__(self, bot: commands.Bot, service: ModerationService) -> None:
        self.bot = bot
        self._service = service

    @app_commands.command(name="ban", description="Bane um membro do servidor.")
    @app_commands.guild_only()
    @app_commands.describe(
        member="Membro que será banido.",
        reason="Motivo do banimento.",
    )
    @app_commands.default_permissions(ban_members=True)
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str | None = "Nenhum motivo informado.",
    ) -> None:
        prepared = await self._prepare_member_action(
            interaction,
            member,
            ModerationActionType.BAN,
            reason,
        )
        if prepared is None:
            return
        guild, normalized_reason = prepared

        try:
            await member.ban(
                reason=self._audit_reason(normalized_reason, interaction.user.id)
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "Eu não tenho permissão para banir esse membro.", ephemeral=True
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                "O Discord não conseguiu banir esse membro.", ephemeral=True
            )
            return

        case = await self._record_completed_action(
            guild,
            member,
            interaction.user.id,
            ModerationActionType.BAN,
            normalized_reason,
        )
        if case is None:
            await self._report_unrecorded_action(interaction, "banimento")
            return
        await interaction.followup.send(
            f"{member.mention} foi banido com sucesso.\n"
            f"**Motivo:** {normalized_reason}",
            ephemeral=True,
        )
        await self._send_case_log_safely(guild, case, member)

    @app_commands.command(name="kick", description="Expulsa um membro do servidor.")
    @app_commands.guild_only()
    @app_commands.describe(
        member="Membro que será expulso.",
        reason="Motivo da expulsão.",
    )
    @app_commands.default_permissions(kick_members=True)
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str | None = "Nenhum motivo informado.",
    ) -> None:
        prepared = await self._prepare_member_action(
            interaction,
            member,
            ModerationActionType.KICK,
            reason,
        )
        if prepared is None:
            return
        guild, normalized_reason = prepared

        try:
            await member.kick(
                reason=self._audit_reason(normalized_reason, interaction.user.id)
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "Eu não tenho permissão para expulsar esse membro.", ephemeral=True
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                "O Discord não conseguiu expulsar esse membro.", ephemeral=True
            )
            return

        case = await self._record_completed_action(
            guild,
            member,
            interaction.user.id,
            ModerationActionType.KICK,
            normalized_reason,
        )
        if case is None:
            await self._report_unrecorded_action(interaction, "expulsão")
            return
        await interaction.followup.send(
            f"{member.mention} foi expulso com sucesso.\n"
            f"**Motivo:** {normalized_reason}",
            ephemeral=True,
        )
        await self._send_case_log_safely(guild, case, member)

    @app_commands.command(
        name="mute",
        description="Aplica o castigo nativo do Discord a um membro.",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        member="Membro que receberá o mute.",
        duration="Duração do mute em minutos, de 1 a 40320.",
        reason="Motivo do mute.",
    )
    @app_commands.default_permissions(moderate_members=True)
    async def mute(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        duration: app_commands.Range[int, 1, MAX_MUTE_DURATION_MINUTES],
        reason: str | None = "Nenhum motivo informado.",
    ) -> None:
        try:
            normalized_duration = self._service.normalize_mute_duration(duration)
        except ModerationValidationError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        prepared = await self._prepare_member_action(
            interaction,
            member,
            ModerationActionType.MUTE,
            reason,
        )
        if prepared is None:
            return
        guild, normalized_reason = prepared

        try:
            await member.timeout(
                normalized_duration,
                reason=self._audit_reason(normalized_reason, interaction.user.id),
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "Eu não posso aplicar mute nesse membro. Verifique minhas "
                "permissões e a hierarquia de cargos.",
                ephemeral=True,
            )
            return
        except (discord.HTTPException, TypeError):
            await interaction.followup.send(
                "O Discord não conseguiu aplicar o mute nesse membro.",
                ephemeral=True,
            )
            return

        case = await self._record_completed_action(
            guild,
            member,
            interaction.user.id,
            ModerationActionType.MUTE,
            normalized_reason,
            duration=normalized_duration,
        )
        if case is None:
            await self._report_unrecorded_action(interaction, "mute")
            return
        await interaction.followup.send(
            f"{member.mention} recebeu mute por "
            f"**{self._format_duration(normalized_duration)}**.\n"
            f"**Motivo:** {normalized_reason}",
            ephemeral=True,
        )
        await self._send_case_log_safely(guild, case, member)

    @app_commands.command(
        name="warn",
        description="Registra uma advertência para um membro.",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        member="Membro que receberá a advertência.",
        reason="Motivo da advertência.",
    )
    @app_commands.default_permissions(moderate_members=True)
    async def warn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str | None = "Nenhum motivo informado.",
    ) -> None:
        prepared = await self._prepare_member_action(
            interaction,
            member,
            ModerationActionType.WARN,
            reason,
        )
        if prepared is None:
            return
        guild, normalized_reason = prepared

        case = await self._record_completed_action(
            guild,
            member,
            interaction.user.id,
            ModerationActionType.WARN,
            normalized_reason,
            metadata={"notification_channel": "direct_message"},
        )
        if case is None:
            await interaction.followup.send(
                "Não foi possível registrar a advertência.", ephemeral=True
            )
            return

        notified = await self._notify_warning(guild, member, case)
        notification = (
            "O usuário foi notificado por mensagem direta."
            if notified
            else "A advertência foi registrada, mas a mensagem direta não foi entregue."
        )
        await interaction.followup.send(
            f"Advertência registrada para {member.mention}.\n"
            f"**Motivo:** {normalized_reason}\n{notification}",
            ephemeral=True,
        )
        await self._send_case_log_safely(guild, case, member)

    async def _prepare_member_action(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        action_type: ModerationActionType,
        reason: str | None,
    ) -> tuple[discord.Guild, str] | None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Este comando só pode ser usado dentro de um servidor.",
                ephemeral=True,
            )
            return None

        me = guild.me
        if me is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Não foi possível validar as permissões do bot.",
                ephemeral=True,
            )
            return None
        try:
            normalized_reason = self._service.normalize_case_reason(
                reason or "Nenhum motivo informado."
            )
        except ModerationValidationError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return None

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await self._service.authorize_action(
                guild.id,
                moderation_principal(interaction.user),
                moderation_principal(member),
                moderation_principal(me),
                action_type=action_type,
            )
        except (ModerationAuthorizationError, ModerationValidationError) as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return None
        except Exception:
            logger.exception(
                "moderation.authorization_failed guild_id=%s action=%s "
                "moderator_user_id=%s target_user_id=%s",
                guild.id,
                action_type.value,
                interaction.user.id,
                member.id,
            )
            await interaction.followup.send(
                "Não foi possível validar a autorização de moderação agora.",
                ephemeral=True,
            )
            return None
        return guild, normalized_reason

    async def _record_completed_action(
        self,
        guild: discord.Guild,
        member: discord.Member,
        moderator_user_id: int,
        action_type: ModerationActionType,
        reason: str,
        *,
        duration: timedelta | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ModerationCase | None:
        try:
            return await self._service.create_case(
                ModerationCaseCreate(
                    guild_id=guild.id,
                    action_type=action_type,
                    target_user_id=member.id,
                    moderator_user_id=moderator_user_id,
                    reason=reason,
                    duration=duration,
                    status=ModerationCaseStatus.COMPLETED,
                    metadata={
                        "target_display_name": str(member),
                        **(metadata or {}),
                    },
                )
            )
        except Exception:
            logger.exception(
                "moderation.case.persist_failed guild_id=%s action=%s "
                "target_user_id=%s moderator_user_id=%s",
                guild.id,
                action_type.value,
                member.id,
                moderator_user_id,
            )
            return None

    async def _notify_warning(
        self,
        guild: discord.Guild,
        member: discord.Member,
        case: ModerationCase,
    ) -> bool:
        try:
            await member.send(
                f"Você recebeu uma advertência no servidor "
                f"**{discord.utils.escape_markdown(guild.name)}**.\n"
                f"**Caso:** #{case.id}\n"
                f"**Motivo:** {case.reason}",
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return True
        except (discord.Forbidden, discord.HTTPException):
            logger.warning(
                "moderation.warn.dm_delivery_failed guild_id=%s case_id=%s "
                "target_user_id=%s",
                guild.id,
                case.id,
                member.id,
            )
            return False
        except Exception:
            logger.exception(
                "moderation.warn.dm_delivery_failed guild_id=%s case_id=%s "
                "target_user_id=%s",
                guild.id,
                case.id,
                member.id,
            )
            return False

    async def _send_case_log_safely(
        self,
        guild: discord.Guild,
        case: ModerationCase,
        member: discord.Member,
    ) -> None:
        try:
            await self._send_case_log(guild, case, member)
        except Exception:
            logger.exception(
                "moderation.log_delivery_failed guild_id=%s case_id=%s "
                "channel_id=unavailable",
                guild.id,
                case.id,
            )

    async def _send_case_log(
        self,
        guild: discord.Guild,
        case: ModerationCase,
        member: discord.Member,
    ) -> None:
        settings = await self._service.get_settings(guild.id)
        if settings.log_channel_id is None:
            return
        channel = guild.get_channel(settings.log_channel_id)
        if not isinstance(channel, discord.TextChannel):
            logger.warning(
                "moderation.log_channel_unavailable guild_id=%s channel_id=%s",
                guild.id,
                settings.log_channel_id,
            )
            return
        embed = discord.Embed(
            title=f"Caso de moderação #{case.id}",
            color=0xED4245,
            timestamp=case.created_at,
        )
        embed.add_field(
            name="Ação",
            value=_ACTION_LABELS.get(case.action_type, case.action_type.value),
            inline=True,
        )
        if case.duration is not None:
            embed.add_field(
                name="Duração",
                value=self._format_duration(case.duration),
                inline=True,
            )
        embed.add_field(name="Usuário", value=f"{member} (`{member.id}`)", inline=False)
        embed.add_field(name="Moderador", value=f"`{case.moderator_user_id}`")
        embed.add_field(name="Motivo", value=case.reason, inline=False)
        try:
            await channel.send(
                embed=embed, allowed_mentions=discord.AllowedMentions.none()
            )
        except (discord.Forbidden, discord.HTTPException):
            logger.exception(
                "moderation.log_delivery_failed guild_id=%s channel_id=%s case_id=%s",
                guild.id,
                channel.id,
                case.id,
            )

    @staticmethod
    async def _report_unrecorded_action(
        interaction: discord.Interaction,
        action_name: str,
    ) -> None:
        await interaction.followup.send(
            f"A ação de {action_name} foi executada, mas não foi possível "
            "registrar o caso de moderação. A equipe técnica foi notificada.",
            ephemeral=True,
        )

    @staticmethod
    def _audit_reason(reason: str, moderator_user_id: int) -> str:
        suffix = f" | Responsável ID: {moderator_user_id}"
        return f"{reason[: 512 - len(suffix)]}{suffix}"

    @staticmethod
    def _format_duration(duration: timedelta) -> str:
        total_minutes = int(duration.total_seconds()) // 60
        days, remaining_minutes = divmod(total_minutes, 24 * 60)
        hours, minutes = divmod(remaining_minutes, 60)
        parts: list[str] = []
        if days:
            parts.append(f"{days} dia{'s' if days != 1 else ''}")
        if hours:
            parts.append(f"{hours} hora{'s' if hours != 1 else ''}")
        if minutes:
            parts.append(f"{minutes} minuto{'s' if minutes != 1 else ''}")
        return ", ".join(parts) or "menos de um minuto"


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModerationCog(bot, bot.moderation_service))
