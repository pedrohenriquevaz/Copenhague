from __future__ import annotations

from io import BytesIO
from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from app.models.economy import UserWallet
from app.models.shop import LevelConfig, LevelUpgradePurchase
from app.services.economy_service import EconomyService, EconomyValidationError
from app.services.game_progress_service import GameProgressService
from app.services.shop_service import ShopService
from app.ui.ranking_image import RANKING_IMAGE_FILENAME, render_ranking_podium_image
from app.utils.embeds import (
    build_profile_badges,
    build_profile_embed,
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

    @app_commands.command(name="perfil", description="Mostra seu perfil econômico.")
    @app_commands.guild_only()
    async def perfil(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return

        target = usuario or interaction.user
        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        progress_service = cast(GameProgressService, self.bot.game_progress_service)  # type: ignore[attr-defined]
        shop_service = cast(ShopService, self.bot.shop_service)  # type: ignore[attr-defined]

        achievements = await progress_service.list_user_achievements(
            interaction.guild.id,
            target.id,
        )
        wallet = await self.service.get_wallet(interaction.guild.id, target.id)
        top_wallets = await self.service.list_ranking(interaction.guild.id, limit=10)
        ranking_position = self._ranking_position(target.id, top_wallets)
        history = await self.service.list_history(
            interaction.guild.id,
            target.id,
            limit=4,
        )
        credit_state = await self.service.get_credit_protection_state(
            interaction.guild.id,
            target.id,
        )
        savings_overview = await self.service.get_savings_overview(
            interaction.guild.id,
            target.id,
        )
        level_upgrades = await shop_service.list_user_level_upgrades(
            interaction.guild.id,
            target.id,
        )
        configured_levels = await shop_service.list_levels(
            interaction.guild.id,
            include_inactive=True,
        )
        member = target if isinstance(target, discord.Member) else None
        owned_levels = self._owned_level_configs(
            configured_levels,
            level_upgrades,
            member,
        )
        badges = build_profile_badges(
            wallet,
            top_wallets=top_wallets,
            achievements=achievements,
            level_upgrades=level_upgrades,
            credit_state=credit_state,
            savings_overview=savings_overview,
            owned_levels=owned_levels,
        )
        embed = build_profile_embed(
            wallet,
            settings,
            display_name=self._display_name(target),
            avatar_url=self._avatar_url(target),
            badges=badges,
            achievements=achievements,
            level_upgrades=level_upgrades,
            owned_levels=owned_levels,
            recent_transactions=history,
            ranking_position=ranking_position,
            credit_state=credit_state,
            savings_overview=savings_overview,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

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

        await interaction.response.defer(thinking=True)
        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        wallets = await self.service.list_ranking(interaction.guild.id, limit=10)
        if not wallets:
            await interaction.followup.send("Ainda não há carteiras com pontos.")
            return

        display_names, avatar_images = await self._ranking_display_data(
            interaction.guild,
            wallets,
        )
        image_bytes = render_ranking_podium_image(
            wallets,
            settings,
            display_names=display_names,
            avatar_images=avatar_images,
        )
        file = discord.File(
            BytesIO(image_bytes),
            filename=RANKING_IMAGE_FILENAME,
        )
        await interaction.followup.send(file=file)

    @staticmethod
    def _display_name(user: discord.abc.User) -> str:
        return getattr(user, "display_name", None) or user.name

    @staticmethod
    def _avatar_url(user: discord.abc.User) -> str | None:
        avatar = getattr(user, "display_avatar", None)
        return avatar.url if avatar is not None else None

    @staticmethod
    def _ranking_position(user_id: int, wallets: list[UserWallet]) -> int | None:
        for index, wallet in enumerate(wallets, start=1):
            if wallet.user_id == user_id:
                return index
        return None

    @staticmethod
    def _owned_level_configs(
        configured_levels: list[LevelConfig],
        level_upgrades: list[LevelUpgradePurchase],
        member: discord.Member | None,
    ) -> list[LevelConfig]:
        owned_level_numbers = {purchase.level for purchase in level_upgrades}
        role_ids = {role.id for role in member.roles} if member is not None else set()
        levels = {
            level.level: level
            for level in configured_levels
            if level.level in owned_level_numbers or level.role_id in role_ids
        }
        return [levels[key] for key in sorted(levels)]

    async def _ranking_display_data(
        self,
        guild: discord.Guild,
        wallets: list[UserWallet],
    ) -> tuple[dict[int, str], dict[int, bytes]]:
        display_names: dict[int, str] = {}
        avatar_images: dict[int, bytes] = {}
        for index, wallet in enumerate(wallets, start=1):
            member = await self._resolve_member(guild, wallet.user_id)
            if member is None:
                display_names[wallet.user_id] = f"Usuário {wallet.user_id}"
                continue
            display_names[wallet.user_id] = member.display_name
            avatar_size = 256 if index <= 3 else 128
            avatar_bytes = await self._read_avatar(member, size=avatar_size)
            if avatar_bytes is not None:
                avatar_images[wallet.user_id] = avatar_bytes
        return display_names, avatar_images

    @staticmethod
    async def _resolve_member(
        guild: discord.Guild,
        user_id: int,
    ) -> discord.Member | None:
        member = guild.get_member(user_id)
        if member is not None:
            return member
        try:
            return await guild.fetch_member(user_id)
        except discord.HTTPException:
            return None

    @staticmethod
    async def _read_avatar(member: discord.Member, *, size: int) -> bytes | None:
        try:
            return await member.display_avatar.with_size(size).read()
        except discord.HTTPException:
            return None


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EconomyCog(bot))
