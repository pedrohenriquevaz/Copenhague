from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class ModerationCog(commands.Cog):
    """Comandos de moderacao do bot."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="ban",
        description="Bane um membro do servidor.",
    )
    @app_commands.describe(
        member="Membro que sera banido.",
        reason="Motivo do banimento.",
    )
    @app_commands.default_permissions(ban_members=True)
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str | None = "Nenhum motivo informado.",
    ) -> None:
        """Bane um membro do servidor."""
        if not interaction.guild:
            await interaction.response.send_message(
                "Este comando so pode ser usado dentro de um servidor.",
                ephemeral=True,
            )
            return

        if member == interaction.user:
            await interaction.response.send_message(
                "Voce nao pode banir a si mesmo.",
                ephemeral=True,
            )
            return

        if member == interaction.guild.me:
            await interaction.response.send_message(
                "Eu nao posso banir a mim mesmo.",
                ephemeral=True,
            )
            return

        if (
            isinstance(interaction.user, discord.Member)
            and member.top_role >= interaction.user.top_role
            and interaction.guild.owner_id != interaction.user.id
        ):
            await interaction.response.send_message(
                "Voce nao pode banir um membro com cargo igual ou superior ao seu.",
                ephemeral=True,
            )
            return

        me = interaction.guild.me
        if me is None:
            await interaction.response.send_message(
                "Nao foi possivel validar as permissoes do bot.",
                ephemeral=True,
            )
            return

        if member.top_role >= me.top_role:
            await interaction.response.send_message(
                "Eu nao posso banir esse membro porque o cargo dele e igual "
                "ou superior ao meu.",
                ephemeral=True,
            )
            return

        try:
            await member.ban(reason=f"{reason} | Responsavel: {interaction.user}")
            await interaction.response.send_message(
                f"{member.mention} foi banido com sucesso.\n**Motivo:** {reason}"
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "Eu nao tenho permissao para banir esse membro.",
                ephemeral=True,
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                "Ocorreu um erro ao tentar banir esse membro.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModerationCog(bot))
