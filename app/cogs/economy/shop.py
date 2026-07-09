from __future__ import annotations

from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from app.models.shop import RewardType, StockMode
from app.services.shop_service import ShopService, ShopValidationError
from app.ui.shop_panel import (
    PublicBalanceButton,
    PublicConvertActivityButton,
    PublicLevelUpgradeButton,
    PublicRewardSelect,
    PublicShopView,
    ShopView,
    send_level_upgrade_confirmation,
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
        levels = await self.service.list_levels(interaction.guild.id)
        await interaction.response.send_message(
            embed=build_shop_embed(rewards, settings, levels=levels),
            view=ShopView(self.bot, rewards, settings),
            ephemeral=True,
        )

    @app_commands.command(
        name="subir_nivel",
        description="Compra o próximo nível disponível.",
    )
    @app_commands.guild_only()
    async def subir_nivel(self, interaction: discord.Interaction) -> None:
        await send_level_upgrade_confirmation(self.bot, interaction)

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
        name="reward_update",
        description="Atualiza uma recompensa existente na loja.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        item_id="ID da recompensa.",
        nome="Novo nome da recompensa.",
        descricao="Nova descricao da recompensa.",
        tipo="Novo tipo da recompensa.",
        preco="Novo preco em pontos.",
        estoque="Novo estoque. Define o item como limitado.",
        estoque_ilimitado="Marca o estoque como ilimitado.",
        max_por_usuario="Novo limite por usuario. Use 0 para remover o limite.",
        cargo_entregue="Novo cargo entregue quando o tipo for ROLE.",
        mensagem_entrega="Nova mensagem de entrega. Use texto vazio para limpar.",
        ativo="Ativa ou desativa o item na loja.",
    )
    async def reward_update(
        self,
        interaction: discord.Interaction,
        item_id: int,
        nome: str | None = None,
        descricao: str | None = None,
        tipo: str | None = None,
        preco: int | None = None,
        estoque: int | None = None,
        estoque_ilimitado: bool = False,
        max_por_usuario: int | None = None,
        cargo_entregue: discord.Role | None = None,
        mensagem_entrega: str | None = None,
        ativo: bool | None = None,
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
        if estoque_ilimitado and estoque is not None:
            await interaction.response.send_message(
                "Use estoque ou estoque_ilimitado, nao os dois ao mesmo tempo.",
                ephemeral=True,
            )
            return

        reward_type = None
        if tipo is not None:
            try:
                reward_type = RewardType(tipo.strip().upper())
            except ValueError:
                await interaction.response.send_message(
                    "Tipo invalido. Use ROLE, CUSTOM_TEXT, MANUAL_REWARD, "
                    "DIGITAL_CODE, VIP_ACCESS ou EVENT_ENTRY.",
                    ephemeral=True,
                )
                return

        stock_mode = None
        if estoque_ilimitado:
            stock_mode = StockMode.UNLIMITED
        elif estoque is not None:
            stock_mode = StockMode.LIMITED

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            reward = await self.service.update_reward(
                guild_id=interaction.guild.id,
                reward_id=item_id,
                actor_id=interaction.user.id,
                name=nome,
                description=descricao,
                reward_type=reward_type,
                price=preco,
                stock_quantity=estoque,
                stock_mode=stock_mode,
                max_per_user=max_por_usuario,
                role_id=cargo_entregue.id if cargo_entregue else None,
                delivery_message=mensagem_entrega,
                is_active=ativo,
            )
        except ShopValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        stock = (
            "ilimitado" if reward.stock_quantity is None else str(reward.stock_quantity)
        )
        await interaction.followup.send(
            (
                "Recompensa atualizada com sucesso.\n\n"
                f"ID: **{reward.id}**\n"
                f"Nome: **{reward.name}**\n"
                f"Preco: **{format_points(reward.price, settings.currency_name)}**\n"
                f"Estoque: **{stock}**\n"
                f"Ativa: **{'sim' if reward.is_active else 'nao'}**"
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="reward_remove",
        description="Remove uma recompensa da loja.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        item_id="ID da recompensa.",
        confirmar="Confirme a remocao permanente da loja.",
        motivo="Motivo registrado na auditoria.",
    )
    async def reward_remove(
        self,
        interaction: discord.Interaction,
        item_id: int,
        confirmar: bool = False,
        motivo: str | None = None,
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
        if not confirmar:
            await interaction.response.send_message(
                "Para remover essa recompensa, execute novamente com confirmar: true.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            reward = await self.service.remove_reward(
                guild_id=interaction.guild.id,
                reward_id=item_id,
                actor_id=interaction.user.id,
                reason=motivo,
            )
        except ShopValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        await interaction.followup.send(
            (
                "Recompensa removida da loja com sucesso.\n\n"
                f"ID: **{reward.id}**\n"
                f"Nome: **{reward.name}**"
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
        levels = await self.service.list_levels(
            interaction.guild.id,
            include_inactive=True,
        )
        await interaction.response.send_message(
            embed=build_shop_embed(rewards, settings, levels=levels),
            ephemeral=True,
        )

    @app_commands.command(
        name="nivel_configurar",
        description="Configura um nível progressivo comprável na loja.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        nivel="Número progressivo do nível.",
        cargo="Cargo associado a esse nível.",
        custo="Quantidade de pontos para comprar esse nível.",
        ativo="Define se o nível pode ser comprado.",
    )
    async def nivel_configurar(
        self,
        interaction: discord.Interaction,
        nivel: int,
        cargo: discord.Role,
        custo: int,
        ativo: bool = True,
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

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            config = await self.service.configure_level(
                guild_id=interaction.guild.id,
                level=nivel,
                role_id=cargo.id,
                price=custo,
                is_active=ativo,
                actor_id=interaction.user.id,
            )
        except ShopValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        await interaction.followup.send(
            (
                "Nível configurado com sucesso.\n\n"
                f"Nível: **{config.level}**\n"
                f"Cargo: {cargo.mention}\n"
                f"Custo: **{format_points(config.price, settings.currency_name)}**\n"
                f"Ativo: **{'sim' if config.is_active else 'nao'}**"
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="nivel_listar",
        description="Lista os níveis progressivos configurados.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def nivel_listar(self, interaction: discord.Interaction) -> None:
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
        levels = await self.service.list_levels(
            interaction.guild.id,
            include_inactive=True,
        )
        if not levels:
            await interaction.response.send_message(
                "Nenhum nível foi configurado ainda.",
                ephemeral=True,
            )
            return

        lines = [
            (
                f"**Nível {level.level}** | <@&{level.role_id}> | "
                f"{format_points(level.price, settings.currency_name)} | "
                f"{'ativo' if level.is_active else 'inativo'}"
            )
            for level in levels
        ]
        await interaction.response.send_message(
            "\n".join(lines),
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
        levels = await self.service.list_levels(interaction.guild.id)
        shop_embed = build_shop_embed(
            rewards,
            settings,
            image_url=arquivo.url if arquivo is not None else None,
            levels=levels,
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
    bot.add_dynamic_items(
        PublicRewardSelect,
        PublicBalanceButton,
        PublicConvertActivityButton,
        PublicLevelUpgradeButton,
    )
