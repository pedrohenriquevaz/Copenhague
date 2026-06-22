from __future__ import annotations

import asyncio

from app.core.bot import DiscordBot
from app.core.config import get_settings


async def main() -> None:
    settings = get_settings()
    bot = DiscordBot()

    async with bot:
        await bot.start(settings.DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
