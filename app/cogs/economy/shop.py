from __future__ import annotations

from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from app.models.shop import RewardType, StockMode
from app.services.shop_service import ShopService, ShopValidationError
from app.ui.shop_panel import (
    PublicBalanceButton,
    PublicRewardSelect,
    PublicShopView,
    ShopView,
)
from app.utils.embeds import build_shop_embed, format_points
from app.utils.permissions import has_manage_guild


class ShopCog(commands.Cog):
    """Comandos de loja e recompensas."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.service = cast(ShopService, bot.shop_service)  # type: ignore[attr-defined]

    @app_commands.command(name="loja", description="Abre a loja de recompensas.")
    @app_commands.guild_only()
    async def loja(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return

        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        rewards = await self.service.list_rewards(interaction.guild.id)
        await interaction.response.send_message(
            embed=build_shop_embed(rewards, settings),
            view=ShopView(self.bot, rewards, settings) if rewards else None,
            ephemeral=True,
        )

    @app_commands.command(
        name="reward_create",
        description="Cria uma recompensa na loja.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def reward_create(
        self,
        interaction: discord.Interaction,
        nome: str,
        descricao: str,
        tipo: str,
        preco: int,
        estoque: int | None = None,
        max_por_usuario: int | None = 1,
        cargo_entregue: discord.Role | None = None,
        mensagem_entrega: str | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return
        if not has_manage_guild(interaction.user):
            await interaction.response.send_message(
                "Voce nao tem permissao para usar esse comando.",
                ephemeral=True,
            )
            return

        try:
            reward_type = RewardType(tipo.strip().upper())
        except ValueError:
            await interaction.response.send_message(
                "Tipo invalido. Use ROLE, CUSTOM_TEXT, MANUAL_REWARD, "
                "DIGITAL_CODE, VIP_ACCESS ou EVENT_ENTRY.",
                ephemeral=True,
            )
            return

        stock_mode = StockMode.UNLIMITED if estoque is None else StockMode.LIMITED
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            reward = await self.service.create_reward(
                guild_id=interaction.guild.id,
                name=nome,
                description=descricao,
                reward_type=reward_type,
                price=preco,
                stock_quantity=estoque,
                stock_mode=stock_mode,
                max_per_user=max_por_usuario,
                role_id=cargo_entregue.id if cargo_entregue else None,
                delivery_message=mensagem_entrega,
                created_by=interaction.user.id,
            )
        except ShopValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        await interaction.followup.send(
            (
                f"Recompensa criada com sucesso. ID: **{reward.id}**\n"
                f"Nome: **{reward.name}**\n"
                f"Preco: **{format_points(reward.price, settings.currency_name)}**"
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="reward_list",
        description="Lista recompensas cadastradas.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def reward_list(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return
        if not has_manage_guild(interaction.user):
            await interaction.response.send_message(
                "Voce nao tem permissao para usar esse comando.",
                ephemeral=True,
            )
            return

        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        rewards = await self.service.list_rewards(
            interaction.guild.id,
            include_inactive=True,
        )
        await interaction.response.send_message(
            embed=build_shop_embed(rewards, settings),
            ephemeral=True,
        )

    @app_commands.command(
        name="embed_loja",
        description="Publica a embed fixa da loja em um canal.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def embed_loja(
        self,
        interaction: discord.Interaction,
        arquivo: discord.Attachment | None = None,
        canal: discord.TextChannel | discord.Thread | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return
        if not has_manage_guild(interaction.user):
            await interaction.response.send_message(
                "Voce nao tem permissao para usar esse comando.",
                ephemeral=True,
            )
            return

        target_channel = canal or interaction.channel
        if target_channel is None or not hasattr(target_channel, "send"):
            await interaction.response.send_message(
                "Nao foi possivel identificar o canal da loja.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        rewards = await self.service.list_rewards(interaction.guild.id)
        shop_embed = build_shop_embed(
            rewards,
            settings,
            image_url=arquivo.url if arquivo is not None else None,
        )

        try:
            message = await target_channel.send(
                embed=shop_embed,
                view=PublicShopView(self.bot, interaction.guild.id, rewards, settings),
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "Nao tenho permissao para enviar mensagens nesse canal.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                "Ocorreu um erro ao publicar a loja.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"Embed da loja publicada: {message.jump_url}",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ShopCog(bot))
    bot.add_dynamic_items(PublicRewardSelect, PublicBalanceButton)
