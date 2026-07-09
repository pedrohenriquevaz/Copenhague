from __future__ import annotations

from typing import cast

import discord
from discord.ext import commands

from app.models.guild_settings import GuildEconomySettings
from app.models.shop import (
    LevelConfig,
    LevelUpgradeStatus,
    RewardItem,
    ShopPurchaseStatus,
)
from app.services.activity_service import ActivityService
from app.services.economy_service import EconomyService
from app.services.shop_service import ShopService
from app.utils.embeds import (
    build_activity_conversion_embed,
    build_purchases_embed,
    build_wallet_embed,
    format_points,
)


def _format_stock(reward: RewardItem) -> str:
    if reward.stock_quantity == 0:
        return "Esgotado"
    if reward.stock_quantity is None:
        return "Estoque: ilimitado"
    return f"Estoque: {reward.stock_quantity}"


def _build_reward_options(
    rewards: list[RewardItem],
    settings: GuildEconomySettings,
) -> list[discord.SelectOption]:
    return [
        discord.SelectOption(
            label=reward.name[:100],
            value=str(reward.id),
            description=(
                f"{format_points(reward.price, settings.currency_name)} | "
                f"{_format_stock(reward)}"
            )[:100],
        )
        for reward in rewards[:25]
    ]


async def _send_wallet_embed(
    bot: commands.Bot,
    interaction: discord.Interaction,
) -> None:
    if interaction.guild is None:
        await interaction.response.send_message(
            "A loja so funciona dentro de um servidor.",
            ephemeral=True,
        )
        return

    economy = cast(EconomyService, bot.economy_service)  # type: ignore[attr-defined]
    repository = bot.economy_repository  # type: ignore[attr-defined]
    settings = await repository.get_guild_settings(interaction.guild.id)
    wallet = await economy.get_wallet(interaction.guild.id, interaction.user.id)
    await interaction.response.send_message(
        embed=build_wallet_embed(wallet, settings),
        ephemeral=True,
    )


async def _convert_activity(
    bot: commands.Bot,
    interaction: discord.Interaction,
) -> None:
    if interaction.guild is None:
        await interaction.response.send_message(
            "A loja so funciona dentro de um servidor.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    activity = cast(ActivityService, bot.activity_service)  # type: ignore[attr-defined]
    repository = bot.economy_repository  # type: ignore[attr-defined]
    settings = await repository.get_guild_settings(interaction.guild.id)
    result = await activity.convert_activity(
        guild_id=interaction.guild.id,
        user_id=interaction.user.id,
    )
    await interaction.followup.send(
        embed=build_activity_conversion_embed(result, settings),
        ephemeral=True,
    )


async def _send_purchase_confirmation(
    bot: commands.Bot,
    interaction: discord.Interaction,
    reward: RewardItem,
) -> None:
    if interaction.guild is None:
        await interaction.response.send_message(
            "A loja so funciona dentro de um servidor.",
            ephemeral=True,
        )
        return

    economy = cast(EconomyService, bot.economy_service)  # type: ignore[attr-defined]
    repository = bot.economy_repository  # type: ignore[attr-defined]
    settings = await repository.get_guild_settings(interaction.guild.id)
    wallet = await economy.get_wallet(interaction.guild.id, interaction.user.id)
    stock = _format_stock(reward)
    embed = discord.Embed(
        title="Confirmar compra?",
        description=reward.description,
        color=discord.Color.purple(),
    )
    embed.add_field(name="Recompensa", value=reward.name, inline=False)
    embed.add_field(
        name="Preço",
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
        view=ConfirmPurchaseView(bot, reward.id),
        ephemeral=True,
    )


async def send_level_upgrade_confirmation(
    bot: commands.Bot,
    interaction: discord.Interaction,
) -> None:
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            "A loja so funciona dentro de um servidor.",
            ephemeral=True,
        )
        return

    shop = cast(ShopService, bot.shop_service)  # type: ignore[attr-defined]
    economy = cast(EconomyService, bot.economy_service)  # type: ignore[attr-defined]
    repository = bot.economy_repository  # type: ignore[attr-defined]
    settings = await repository.get_guild_settings(interaction.guild.id)
    current_role_ids = {role.id for role in interaction.user.roles}
    current_level, next_level, levels = await shop.get_next_level(
        guild_id=interaction.guild.id,
        user_id=interaction.user.id,
        current_role_ids=current_role_ids,
    )
    if not levels:
        await interaction.response.send_message(
            "Nenhum nível foi configurado para este servidor ainda.",
            ephemeral=True,
        )
        return
    if next_level is None:
        await interaction.response.send_message(
            "Você já está no maior nível disponível.",
            ephemeral=True,
        )
        return

    role = interaction.guild.get_role(next_level.role_id)
    if role is None:
        await interaction.response.send_message(
            "O cargo associado ao próximo nível não existe mais.",
            ephemeral=True,
        )
        return

    wallet = await economy.get_wallet(interaction.guild.id, interaction.user.id)
    embed = discord.Embed(
        title="Confirmar upgrade de nível?",
        description=(
            "Essa compra troca seu cargo de nível automaticamente e não possui "
            "reembolso."
        ),
        color=discord.Color.purple(),
    )
    embed.add_field(
        name="Nível atual",
        value=str(current_level or "sem nível"),
        inline=True,
    )
    embed.add_field(
        name="Próximo nível",
        value=f"Nível {next_level.level}",
        inline=True,
    )
    embed.add_field(name="Cargo", value=role.mention, inline=True)
    embed.add_field(
        name="Custo",
        value=format_points(next_level.price, settings.currency_name),
        inline=True,
    )
    embed.add_field(
        name="Seu saldo",
        value=format_points(wallet.balance, settings.currency_name),
        inline=True,
    )
    embed.add_field(
        name="Saldo apos compra",
        value=format_points(wallet.balance - next_level.price, settings.currency_name),
        inline=False,
    )
    await interaction.response.send_message(
        embed=embed,
        view=ConfirmLevelUpgradeView(bot, next_level.level),
        ephemeral=True,
    )


