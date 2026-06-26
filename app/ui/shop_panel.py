from __future__ import annotations

from typing import cast

import discord
from discord.ext import commands

from app.models.shop import RewardItem, ShopPurchaseStatus
from app.services.economy_service import EconomyService
from app.services.shop_service import ShopService
from app.utils.embeds import build_purchases_embed, build_wallet_embed, format_points


class ShopView(discord.ui.View):
    """View ephemeral da loja com select de recompensas."""

    def __init__(self, bot: commands.Bot, rewards: list[RewardItem]) -> None:
        super().__init__(timeout=300)
        self.bot = bot
        self.rewards = rewards
        self.add_item(RewardSelect(bot, rewards))

    @discord.ui.button(label="Ver saldo", style=discord.ButtonStyle.secondary)
    async def balance(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "A loja so funciona dentro de um servidor.",
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

    @discord.ui.button(label="Minhas compras", style=discord.ButtonStyle.secondary)
    async def purchases(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "A loja so funciona dentro de um servidor.",
                ephemeral=True,
            )
            return

        shop = cast(ShopService, self.bot.shop_service)  # type: ignore[attr-defined]
        repository = self.bot.economy_repository  # type: ignore[attr-defined]
        settings = await repository.get_guild_settings(interaction.guild.id)
        purchases = await shop.list_purchases(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(
            embed=build_purchases_embed(purchases, settings),
            ephemeral=True,
        )


class RewardSelect(discord.ui.Select):
    """Select menu de recompensas."""

    def __init__(self, bot: commands.Bot, rewards: list[RewardItem]) -> None:
        self.bot = bot
        self.reward_map = {str(reward.id): reward for reward in rewards[:25]}
        options = [
            discord.SelectOption(
                label=reward.name[:100],
                value=str(reward.id),
                description=f"{reward.price} pontos | {reward.type.value}"[:100],
            )
            for reward in rewards[:25]
        ]
        super().__init__(
            placeholder="Escolha uma recompensa",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "A loja so funciona dentro de um servidor.",
                ephemeral=True,
            )
            return

        reward = self.reward_map.get(self.values[0])
        if reward is None:
            await interaction.response.send_message(
                "Essa recompensa nao esta mais disponivel.",
                ephemeral=True,
            )
            return

        economy = cast(EconomyService, self.bot.economy_service)  # type: ignore[attr-defined]
        repository = self.bot.economy_repository  # type: ignore[attr-defined]
        settings = await repository.get_guild_settings(interaction.guild.id)
        wallet = await economy.get_wallet(interaction.guild.id, interaction.user.id)
        stock = (
            "ilimitado" if reward.stock_quantity is None else str(reward.stock_quantity)
        )
        embed = discord.Embed(
            title="Confirmar compra?",
            description=reward.description,
            color=discord.Color.purple(),
        )
        embed.add_field(name="Recompensa", value=reward.name, inline=False)
        embed.add_field(
            name="Preco",
            value=format_points(reward.price, settings.currency_name),
            inline=True,
        )
        embed.add_field(
            name="Seu saldo",
            value=format_points(wallet.balance, settings.currency_name),
            inline=True,
        )
        embed.add_field(name="Estoque", value=stock, inline=True)
        embed.add_field(
            name="Saldo apos compra",
            value=format_points(wallet.balance - reward.price, settings.currency_name),
            inline=False,
        )
        await interaction.response.send_message(
            embed=embed,
            view=ConfirmPurchaseView(self.bot, reward.id),
            ephemeral=True,
        )


class ConfirmPurchaseView(discord.ui.View):
    """Confirmacao de compra."""

    def __init__(self, bot: commands.Bot, reward_id: int) -> None:
        super().__init__(timeout=120)
        self.bot = bot
        self.reward_id = reward_id

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success)
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "A loja so funciona dentro de um servidor.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        shop = cast(ShopService, self.bot.shop_service)  # type: ignore[attr-defined]
        repository = self.bot.economy_repository  # type: ignore[attr-defined]
        settings = await repository.get_guild_settings(interaction.guild.id)
        result = await shop.purchase_reward(
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            reward_id=self.reward_id,
        )

        if result.status is ShopPurchaseStatus.SUCCESS and result.reward:
            embed = discord.Embed(
                title="Compra realizada com sucesso",
                color=discord.Color.green(),
            )
            embed.add_field(name="Recompensa", value=result.reward.name, inline=False)
            embed.add_field(
                name="Pontos gastos",
                value=format_points(result.reward.price, settings.currency_name),
                inline=True,
            )
            embed.add_field(
                name="Saldo atual",
                value=format_points(result.balance_after, settings.currency_name),
                inline=True,
            )
            if result.reward.delivery_message:
                embed.add_field(
                    name="Entrega",
                    value=result.reward.delivery_message,
                    inline=False,
                )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        messages = {
            ShopPurchaseStatus.REWARD_NOT_FOUND: "Nao encontrei essa recompensa.",
            ShopPurchaseStatus.REWARD_INACTIVE: "Essa recompensa esta inativa.",
            ShopPurchaseStatus.INSUFFICIENT_BALANCE: (
                f"Saldo insuficiente. Faltam "
                f"{format_points(result.missing_points, settings.currency_name)}."
            ),
            ShopPurchaseStatus.OUT_OF_STOCK: "Essa recompensa esta esgotada.",
            ShopPurchaseStatus.LIMIT_REACHED: (
                "Voce ja atingiu o limite de compras dessa recompensa."
            ),
        }
        await interaction.followup.send(
            messages.get(result.status, "Nao foi possivel concluir a compra."),
            ephemeral=True,
        )

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_message("Compra cancelada.", ephemeral=True)
