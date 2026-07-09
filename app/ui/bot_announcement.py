from __future__ import annotations

from typing import cast

import discord
from discord.ext import commands

from app.services.economy_service import EconomyService, EconomyValidationError
from app.utils.embeds import format_points


def build_bot_announcement_embed(*, image_url: str | None = None) -> discord.Embed:
    """Cria a embed pública de apresentação do bot."""

    embed = discord.Embed(
        title="Central do bot",
        description=(
            "Participe do servidor, acumule pontos e use-os na loja, em jogos, "
            "apostas saudáveis de campeonatos e eventos da comunidade.\n\n"
            "Use os botões abaixo para ver os comandos, resgatar seu presente "
            "diário ou pegar seu pacote inicial."
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
    """Documentação resumida dos comandos livres para usuários."""

    embed = discord.Embed(
        title="Ajuda e comandos",
        description=(
            "Estes são os comandos disponíveis para membros comuns. "
            "Comandos administrativos ficam fora desta lista."
        ),
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="Economia e atividade",
        value=(
            "`/saldo` consulta seus pontos ou os pontos de outro usuário.\n"
            "`/perfil` mostra o perfil econômico.\n"
            "`/transferir` envia pontos para outro usuário.\n"
            "`/historico` lista suas transações recentes.\n"
            "`/ranking` mostra o ranking de pontos do servidor.\n"
            "`/converter_atividade` transforma mensagens e tempo em call em pontos."
        ),
        inline=False,
    )
    embed.add_field(
        name="Loja e recompensas",
        value=(
            "`/loja` abre a loja para trocar pontos por recompensas.\n"
            "`Presente diário` resgata pontos uma vez por dia.\n"
            "`Pacote inicial` resgata pontos uma única vez por usuário."
        ),
        inline=False,
    )
    embed.add_field(
        name="Jogos",
        value=(
            "`/blackjack` joga BlackJack apostando pontos.\n"
            "`/cara_coroa`, `/dado`, `/slot` e `/roleta` são jogos rápidos.\n"
            "`/duelo` desafia outro membro em uma aposta.\n"
            "`/corrida` aposta em uma corrida individual de mascotes.\n"
            "`/raspadinha` compra uma raspadinha virtual."
        ),
        inline=False,
    )
    embed.add_field(
        name="Progresso",
        value=(
            "`/jogos_perfil` mostra estatísticas de jogos.\n"
            "`/jogos_ranking` mostra o ranking de lucro em jogos.\n"
            "`/jogos_historico` mostra seu histórico recente de apostas.\n"
            "`/conquistas` mostra conquistas de jogos.\n"
            "`/jackpot` mostra o jackpot atual da raspadinha.\n"
            "`/evento_sazonal` mostra o tema sazonal dos jogos."
        ),
        inline=False,
    )
    embed.add_field(
        name="Eventos por botão",
        value=(
            "Bets, bolões, giveaways, formulários e corridas coletivas publicados "
            "no chat usam os botões da própria embed para participação."
        ),
        inline=False,
    )
    embed.add_field(
        name="Utilidade",
        value=(
            "`/lembrete` agenda um lembrete simples por DM.\n"
            "`/ping` mostra a latência atual do bot."
        ),
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
        name="Você recebeu",
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
    """Botões persistentes do anúncio do bot."""

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
        label="Presente diário",
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
            title="Presente diário resgatado",
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
                "Este painel só pode ser usado em servidores.",
                ephemeral=True,
            )
            return
        if interaction.user.bot:
            await interaction.response.send_message(
                "Bots não podem resgatar recompensas.",
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
