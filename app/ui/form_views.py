from __future__ import annotations

from typing import cast

import discord
from discord.ext import commands

from app.models.form import FormDefinition, FormQuestion, FormQuestionType
from app.services.form_service import FormService
from app.ui.form_modals import DynamicFormModal, submit_form_response


class DynamicFormView(discord.ui.View):
    """View persistente com botao de abertura do formulario."""

    def __init__(self, bot: commands.Bot, form_id: int) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.form_id = form_id

        self.answer_button = discord.ui.Button(
            label="Responder",
            style=discord.ButtonStyle.primary,
            custom_id=f"form_answer:{form_id}",
        )
        self.answer_button.callback = self._on_answer
        self.add_item(self.answer_button)

    async def _on_answer(self, interaction: discord.Interaction) -> None:
        service = cast(FormService | None, getattr(self.bot, "form_service", None))
        if service is None:
            await interaction.response.send_message(
                "O sistema de formularios nao esta disponivel agora.",
                ephemeral=True,
            )
            return

        form = await service.get_form(self.form_id)
        if form is None:
            await interaction.response.send_message(
                "Este formulario nao foi encontrado.",
                ephemeral=True,
            )
            return

        if not form.is_active:
            await interaction.response.send_message(
                "Este formulario ja foi encerrado.",
                ephemeral=True,
            )
            return

        select_questions = [
            question
            for question in form.questions
            if question.type is not FormQuestionType.SHORT
        ]
        if select_questions:
            await interaction.response.send_message(
                "Selecione as respostas abaixo para continuar.",
                view=FormSelectionView(self.bot, form, select_questions),
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(DynamicFormModal(self.bot, form))


class FormSelectionView(discord.ui.View):
    """View efemera para perguntas de selecao antes do modal."""

    def __init__(
        self,
        bot: commands.Bot,
        form: FormDefinition,
        questions: list[FormQuestion],
    ) -> None:
        super().__init__(timeout=300)
        self.bot = bot
        self.form = form
        self.questions = questions
        self.answers: dict[str, str] = {}

        for question in questions:
            self.add_item(FormQuestionSelect(question))

        self.continue_button = discord.ui.Button(
            label="Continuar",
            style=discord.ButtonStyle.primary,
        )
        self.continue_button.callback = self._on_continue
        self.add_item(self.continue_button)

    async def _on_continue(self, interaction: discord.Interaction) -> None:
        missing = [
            question.label
            for question in self.questions
            if question.required and question.id not in self.answers
        ]
        if missing:
            await interaction.response.send_message(
                f"Responda antes: {', '.join(missing)}.",
                ephemeral=True,
            )
            return

        has_short_questions = any(
            question.type is FormQuestionType.SHORT for question in self.form.questions
        )
        if has_short_questions:
            await interaction.response.send_modal(
                DynamicFormModal(self.bot, self.form, self.answers)
            )
            return

        await submit_form_response(interaction, self.bot, self.form, self.answers)


class FormQuestionSelect(discord.ui.Select):
    """Select menu vinculado a uma pergunta do formulario."""

    def __init__(self, question: FormQuestion) -> None:
        self.question = question
        max_values = len(question.options)
        if question.type is FormQuestionType.SELECT:
            max_values = 1

        super().__init__(
            placeholder=question.label[:100],
            min_values=1 if question.required else 0,
            max_values=max_values,
            options=[
                discord.SelectOption(label=option[:100], value=option[:100])
                for option in question.options
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not isinstance(self.view, FormSelectionView):
            await interaction.response.send_message(
                "Nao foi possivel atualizar esta selecao.",
                ephemeral=True,
            )
            return

        self.view.answers[self.question.id] = ", ".join(self.values)
        await interaction.response.defer()
