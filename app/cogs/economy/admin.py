from __future__ import annotations

from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from app.services.economy_service import EconomyService, EconomyValidationError
from app.utils.embeds import format_points
from app.utils.permissions import has_administrator, has_manage_guild, has_role


class EconomyAdminCog(commands.Cog):
    """Comandos administrativos da economia."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.service = cast(EconomyService, bot.economy_service)  # type: ignore[attr-defined]

    async def _can_manage_economy(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            return False
        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        return has_manage_guild(interaction.user) or has_role(
            interaction.user,
            settings.economy_manager_role_id,
        )

    @app_commands.command(
        name="give_points",
        description="Concede pontos manualmente a um usuario.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def give_points(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        quantidade: int,
        motivo: str,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return
        if usuario.bot:
            await interaction.response.send_message(
                "Nao e possivel conceder pontos a bots.",
                ephemeral=True,
            )
            return
        if not await self._can_manage_economy(interaction):
            await interaction.response.send_message(
                "Voce nao tem permissao para usar esse comando.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        try:
            result = await self.service.give_points(
                guild_id=interaction.guild.id,
                user_id=usuario.id,
                actor_id=interaction.user.id,
                amount=quantidade,
                reason=motivo,
            )
        except EconomyValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        formatted_balance = format_points(result.wallet.balance, settings.currency_name)
        await interaction.followup.send(
            (
                "Pontos concedidos com sucesso.\n\n"
                f"Usuario: {usuario.mention}\n"
                f"Quantidade: {format_points(quantidade, settings.currency_name)}\n"
                f"Motivo: {motivo}\n"
                f"Novo saldo: {formatted_balance}"
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="remove_points",
        description="Remove pontos manualmente de um usuario.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def remove_points(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        quantidade: int,
        motivo: str,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return
        if usuario.bot:
            await interaction.response.send_message(
                "Nao e possivel remover pontos de bots.",
                ephemeral=True,
            )
            return
        if not has_administrator(interaction.user):
            await interaction.response.send_message(
                "Voce nao tem permissao para usar esse comando.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        try:
            result = await self.service.remove_points(
                guild_id=interaction.guild.id,
                user_id=usuario.id,
                actor_id=interaction.user.id,
                amount=quantidade,
                reason=motivo,
            )
        except EconomyValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        formatted_balance = format_points(result.wallet.balance, settings.currency_name)
        await interaction.followup.send(
            (
                "Pontos removidos com sucesso.\n\n"
                f"Usuario: {usuario.mention}\n"
                f"Quantidade: {format_points(quantidade, settings.currency_name)}\n"
                f"Motivo: {motivo}\n"
                f"Novo saldo: {formatted_balance}"
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="economy_status",
        description="Mostra a configuracao atual da economia.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def economy_status(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return
        if not await self._can_manage_economy(interaction):
            await interaction.response.send_message(
                "Voce nao tem permissao para usar esse comando.",
                ephemeral=True,
            )
            return

        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        embed = discord.Embed(title="Status da economia", color=discord.Color.green())
        embed.add_field(name="Moeda", value=settings.currency_name, inline=True)
        embed.add_field(
            name="Provider",
            value=settings.activity_provider,
            inline=True,
        )
        embed.add_field(
            name="Taxa call",
            value=f"{settings.voice_points_per_minute}/min",
            inline=True,
        )
        embed.add_field(
            name="Taxa mensagem",
            value=str(settings.message_points),
            inline=True,
        )
        embed.add_field(
            name="Limite admin",
            value=format_points(
                settings.max_admin_grant_per_use,
                settings.currency_name,
            ),
            inline=True,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EconomyAdminCog(bot))
