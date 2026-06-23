from __future__ import annotations

import logging
from typing import cast

import discord
from discord.ext import commands

from app.models.giveaway import GiveawayDrawStatus
from app.services.giveaway_service import GiveawayService
from app.utils.embeds import (
    build_giveaway_claim_embed,
    build_giveaway_event_embed,
    format_reward_text,
)

logger = logging.getLogger(__name__)


class GiveawayClaimView(discord.ui.View):
    """Botao persistente usado para resgatar um codigo do evento."""

    def __init__(self, bot: commands.Bot, event_id: int) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.event_id = event_id

        self.claim_button = discord.ui.Button(
            label="Resgatar codigo",
            style=discord.ButtonStyle.primary,
            custom_id=f"giveaway_claim:{event_id}",
        )
        self.claim_button.callback = self._on_claim
        self.add_item(self.claim_button)

    async def _on_claim(self, interaction: discord.Interaction) -> None:
        service = cast(
            GiveawayService | None,
            getattr(self.bot, "giveaway_service", None),
        )
        if service is None:
            await interaction.response.send_message(
                "O sistema de giveaway nao esta disponivel agora.",
                ephemeral=True,
            )
            return

        result = await service.draw_code_for_user(self.event_id, interaction.user.id)

        if result.status is GiveawayDrawStatus.EVENT_NOT_FOUND:
            await interaction.response.send_message(
                "Este evento nao foi encontrado.",
                ephemeral=True,
            )
            return

        if result.status is GiveawayDrawStatus.EVENT_INACTIVE:
            await interaction.response.send_message(
                "Este evento esta encerrado ou sem codigos disponiveis no momento.",
                ephemeral=True,
            )
            return

        if result.status is GiveawayDrawStatus.SOLD_OUT:
            await interaction.response.send_message(
                "Este evento acabou de ficar sem codigos disponiveis.",
                ephemeral=True,
            )
            await self._refresh_event_message(
                result.event.id if result.event else self.event_id
            )
            return

        if (
            result.status is GiveawayDrawStatus.ALREADY_CLAIMED
            and result.claim is not None
        ):
            claim = result.claim
            reward_text = format_reward_text(claim.reward_name, claim.reward_amount)
            await interaction.response.send_message(
                (
                    "Voce ja participou deste evento.\n"
                    f"Seu codigo foi `{claim.code}` e a premiacao foi {reward_text}."
                ),
                ephemeral=True,
            )
            return

        if result.code is None or result.claim is None or result.event is None:
            await interaction.response.send_message(
                "Nao foi possivel concluir seu resgate agora.",
                ephemeral=True,
            )
            return

        code = result.code
        claim = result.claim
        event = result.event
        won = code.reward_amount is not None or code.reward_name is not None

        claim_embed = build_giveaway_claim_embed(
            code.code,
            reward_name=code.reward_name,
            reward_amount=code.reward_amount,
            won=won,
        )

        await interaction.response.send_message(embed=claim_embed, ephemeral=True)

        if won:
            await self._notify_user(event, interaction.user, claim)

            reward_text = format_reward_text(code.reward_name, code.reward_amount)
            channel = interaction.channel
            if channel is not None:
                try:
                    await channel.send(
                        f"\U0001f389 {interaction.user.mention} acabou de ganhar "
                        f"{reward_text} com o codigo `{claim.code}`!"
                    )
                except discord.Forbidden:
                    logger.warning(
                        "Sem permissao para anunciar ganho do giveaway no canal %s.",
                        getattr(channel, "id", "desconhecido"),
                    )
                except discord.HTTPException:
                    logger.exception("Erro ao enviar anuncio publico do giveaway.")

        await self._refresh_event_message(event.id)

    async def _notify_user(
        self,
        event,
        winner: discord.abc.User,
        claim,
    ) -> None:
        notify_user_id = event.notify_user_id
        if notify_user_id is None:
            return

        if notify_user_id == winner.id:
            return

        notify_user = self.bot.get_user(notify_user_id)
        if notify_user is None:
            try:
                notify_user = await self.bot.fetch_user(notify_user_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                logger.warning(
                    "Nao foi possivel localizar o usuario de notificacao %s.",
                    notify_user_id,
                )
                return

        reward_text = format_reward_text(claim.reward_name, claim.reward_amount)
        try:
            await notify_user.send(
                f"{winner.display_name} ganhou {reward_text} "
                f"com o codigo `{claim.code}`."
            )
        except discord.Forbidden:
            logger.warning(
                "O usuario de notificacao %s bloqueou mensagens privadas.",
                notify_user_id,
            )
        except discord.HTTPException:
            logger.exception("Erro ao enviar DM de notificacao do giveaway.")

    async def _refresh_event_message(self, event_id: int) -> None:
        """Atualiza o embed publico com os codigos restantes."""

        service = cast(
            GiveawayService | None,
            getattr(self.bot, "giveaway_service", None),
        )
        if service is None:
            return

        event = await service.get_event(event_id)
        if event is None or event.channel_id is None or event.message_id is None:
            return

        stats = await service.get_event_stats(event_id)
        if stats is None:
            return

        channel = self.bot.get_channel(event.channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(event.channel_id)
            except (discord.Forbidden, discord.HTTPException):
                logger.warning(
                    "Nao foi possivel localizar o canal do giveaway %s.",
                    event_id,
                )
                return

        if not hasattr(channel, "fetch_message"):
            return

        try:
            message = await channel.fetch_message(event.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            logger.warning(
                "Nao foi possivel atualizar a mensagem do giveaway %s.",
                event_id,
            )
            return

        self.claim_button.disabled = (not event.is_active) or stats.available_codes <= 0
        embed = build_giveaway_event_embed(event, stats, closed=not event.is_active)
        try:
            await message.edit(embed=embed, view=self)
        except discord.HTTPException:
            logger.exception(
                "Erro ao atualizar a mensagem publica do giveaway %s.",
                event_id,
            )
