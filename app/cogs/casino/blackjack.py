from __future__ import annotations

from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from app.services.blackjack_service import BlackjackService, BlackjackValidationError
from app.ui.blackjack_view import (
    BlackjackView,
    announce_blackjack_result,
    build_blackjack_embed,
)
from app.ui.casino_animation import (
    blackjack_animation,
    build_casino_animation_embed,
    play_casino_animation,
)


class BlackjackCog(commands.Cog):
    """Comando do cassino para BlackJack."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.service = cast(BlackjackService, bot.blackjack_service)  # type: ignore[attr-defined]

    @app_commands.command(
        name="blackjack",
        description="Jogue BlackJack apostando seus pontos.",
    )
    @app_commands.guild_only()
    async def blackjack(self, interaction: discord.Interaction, aposta: int) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return

        if interaction.user.bot:
            await interaction.response.send_message(
                "Bots nao podem jogar BlackJack.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )

        try:
            session = await self.service.start_game(
                guild_id=interaction.guild.id,
                user_id=interaction.user.id,
                bet=aposta,
            )
        except BlackjackValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        view = None
        if not session.is_finished:
            view = BlackjackView(self.bot, session, settings)

        animation = blackjack_animation("deal")
        message = await interaction.followup.send(
            embed=build_casino_animation_embed(animation),
            ephemeral=True,
            wait=True,
        )
        await play_casino_animation(message, animation)
        edit_kwargs = {"embed": build_blackjack_embed(session, settings)}
        if view is not None:
            edit_kwargs["view"] = view

        await message.edit(**edit_kwargs)
        if view is not None:
            view.message = message
        elif session.is_finished:
            await announce_blackjack_result(interaction, session, settings)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BlackjackCog(bot))
