from __future__ import annotations

from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from app.models.economy import UserProfileResetResult
from app.services.economy_service import EconomyService, EconomyValidationError
from app.utils.embeds import format_points
from app.utils.permissions import has_administrator, has_manage_guild, has_role


class EconomyAdminCog(commands.Cog):
    """Comandos administrativos da economia."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.service = cast(EconomyService, bot.economy_service)  # type: ignore[attr-defined]

    async def _can_manage_economy(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            return False
        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        return has_manage_guild(interaction.user) or has_role(
            interaction.user,
            settings.economy_manager_role_id,
        )

    @app_commands.command(
        name="give_points",
        description="Concede pontos manualmente a um usuario.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def give_points(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        quantidade: int,
        motivo: str,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return
        if usuario.bot:
            await interaction.response.send_message(
                "Nao e possivel conceder pontos a bots.",
                ephemeral=True,
            )
            return
        if not await self._can_manage_economy(interaction):
            await interaction.response.send_message(
                "Voce nao tem permissao para usar esse comando.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        try:
            result = await self.service.give_points(
                guild_id=interaction.guild.id,
                user_id=usuario.id,
                actor_id=interaction.user.id,
                amount=quantidade,
                reason=motivo,
            )
        except EconomyValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        formatted_balance = format_points(result.wallet.balance, settings.currency_name)
        await interaction.followup.send(
            (
                "Pontos concedidos com sucesso.\n\n"
                f"Usuario: {usuario.mention}\n"
                f"Quantidade: {format_points(quantidade, settings.currency_name)}\n"
                f"Motivo: {motivo}\n"
                f"Novo saldo: {formatted_balance}"
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="give_points_role",
        description="Concede pontos a todos os usuarios de um cargo.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        cargo="Cargo que recebera os pontos.",
        quantidade="Quantidade de pontos para cada usuario do cargo.",
        motivo="Motivo registrado no historico e auditoria.",
    )
    async def give_points_role(
        self,
        interaction: discord.Interaction,
        cargo: discord.Role,
        quantidade: int,
        motivo: str,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return
        if cargo.is_default():
            await interaction.response.send_message(
                "Informe um cargo especifico. O @everyone nao e aceito aqui.",
                ephemeral=True,
            )
            return
        if not await self._can_manage_economy(interaction):
            await interaction.response.send_message(
                "Voce nao tem permissao para usar esse comando.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        members = await self._members_for_role(interaction.guild, cargo)
        if not members:
            await interaction.followup.send(
                (
                    "Nao encontrei usuarios elegiveis nesse cargo.\n"
                    "Se o cargo tem membros, verifique se o Members Intent esta "
                    "habilitado no portal do Discord e no `.env` do bot."
                ),
                ephemeral=True,
            )
            return

        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        try:
            results = await self.service.give_points_bulk(
                guild_id=interaction.guild.id,
                user_ids=[member.id for member in members],
                actor_id=interaction.user.id,
                amount=quantidade,
                reason=motivo,
                metadata={"role_id": cargo.id, "role_name": cargo.name},
            )
        except EconomyValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        total = quantidade * len(results)
        await interaction.followup.send(
            (
                "Distribuicao concluida com sucesso.\n\n"
                f"Cargo: {cargo.mention}\n"
                f"Usuarios contemplados: **{len(results)}**\n"
                f"Quantidade por usuario: "
                f"{format_points(quantidade, settings.currency_name)}\n"
                f"Total distribuido: {format_points(total, settings.currency_name)}\n"
                f"Motivo: {motivo}"
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="economy_config",
        description="Atualiza configuracoes de economia do servidor.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        moeda="Nome exibido para a moeda do servidor.",
        pontos_call="Pontos por minuto em call.",
        pontos_mensagem="Pontos por mensagem.",
        min_call_segundos="Minimo de segundos em call para converter.",
        min_mensagens="Minimo de mensagens para converter.",
        ignorar_afk="Ignora o canal AFK do servidor.",
        contar_call_sozinho="Conta tempo em call mesmo quando o usuario esta sozinho.",
        limite_admin="Limite maximo por uso em comandos administrativos.",
        limite_aposta="Limite maximo por aposta nos jogos.",
        teto_lucro_diario="Teto diario de lucro em jogos. Use 0 para desativar.",
        min_cara_coroa="Aposta minima para cara ou coroa.",
        min_dados="Aposta minima para dados.",
        min_slot="Aposta minima para slot.",
        min_roleta="Aposta minima para roleta.",
        min_corrida_mascote="Aposta minima para corrida de mascotes.",
        min_duelo="Aposta minima para duelos.",
        min_blackjack="Aposta minima para BlackJack.",
        min_raspadinha="Custo minimo permitido para comprar raspadinhas.",
        min_corrida_coletiva="Aposta minima para corrida coletiva.",
        min_bet_partidas="Aposta minima para bets de partidas.",
        cargo_gerente="Cargo que tambem pode gerenciar economia.",
        canal_economia="Canal principal do painel de economia.",
        canal_loja="Canal principal da loja.",
        canal_logs="Canal de logs da staff.",
    )
    async def economy_config(
        self,
        interaction: discord.Interaction,
        moeda: str | None = None,
        pontos_call: int | None = None,
        pontos_mensagem: int | None = None,
        min_call_segundos: int | None = None,
        min_mensagens: int | None = None,
        ignorar_afk: bool | None = None,
        contar_call_sozinho: bool | None = None,
        limite_admin: int | None = None,
        limite_aposta: int | None = None,
        teto_lucro_diario: int | None = None,
        min_cara_coroa: int | None = None,
        min_dados: int | None = None,
        min_slot: int | None = None,
        min_roleta: int | None = None,
        min_corrida_mascote: int | None = None,
        min_duelo: int | None = None,
        min_blackjack: int | None = None,
        min_raspadinha: int | None = None,
        min_corrida_coletiva: int | None = None,
        min_bet_partidas: int | None = None,
        cargo_gerente: discord.Role | None = None,
        canal_economia: discord.TextChannel | discord.Thread | None = None,
        canal_loja: discord.TextChannel | discord.Thread | None = None,
        canal_logs: discord.TextChannel | discord.Thread | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return
        if not await self._can_manage_economy(interaction):
            await interaction.response.send_message(
                "Voce nao tem permissao para usar esse comando.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            settings = await self.service.configure_settings(
                guild_id=interaction.guild.id,
                actor_id=interaction.user.id,
                currency_name=moeda,
                voice_points_per_minute=pontos_call,
                message_points=pontos_mensagem,
                min_voice_seconds_to_claim=min_call_segundos,
                min_messages_to_claim=min_mensagens,
                ignore_afk_channel=ignorar_afk,
                count_voice_when_alone=contar_call_sozinho,
                max_admin_grant_per_use=limite_admin,
                casino_max_bet=limite_aposta,
                casino_daily_profit_limit=teto_lucro_diario,
                casino_min_bet_coin_flip=min_cara_coroa,
                casino_min_bet_dice=min_dados,
                casino_min_bet_slot=min_slot,
                casino_min_bet_roulette=min_roleta,
                casino_min_bet_mascot_race=min_corrida_mascote,
                casino_min_bet_duel=min_duelo,
                casino_min_bet_blackjack=min_blackjack,
                casino_min_bet_scratch_card=min_raspadinha,
                casino_min_bet_collective_race=min_corrida_coletiva,
                casino_min_bet_match_bet=min_bet_partidas,
                economy_manager_role_id=cargo_gerente.id if cargo_gerente else None,
                economy_channel_id=canal_economia.id if canal_economia else None,
                shop_channel_id=canal_loja.id if canal_loja else None,
                staff_log_channel_id=canal_logs.id if canal_logs else None,
            )
        except EconomyValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        await interaction.followup.send(
            embed=_build_economy_config_embed(settings),
            ephemeral=True,
        )

    @app_commands.command(
        name="economy_limitadores",
        description="Liga ou desliga os limitadores de lucro dos jogos.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        ativo=(
            "Ativa teto diario, dificuldade dinamica e limite diario de raspadinhas."
        )
    )
    async def economy_limitadores(
        self,
        interaction: discord.Interaction,
        ativo: bool,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return
        if not await self._can_manage_economy(interaction):
            await interaction.response.send_message(
                "Voce nao tem permissao para usar esse comando.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = await self.service.configure_settings(
            guild_id=interaction.guild.id,
            actor_id=interaction.user.id,
            casino_limiters_enabled=ativo,
        )
        status = "ativados" if settings.casino_limiters_enabled else "desativados"
        await interaction.followup.send(
            content=f"Limitadores dos jogos {status}.",
            embed=_build_economy_config_embed(settings),
            ephemeral=True,
        )

    @app_commands.command(
        name="remove_points",
        description="Remove pontos manualmente de um usuario.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def remove_points(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        quantidade: int,
        motivo: str,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return
        if usuario.bot:
            await interaction.response.send_message(
                "Nao e possivel remover pontos de bots.",
                ephemeral=True,
            )
            return
        if not has_administrator(interaction.user):
            await interaction.response.send_message(
                "Voce nao tem permissao para usar esse comando.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        try:
            result = await self.service.remove_points(
                guild_id=interaction.guild.id,
                user_id=usuario.id,
                actor_id=interaction.user.id,
                amount=quantidade,
                reason=motivo,
            )
        except EconomyValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        formatted_balance = format_points(result.wallet.balance, settings.currency_name)
        await interaction.followup.send(
            (
                "Pontos removidos com sucesso.\n\n"
                f"Usuario: {usuario.mention}\n"
                f"Quantidade: {format_points(quantidade, settings.currency_name)}\n"
                f"Motivo: {motivo}\n"
                f"Novo saldo: {formatted_balance}"
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="reset_profile",
        description="Reseta economia, jogos e conquistas de um usuario.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        usuario="Usuario que tera o perfil resetado.",
        motivo="Motivo registrado na auditoria.",
        confirmar="Marque como verdadeiro para confirmar o reset.",
    )
    async def reset_profile(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        motivo: str,
        confirmar: bool,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return
        if usuario.bot:
            await interaction.response.send_message(
                "Nao e possivel resetar o perfil de bots.",
                ephemeral=True,
            )
            return
        if not confirmar:
            await interaction.response.send_message(
                "Marque `confirmar` como verdadeiro para executar o reset.",
                ephemeral=True,
            )
            return
        if not has_administrator(interaction.user):
            await interaction.response.send_message(
                "Voce nao tem permissao para usar esse comando.",
                ephemeral=True,
            )
            return

        reason = motivo.strip()
        if not reason:
            await interaction.response.send_message(
                "Informe um motivo para a operacao.",
                ephemeral=True,
            )
            return
        if len(reason) > 500:
            await interaction.response.send_message(
                "O motivo nao pode passar de 500 caracteres.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        guild_id = interaction.guild.id
        user_id = usuario.id
        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            guild_id
        )

        related_counts: dict[str, int] = {}
        progress_counts = await self.bot.game_progress_repository.reset_user_profile(  # type: ignore[attr-defined]
            guild_id,
            user_id,
        )
        related_counts.update(progress_counts)
        match_counts = await self.bot.match_bet_repository.reset_user_profile(  # type: ignore[attr-defined]
            guild_id,
            user_id,
        )
        related_counts.update(match_counts)
        await self.bot.casino_service.reset_user_state(guild_id, user_id)  # type: ignore[attr-defined]
        await self.bot.blackjack_service.reset_user_state(guild_id, user_id)  # type: ignore[attr-defined]

        try:
            result = await self.service.reset_user_profile(
                guild_id=guild_id,
                user_id=user_id,
                actor_id=interaction.user.id,
                reason=reason,
                related_counts=related_counts,
            )
        except EconomyValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        wallet_before = result.wallet_before
        previous_balance = wallet_before.balance if wallet_before else 0
        previous_earned = wallet_before.total_earned if wallet_before else 0
        previous_spent = wallet_before.total_spent if wallet_before else 0
        await interaction.followup.send(
            (
                "Perfil resetado com sucesso.\n\n"
                f"Usuario: {usuario.mention}\n"
                f"Saldo anterior: "
                f"{format_points(previous_balance, settings.currency_name)}\n"
                f"Total ganho anterior: "
                f"{format_points(previous_earned, settings.currency_name)}\n"
                f"Total gasto anterior: "
                f"{format_points(previous_spent, settings.currency_name)}\n"
                f"Motivo: {reason}\n\n"
                "Registros removidos:\n"
                f"{_format_reset_counts(result, related_counts)}"
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="economy_status",
        description="Mostra a configuracao atual da economia.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def economy_status(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado em servidores.",
                ephemeral=True,
            )
            return
        if not await self._can_manage_economy(interaction):
            await interaction.response.send_message(
                "Voce nao tem permissao para usar esse comando.",
                ephemeral=True,
            )
            return

        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        embed = discord.Embed(title="Status da economia", color=discord.Color.green())
        embed.add_field(name="Moeda", value=settings.currency_name, inline=True)
        embed.add_field(
            name="Provider",
            value=settings.activity_provider,
            inline=True,
        )
        embed.add_field(
            name="Taxa call",
            value=f"{settings.voice_points_per_minute}/min",
            inline=True,
        )
        embed.add_field(
            name="Taxa mensagem",
            value=str(settings.message_points),
            inline=True,
        )
        embed.add_field(
            name="Limite admin",
            value=format_points(
                settings.max_admin_grant_per_use,
                settings.currency_name,
            ),
            inline=True,
        )
        embed.add_field(
            name="Limite de aposta",
            value=format_points(settings.casino_max_bet, settings.currency_name),
            inline=True,
        )
        daily_profit = (
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
        embed.add_field(
            name="Teto de lucro diario",
            value=daily_profit,
            inline=True,
        )
        embed.add_field(
            name="Limitadores",
            value="Ativados" if settings.casino_limiters_enabled else "Desativados",
            inline=True,
        )
        embed.add_field(
            name="Apostas minimas",
            value=_format_min_bets(settings),
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @staticmethod
    async def _members_for_role(
        guild: discord.Guild,
        role: discord.Role,
    ) -> list[discord.Member]:
        if not guild.chunked:
            try:
                await guild.chunk(cache=True)
            except discord.DiscordException:
                pass

        return [
            member for member in role.members if not member.bot and role in member.roles
        ]


def _build_economy_config_embed(settings) -> discord.Embed:
    embed = discord.Embed(
        title="Configuracao da economia atualizada",
        color=discord.Color.green(),
    )
    embed.add_field(name="Moeda", value=settings.currency_name, inline=True)
    embed.add_field(
        name="Call",
        value=f"{settings.voice_points_per_minute}/min",
        inline=True,
    )
    embed.add_field(
        name="Mensagem",
        value=str(settings.message_points),
        inline=True,
    )
    embed.add_field(
        name="Minimos",
        value=(
            f"Call: {settings.min_voice_seconds_to_claim}s\n"
            f"Mensagens: {settings.min_messages_to_claim}"
        ),
        inline=True,
    )
    embed.add_field(
        name="Regras de voz",
        value=(
            f"AFK ignorado: {'sim' if settings.ignore_afk_channel else 'nao'}\n"
            "Conta sozinho: "
            f"{'sim' if settings.count_voice_when_alone else 'nao'}"
        ),
        inline=True,
    )
    embed.add_field(
        name="Limite admin",
        value=format_points(
            settings.max_admin_grant_per_use,
            settings.currency_name,
        ),
        inline=True,
    )
    embed.add_field(
        name="Jogos",
        value=(
            f"Aposta maxima: "
            f"{format_points(settings.casino_max_bet, settings.currency_name)}\n"
            "Limitadores: "
            f"{_format_limiters_status(settings)}\n"
            "Teto diario: "
            f"{_format_daily_profit_limit(settings)}"
        ),
        inline=True,
    )
    embed.add_field(
        name="Apostas minimas",
        value=_format_min_bets(settings),
        inline=False,
    )
    embed.add_field(
        name="Canais",
        value=(
            f"Economia: {_format_channel(settings.economy_channel_id)}\n"
            f"Loja: {_format_channel(settings.shop_channel_id)}\n"
            f"Logs: {_format_channel(settings.staff_log_channel_id)}"
        ),
        inline=False,
    )
    embed.add_field(
        name="Cargo gerente",
        value=(
            f"<@&{settings.economy_manager_role_id}>"
            if settings.economy_manager_role_id
            else "Nao configurado"
        ),
        inline=False,
    )
    return embed


def _format_channel(channel_id: int | None) -> str:
    return f"<#{channel_id}>" if channel_id else "Nao configurado"


def _format_daily_profit_limit(settings) -> str:
    if not settings.casino_limiters_enabled:
        return "Desativado pelos limitadores"
    if settings.casino_daily_profit_limit <= 0:
        return "Desativado"
    return format_points(settings.casino_daily_profit_limit, settings.currency_name)


def _format_limiters_status(settings) -> str:
    return "Ativados" if settings.casino_limiters_enabled else "Desativados"


def _format_min_bets(settings) -> str:
    items = (
        ("Cara/coroa", settings.casino_min_bet_coin_flip),
        ("Dados", settings.casino_min_bet_dice),
        ("Slot", settings.casino_min_bet_slot),
        ("Roleta", settings.casino_min_bet_roulette),
        ("Mascotes", settings.casino_min_bet_mascot_race),
        ("Duelo", settings.casino_min_bet_duel),
        ("BlackJack", settings.casino_min_bet_blackjack),
        ("Raspadinha", settings.casino_min_bet_scratch_card),
        ("Corrida coletiva", settings.casino_min_bet_collective_race),
        ("Bets partidas", settings.casino_min_bet_match_bet),
    )
    return "\n".join(
        f"{label}: {format_points(value, settings.currency_name)}"
        for label, value in items
    )


def _format_reset_counts(
    result: UserProfileResetResult,
    related_counts: dict[str, int],
) -> str:
    counts = {
        "Carteiras": result.deleted_wallets,
        "Transacoes": result.deleted_transactions,
        "Compras da loja": result.deleted_purchases,
        "Resgates da economia": result.deleted_reward_claims,
        "Cursores de atividade": result.deleted_activity_cursors,
        "Mensagens de atividade": result.deleted_message_stats,
        "Sessoes de voz": result.deleted_voice_sessions,
        "Conquistas": related_counts.get("achievements", 0),
        "Apostas em corridas": related_counts.get("collective_race_bets", 0),
        "Tickets de partidas": related_counts.get("match_bet_tickets", 0),
    }
    lines = [f"- {label}: **{count}**" for label, count in counts.items() if count]
    if not lines:
        return "- Nenhum registro antigo encontrado."
    return "\n".join(lines)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EconomyAdminCog(bot))
