from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class PurgeCog(commands.Cog):
    """Comando de limpeza de mensagens."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="purge",
        description="Remove mensagens recentes do canal atual.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(
        quantidade="Quantidade de mensagens para remover, de 1 a 100.",
        motivo="Motivo opcional da limpeza.",
    )
    async def purge_messages(
        self,
        interaction: discord.Interaction,
        quantidade: int,
        motivo: str | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return

        permissions = getattr(interaction.user, "guild_permissions", None)
        if not permissions or not (
            permissions.manage_messages or permissions.administrator
        ):
            await interaction.response.send_message(
                "Voce nao tem permissao para limpar mensagens.",
                ephemeral=True,
            )
            return
        if quantidade < 1 or quantidade > 100:
            await interaction.response.send_message(
                "Informe uma quantidade entre 1 e 100 mensagens.",
                ephemeral=True,
            )
            return

        channel = interaction.channel
        if channel is None or not hasattr(channel, "purge"):
            await interaction.response.send_message(
                "Este canal nao permite limpeza de mensagens.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            deleted = await channel.purge(
                limit=quantidade,
                reason=motivo or f"Purge executado por {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "Nao tenho permissao para apagar mensagens neste canal.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                "Nao consegui apagar as mensagens solicitadas.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"Limpeza concluida. Mensagens removidas: **{len(deleted)}**.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PurgeCog(bot))
