from __future__ import annotations

from io import BytesIO
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
from app.ui.blackjack_table_image import (
    BLACKJACK_TABLE_FILENAME,
    render_blackjack_table_image,
)
from app.ui.casino_animation import (
    blackjack_animation,
    build_casino_animation_embed,
    play_casino_animation,
)
from app.ui.game_notifications import announce_game_result
from app.utils.embeds import format_points

OUTCOME_TEXT = {
    BlackjackOutcome.PLAYER_BLACKJACK: "BlackJack natural! Você venceu.",
    BlackjackOutcome.PLAYER_WIN: "Você venceu a banca.",
    BlackjackOutcome.DEALER_WIN: "A banca venceu.",
    BlackjackOutcome.PUSH: "Empate. Sua aposta foi devolvida.",
    BlackjackOutcome.PLAYER_BUST: "Você estourou 21 pontos.",
    BlackjackOutcome.DEALER_BLACKJACK: "A banca abriu BlackJack natural.",
    BlackjackOutcome.EXPIRED: "Partida encerrada por inatividade.",
}


def build_blackjack_embed(
    session: BlackjackSession,
    settings: GuildEconomySettings,
    *,
    player_display_name: str | None = None,
    player_avatar_url: str | None = None,
) -> discord.Embed:
    """Cria o embed de uma partida de BlackJack."""

    color = discord.Color.gold() if not session.is_finished else _result_color(session)
    embed = discord.Embed(title="♣ Blackjack", color=color)
    if player_avatar_url:
        embed.set_thumbnail(url=player_avatar_url)
    embed.set_image(url=f"attachment://{BLACKJACK_TABLE_FILENAME}")

    dealer_score = _format_dealer_score(session)
    player_score = session.player_hand.value
    player_name = player_display_name or "Você"
    quote = _status_quote(session)
    embed.description = (
        f"*{quote}*\n\n"
        f"**Aposta:** {format_points(session.bet, settings.currency_name)}\n"
        f"**Banca ({dealer_score}):**\n"
        f"{_format_dealer_hand(session)}\n\n"
        f"**{player_name} ({player_score}):**\n"
        f"{_format_hand(session.player_hand)}"
    )

    if session.is_finished:
        embed.add_field(
            name="Resultado",
            value=OUTCOME_TEXT.get(session.outcome, "Partida finalizada."),
            inline=False,
        )
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
        if session.cashback > 0:
            embed.add_field(
                name="Cashback de proteção",
                value=format_points(session.cashback, settings.currency_name),
                inline=True,
            )
        if session.win_streak > 1:
            multiplier = f"{session.payout_multiplier_percent / 100:.2f}x"
            bonus = format_points(session.streak_bonus, settings.currency_name)
            embed.add_field(
                name="Winstreak",
                value=(
                    f"{session.win_streak} vitorias seguidas\n"
                    f"Multiplicador: **{multiplier}**\n"
                    f"Bonus: {bonus}"
                ),
                inline=False,
            )
    else:
        embed.add_field(
            name="Opções da mão",
            value=(
                "Dobrar disponível."
                if session.can_double
                else "Dobrar indisponível depois de pedir carta."
            ),
            inline=True,
        )

    embed.set_footer(text="Banca para em soft 17 · BlackJack natural paga 2,5x")
    return embed


def build_blackjack_attachment(
    session: BlackjackSession,
    settings: GuildEconomySettings,
    *,
    player_display_name: str | None = None,
) -> discord.File:
    image = render_blackjack_table_image(
        session,
        settings,
        player_display_name=player_display_name,
    )
    return discord.File(BytesIO(image), filename=BLACKJACK_TABLE_FILENAME)


def build_blackjack_message_kwargs(
    session: BlackjackSession,
    settings: GuildEconomySettings,
    *,
    player_display_name: str | None = None,
    player_avatar_url: str | None = None,
) -> dict[str, object]:
    return {
        "embed": build_blackjack_embed(
            session,
            settings,
            player_display_name=player_display_name,
            player_avatar_url=player_avatar_url,
        ),
        "attachments": [
            build_blackjack_attachment(
                session,
                settings,
                player_display_name=player_display_name,
            )
        ],
    }


async def announce_blackjack_result(
    interaction: discord.Interaction,
    session: BlackjackSession,
    settings: GuildEconomySettings,
) -> None:
    """Anuncia vitorias e derrotas expressivas do BlackJack no canal."""

    await announce_game_result(
        interaction,
        user_id=session.user_id,
        game_name="BlackJack",
        stake=session.bet,
        payout=session.payout,
        settings=settings,
        win_streak=session.win_streak,
        multiplier_percent=session.payout_multiplier_percent,
    )
    return
    """
    try:
        await channel.send(
            "🎉 "
            f"{interaction.user.mention} acabou de ganhar "
            f"{format_points(session.payout, settings.currency_name)} no BlackJack!"
        )
    except discord.HTTPException:
        return
    """


