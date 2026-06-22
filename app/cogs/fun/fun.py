from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class FunCog(commands.Cog):
    """Comandos diversos/fun do bot."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="Exibe a latência atual do bot.")
    async def ping(self, interaction: discord.Interaction) -> None:
        latency_ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(
            f"🏓 Pong! Latência atual: **{latency_ms}ms**"
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(FunCog(bot))
