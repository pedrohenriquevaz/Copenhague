from __future__ import annotations

from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from app.services.activity_service import ActivityService
from app.ui.economy_panel import EconomyPanelView
from app.utils.embeds import build_activity_conversion_embed
from app.utils.permissions import has_manage_guild


class ActivityCog(commands.Cog):
    """Tracking nativo e conversao de atividade."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.service = cast(ActivityService, bot.activity_service)  # type: ignore[attr-defined]

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

        if after.channel and before.channel != after.channel:
            await self.service.start_voice_session(
                guild_id=member.guild.id,
                user_id=member.id,
                channel_id=after.channel.id,
                is_bot=member.bot,
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
    async def economy_panel_setup(
        self,
        interaction: discord.Interaction,
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
        embed = discord.Embed(
            title="Economia da Comunidade",
            description=(
                "Acumule atividade participando das calls e conversando nos chats.\n"
                "Quando quiser, clique abaixo para converter sua atividade acumulada "
                "em pontos."
            ),
            color=discord.Color.green(),
        )
        embed.add_field(
            name="Conversao atual",
            value=(
                f"1 minuto em call = {settings.voice_points_per_minute} "
                f"{settings.currency_name}\n"
                f"1 mensagem = {settings.message_points} {settings.currency_name}"
            ),
            inline=False,
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