class BlackjackView(discord.ui.View):
    """Botoes efemeros de uma partida de BlackJack."""

    def __init__(
        self,
        bot: commands.Bot,
        session: BlackjackSession,
        settings: GuildEconomySettings,
        *,
        player_display_name: str | None = None,
        player_avatar_url: str | None = None,
    ) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.session = session
        self.settings = settings
        self.initial_bet = session.bet
        self.player_display_name = player_display_name
        self.player_avatar_url = player_avatar_url
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

    @discord.ui.button(label="Split", style=discord.ButtonStyle.secondary, row=0)
    async def split_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_message(
            "Split ainda não está disponível nesta mesa.",
            ephemeral=True,
        )

    @discord.ui.button(label="Seguro", style=discord.ButtonStyle.secondary, row=0)
    async def insurance_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_message(
            "Seguro ainda não está disponível nesta mesa.",
            ephemeral=True,
        )

    @discord.ui.button(
        label="Começar nova partida",
        style=discord.ButtonStyle.success,
        row=1,
    )
    async def new_game_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self._start_new_game(interaction)

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
                    **self._build_message_kwargs(),
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
        await interaction.response.defer()

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
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        self._set_buttons_disabled(True)
        animation = blackjack_animation(action)
        await interaction.edit_original_response(
            embed=build_casino_animation_embed(animation),
            attachments=[],
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
                **self._build_message_kwargs(),
                view=self,
            )
        else:
            await message.edit(
                **self._build_message_kwargs(),
                view=self,
            )

        if self.session.is_finished:
            await announce_blackjack_result(interaction, self.session, self.settings)

    async def _start_new_game(self, interaction: discord.Interaction) -> None:
        service = cast(BlackjackService, self.bot.blackjack_service)  # type: ignore[attr-defined]
        await interaction.response.defer()
        try:
            next_session = await service.start_game(
                guild_id=self.session.guild_id,
                user_id=self.session.user_id,
                bet=self.initial_bet,
            )
        except BlackjackValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        self.session = next_session
        self.initial_bet = next_session.bet
        self._set_buttons_disabled(True)
        animation = blackjack_animation("deal")
        await interaction.edit_original_response(
            embed=build_casino_animation_embed(animation),
            attachments=[],
            view=self,
        )
        try:
            message = await interaction.original_response()
        except discord.HTTPException:
            message = self.message
        if message is not None:
            self.message = message
            await play_casino_animation(message, animation)
        self._refresh_buttons()
        if message is None:
            await interaction.edit_original_response(
                **self._build_message_kwargs(),
                view=self,
            )
        else:
            await message.edit(**self._build_message_kwargs(), view=self)
        if self.session.is_finished:
            await announce_blackjack_result(interaction, self.session, self.settings)

    def _refresh_buttons(self) -> None:
        for item in self.children:
            if not isinstance(item, discord.ui.Button):
                continue
            if item.label in {"Split", "Seguro"}:
                item.disabled = True
                continue
            if item.label == "Começar nova partida":
                item.disabled = not self.session.is_finished
                continue
            item.disabled = self.session.is_finished
            if item.label == "Dobrar" and not self.session.is_finished:
                item.disabled = not self.session.can_double

    def _set_buttons_disabled(self, disabled: bool) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = disabled

    def _build_embed(self) -> discord.Embed:
        return build_blackjack_embed(
            self.session,
            self.settings,
            player_display_name=self.player_display_name,
            player_avatar_url=self.player_avatar_url,
        )

    def _build_message_kwargs(self) -> dict[str, object]:
        return build_blackjack_message_kwargs(
            self.session,
            self.settings,
            player_display_name=self.player_display_name,
            player_avatar_url=self.player_avatar_url,
        )


def _format_hand(hand: BlackjackHand) -> str:
    return _format_cards(hand.cards)


def _format_dealer_hand(session: BlackjackSession) -> str:
    cards = list(session.dealer_hand.cards)
    if not session.is_finished and len(cards) == 1:
        return f"{_format_cards(cards)} `{_hidden_card_label()}`"
    return _format_cards(cards)


def _format_cards(cards: list[BlackjackCard]) -> str:
    return " ".join(f"`{_card_label(card)}`" for card in cards) or "-"


def _card_label(card: BlackjackCard) -> str:
    return f"{_suit_symbol(card.suit)} {card.display}"


def _hidden_card_label() -> str:
    return "? ?"


def _suit_symbol(suit) -> str:
    symbols = {
        "S": "♠",
        "H": "♥",
        "D": "♦",
        "C": "♣",
    }
    return symbols.get(str(suit.value), str(suit.value))


def _format_dealer_score(session: BlackjackSession) -> str:
    if not session.is_finished and len(session.dealer_hand.cards) == 1:
        return f"{session.dealer_hand.value}+?"
    return str(session.dealer_hand.value)


def _status_quote(session: BlackjackSession) -> str:
    if not session.is_finished:
        if session.can_double:
            return "Mesa aberta. Você ainda pode dobrar nesta mão."
        if session.player_hand.value == 21:
            return "Vinte e um cravado. Agora é com a banca."
        return "Escolha sua próxima jogada."
    if session.outcome is BlackjackOutcome.PLAYER_BLACKJACK:
        return "Natural bonito. Essa mão veio pronta."
    if session.outcome is BlackjackOutcome.PLAYER_WIN:
        return "Boa mão. Você venceu a banca."
    if session.outcome is BlackjackOutcome.PUSH:
        return "Empate limpo. A aposta voltou para você."
    if session.outcome is BlackjackOutcome.PLAYER_BUST:
        return "Passou de 21. A mesa cobrou a ousadia."
    if session.outcome is BlackjackOutcome.DEALER_BLACKJACK:
        return "A banca abriu BlackJack natural."
    if session.outcome is BlackjackOutcome.EXPIRED:
        return "A mesa esfriou e a partida foi encerrada."
    return "A banca levou essa mão."


def _result_color(session: BlackjackSession) -> discord.Color:
    if session.outcome in {
        BlackjackOutcome.PLAYER_BLACKJACK,
        BlackjackOutcome.PLAYER_WIN,
    }:
        return discord.Color.green()
    if session.outcome is BlackjackOutcome.PUSH:
        return discord.Color.blurple()
    return discord.Color.red()