async def _apply_level_role(
    *,
    bot: commands.Bot,
    guild: discord.Guild,
    member: discord.Member,
    target_level: LevelConfig,
    levels: list[LevelConfig],
) -> str | None:
    role_error = _validate_level_role_change(
        bot=bot,
        guild=guild,
        member=member,
        target_level=target_level,
        levels=levels,
    )
    if role_error is not None:
        return role_error

    target_role = guild.get_role(target_level.role_id)
    if target_role is None:
        return "O cargo associado ao nível comprado não existe mais."

    old_roles = [
        role
        for level in levels
        if level.role_id != target_level.role_id
        if (role := guild.get_role(level.role_id)) is not None
        if role in member.roles
    ]
    try:
        if old_roles:
            await member.remove_roles(
                *old_roles,
                reason=f"Upgrade para nível {target_level.level}",
            )
        if target_role not in member.roles:
            await member.add_roles(
                target_role,
                reason=f"Upgrade para nível {target_level.level}",
            )
    except discord.Forbidden:
        return "Não tenho permissão para alterar os cargos desse usuário."
    except discord.HTTPException:
        return "O Discord recusou a alteração de cargos. Tente novamente."
    return None


def _validate_level_role_change(
    *,
    bot: commands.Bot,
    guild: discord.Guild,
    member: discord.Member,
    target_level: LevelConfig,
    levels: list[LevelConfig],
) -> str | None:
    bot_user = bot.user
    bot_member = guild.me
    if bot_member is None and bot_user is not None:
        bot_member = guild.get_member(bot_user.id)
    if bot_member is None:
        return "Não consegui identificar meu membro no servidor."
    if not bot_member.guild_permissions.manage_roles:
        return "Preciso da permissão Gerenciar Cargos para entregar níveis."

    target_role = guild.get_role(target_level.role_id)
    if target_role is None:
        return "O cargo associado ao nível comprado não existe mais."
    if target_role >= bot_member.top_role:
        return (
            "Não consigo entregar esse cargo porque ele está acima do meu cargo "
            "mais alto."
        )

    for level in levels:
        role = guild.get_role(level.role_id)
        if role is None:
            continue
        if role in member.roles:
            if role >= bot_member.top_role:
                return (
                    "Não consigo remover um dos cargos antigos de nível porque "
                    "ele está acima do meu cargo mais alto."
                )
    return None


