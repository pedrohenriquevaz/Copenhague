from __future__ import annotations

import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast

import discord
from discord import app_commands
from discord.ext import commands, tasks

from app.models.giveaway import (
    GiveawayClaim,
    GiveawayCode,
    GiveawayCreationResult,
    GiveawayEvent,
    GiveawayFinalizationResult,
)
from app.services.giveaway_service import GiveawayService, GiveawayValidationError
from app.utils.embeds import (
    build_giveaway_event_embed,
    build_giveaway_final_embed,
    format_reward_text,
    parse_color_value,
)

from .views import GiveawayClaimView

logger = logging.getLogger(__name__)


class GiveawayCog(commands.Cog):
    """Comandos administrativos e integracao do giveaway."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.service = cast(GiveawayService, bot.giveaway_service)  # type: ignore[attr-defined]

    def cog_unload(self) -> None:
        if self.expiry_watcher.is_running():
            self.expiry_watcher.cancel()

    async def register_active_views(self) -> None:
        """Re-registra os botoes persistentes dos eventos ativos."""

        events = await self.service.list_active_published_events()
        for event in events:
            if event.message_id is None:
                continue

            self.bot.add_view(
                GiveawayClaimView(self.bot, event.id),
                message_id=event.message_id,
            )
            logger.info(
                "View persistente registrada para o giveaway #%s (mensagem %s).",
                event.id,
                event.message_id,
            )

    @tasks.loop(minutes=1)
    async def expiry_watcher(self) -> None:
        """Finaliza automaticamente os eventos expirados."""

        events = await self.service.get_expiring_events()
        for event in events:
            await self._finalize_event(event, delete_original_message=False)

    @expiry_watcher.before_loop
    async def before_expiry_watcher(self) -> None:
        await self.bot.wait_until_ready()

    @app_commands.command(
        name="giveaway_create",
        description="Cria um evento de distribuicao de codigos.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        title="Titulo do evento.",
        description="Descricao exibida no anuncio do evento.",
        total_codes="Quantidade total de codigos que serao gerados.",
        reward_plan=(
            "Plano de premios. Formatos aceitos: "
            "nome|valor|quantidade;valor|quantidade; ou JSON."
        ),
        notify_user=("Usuario que recebera DM quando alguem ganhar uma premiacao."),
    )
    async def giveaway_create(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        total_codes: int,
        reward_plan: str | None = None,
        notify_user: discord.User | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado dentro de um servidor.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            result: GiveawayCreationResult = await self.service.create_event(
                title=title,
                description=description,
                created_by=interaction.user.id,
                total_codes=total_codes,
                reward_plan=reward_plan,
                notify_user_id=notify_user.id if notify_user else None,
            )
        except GiveawayValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        event = result.event
        reward_summary = "Nenhum premio definido"
        if result.rewarded_codes > 0:
            reward_parts: list[str] = []
            for tier in result.reward_tiers:
                reward_parts.append(
                    f"{tier.quantity}x "
                    f"{format_reward_text(tier.reward_name, tier.reward_amount)}"
                )
            reward_summary = ", ".join(reward_parts)

        notify_summary = (
            notify_user.mention if notify_user is not None else "Sem DM de notificacao"
        )
        await interaction.followup.send(
            (
                f"Evento criado com sucesso. ID: **{event.id}**\n"
                f"Codigos totais: **{event.total_codes}**\n"
                f"Codigos premiados: **{result.rewarded_codes}**\n"
                f"Premios: **{reward_summary}**\n"
                f"Notificacao privada: **{notify_summary}**"
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="giveaway_publish",
        description="Publica a mensagem do evento com o botao de resgate.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        event_id="ID do evento criado pelo giveaway_create.",
        channel="Canal onde a mensagem sera publicada. Se omitido, usa o canal atual.",
        embed_color="Cor hexadecimal do embed, por exemplo FFAA00.",
        duration_minutes="Tempo, em minutos, que o evento ficara publicado.",
    )
    async def giveaway_publish(
        self,
        interaction: discord.Interaction,
        event_id: int,
        channel: discord.TextChannel | discord.Thread | None = None,
        embed_color: str | None = None,
        duration_minutes: int | None = None,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado dentro de um servidor.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        event = await self.service.get_event(event_id)
        if event is None:
            await interaction.followup.send(
                "Nao encontrei um evento com esse ID.",
                ephemeral=True,
            )
            return

        if event.message_id is not None:
            await interaction.followup.send(
                "Esse evento ja foi publicado anteriormente.",
                ephemeral=True,
            )
            return

        target_channel = channel or interaction.channel
        if target_channel is None:
            await interaction.followup.send(
                "Nao foi possivel identificar o canal para publicar o evento.",
                ephemeral=True,
            )
            return

        if not hasattr(target_channel, "send"):
            await interaction.followup.send(
                "O canal escolhido nao suporta publicacao de mensagens.",
                ephemeral=True,
            )
            return

        if duration_minutes is not None and duration_minutes <= 0:
            await interaction.followup.send(
                "O tempo de publicacao precisa ser maior que zero.",
                ephemeral=True,
            )
            return

        parsed_color = None
        if embed_color is not None:
            try:
                parsed_color = parse_color_value(embed_color)
            except ValueError:
                await interaction.followup.send(
                    "A cor do embed precisa estar em hexadecimal valido.",
                    ephemeral=True,
                )
                return

        event_to_publish = event
        if parsed_color is not None:
            event_to_publish = replace(event_to_publish, embed_color=parsed_color)

        if duration_minutes is not None:
            event_to_publish = replace(
                event_to_publish,
                expires_at=datetime.now(UTC) + timedelta(minutes=duration_minutes),
            )

        embed = build_giveaway_event_embed(event_to_publish, None)
        view = GiveawayClaimView(self.bot, event.id)

        try:
            message = await target_channel.send(embed=embed, view=view)
        except discord.Forbidden:
            await interaction.followup.send(
                "Nao tenho permissao para enviar mensagens nesse canal.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                "Ocorreu um erro ao publicar o evento.",
                ephemeral=True,
            )
            return

        published = await self.service.publish_event(
            event.id,
            channel_id=target_channel.id,
            message_id=message.id,
            embed_color=parsed_color,
            expires_in_minutes=duration_minutes,
        )
        self.bot.add_view(view, message_id=message.id)

        channel_mention = getattr(target_channel, "mention", f"<#{target_channel.id}>")
        await interaction.followup.send(
            (
                f"Evento publicado em {channel_mention}.\n"
                f"Link da mensagem: {message.jump_url}\n"
                f"Evento ativo: **{published.is_active}**"
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="giveaway_unpublish",
        description=(
            "Despublica e encerra o evento, enviando o resumo dos codigos " "restantes."
        ),
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        event_id="ID do evento a encerrar.",
        delete_message="Se verdadeiro, a mensagem original sera apagada.",
    )
    async def giveaway_unpublish(
        self,
        interaction: discord.Interaction,
        event_id: int,
        delete_message: bool = True,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado dentro de um servidor.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        event = await self.service.get_event(event_id)
        if event is None:
            await interaction.followup.send(
                "Nao encontrei um evento com esse ID.",
                ephemeral=True,
            )
            return

        await self._finalize_event(event, delete_original_message=delete_message)
        await interaction.followup.send(
            "Evento encerrado com sucesso.",
            ephemeral=True,
        )

    @app_commands.command(
        name="giveaway_codes",
        description="Consulta os codigos ainda disponiveis de um evento.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        event_id="ID do evento do giveaway.",
    )
    async def giveaway_codes(
        self,
        interaction: discord.Interaction,
        event_id: int,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado dentro de um servidor.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        message, remaining_codes = await self._build_available_codes_response(event_id)
        await interaction.followup.send(message, ephemeral=True)

        remaining_lines = self._format_available_code_lines(remaining_codes)
        for chunk in self._chunk_lines(remaining_lines, limit=1800):
            await interaction.followup.send(
                f"```text\n{chunk}\n```",
                ephemeral=True,
            )

    @app_commands.command(
        name="give_ticket",
        description="Adiciona tickets extras de resgate para um usuario.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        event_id="ID do evento do giveaway.",
        user="Usuario que recebera tickets extras.",
        amount="Quantidade de tickets extras a adicionar.",
    )
    async def give_ticket(
        self,
        interaction: discord.Interaction,
        event_id: int,
        user: discord.User,
        amount: int = 1,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado dentro de um servidor.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            balance = await self.service.add_user_tickets(
                event_id,
                user.id,
                amount,
            )
        except GiveawayValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        await interaction.followup.send(
            (
                f"{amount} ticket(s) extra(s) adicionados para {user.mention}.\n"
                f"Tickets extras restantes no evento **{event_id}**: "
                f"**{balance.extra_tickets}**.\n"
                f"Resgates disponiveis a partir de agora: "
                f"**1 + {balance.extra_tickets} extra(s)**."
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="user_ticket",
        description="Consulta os tickets extras restantes de um usuario.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        event_id="ID do evento do giveaway.",
        user="Usuario consultado.",
    )
    async def user_ticket(
        self,
        interaction: discord.Interaction,
        event_id: int,
        user: discord.User,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado dentro de um servidor.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            balance = await self.service.get_user_ticket_balance(event_id, user.id)
        except GiveawayValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        await interaction.followup.send(
            (
                f"{user.mention} possui **{balance.extra_tickets}** "
                f"ticket(s) extra(s) restante(s) no evento **{event_id}**.\n"
                f"Por padrao, todo usuario tem 1 resgate gratuito por evento."
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="remove_ticket",
        description="Remove tickets extras de resgate de um usuario.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        event_id="ID do evento do giveaway.",
        user="Usuario que perdera tickets extras.",
        amount="Quantidade de tickets extras a remover.",
    )
    async def remove_ticket(
        self,
        interaction: discord.Interaction,
        event_id: int,
        user: discord.User,
        amount: int = 1,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando so pode ser usado dentro de um servidor.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            balance = await self.service.remove_user_tickets(
                event_id,
                user.id,
                amount,
            )
        except GiveawayValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        await interaction.followup.send(
            (
                f"{amount} ticket(s) extra(s) removidos de {user.mention}.\n"
                f"Tickets extras restantes no evento **{event_id}**: "
                f"**{balance.extra_tickets}**."
            ),
            ephemeral=True,
        )

    @commands.command(name="give_ticket")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def give_ticket_prefix(
        self,
        ctx: commands.Context,
        event_id: int,
        user: discord.User,
        amount: int = 1,
    ) -> None:
        """Adiciona tickets extras usando comando prefixado."""

        async with ctx.typing():
            balance = await self.service.add_user_tickets(event_id, user.id, amount)

        await ctx.reply(
            (
                f"{amount} ticket(s) extra(s) adicionados para {user.mention}.\n"
                f"Tickets extras restantes no evento **{event_id}**: "
                f"**{balance.extra_tickets}**.\n"
                f"Resgates disponiveis a partir de agora: "
                f"**1 + {balance.extra_tickets} extra(s)**."
            ),
            mention_author=False,
        )

    @commands.command(name="user_ticket")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def user_ticket_prefix(
        self,
        ctx: commands.Context,
        event_id: int,
        user: discord.User,
    ) -> None:
        """Consulta tickets extras usando comando prefixado."""

        async with ctx.typing():
            balance = await self.service.get_user_ticket_balance(event_id, user.id)

        await ctx.reply(
            (
                f"{user.mention} possui **{balance.extra_tickets}** "
                f"ticket(s) extra(s) restante(s) no evento **{event_id}**.\n"
                f"Por padrao, todo usuario tem 1 resgate gratuito por evento."
            ),
            mention_author=False,
        )

    @commands.command(name="remove_ticket")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def remove_ticket_prefix(
        self,
        ctx: commands.Context,
        event_id: int,
        user: discord.User,
        amount: int = 1,
    ) -> None:
        """Remove tickets extras usando comando prefixado."""

        async with ctx.typing():
            balance = await self.service.remove_user_tickets(event_id, user.id, amount)

        await ctx.reply(
            (
                f"{amount} ticket(s) extra(s) removidos de {user.mention}.\n"
                f"Tickets extras restantes no evento **{event_id}**: "
                f"**{balance.extra_tickets}**."
            ),
            mention_author=False,
        )

    async def _finalize_event(
        self,
        event: GiveawayEvent,
        *,
        delete_original_message: bool,
    ) -> None:
        if not event.is_active and event.message_id is None:
            return

        try:
            finalization: GiveawayFinalizationResult = (
                await self.service.finalize_event(event.id)
            )
        except RuntimeError:
            return

        if event.message_id is not None:
            self.bot.add_view(
                GiveawayClaimView(self.bot, event.id),
                message_id=event.message_id,
            )

        if event.channel_id is None:
            return

        channel = self.bot.get_channel(event.channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(event.channel_id)
            except (discord.Forbidden, discord.HTTPException):
                logger.warning(
                    "Nao foi possivel encontrar o canal para finalizar o evento %s.",
                    event.id,
                )
                return

        final_embed = build_giveaway_final_embed(
            finalization.event,
            finalization.remaining_codes,
            self._format_winner_lines(finalization.winning_claims),
        )
        summary_message = None
        if hasattr(channel, "send"):
            try:
                summary_message = await channel.send(embed=final_embed)
                remaining_lines = [
                    (
                        f"`{item.code}` - "
                        f"{format_reward_text(item.reward_name, item.reward_amount)}"
                    )
                    for item in finalization.remaining_codes
                ]
                for chunk in self._chunk_lines(remaining_lines, limit=1800):
                    await channel.send(f"```text\n{chunk}\n```")
            except discord.HTTPException:
                logger.exception(
                    "Erro ao enviar resumo final do giveaway %s.", event.id
                )

        if event.message_id is None or not hasattr(channel, "fetch_message"):
            return

        try:
            message = await channel.fetch_message(event.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            logger.warning(
                "Nao foi possivel acessar a mensagem do evento %s.", event.id
            )
            return

        closed_view = GiveawayClaimView(self.bot, event.id)
        closed_view.claim_button.disabled = True
        closed_embed = build_giveaway_event_embed(finalization.event, None, closed=True)
        try:
            if delete_original_message:
                await message.delete()
            else:
                await message.edit(embed=closed_embed, view=closed_view)
        except discord.HTTPException:
            logger.exception("Erro ao concluir o evento giveaway %s.", event.id)
        finally:
            if summary_message is not None:
                logger.info(
                    "Resumo final publicado para giveaway %s: %s",
                    event.id,
                    summary_message.id,
                )

    @staticmethod
    def _chunk_lines(lines: list[str], *, limit: int) -> list[str]:
        chunks: list[str] = []
        current = ""

        for line in lines:
            candidate = f"{current}\n{line}" if current else line
            if len(candidate) > limit and current:
                chunks.append(current)
                current = line
                continue
            current = candidate

        if current:
            chunks.append(current)

        return chunks

    async def _build_available_codes_response(
        self,
        event_id: int,
    ) -> tuple[str, list[GiveawayCode]]:
        event = await self.service.get_event(event_id)
        if event is None:
            return "Nao encontrei um evento com esse ID.", []

        stats = await self.service.get_event_stats(event_id)
        remaining_codes = await self.service.list_remaining_codes(event_id)

        if stats is None:
            return "Nao foi possivel carregar os dados do evento.", []

        status = "ativo" if event.is_active else "encerrado"
        message = (
            f"Evento **#{event.id}** ({status}): **{event.title}**\n"
            f"Codigos totais: **{stats.total_codes}**\n"
            f"Codigos resgatados: **{stats.claimed_codes}**\n"
            f"Codigos disponiveis: **{stats.available_codes}**"
        )

        if not remaining_codes:
            message = f"{message}\n\nNao ha codigos disponiveis para este evento."

        return message, remaining_codes

    @staticmethod
    def _format_available_code_lines(codes: list[GiveawayCode]) -> list[str]:
        return [
            f"{item.code} - {format_reward_text(item.reward_name, item.reward_amount)}"
            for item in codes
        ]

    @staticmethod
    def _format_winner_lines(claims: list[GiveawayClaim]) -> list[str]:
        return [
            (
                f"{index}. <@{claim.user_id}> (`{claim.user_id}`) - "
                f"`{claim.code}` - "
                f"{format_reward_text(claim.reward_name, claim.reward_amount)}"
            )
            for index, claim in enumerate(claims, start=1)
        ]

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        original_error = getattr(error, "original", error)

        if isinstance(original_error, GiveawayValidationError):
            if interaction.response.is_done():
                await interaction.followup.send(str(original_error), ephemeral=True)
            else:
                await interaction.response.send_message(
                    str(original_error),
                    ephemeral=True,
                )
            return

        if isinstance(
            error, (app_commands.MissingPermissions, app_commands.CheckFailure)
        ):
            message = "Voce nao tem permissao para executar este comando."
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
            return

        logger.exception("Erro inesperado no giveaway: %s", error)
        message = "Ocorreu um erro inesperado ao executar o giveaway."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    async def cog_command_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ) -> None:
        if isinstance(error, GiveawayValidationError):
            await ctx.reply(str(error), mention_author=False)
            return

        if isinstance(error, commands.CommandInvokeError) and isinstance(
            error.original,
            GiveawayValidationError,
        ):
            await ctx.reply(str(error.original), mention_author=False)
            return

        if isinstance(error, commands.MissingPermissions):
            await ctx.reply(
                "Voce nao tem permissao para executar este comando.",
                mention_author=False,
            )
            return

        if isinstance(error, commands.NoPrivateMessage):
            await ctx.reply(
                "Este comando so pode ser usado dentro de um servidor.",
                mention_author=False,
            )
            return

        if isinstance(
            error,
            (
                commands.BadArgument,
                commands.MissingRequiredArgument,
                commands.TooManyArguments,
            ),
        ):
            await ctx.reply(
                (
                    "Uso: `cp!give_ticket <event_id> <usuario> [quantidade]`, "
                    "`cp!user_ticket <event_id> <usuario>` ou "
                    "`cp!remove_ticket <event_id> <usuario> [quantidade]`."
                ),
                mention_author=False,
            )
            return

        logger.exception("Erro inesperado no comando prefixado de giveaway: %s", error)
        await ctx.reply(
            "Ocorreu um erro inesperado ao executar o giveaway.",
            mention_author=False,
        )


async def setup(bot: commands.Bot) -> None:
    cog = GiveawayCog(bot)
    await bot.add_cog(cog)
    await cog.register_active_views()
    if not cog.expiry_watcher.is_running():
        cog.expiry_watcher.start()
