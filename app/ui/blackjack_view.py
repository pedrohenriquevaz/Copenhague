from __future__ import annotations

from typing import cast

import discord
from discord.ext import commands

from app.models.casino import (
    BlackjackCard,
    BlackjackHand,
    BlackjackOutcome,
    BlackjackSession,
)
from app.models.guild_settings import GuildEconomySettings
from app.services.blackjack_service import BlackjackService, BlackjackValidationError
from app.ui.casino_animation import (
    blackjack_animation,
    build_casino_animation_embed,
    play_casino_animation,
)
from app.utils.embeds import format_points

OUTCOME_TEXT = {
    BlackjackOutcome.PLAYER_BLACKJACK: "BlackJack natural! Voce venceu.",
    BlackjackOutcome.PLAYER_WIN: "Voce venceu a banca.",
    BlackjackOutcome.DEALER_WIN: "A banca venceu.",
    BlackjackOutcome.PUSH: "Empate. Sua aposta foi devolvida.",
    BlackjackOutcome.PLAYER_BUST: "Voce estourou 21 pontos.",
    BlackjackOutcome.DEALER_BLACKJACK: "A banca abriu BlackJack natural.",
    BlackjackOutcome.EXPIRED: "Partida encerrada por inatividade.",
}


def build_blackjack_embed(
    session: BlackjackSession,
    settings: GuildEconomySettings,
) -> discord.Embed:
    """Cria o embed de uma partida de BlackJack."""

    color = discord.Color.gold() if not session.is_finished else _result_color(session)
    embed = discord.Embed(title="BlackJack", color=color)

    if session.is_finished:
        embed.description = OUTCOME_TEXT.get(
            session.outcome,
            "Partida finalizada.",
        )
    else:
        embed.description = "Escolha sua jogada usando os botoes abaixo."

    embed.add_field(
        name="Sua mao",
        value=_format_hand(session.player_hand),
        inline=False,
    )
    embed.add_field(
        name="Mao da banca",
        value=_format_dealer_hand(session),
        inline=False,
    )

    if session.is_finished:
        embed.add_field(
            name="Pagamento",
            value=format_points(session.payout, settings.currency_name),
            inline=True,
        )
        embed.add_field(
            name="Aposta final",
            value=format_points(session.bet, settings.currency_name),
            inline=True,
        )
    else:
        embed.add_field(
            name="Aposta atual",
            value=format_points(session.bet, settings.currency_name),
            inline=True,
        )
        embed.add_field(
            name="Dobrar",
            value="Disponivel" if session.can_double else "Indisponivel",
            inline=True,
        )

    return embed


async def announce_blackjack_win(
    interaction: discord.Interaction,
    session: BlackjackSession,
    settings: GuildEconomySettings,
) -> None:
    """Anuncia vitorias reais do BlackJack no canal."""

    if session.payout <= session.bet:
        return

    channel = interaction.channel
    if channel is None or not hasattr(channel, "send"):
        return

    try:
        await channel.send(
            "🎉 "
            f"{interaction.user.mention} acabou de ganhar "
            f"{format_points(session.payout, settings.currency_name)} no BlackJack!"
        )
    except discord.HTTPException:
        return


class BlackjackView(discord.ui.View):
    """Botoes efemeros de uma partida de BlackJack."""

    def __init__(
        self,
        bot: commands.Bot,
        session: BlackjackSession,
        settings: GuildEconomySettings,
    ) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.session = session
        self.settings = settings
        self.message: discord.Message | None = None
        self._refresh_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or interaction.guild.id != self.session.guild_id:
            await interaction.response.send_message(
                "Essa partida nao pertence a este servidor.",
                ephemeral=True,
            )
            return False

        if interaction.user.id != self.session.user_id:
            await interaction.response.send_message(
                "Essa partida pertence a outro jogador.",
                ephemeral=True,
            )
            return False

        return True

    @discord.ui.button(label="Pedir carta", style=discord.ButtonStyle.primary, row=0)
    async def hit_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self._run_action(interaction, "hit")

    @discord.ui.button(label="Parar", style=discord.ButtonStyle.secondary, row=0)
    async def stand_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self._run_action(interaction, "stand")

    @discord.ui.button(label="Dobrar", style=discord.ButtonStyle.success, row=0)
    async def double_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self._run_action(interaction, "double")

    async def on_timeout(self) -> None:
        if self.session.is_finished:
            return

        service = cast(BlackjackService, self.bot.blackjack_service)  # type: ignore[attr-defined]
        expired = await service.expire_game(self.session.guild_id, self.session.user_id)
        if expired is not None:
            self.session = expired

        self._refresh_buttons()
        if self.message is not None:
            try:
                await self.message.edit(
                    embed=build_blackjack_embed(self.session, self.settings),
                    view=self,
                )
            except discord.HTTPException:
                return

    async def _run_action(
        self,
        interaction: discord.Interaction,
        action: str,
    ) -> None:
        service = cast(BlackjackService, self.bot.blackjack_service)  # type: ignore[attr-defined]

        try:
            if action == "hit":
                next_session = await service.hit(
                    self.session.guild_id,
                    self.session.user_id,
                )
            elif action == "stand":
                next_session = await service.stand(
                    self.session.guild_id,
                    self.session.user_id,
                )
            else:
                next_session = await service.double_down(
                    self.session.guild_id,
                    self.session.user_id,
                )
        except BlackjackValidationError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        self._set_buttons_disabled(True)
        animation = blackjack_animation(action)
        await interaction.response.edit_message(
            embed=build_casino_animation_embed(animation),
            view=self,
        )
        try:
            message = await interaction.original_response()
        except discord.HTTPException:
            message = self.message

        if message is not None:
            self.message = message
            await play_casino_animation(message, animation)

        self.session = next_session
        self._refresh_buttons()
        if message is None:
            await interaction.edit_original_response(
                embed=build_blackjack_embed(self.session, self.settings),
                view=self,
            )
        else:
            await message.edit(
                embed=build_blackjack_embed(self.session, self.settings),
                view=self,
            )

        if self.session.is_finished:
            await announce_blackjack_win(interaction, self.session, self.settings)

    def _refresh_buttons(self) -> None:
        for item in self.children:
            if not isinstance(item, discord.ui.Button):
                continue
            item.disabled = self.session.is_finished
            if item.label == "Dobrar" and not self.session.is_finished:
                item.disabled = not self.session.can_double

    def _set_buttons_disabled(self, disabled: bool) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = disabled


def _format_hand(hand: BlackjackHand) -> str:
    cards = _format_cards(hand.cards)
    return f"{cards}\nTotal: **{hand.value}**"


def _format_dealer_hand(session: BlackjackSession) -> str:
    return _format_hand(session.dealer_hand)


def _format_cards(cards: list[BlackjackCard]) -> str:
    return " ".join(f"`{card.display}`" for card in cards) or "-"


def _result_color(session: BlackjackSession) -> discord.Color:
    if session.outcome in {
        BlackjackOutcome.PLAYER_BLACKJACK,
        BlackjackOutcome.PLAYER_WIN,
    }:
        return discord.Color.green()
    if session.outcome is BlackjackOutcome.PUSH:
        return discord.Color.blurple()
    return discord.Color.red()
