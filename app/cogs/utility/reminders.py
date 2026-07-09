from __future__ import annotations

import asyncio

import discord
from discord import app_commands
from discord.ext import commands


class RemindersCog(commands.Cog):
    """Lembretes simples em memoria."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._tasks: set[asyncio.Task[None]] = set()

    def cog_unload(self) -> None:
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

    @app_commands.command(
        name="lembrete",
        description="Agenda um lembrete simples por DM.",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        minutos="Tempo ate o lembrete, de 1 a 1440 minutos.",
        texto="Texto do lembrete.",
    )
    async def schedule_reminder(
        self,
        interaction: discord.Interaction,
        minutos: int,
        texto: str,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return
        if minutos < 1 or minutos > 1440:
            await interaction.response.send_message(
                "Informe um tempo entre 1 e 1440 minutos.",
                ephemeral=True,
            )
            return

        normalized_text = texto.strip()
        if not normalized_text:
            await interaction.response.send_message(
                "Informe o texto do lembrete.",
                ephemeral=True,
            )
            return
        if len(normalized_text) > 500:
            await interaction.response.send_message(
                "O lembrete deve ter ate 500 caracteres.",
                ephemeral=True,
            )
            return

        task = asyncio.create_task(
            self._send_reminder(
                user=interaction.user,
                channel=interaction.channel,
                minutes=minutos,
                text=normalized_text,
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        await interaction.response.send_message(
            f"Lembrete agendado para daqui a **{minutos}** minuto(s).",
            ephemeral=True,
        )

    async def _send_reminder(
        self,
        *,
        user: discord.abc.User,
        channel: discord.abc.Messageable | None,
        minutes: int,
        text: str,
    ) -> None:
        await asyncio.sleep(minutes * 60)
        message = f"Lembrete: {text}"
        try:
            await user.send(message)
            return
        except discord.HTTPException:
            pass

        if channel is None or not hasattr(channel, "send"):
            return
        try:
            await channel.send(f"{user.mention} {message}")
        except discord.HTTPException:
            return


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RemindersCog(bot))
