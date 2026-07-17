from __future__ import annotations

from typing import cast

import discord
from discord.ext import commands

from app.services.mlbb_auth_service import MlbbAuthService
from app.ui.mlbb_panel import MlbbPanelView, build_mlbb_panel_embed


class MlbbAdminController:
    """Handler administrativo usado pelo Cog dono do grupo /mlbb."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def publish_panel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        service = cast(MlbbAuthService, self.bot.mlbb_auth_service)  # type: ignore[attr-defined]
        if not service.enabled:
            await interaction.followup.send(
                "A integracao MLBB esta desabilitada neste ambiente.",
                ephemeral=True,
            )
            return
        message = await channel.send(
            embed=build_mlbb_panel_embed(),
            view=MlbbPanelView(self.bot),
        )
        await interaction.followup.send(
            f"Painel MLBB publicado: {message.jump_url}", ephemeral=True
        )
