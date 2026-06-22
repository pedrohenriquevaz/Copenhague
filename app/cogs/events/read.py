from __future__ import annotations

import logging

from discord.ext import commands

logger = logging.getLogger(__name__)


class ReadyEvents(commands.Cog):
    """Eventos relacionados ao ciclo de vida do bot."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        logger.info("Bot conectado como %s (ID: %s)", self.bot.user, self.bot.user.id)
        logger.info("Bot esta pronto e operacional.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReadyEvents(bot))
