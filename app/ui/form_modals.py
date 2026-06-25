from __future__ import annotations

import logging
from typing import cast

import discord
from discord.ext import commands

from app.models.form import FormDefinition, FormQuestionType, FormSubmitStatus
from app.services.form_service import FormService, FormValidationError
from app.utils.embeds import build_form_response_embed

logger = logging.getLogger(__name__)


class DynamicFormModal(discord.ui.Modal):
    """Modal usado para coletar respostas curtas do formulario."""

    def __init__(
        self,
        bot: commands.Bot,
        form: FormDefinition,
        selected_answers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(title=form.title[:45])
        self.bot = bot
        self.form = form
        self.selected_answers = selected_answers or {}
        self.inputs: dict[str, discord.ui.TextInput] = {}

        for question in form.questions:
            if question.type is not FormQuestionType.SHORT:
                continue

            text_input = discord.ui.TextInput(
                label=question.label[:45],
                style=discord.TextStyle.paragraph,
                required=question.required,
                max_length=1000,
            )
            self.inputs[question.id] = text_input
            self.add_item(text_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        answers = dict(self.selected_answers)
        for question_id, text_input in self.inputs.items():
            answers[question_id] = str(text_input.value)

        await submit_form_response(interaction, self.bot, self.form, answers)


async def submit_form_response(
    interaction: discord.Interaction,
    bot: commands.Bot,
    form: FormDefinition,
    answers: dict[str, str],
) -> None:
    service = cast(FormService | None, getattr(bot, "form_service", None))
    if service is None:
        await interaction.response.send_message(
            "O sistema de formularios nao esta disponivel agora.",
            ephemeral=True,
        )
        return

    try:
        result = await service.submit_response(form.id, interaction.user.id, answers)
    except FormValidationError as exc:
        await interaction.response.send_message(str(exc), ephemeral=True)
        return

    if result.status is FormSubmitStatus.FORM_NOT_FOUND:
        await interaction.response.send_message(
            "Este formulario nao foi encontrado.",
            ephemeral=True,
        )
        return

    if result.status is FormSubmitStatus.FORM_CLOSED:
        await interaction.response.send_message(
            "Este formulario ja foi encerrado.",
            ephemeral=True,
        )
        return

    if result.status is FormSubmitStatus.ALREADY_SUBMITTED:
        await interaction.response.send_message(
            "Voce ja enviou uma resposta para este formulario.",
            ephemeral=True,
        )
        return

    if result.form is None or result.response is None:
        await interaction.response.send_message(
            "Nao foi possivel registrar sua resposta agora.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        "Resposta enviada com sucesso.",
        ephemeral=True,
    )
    await _notify_response_channel(interaction, bot, result.form, result.response)


async def _notify_response_channel(
    interaction: discord.Interaction,
    bot: commands.Bot,
    form: FormDefinition,
    response,
) -> None:
    channel = bot.get_channel(form.response_channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(form.response_channel_id)
        except (discord.Forbidden, discord.HTTPException):
            logger.warning(
                "Nao foi possivel localizar o canal de respostas do formulario %s.",
                form.id,
            )
            return

    if not hasattr(channel, "send"):
        logger.warning(
            "Canal de respostas do formulario %s nao aceita mensagens.",
            form.id,
        )
        return

    try:
        await channel.send(
            content=(
                f"Nova resposta de {interaction.user.mention} "
                f"(`{interaction.user.id}`)"
            ),
            embed=build_form_response_embed(form, response),
        )
    except discord.HTTPException:
        logger.exception(
            "Nao foi possivel enviar resposta do formulario %s.",
            form.id,
        )
