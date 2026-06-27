from __future__ import annotations

from typing import cast

import discord
from discord.ext import commands

from app.services.activity_service import ActivityService
from app.services.economy_service import EconomyService
from app.services.shop_service import ShopService
from app.ui.shop_panel import ShopView
from app.utils.embeds import (
    build_activity_conversion_embed,
    build_shop_embed,
    build_transaction_history_embed,
    build_wallet_embed,
)


class EconomyPanelView(discord.ui.View):
    """Painel persistente de economia."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Converter atividade",
        style=discord.ButtonStyle.primary,
        custom_id="economy_panel:convert",
    )
    async def convert_activity(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este painel so funciona dentro de um servidor.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        activity = cast(ActivityService, self.bot.activity_service)  # type: ignore[attr-defined]
        repository = self.bot.economy_repository  # type: ignore[attr-defined]
        settings = await repository.get_guild_settings(interaction.guild.id)
        result = await activity.convert_activity(
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
        )
        await interaction.followup.send(
            embed=build_activity_conversion_embed(result, settings),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Ver saldo",
        style=discord.ButtonStyle.secondary,
        custom_id="economy_panel:balance",
    )
    async def balance(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este painel so funciona dentro de um servidor.",
                ephemeral=True,
            )
            return

        economy = cast(EconomyService, self.bot.economy_service)  # type: ignore[attr-defined]
        repository = self.bot.economy_repository  # type: ignore[attr-defined]
        settings = await repository.get_guild_settings(interaction.guild.id)
        wallet = await economy.get_wallet(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(
            embed=build_wallet_embed(wallet, settings),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Abrir loja",
        style=discord.ButtonStyle.success,
        custom_id="economy_panel:shop",
    )
    async def open_shop(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este painel so funciona dentro de um servidor.",
                ephemeral=True,
            )
            return

        shop = cast(ShopService, self.bot.shop_service)  # type: ignore[attr-defined]
        repository = self.bot.economy_repository  # type: ignore[attr-defined]
        settings = await repository.get_guild_settings(interaction.guild.id)
        rewards = await shop.list_rewards(interaction.guild.id)
        await interaction.response.send_message(
            embed=build_shop_embed(rewards, settings),
            view=ShopView(self.bot, rewards, settings) if rewards else None,
            ephemeral=True,
        )

    @discord.ui.button(
        label="Historico",
        style=discord.ButtonStyle.secondary,
        custom_id="economy_panel:history",
    )
    async def history(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este painel so funciona dentro de um servidor.",
                ephemeral=True,
            )
            return

        economy = cast(EconomyService, self.bot.economy_service)  # type: ignore[attr-defined]
        repository = self.bot.economy_repository  # type: ignore[attr-defined]
        settings = await repository.get_guild_settings(interaction.guild.id)
        transactions = await economy.list_history(
            interaction.guild.id,
            interaction.user.id,
        )
        await interaction.response.send_message(
            embed=build_transaction_history_embed(transactions, settings),
            ephemeral=True,
        )
