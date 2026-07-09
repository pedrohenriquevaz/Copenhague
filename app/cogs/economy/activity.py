from __future__ import annotations

from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from app.models.guild_settings import GuildEconomySettings
from app.services.activity_service import ActivityService
from app.ui.economy_panel import EconomyPanelView
from app.utils.embeds import build_activity_conversion_embed, build_economy_panel_embed
from app.utils.permissions import has_manage_guild


class ActivityCog(commands.Cog):
    """Tracking nativo e conversao de atividade."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.service = cast(ActivityService, bot.activity_service)  # type: ignore[attr-defined]

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        for guild in self.bot.guilds:
            for channel in guild.voice_channels:
                await self._sync_voice_channel(channel)
            for channel in guild.stage_channels:
                await self._sync_voice_channel(channel)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return

        await self.service.record_message(
            guild_id=message.guild.id,
            channel_id=message.channel.id,
            user_id=message.author.id,
            is_bot=message.author.bot,
        )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.guild is None or member.bot:
            return

        if before.channel and before.channel != after.channel:
            await self.service.close_voice_sessions(
                guild_id=member.guild.id,
                user_id=member.id,
                is_bot=member.bot,
            )
            await self._sync_voice_channel(before.channel)

        if after.channel and before.channel != after.channel:
            await self._sync_voice_channel(after.channel)

        if before.channel == after.channel and after.channel is not None:
            await self._sync_voice_channel(after.channel)

    async def _sync_voice_channel(
        self,
        channel: discord.VoiceChannel | discord.StageChannel,
    ) -> None:
        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            channel.guild.id
        )
        should_track_channel = self._should_track_voice_channel(channel, settings)

        for user_id, is_bot, is_muted in self._voice_channel_users(channel):
            if is_bot:
                continue

            if should_track_channel and not is_muted:
                await self.service.start_voice_session(
                    guild_id=channel.guild.id,
                    user_id=user_id,
                    channel_id=channel.id,
                    is_bot=is_bot,
                )
            else:
                await self.service.close_voice_sessions(
                    guild_id=channel.guild.id,
                    user_id=user_id,
                    is_bot=is_bot,
                )

    def _should_track_voice_channel(
        self,
        channel: discord.VoiceChannel | discord.StageChannel,
        settings: GuildEconomySettings,
    ) -> bool:
        if settings.ignore_afk_channel and channel.guild.afk_channel == channel:
            return False
        if settings.count_voice_when_alone:
            return True

        human_users = [
            user_id
            for user_id, is_bot, is_muted in self._voice_channel_users(channel)
            if not is_bot and not is_muted
        ]
        return len(human_users) > 1

    def _voice_channel_users(
        self,
        channel: discord.VoiceChannel | discord.StageChannel,
    ) -> list[tuple[int, bool, bool]]:
        members = channel.members
        if members:
            return [
                (member.id, member.bot, self._is_voice_state_muted(member.voice))
                for member in members
            ]

        bot_user_id = self.bot.user.id if self.bot.user else None
        return [
            (
                user_id,
                user_id == bot_user_id,
                self._is_voice_state_muted(voice_state),
            )
            for user_id, voice_state in channel.voice_states.items()
        ]

    @staticmethod
    def _is_voice_state_muted(voice_state: discord.VoiceState | None) -> bool:
        if voice_state is None:
            return False
        return bool(
            voice_state.self_mute
            or voice_state.mute
            or getattr(voice_state, "suppress", False)
        )

    @app_commands.command(
        name="converter_atividade",
        description="Converte sua atividade acumulada em pontos.",
    )
    @app_commands.guild_only()
    async def converter_atividade(self, interaction: discord.Interaction) -> None:
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
        result = await self.service.convert_activity(
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
        )
        await interaction.followup.send(
            embed=build_activity_conversion_embed(result, settings),
            ephemeral=True,
        )

    @app_commands.command(
        name="economy_panel_setup",
        description="Publica o painel de economia no canal atual ou informado.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        arquivo="Imagem exibida dentro da embed do painel.",
        canal="Canal onde o painel sera publicado.",
    )
    async def economy_panel_setup(
        self,
        interaction: discord.Interaction,
        arquivo: discord.Attachment | None = None,
        canal: discord.TextChannel | discord.Thread | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return
        if not has_manage_guild(interaction.user):
            await interaction.response.send_message(
                "Voce nao tem permissao para usar esse comando.",
                ephemeral=True,
            )
            return

        target_channel = canal or interaction.channel
        if target_channel is None or not hasattr(target_channel, "send"):
            await interaction.response.send_message(
                "Nao foi possivel identificar o canal do painel.",
                ephemeral=True,
            )
            return

        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        embed = build_economy_panel_embed(
            settings,
            image_url=arquivo.url if arquivo is not None else None,
        )
        message = await target_channel.send(
            embed=embed, view=EconomyPanelView(self.bot)
        )
        await interaction.response.send_message(
            f"Painel publicado: {message.jump_url}",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    cog = ActivityCog(bot)
    await bot.add_cog(cog)
    bot.add_view(EconomyPanelView(bot))
