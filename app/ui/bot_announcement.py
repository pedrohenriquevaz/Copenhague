from __future__ import annotations

from typing import cast

import discord
from discord.ext import commands

from app.services.economy_service import EconomyService, EconomyValidationError
from app.utils.embeds import format_points


def build_bot_announcement_embed(*, image_url: str | None = None) -> discord.Embed:
    """Cria a embed publica de apresentacao do bot."""

    embed = discord.Embed(
        title="Central do Bot",
        description=(
            "Participe do servidor, acumule pontos e use-os na loja, em jogos, "
            "apostas saudaveis de campeonatos e eventos da comunidade.\n\n"
            "Use os botoes abaixo para ver os comandos, resgatar seu presente "
            "diario ou pegar seu pacote inicial."
        ),
        color=discord.Color.gold(),
    )
    embed.add_field(
        name="Como ganhar pontos",
        value=(
            "Converse nos chats, participe de calls, resgate recompensas do painel "
            "e acompanhe eventos especiais."
        ),
        inline=False,
    )
    embed.add_field(
        name="Onde usar",
        value=(
            "Loja de recompensas, cassino de pontos, raspadinhas, corridas, duelos "
            "e bets de campeonatos."
        ),
        inline=False,
    )
    if image_url:
        embed.set_image(url=image_url)
    return embed


def build_user_commands_embed() -> discord.Embed:
    """Documentacao resumida dos comandos livres para usuarios."""

    embed = discord.Embed(
        title="Ajuda e Comandos",
        description=(
            "Estes sao os principais comandos livres para usuarios. "
            "Comandos administrativos ficam fora desta lista."
        ),
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="Economia",
        value=(
            "`/saldo` consulta seus pontos.\n"
            "`/perfil` mostra seu perfil economico.\n"
            "`/historico` lista transacoes recentes.\n"
            "`/ranking` mostra o ranking de pontos.\n"
            "`/converter_atividade` transforma atividade em pontos."
        ),
        inline=False,
    )
    embed.add_field(
        name="Loja",
        value="`/loja` abre a loja para trocar pontos por recompensas.",
        inline=False,
    )
    embed.add_field(
        name="Jogos",
        value=(
            "`/blackjack`, `/cara_coroa`, `/dado`, `/slot`, `/roleta`, "
            "`/duelo`, `/corrida` e `/raspadinha`."
        ),
        inline=False,
    )
    embed.add_field(
        name="Progresso",
        value=(
            "`/jogos_perfil`, `/jogos_ranking`, `/jogos_historico`, "
            "`/conquistas`, `/jackpot` e `/evento_sazonal`."
        ),
        inline=False,
    )
    embed.add_field(
        name="Eventos e apostas",
        value=(
            "Quando houver bolao, bet ou corrida coletiva publicados no chat, "
            "use os botoes da propria embed para participar."
        ),
        inline=False,
    )
    embed.add_field(
        name="Painel",
        value=(
            "`Presente diario` pode ser resgatado uma vez por dia.\n"
            "`Pacote inicial` pode ser resgatado uma unica vez por usuario."
        ),
        inline=False,
    )
    embed.add_field(
        name="Utilidade",
        value="`/ping` mostra a latencia atual do bot.",
        inline=False,
    )
    return embed


def build_reward_claim_embed(
    *,
    title: str,
    amount: int,
    balance: int,
    currency_name: str,
) -> discord.Embed:
    embed = discord.Embed(title=title, color=discord.Color.green())
    embed.add_field(
        name="Voce recebeu",
        value=format_points(amount, currency_name),
        inline=True,
    )
    embed.add_field(
        name="Saldo atual",
        value=format_points(balance, currency_name),
        inline=True,
    )
    return embed


class BotAnnouncementView(discord.ui.View):
    """Botoes persistentes do anuncio do bot."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Ajuda/comandos",
        style=discord.ButtonStyle.primary,
        custom_id="bot_announcement:help",
    )
    async def help_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_message(
            embed=build_user_commands_embed(),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Presente diario",
        style=discord.ButtonStyle.success,
        custom_id="bot_announcement:daily_gift",
    )
    async def daily_gift_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self._claim_reward(
            interaction,
            claim="daily",
            title="Presente diario resgatado",
        )

    @discord.ui.button(
        label="Pacote inicial",
        style=discord.ButtonStyle.secondary,
        custom_id="bot_announcement:starter_pack",
    )
    async def starter_pack_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self._claim_reward(
            interaction,
            claim="starter",
            title="Pacote inicial resgatado",
        )

    async def _claim_reward(
        self,
        interaction: discord.Interaction,
        *,
        claim: str,
        title: str,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este painel so pode ser usado em servidores.",
                ephemeral=True,
            )
            return
        if interaction.user.bot:
            await interaction.response.send_message(
                "Bots nao podem resgatar recompensas.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        service = cast(EconomyService, self.bot.economy_service)  # type: ignore[attr-defined]
        settings = await self.bot.economy_repository.get_guild_settings(  # type: ignore[attr-defined]
            interaction.guild.id
        )
        try:
            if claim == "daily":
                result = await service.claim_daily_gift(
                    guild_id=interaction.guild.id,
                    user_id=interaction.user.id,
                )
            else:
                result = await service.claim_starter_pack(
                    guild_id=interaction.guild.id,
                    user_id=interaction.user.id,
                )
        except EconomyValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        await interaction.followup.send(
            embed=build_reward_claim_embed(
                title=title,
                amount=result.amount,
                balance=result.wallet.balance,
                currency_name=settings.currency_name,
            ),
            ephemeral=True,
        )