class PublicRewardSelect(
    discord.ui.DynamicItem[discord.ui.Select],
    template=r"^shop_panel:reward_select:(?P<guild_id>\d+)$",
):
    """Select dinamico da loja fixa."""

    def __init__(
        self,
        bot: commands.Bot,
        guild_id: int,
        rewards: list[RewardItem] | None = None,
        settings: GuildEconomySettings | None = None,
        item: discord.ui.Select | None = None,
    ) -> None:
        if item is None:
            if rewards is None or settings is None:
                raise ValueError(
                    "A loja publica precisa de recompensas e configuracoes."
                )
            select = discord.ui.Select(
                placeholder="Escolha uma recompensa",
                min_values=1,
                max_values=1,
                options=_build_reward_options(rewards, settings),
                custom_id=f"shop_panel:reward_select:{guild_id}",
                row=0,
            )
        else:
            select = item
        super().__init__(select)
        self.bot = bot
        self.guild_id = guild_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
    ) -> PublicRewardSelect:
        bot = cast(commands.Bot, interaction.client)
        guild_id = int(match.group("guild_id"))
        return cls(
            bot,
            guild_id,
            item=cast(discord.ui.Select, item),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or interaction.guild.id != self.guild_id:
            await interaction.response.send_message(
                "Essa loja nao pertence a este servidor.",
                ephemeral=True,
            )
            return

        try:
            reward_id = int(self.item.values[0])
        except (IndexError, ValueError):
            await interaction.response.send_message(
                "Nao foi possivel identificar essa recompensa.",
                ephemeral=True,
            )
            return

        shop = cast(ShopService, self.bot.shop_service)  # type: ignore[attr-defined]
        reward = await shop.get_reward(reward_id)
        if reward is None or reward.guild_id != self.guild_id or not reward.is_active:
            await interaction.response.send_message(
                "Essa recompensa nao esta mais disponivel.",
                ephemeral=True,
            )
            return

        await _send_purchase_confirmation(self.bot, interaction, reward)


class PublicBalanceButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"^shop_panel:balance:(?P<guild_id>\d+)$",
):
    """Botao dinamico de consulta de pontos da loja fixa."""

    def __init__(self, bot: commands.Bot, guild_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label="Consultar Pontos",
                style=discord.ButtonStyle.secondary,
                custom_id=f"shop_panel:balance:{guild_id}",
                row=1,
            )
        )
        self.bot = bot
        self.guild_id = guild_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
    ) -> PublicBalanceButton:
        return cls(
            cast(commands.Bot, interaction.client),
            int(match.group("guild_id")),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or interaction.guild.id != self.guild_id:
            await interaction.response.send_message(
                "Essa loja nao pertence a este servidor.",
                ephemeral=True,
            )
            return

        await _send_wallet_embed(self.bot, interaction)


class PublicConvertActivityButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"^shop_panel:convert:(?P<guild_id>\d+)$",
):
    """Botao dinamico para converter atividade pela loja fixa."""

    def __init__(self, bot: commands.Bot, guild_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label="Converter atividade",
                style=discord.ButtonStyle.primary,
                custom_id=f"shop_panel:convert:{guild_id}",
                row=1,
            )
        )
        self.bot = bot
        self.guild_id = guild_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
    ) -> PublicConvertActivityButton:
        return cls(
            cast(commands.Bot, interaction.client),
            int(match.group("guild_id")),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or interaction.guild.id != self.guild_id:
            await interaction.response.send_message(
                "Essa loja nao pertence a este servidor.",
                ephemeral=True,
            )
            return

        await _convert_activity(self.bot, interaction)


class PublicLevelUpgradeButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"^shop_panel:level:(?P<guild_id>\d+)$",
):
    """Botão dinâmico para compra de upgrade de nível."""

    def __init__(self, bot: commands.Bot, guild_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label="Subir nível",
                style=discord.ButtonStyle.success,
                custom_id=f"shop_panel:level:{guild_id}",
                row=1,
            )
        )
        self.bot = bot
        self.guild_id = guild_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
    ) -> PublicLevelUpgradeButton:
        return cls(
            cast(commands.Bot, interaction.client),
            int(match.group("guild_id")),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or interaction.guild.id != self.guild_id:
            await interaction.response.send_message(
                "Essa loja nao pertence a este servidor.",
                ephemeral=True,
            )
            return

        await send_level_upgrade_confirmation(self.bot, interaction)


class PublicShopView(discord.ui.View):
    """View publica da loja fixa."""

    def __init__(
        self,
        bot: commands.Bot,
        guild_id: int,
        rewards: list[RewardItem],
        settings: GuildEconomySettings,
    ) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        if rewards:
            self.add_item(
                PublicRewardSelect(
                    bot,
                    guild_id,
                    rewards,
                    settings,
                )
            )
        self.add_item(PublicBalanceButton(bot, guild_id))
        self.add_item(PublicConvertActivityButton(bot, guild_id))
        self.add_item(PublicLevelUpgradeButton(bot, guild_id))


class ShopView(discord.ui.View):
    """View ephemeral da loja com select de recompensas."""

    def __init__(
        self,
        bot: commands.Bot,
        rewards: list[RewardItem],
        settings: GuildEconomySettings,
    ) -> None:
        super().__init__(timeout=300)
        self.bot = bot
        self.rewards = rewards
        if rewards:
            self.add_item(RewardSelect(bot, rewards, settings, row=0))

    @discord.ui.button(label="Ver saldo", style=discord.ButtonStyle.secondary, row=1)
    async def balance(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await _send_wallet_embed(self.bot, interaction)

    @discord.ui.button(
        label="Converter atividade",
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def convert_activity(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await _convert_activity(self.bot, interaction)

    @discord.ui.button(
        label="Minhas compras",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
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

    @discord.ui.button(
        label="Subir nível",
        style=discord.ButtonStyle.success,
        row=2,
    )
    async def level_upgrade(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await send_level_upgrade_confirmation(self.bot, interaction)


class RewardSelect(discord.ui.Select):
    """Select menu de recompensas."""

    def __init__(
        self,
        bot: commands.Bot,
        rewards: list[RewardItem],
        settings: GuildEconomySettings,
        *,
        custom_id: str | None = None,
        row: int | None = None,
    ) -> None:
        self.bot = bot
        self.reward_map = {str(reward.id): reward for reward in rewards[:25]}
        select_kwargs = {}
        if custom_id is not None:
            select_kwargs["custom_id"] = custom_id
        if row is not None:
            select_kwargs["row"] = row
        super().__init__(
            placeholder="Escolha uma recompensa",
            min_values=1,
            max_values=1,
            options=_build_reward_options(rewards, settings),
            **select_kwargs,
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

        await _send_purchase_confirmation(self.bot, interaction, reward)


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


class ConfirmLevelUpgradeView(discord.ui.View):
    """Confirmação de compra de upgrade de nível."""

    def __init__(self, bot: commands.Bot, level: int) -> None:
        super().__init__(timeout=120)
        self.bot = bot
        self.level = level

    @discord.ui.button(label="Confirmar upgrade", style=discord.ButtonStyle.success)
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if interaction.guild is None or not isinstance(
            interaction.user,
            discord.Member,
        ):
            await interaction.response.send_message(
                "A loja so funciona dentro de um servidor.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        shop = cast(ShopService, self.bot.shop_service)  # type: ignore[attr-defined]
        repository = self.bot.economy_repository  # type: ignore[attr-defined]
        settings = await repository.get_guild_settings(interaction.guild.id)
        current_role_ids = {role.id for role in interaction.user.roles}
        _, next_level, levels = await shop.get_next_level(
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            current_role_ids=current_role_ids,
        )
        if next_level is None or next_level.level != self.level:
            await interaction.followup.send(
                "Seu próximo nível mudou. Abra a confirmação de compra novamente.",
                ephemeral=True,
            )
            return

        role_error = _validate_level_role_change(
            bot=self.bot,
            guild=interaction.guild,
            member=interaction.user,
            target_level=next_level,
            levels=levels,
        )
        if role_error is not None:
            await interaction.followup.send(role_error, ephemeral=True)
            return

        result = await shop.purchase_level_upgrade(
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            level=self.level,
        )
        if result.status is LevelUpgradeStatus.SUCCESS and result.level_config:
            role_error = await _apply_level_role(
                bot=self.bot,
                guild=interaction.guild,
                member=interaction.user,
                target_level=result.level_config,
                levels=levels,
            )
            embed = discord.Embed(
                title="Nivel adquirido com sucesso",
                description=(
                    f"Você subiu para o **nível {result.level_config.level}**."
                ),
                color=discord.Color.green(),
            )
            embed.add_field(
                name="Cargo recebido",
                value=f"<@&{result.level_config.role_id}>",
                inline=False,
            )
            embed.add_field(
                name="Pontos gastos",
                value=format_points(
                    result.level_config.price,
                    settings.currency_name,
                ),
                inline=True,
            )
            embed.add_field(
                name="Saldo atual",
                value=format_points(result.balance_after, settings.currency_name),
                inline=True,
            )
            if role_error is not None:
                embed.add_field(
                    name="Atenção",
                    value=(
                        "A compra foi registrada, mas o cargo não foi aplicado: "
                        f"{role_error}"
                    ),
                    inline=False,
                )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        messages = {
            LevelUpgradeStatus.LEVEL_NOT_FOUND: "Esse nível não existe mais.",
            LevelUpgradeStatus.LEVEL_INACTIVE: "Esse nível está inativo.",
            LevelUpgradeStatus.ALREADY_OWNED: "Você já comprou esse nível.",
            LevelUpgradeStatus.INSUFFICIENT_BALANCE: (
                f"Saldo insuficiente. Faltam "
                f"{format_points(result.missing_points, settings.currency_name)}."
            ),
        }
        await interaction.followup.send(
            messages.get(result.status, "Não foi possível comprar esse nível."),
            ephemeral=True,
        )

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_message("Upgrade cancelado.", ephemeral=True)
