from __future__ import annotations

from typing import cast

import discord
from discord.ext import commands

from app.services.activity_service import ActivityService
from app.services.economy_service import EconomyService, EconomyValidationError
from app.utils.embeds import (
    build_activity_conversion_embed,
    build_savings_embed,
    build_transaction_history_embed,
    build_wallet_embed,
    format_points,
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
        label="Transferir pontos",
        style=discord.ButtonStyle.secondary,
        custom_id="economy_panel:transfer",
    )
    async def transfer_points(
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

        await interaction.response.send_message(
            (
                "Use `/transferir usuario: valor:` para transferir pontos.\n"
                "No campo `usuario`, selecione ou mencione a pessoa pelo Discord."
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Poupança",
        style=discord.ButtonStyle.secondary,
        custom_id="economy_panel:savings",
    )
    async def savings(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este painel só funciona dentro de um servidor.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        economy = cast(EconomyService, self.bot.economy_service)  # type: ignore[attr-defined]
        repository = self.bot.economy_repository  # type: ignore[attr-defined]
        settings = await repository.get_guild_settings(interaction.guild.id)
        overview = await economy.get_savings_overview(
            interaction.guild.id,
            interaction.user.id,
        )
        await interaction.followup.send(
            embed=build_savings_embed(overview, settings),
            view=SavingsPanelView(self.bot),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Histórico",
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


class SavingsPanelView(discord.ui.View):
    """Controles efemeros da poupanca."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(timeout=180)
        self.bot = bot

    @discord.ui.button(label="Depositar", style=discord.ButtonStyle.primary)
    async def deposit(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_modal(
            SavingsAmountModal(self.bot, action="deposit")
        )

    @discord.ui.button(label="Sacar", style=discord.ButtonStyle.secondary)
    async def withdraw(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_modal(
            SavingsAmountModal(self.bot, action="withdraw")
        )

    @discord.ui.button(label="Atualizar", style=discord.ButtonStyle.secondary)
    async def refresh(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este painel só funciona dentro de um servidor.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        economy = cast(EconomyService, self.bot.economy_service)  # type: ignore[attr-defined]
        repository = self.bot.economy_repository  # type: ignore[attr-defined]
        settings = await repository.get_guild_settings(interaction.guild.id)
        overview = await economy.get_savings_overview(
            interaction.guild.id,
            interaction.user.id,
        )
        await interaction.followup.send(
            embed=build_savings_embed(overview, settings),
            view=SavingsPanelView(self.bot),
            ephemeral=True,
        )


class SavingsAmountModal(discord.ui.Modal):
    """Modal para depositar ou sacar da poupanca."""

    amount = discord.ui.TextInput(
        label="Valor",
        placeholder="Ex.: 500",
        min_length=1,
        max_length=16,
    )

    def __init__(self, bot: commands.Bot, *, action: str) -> None:
        title = "Depositar na poupança" if action == "deposit" else "Sacar poupança"
        super().__init__(title=title)
        self.bot = bot
        self.action = action

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este painel só funciona dentro de um servidor.",
                ephemeral=True,
            )
            return

        try:
            amount = _parse_amount(str(self.amount.value))
        except ValueError:
            await interaction.response.send_message(
                "Informe um valor inteiro válido.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        economy = cast(EconomyService, self.bot.economy_service)  # type: ignore[attr-defined]
        repository = self.bot.economy_repository  # type: ignore[attr-defined]
        settings = await repository.get_guild_settings(interaction.guild.id)
        try:
            if self.action == "deposit":
                result = await economy.deposit_savings(
                    guild_id=interaction.guild.id,
                    user_id=interaction.user.id,
                    amount=amount,
                )
                description = (
                    "Depósito realizado com sucesso. Esse valor ficará preso por "
                    "24 horas antes de poder ser sacado."
                )
                title = "Poupança atualizada"
            else:
                result = await economy.withdraw_savings(
                    guild_id=interaction.guild.id,
                    user_id=interaction.user.id,
                    amount=amount,
                )
                description = "Saque realizado com sucesso."
                title = "Poupança atualizada"
        except EconomyValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        embed = build_savings_embed(
            result.overview,
            settings,
            title=title,
            description=description,
        )
        embed.add_field(
            name="Valor movimentado",
            value=format_points(result.amount, settings.currency_name),
            inline=True,
        )
        await interaction.followup.send(
            embed=embed,
            view=SavingsPanelView(self.bot),
            ephemeral=True,
        )


def _parse_amount(value: str) -> int:
    normalized = value.strip().replace(".", "").replace(" ", "")
    if not normalized.isdigit():
        raise ValueError("invalid amount")
    return int(normalized)
