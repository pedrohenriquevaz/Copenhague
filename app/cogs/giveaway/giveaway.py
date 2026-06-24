from __future__ import annotations

import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast

import discord
from discord import app_commands
from discord.ext import commands, tasks

from app.models.giveaway import (
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

        stats = await self.service.get_event_stats(event.id)
        if stats is None:
            await interaction.followup.send(
                "Nao foi possivel carregar os dados do evento.",
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

        embed = build_giveaway_event_embed(event_to_publish, stats)
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


async def setup(bot: commands.Bot) -> None:
    cog = GiveawayCog(bot)
    await bot.add_cog(cog)
    await cog.register_active_views()
    if not cog.expiry_watcher.is_running():
        cog.expiry_watcher.start()
