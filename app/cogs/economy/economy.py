from __future__ import annotations

from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from app.services.economy_service import EconomyService
from app.utils.embeds import (
    build_ranking_embed,
    build_transaction_history_embed,
    build_wallet_embed,
)


class EconomyCog(commands.Cog):
    """Comandos publicos de economia."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.service = cast(EconomyService, bot.economy_service)  # type: ignore[attr-defined]

    @app_commands.command(name="saldo", description="Mostra seu saldo de pontos.")
    @app_commands.guild_only()
    async def saldo(
        self,
        interaction: discord.Interaction,
        usuario: discord.User | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return

        target = usuario or interaction.user
        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        wallet = await self.service.get_wallet(interaction.guild.id, target.id)
        await interaction.response.send_message(
            embed=build_wallet_embed(wallet, settings, title=f"Carteira de {target}"),
            ephemeral=True,
        )

    @app_commands.command(name="perfil", description="Mostra seu perfil economico.")
    @app_commands.guild_only()
    async def perfil(
        self,
        interaction: discord.Interaction,
        usuario: discord.User | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return

        target = usuario or interaction.user
        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        wallet = await self.service.get_wallet(interaction.guild.id, target.id)
        embed = build_wallet_embed(
            wallet, settings, title=f"Perfil economico de {target}"
        )
        history = await self.service.list_history(
            interaction.guild.id, target.id, limit=3
        )
        embed.add_field(
            name="Transacoes recentes",
            value="\n".join(transaction.type.value for transaction in history) or "-",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="historico",
        description="Mostra suas transacoes recentes.",
    )
    @app_commands.guild_only()
    async def historico(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return

        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        transactions = await self.service.list_history(
            interaction.guild.id,
            interaction.user.id,
        )
        await interaction.response.send_message(
            embed=build_transaction_history_embed(transactions, settings),
            ephemeral=True,
        )

    @app_commands.command(
        name="ranking",
        description="Mostra o ranking de pontos do servidor.",
    )
    @app_commands.guild_only()
    async def ranking(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return

        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        wallets = await self.service.list_ranking(interaction.guild.id, limit=10)
        await interaction.response.send_message(
            embed=build_ranking_embed(wallets, settings),
            ephemeral=False,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EconomyCog(bot))
