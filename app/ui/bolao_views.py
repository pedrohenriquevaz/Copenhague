from __future__ import annotations

from typing import cast

import discord
from discord.ext import commands

from app.services.bolao_service import BolaoService
from app.ui.bolao_modals import BolaoGuessModal


class BolaoGuessView(discord.ui.View):
    """View persistente com botao de envio de palpite."""

    def __init__(self, bot: commands.Bot, bolao_id: int) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.bolao_id = bolao_id

        self.guess_button = discord.ui.Button(
            label="Enviar Palpite",
            style=discord.ButtonStyle.primary,
            custom_id=f"bolao_guess:{bolao_id}",
        )
        self.guess_button.callback = self._on_guess
        self.add_item(self.guess_button)

    async def _on_guess(self, interaction: discord.Interaction) -> None:
        service = cast(BolaoService | None, getattr(self.bot, "bolao_service", None))
        if service is None:
            await interaction.response.send_message(
                "O sistema de bolao nao esta disponivel agora.",
                ephemeral=True,
            )
            return

        event = await service.get_event(self.bolao_id)
        if event is None:
            await interaction.response.send_message(
                "Este bolao nao foi encontrado.",
                ephemeral=True,
            )
            return

        if not event.is_active:
            await interaction.response.send_message(
                "Este bolao ja foi encerrado.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            BolaoGuessModal(
                self.bot,
                self.bolao_id,
                team_1=event.team_1,
                team_2=event.team_2,
            )
        )
