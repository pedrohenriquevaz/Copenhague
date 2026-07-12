from __future__ import annotations

from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from app.models.uno import UnoGameStatus
from app.services.uno_service import UnoService, UnoValidationError
from app.ui.uno_view import (
    UnoGameView,
    UnoLobbyView,
    build_uno_attachment,
    build_uno_embed,
)


class UnoCog(commands.Cog):
    """Comandos e recuperação das mesas multiplayer de UNO."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.service = cast(UnoService, bot.uno_service)  # type: ignore[attr-defined]

    async def cog_load(self) -> None:
        sessions = await self.bot.uno_repository.list_active_games()  # type: ignore[attr-defined]
        for session in sessions:
            if session.message_id is None:
                continue
            if session.status is UnoGameStatus.LOBBY:
                view: discord.ui.View = UnoLobbyView(self.bot, session)
            else:
                view = UnoGameView(self.bot, session)
            self.bot.add_view(view, message_id=session.message_id)

    @app_commands.command(
        name="uno",
        description="Cria uma partida multiplayer de UNO.",
    )
    @app_commands.guild_only()
    @app_commands.describe(nome="Nome opcional da mesa de UNO.")
    async def uno(
        self,
        interaction: discord.Interaction,
        aposta: int,
        nome: str | None = None,
    ) -> None:
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message(
                "Este comando só pode ser usado em um canal de servidor.",
                ephemeral=True,
            )
            return
        if interaction.user.bot:
            await interaction.response.send_message(
                "Bots não podem criar partidas de UNO.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        title = nome or f"UNO de {interaction.user.display_name}"
        try:
            session = await self.service.create_lobby(
                guild_id=interaction.guild.id,
                channel_id=interaction.channel.id,
                created_by=interaction.user.id,
                title=title,
                stake=aposta,
            )
        except UnoValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        view = UnoLobbyView(self.bot, session)
        names = {interaction.user.id: interaction.user.display_name}
        try:
            message = await interaction.channel.send(
                embed=build_uno_embed(session),
                file=build_uno_attachment(session, display_names=names),
                view=view,
            )
        except discord.HTTPException:
            await self.service.cancel_game(session.id or 0, interaction.user.id)
            await interaction.followup.send(
                "Não consegui publicar a mesa de UNO neste canal.",
                ephemeral=True,
            )
            return
        await self.service.attach_message(session.id or 0, message.id)
        await interaction.followup.send("Mesa de UNO criada.", ephemeral=True)

    @app_commands.command(
        name="uno_maquina",
        description="Jogue UNO contra a máquina apostando pontos.",
    )
    @app_commands.guild_only()
    async def uno_maquina(
        self,
        interaction: discord.Interaction,
        aposta: int,
        nome: str | None = None,
    ) -> None:
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message(
                "Este comando só pode ser usado em um canal de servidor.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            session = await self.service.create_pve_game(
                guild_id=interaction.guild.id,
                channel_id=interaction.channel.id,
                created_by=interaction.user.id,
                title=nome or f"UNO de {interaction.user.display_name} vs Máquina",
                stake=aposta,
            )
        except UnoValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        view = UnoGameView(self.bot, session)
        names = {
            interaction.user.id: interaction.user.display_name,
            self.service.MACHINE_USER_ID: "Máquina",
        }
        try:
            message = await interaction.channel.send(
                embed=build_uno_embed(session),
                file=build_uno_attachment(session, display_names=names),
                view=view,
            )
        except discord.HTTPException:
            await self.service.cancel_game(session.id or 0, interaction.user.id)
            await interaction.followup.send(
                "Não consegui publicar a mesa de UNO neste canal.",
                ephemeral=True,
            )
            return
        await self.service.attach_message(session.id or 0, message.id)
        await interaction.followup.send(
            "Partida contra a máquina iniciada.", ephemeral=True
        )

    @commands.Cog.listener()
    async def on_raw_message_delete(
        self,
        payload: discord.RawMessageDeleteEvent,
    ) -> None:
        await self.service.cancel_deleted_message(payload.message_id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UnoCog(bot))
