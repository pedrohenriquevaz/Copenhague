from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from app.models.economy import EconomyTransactionType, UserWallet
from app.utils.embeds import format_points
from app.utils.permissions import has_manage_guild


class AdminPanelCog(commands.Cog):
    """Painel administrativo de maturidade do bot."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="admin_panel",
        description="Mostra um painel central com status e atalhos administrativos.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def admin_panel(self, interaction: discord.Interaction) -> None:
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
        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        economy_summary = await self.bot.economy_repository.get_admin_summary(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        match_summary = await self.bot.match_bet_repository.get_admin_summary(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        game_summary = await self.bot.game_progress_repository.get_admin_summary(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        season = await self.bot.game_progress_service.get_seasonal_theme(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        jackpot = await self.bot.game_progress_service.get_scratch_jackpot(  # type: ignore[attr-defined]
            interaction.guild.id
        )

        wallets = economy_summary["wallets"]
        savings = economy_summary.get("savings", {})
        shop = economy_summary["shop"]
        wallet_balance = int(wallets["balance"])
        savings_balance = int(savings.get("balance", 0))
        circulating = format_points(
            wallet_balance + savings_balance,
            settings.currency_name,
        )
        savings_formatted = format_points(savings_balance, settings.currency_name)
        admin_limit = format_points(
            settings.max_admin_grant_per_use,
            settings.currency_name,
        )
        max_bet = format_points(settings.casino_max_bet, settings.currency_name)
        daily_profit_limit = (
            "Desativado"
            if (
                not settings.casino_limiters_enabled
                or settings.casino_daily_profit_limit <= 0
            )
            else format_points(
                settings.casino_daily_profit_limit,
                settings.currency_name,
            )
        )
        jackpot_amount = format_points(jackpot.amount, settings.currency_name)
        limiters_status = (
            "Ativados" if settings.casino_limiters_enabled else "Desativados"
        )

        embed = discord.Embed(
            title="Painel administrativo",
            description="Visao rapida de operacao, configuracao e modulos ativos.",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Economia",
            value=(
                f"Moeda: **{settings.currency_name}**\n"
                f"Carteiras: **{wallets['count']}**\n"
                f"Poupança: **{savings_formatted}**\n"
                f"Saldo circulante: **{circulating}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Configuracao",
            value=(
                f"Call: **{settings.voice_points_per_minute}/min**\n"
                f"Mensagem: **{settings.message_points}**\n"
                f"Limite admin: **{admin_limit}**\n"
                f"Aposta maxima: **{max_bet}**\n"
                f"Limitadores: **{limiters_status}**\n"
                f"Teto diario: **{daily_profit_limit}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Operacao",
            value=(
                f"Loja ativa: **{shop['rewards_active']}** item(ns)\n"
                f"Bets ativas: **{match_summary['active_matches']}**\n"
                f"Corridas abertas: **{game_summary['open_races']}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Eventos e temporadas",
            value=(
                f"Tema sazonal: **{season.theme.value}**\n"
                f"Jackpot raspadinha: **{jackpot_amount}**\n"
                f"Conquistas liberadas: **{game_summary['unlocked_achievements']}**"
            ),
            inline=False,
        )
        embed.add_field(
            name="Comandos de manutencao",
            value=(
                "`/economy_config` configura taxas, canais e cargo gerente.\n"
                "`/economy_limitadores` liga ou desliga os freios dos jogos.\n"
                "`/admin_analytics` mostra indicadores da economia.\n"
                "`/reward_create`, `/reward_update`, `/reward_remove` "
                "gerenciam a loja.\n"
                "`/bet_criar`, `/bet_odds`, `/bet_encerrar` gerenciam bets."
            ),
            inline=False,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="admin_analytics",
        description="Mostra analytics de economia, loja, jogos e apostas.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def admin_analytics(self, interaction: discord.Interaction) -> None:
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
        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        economy_summary = await self.bot.economy_repository.get_admin_summary(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        match_summary = await self.bot.match_bet_repository.get_admin_summary(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        game_summary = await self.bot.game_progress_repository.get_admin_summary(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        top_wallets = await self.bot.economy_repository.list_top_wallets(  # type: ignore[attr-defined]
            interaction.guild.id,
            limit=5,
        )

        activity = economy_summary["activity"]
        shop = economy_summary["shop"]
        shop_volume = format_points(shop["purchase_volume"], settings.currency_name)
        match_volume = format_points(
            match_summary["total_stake"],
            settings.currency_name,
        )
        race_volume = format_points(
            game_summary["race_stake"],
            settings.currency_name,
        )

        embed = discord.Embed(
            title="Analytics administrativo",
            description="Indicadores acumulados do servidor.",
            color=discord.Color.green(),
        )
        embed.add_field(
            name="Pontos",
            value=_format_points_flow(economy_summary, settings.currency_name),
            inline=False,
        )
        embed.add_field(
            name="Atividade",
            value=(
                f"Mensagens registradas: **{activity['messages']}**\n"
                f"Usuarios com mensagens: **{activity['message_users']}**\n"
                "Tempo em call fechado: "
                f"**{_format_duration(activity['voice_seconds'])}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Loja",
            value=(
                f"Itens ativos: **{shop['rewards_active']}**\n"
                f"Itens inativos: **{shop['rewards_inactive']}**\n"
                f"Compras: **{shop['purchase_count']}**\n"
                f"Volume: **{shop_volume}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Cassino",
            value=_format_casino_flow(economy_summary, settings.currency_name),
            inline=True,
        )
        embed.add_field(
            name="Bets",
            value=(
                f"Partidas: **{match_summary['total_matches']}**\n"
                f"Ativas: **{match_summary['active_matches']}**\n"
                f"Tickets: **{match_summary['total_tickets']}**\n"
                f"Volume apostado: **{match_volume}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Eventos",
            value=(
                f"Corridas: **{game_summary['total_races']}**\n"
                f"Apostas em corridas: **{game_summary['race_bets']}**\n"
                f"Volume corridas: **{race_volume}**\n"
                f"Conquistas: **{game_summary['unlocked_achievements']}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Ranking de saldo",
            value=_format_wallets(top_wallets, settings.currency_name),
            inline=False,
        )
        embed.set_footer(
            text=f"Auditorias registradas: {economy_summary['audit']['count']}"
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


def _format_points_flow(summary: dict, currency_name: str) -> str:
    transactions = summary["transactions"]
    emitted = sum(
        _tx_in(transactions, transaction_type)
        for transaction_type in (
            EconomyTransactionType.ACTIVITY_CONVERSION,
            EconomyTransactionType.ADMIN_GIVE,
            EconomyTransactionType.BOT_REWARD,
            EconomyTransactionType.SYSTEM_ADJUSTMENT,
            EconomyTransactionType.REFUND,
            EconomyTransactionType.MATCH_BET_PAYOUT,
        )
    )
    removed = _tx_out(transactions, EconomyTransactionType.ADMIN_REMOVE)
    spent = summary["wallets"]["spent"]
    savings = summary.get("savings", {})
    savings_balance = int(savings.get("balance", 0))
    savings_interest = int(savings.get("interest_earned", 0))
    emitted += savings_interest
    balance = summary["wallets"]["balance"] + savings_balance
    return (
        f"Emitidos: **{format_points(emitted, currency_name)}**\n"
        f"Removidos por admin: **{format_points(removed, currency_name)}**\n"
        f"Gastos totais: **{format_points(spent, currency_name)}**\n"
        f"Em poupança: **{format_points(savings_balance, currency_name)}**\n"
        f"Juros da poupança: **{format_points(savings_interest, currency_name)}**\n"
        f"Circulando: **{format_points(balance, currency_name)}**"
    )


def _format_casino_flow(summary: dict, currency_name: str) -> str:
    transactions = summary["transactions"]
    bets = _tx_out(transactions, EconomyTransactionType.CASINO_BET)
    payouts = _tx_in(transactions, EconomyTransactionType.CASINO_PAYOUT)
    refunds = _tx_in(transactions, EconomyTransactionType.REFUND)
    return (
        f"Apostado: **{format_points(bets, currency_name)}**\n"
        f"Premiado: **{format_points(payouts, currency_name)}**\n"
        f"Reembolsado: **{format_points(refunds, currency_name)}**"
    )


def _tx_in(transactions: dict, transaction_type: EconomyTransactionType) -> int:
    return int(transactions.get(transaction_type.value, {}).get("in", 0))


def _tx_out(transactions: dict, transaction_type: EconomyTransactionType) -> int:
    return int(transactions.get(transaction_type.value, {}).get("out", 0))


def _format_wallets(wallets: list[UserWallet], currency_name: str) -> str:
    if not wallets:
        return "Nenhuma carteira registrada."
    return "\n".join(
        f"**#{index}** <@{wallet.user_id}> - "
        f"{format_points(wallet.balance, currency_name)}"
        for index, wallet in enumerate(wallets, start=1)
    )


def _format_duration(seconds: int) -> str:
    minutes = seconds // 60
    hours, remaining_minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {remaining_minutes}min"
    return f"{remaining_minutes}min"


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminPanelCog(bot))
