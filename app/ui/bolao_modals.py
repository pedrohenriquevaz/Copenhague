from __future__ import annotations

import logging
from typing import cast

import discord
from discord.ext import commands

from app.models.bolao import BolaoGuessStatus
from app.services.bolao_service import BolaoService, BolaoValidationError
from app.utils.embeds import format_bolao_guess

logger = logging.getLogger(__name__)


class BolaoGuessModal(discord.ui.Modal):
    """Modal usado para coletar o placar do participante."""

    def __init__(
        self,
        bot: commands.Bot,
        bolao_id: int,
        *,
        team_1: str,
        team_2: str,
    ) -> None:
        super().__init__(title="Enviar palpite")
        self.bot = bot
        self.bolao_id = bolao_id
        self.team_1 = team_1
        self.team_2 = team_2
        self.score_team_1 = discord.ui.TextInput(
            label=f"Gols do {team_1}"[:45],
            placeholder="Ex: 2",
            min_length=1,
            max_length=2,
        )
        self.score_team_2 = discord.ui.TextInput(
            label=f"Gols do {team_2}"[:45],
            placeholder="Ex: 1",
            min_length=1,
            max_length=2,
        )
        self.add_item(self.score_team_1)
        self.add_item(self.score_team_2)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        service = cast(BolaoService | None, getattr(self.bot, "bolao_service", None))
        if service is None:
            await interaction.response.send_message(
                "O sistema de bolao nao esta disponivel agora.",
                ephemeral=True,
            )
            return

        try:
            score_team_1 = self._parse_score(str(self.score_team_1.value), self.team_1)
            score_team_2 = self._parse_score(str(self.score_team_2.value), self.team_2)
        except BolaoValidationError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        result = await service.create_guess(
            self.bolao_id,
            interaction.user.id,
            score_team_1,
            score_team_2,
        )

        if result.status is BolaoGuessStatus.EVENT_NOT_FOUND:
            await interaction.response.send_message(
                "Este bolao nao foi encontrado.",
                ephemeral=True,
            )
            return

        if result.status is BolaoGuessStatus.EVENT_CLOSED:
            await interaction.response.send_message(
                "Este bolao ja foi encerrado.",
                ephemeral=True,
            )
            return

        if (
            result.status is BolaoGuessStatus.ALREADY_GUESSED
            and result.event is not None
            and result.guess is not None
        ):
            await interaction.response.send_message(
                (
                    "Voce ja enviou um palpite para este bolao: "
                    f"{format_bolao_guess(result.event, result.guess)}"
                ),
                ephemeral=True,
            )
            return

        if result.event is None or result.guess is None:
            await interaction.response.send_message(
                "Nao foi possivel registrar seu palpite agora.",
                ephemeral=True,
            )
            return

        formatted_guess = format_bolao_guess(result.event, result.guess)
        await interaction.response.send_message(
            f"Palpite registrado com sucesso: {formatted_guess}",
            ephemeral=True,
        )
        await self._notify_receiver(interaction, result.event, result.guess)

    async def _notify_receiver(
        self,
        interaction: discord.Interaction,
        event,
        guess,
    ) -> None:
        receiver = self.bot.get_user(event.receiver_user_id)
        if receiver is None:
            try:
                receiver = await self.bot.fetch_user(event.receiver_user_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                logger.warning(
                    "Nao foi possivel localizar o responsavel do bolao %s: %s.",
                    event.id,
                    event.receiver_user_id,
                )
                return

        try:
            await receiver.send(
                f"Novo palpite recebido no bolao **{event.title}**.\n"
                f"Participante: {interaction.user.mention}\n"
                f"ID do participante: `{interaction.user.id}`\n"
                f"Jogo: {event.team_1} x {event.team_2}\n"
                f"Palpite: {format_bolao_guess(event, guess)}\n"
                f"Enviado em: <t:{int(guess.created_at.timestamp())}:F>"
            )
        except discord.Forbidden:
            logger.warning(
                "Responsavel %s bloqueou DMs para o bolao %s.",
                event.receiver_user_id,
                event.id,
            )
        except discord.HTTPException:
            logger.exception(
                "Nao foi possivel enviar DM ao responsavel do bolao %s.",
                event.id,
            )

    @staticmethod
    def _parse_score(raw: str, field_name: str) -> int:
        value = raw.strip()
        if not value.isdecimal():
            raise BolaoValidationError(
                f"O placar do {field_name} precisa ser um numero inteiro."
            )

        score = int(value)
        BolaoService.validate_score(score)
        return score
