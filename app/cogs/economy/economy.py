from __future__ import annotations

from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from app.services.economy_service import EconomyService, EconomyValidationError
from app.utils.embeds import (
    build_ranking_embed,
    build_transaction_history_embed,
    build_wallet_embed,
    format_points,
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
        name="transferir",
        description="Transfere pontos para outro usuario.",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        usuario="Usuario que recebera os pontos.",
        valor="Quantidade de pontos a transferir.",
    )
    async def transferir(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        valor: int,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return
        if usuario.bot:
            await interaction.response.send_message(
                "Voce nao pode transferir pontos para bots.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        try:
            result = await self.service.transfer_points(
                guild_id=interaction.guild.id,
                sender_id=interaction.user.id,
                receiver_id=usuario.id,
                amount=valor,
            )
        except EconomyValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        embed = discord.Embed(
            title="Transferencia realizada",
            color=discord.Color.green(),
        )
        embed.description = (
            f"{interaction.user.mention} transferiu "
            f"**{format_points(result.amount, settings.currency_name)}** "
            f"para {usuario.mention}."
        )
        embed.add_field(
            name="Seu saldo",
            value=format_points(result.sender_wallet.balance, settings.currency_name),
            inline=True,
        )
        embed.add_field(
            name="Saldo do destinatario",
            value=format_points(result.receiver_wallet.balance, settings.currency_name),
            inline=True,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

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
