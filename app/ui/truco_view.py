from __future__ import annotations

import asyncio
from io import BytesIO
from typing import cast

import discord
from discord.ext import commands

from app.models.guild_settings import GuildEconomySettings
from app.models.truco import (
    TRUCO_VALUES,
    TrucoCard,
    TrucoGameMode,
    TrucoGameStatus,
    TrucoSession,
    TrucoTeam,
)
from app.services.truco_service import TrucoService, TrucoValidationError
from app.ui.game_notifications import announce_game_result_to_channel
from app.ui.truco_table_image import (
    TRUCO_TABLE_FILENAME,
    render_truco_table_image,
)
from app.utils.embeds import format_points

_OPEN_TRUCO_HANDS: dict[
    int,
    dict[
        int,
        discord.Interaction | discord.Message | discord.WebhookMessage,
    ],
] = {}


def build_truco_embed(
    session: TrucoSession,
    settings: GuildEconomySettings,
    *,
    reveal_round: bool = False,
) -> discord.Embed:
    """Cria a mesa pública de Truco."""

    color = discord.Color.green()
    if session.status is TrucoGameStatus.LOBBY:
        color = discord.Color.blurple()
    elif session.status is TrucoGameStatus.CANCELLED:
        color = discord.Color.red()
    elif session.status is TrucoGameStatus.FINISHED:
        color = discord.Color.gold()

    embed = discord.Embed(title="Truco Paulista", color=color)
    embed.description = _build_description(
        session,
        settings,
        reveal_round=reveal_round,
    )
    embed.set_image(url=f"attachment://{TRUCO_TABLE_FILENAME}")
    return embed


def build_truco_attachment(
    session: TrucoSession,
    settings: GuildEconomySettings,
    *,
    display_names: dict[int, str] | None = None,
    reveal_round: bool = False,
) -> discord.File:
    image = render_truco_table_image(
        session,
        settings,
        display_names=display_names,
        reveal_round=reveal_round,
    )
    return discord.File(BytesIO(image), filename=TRUCO_TABLE_FILENAME)


def build_truco_message_kwargs(
    session: TrucoSession,
    settings: GuildEconomySettings,
    *,
    display_names: dict[int, str] | None = None,
    reveal_round: bool = False,
) -> dict[str, object]:
    return {
        "embed": build_truco_embed(
            session,
            settings,
            reveal_round=reveal_round,
        ),
        "attachments": [
            build_truco_attachment(
                session,
                settings,
                display_names=display_names,
                reveal_round=reveal_round,
            )
        ],
    }


class TrucoLobbyView(discord.ui.View):
    """Botões públicos do lobby de Truco."""

    def __init__(
        self,
        bot: commands.Bot,
        game_id: int,
        settings: GuildEconomySettings,
    ) -> None:
        super().__init__(timeout=300)
        self.bot = bot
        self.game_id = game_id
        self.settings = settings

    @discord.ui.button(label="Aceitar", style=discord.ButtonStyle.success)
    async def accept(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        service = cast(TrucoService, self.bot.truco_service)  # type: ignore[attr-defined]
        await interaction.response.defer()
        try:
            session = await service.accept_lobby(self.game_id, interaction.user.id)
        except TrucoValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        await _edit_truco_message(self.bot, interaction, session, self.settings)
        if session.status is TrucoGameStatus.PLAYING:
            await interaction.followup.send(
                "Todos aceitaram. A partida começou.",
                ephemeral=True,
            )

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def decline(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        service = cast(TrucoService, self.bot.truco_service)  # type: ignore[attr-defined]
        await interaction.response.defer()
        try:
            session = await service.decline_lobby(self.game_id, interaction.user.id)
        except TrucoValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        await _edit_truco_message(self.bot, interaction, session, self.settings)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        service = cast(TrucoService, self.bot.truco_service)  # type: ignore[attr-defined]
        await interaction.response.defer()
        try:
            session = await service.cancel_game(self.game_id, interaction.user.id)
        except TrucoValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        await _edit_truco_message(self.bot, interaction, session, self.settings)


class TrucoTableView(discord.ui.View):
    """Controles públicos da mesa de Truco."""

    def __init__(
        self,
        bot: commands.Bot,
        session: TrucoSession,
        settings: GuildEconomySettings,
    ) -> None:
        super().__init__(timeout=900)
        self.bot = bot
        self.game_id = session.id or 0
        self.session = session
        self.settings = settings
        self._refresh_buttons()

    @discord.ui.button(
        label="Ver minhas cartas",
        style=discord.ButtonStyle.primary,
        custom_id="truco:hand",
    )
    async def show_hand(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        service = cast(TrucoService, self.bot.truco_service)  # type: ignore[attr-defined]
        session = await service.get_game(self.game_id)
        if session is None:
            await interaction.response.send_message(
                "Partida de Truco não encontrada.",
                ephemeral=True,
            )
            return
        player = session.player(interaction.user.id)
        if player is None:
            await interaction.response.send_message(
                "Você não participa desta partida.",
                ephemeral=True,
            )
            return
        cards = session.hands.get(interaction.user.id, [])
        await interaction.response.send_message(
            embed=build_truco_hand_embed(session, interaction.user.id),
            view=TrucoHandView(
                self.bot,
                self.game_id,
                self.settings,
                cards,
                hide_cards=session.is_escurona,
            ),
            ephemeral=True,
        )
        _register_truco_hand(self.game_id, interaction.user.id, interaction)

    @discord.ui.button(
        label="Trucar",
        style=discord.ButtonStyle.danger,
        custom_id="truco:request",
    )
    async def truco(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self._run_table_action(interaction, "truco")

    @discord.ui.button(
        label="Correr",
        style=discord.ButtonStyle.secondary,
        custom_id="truco:run",
    )
    async def run(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self._run_table_action(interaction, "run")

    @discord.ui.button(
        label="Aceitar Truco",
        style=discord.ButtonStyle.success,
        custom_id="truco:accept",
    )
    async def accept_truco(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self._run_table_action(interaction, "accept")

    @discord.ui.button(
        label="Aumentar",
        style=discord.ButtonStyle.danger,
        custom_id="truco:raise",
    )
    async def raise_truco(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self._run_table_action(interaction, "raise")

    async def _run_table_action(
        self,
        interaction: discord.Interaction,
        action: str,
    ) -> None:
        service = cast(TrucoService, self.bot.truco_service)  # type: ignore[attr-defined]
        await interaction.response.defer()
        try:
            if action == "truco":
                session = await service.request_truco(
                    self.game_id,
                    interaction.user.id,
                )
            elif action == "run":
                session = await service.run(self.game_id, interaction.user.id)
            elif action == "accept":
                session = await service.accept_truco(
                    self.game_id,
                    interaction.user.id,
                )
            else:
                session = await service.raise_truco(
                    self.game_id,
                    interaction.user.id,
                )
        except TrucoValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        session = await _edit_truco_message(
            self.bot,
            interaction,
            session,
            self.settings,
        )
        await _announce_truco_finish(interaction, session, self.settings)

    def _refresh_buttons(self) -> None:
        challenge = self.session.pending_challenge
        hand_of_eleven = self.session.score_blue == 11 or self.session.score_red == 11
        next_value = _next_truco_value(self.session.hand_value)
        for item in self.children:
            if not isinstance(item, discord.ui.Button):
                continue
            if item.custom_id == "truco:request":
                item.label = f"Pedir {next_value}" if next_value else "Truco máximo"
                item.disabled = (
                    challenge is not None or next_value is None or hand_of_eleven
                )
            elif item.custom_id == "truco:accept":
                item.label = (
                    f"Aceitar {challenge.proposed_value}"
                    if challenge is not None
                    else "Aceitar"
                )
                item.disabled = challenge is None
            elif item.custom_id == "truco:raise":
                raised_value = (
                    _next_truco_value(challenge.proposed_value)
                    if challenge is not None
                    else None
                )
                item.label = f"Pedir {raised_value}" if raised_value else "Aumentar"
                item.disabled = challenge is None or raised_value is None
            elif item.custom_id == "truco:run":
                item.label = (
                    f"Correr ({challenge.current_value})"
                    if challenge is not None
                    else "Correr"
                )


class TrucoHandView(discord.ui.View):
    """Painel privado das cartas do jogador."""

    def __init__(
        self,
        bot: commands.Bot,
        game_id: int,
        settings: GuildEconomySettings,
        cards: list[TrucoCard],
        *,
        hide_cards: bool = False,
    ) -> None:
        super().__init__(timeout=120)
        self.bot = bot
        self.game_id = game_id
        self.settings = settings
        for index, card in enumerate(cards):
            self.add_item(
                _PlayCardButton(index, card, closed=False, hide_card=hide_cards)
            )
        for index, card in enumerate(cards):
            self.add_item(_PlayCardButton(index, card, closed=True, hide_card=True))


class _PlayCardButton(discord.ui.Button):
    def __init__(
        self,
        index: int,
        card: TrucoCard,
        *,
        closed: bool,
        hide_card: bool,
    ) -> None:
        card_label = f"Carta {index + 1}" if hide_card else card.short_label
        label = f"Fechada {index + 1}" if closed else f"Jogar {card_label}"
        super().__init__(
            label=label[:80],
            style=(
                discord.ButtonStyle.secondary if closed else discord.ButtonStyle.primary
            ),
            row=1 if closed else 0,
        )
        self.index = index
        self.closed = closed

    async def callback(self, interaction: discord.Interaction) -> None:
        view = cast(TrucoHandView, self.view)
        _register_truco_hand(view.game_id, interaction.user.id, interaction)
        service = cast(TrucoService, view.bot.truco_service)  # type: ignore[attr-defined]
        await interaction.response.defer(ephemeral=True)
        try:
            session = await service.play_card(
                game_id=view.game_id,
                user_id=interaction.user.id,
                card_index=self.index,
                closed=self.closed,
            )
        except TrucoValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        session = await _edit_truco_message(
            view.bot,
            interaction,
            session,
            view.settings,
        )
        await _announce_truco_finish(interaction, session, view.settings)


def build_truco_hand_embed(session: TrucoSession, user_id: int) -> discord.Embed:
    embed = discord.Embed(title="🃏 Sua mão", color=discord.Color.green())
    hand = session.hands.get(user_id, [])
    if session.is_escurona:
        lines = [f"`{index}` Carta no escuro" for index in range(1, len(hand) + 1)]
    else:
        lines = [f"`{index}` {card.label}" for index, card in enumerate(hand, start=1)]
    turn = (
        "É sua vez." if session.current_turn_user_id == user_id else "Aguarde sua vez."
    )
    embed.description = (
        f"{turn}\n"
        f"Rodada {session.round_number} · Mão vale {session.hand_value}\n\n"
        + ("\n".join(lines) if lines else "Você não possui cartas disponíveis.")
    )
    if session.round_number not in {1, 3}:
        embed.set_footer(
            text="Carta fechada só pode ser usada na primeira ou terceira rodada."
        )
    return embed


async def _edit_truco_message(
    bot: commands.Bot,
    interaction: discord.Interaction,
    session: TrucoSession,
    settings: GuildEconomySettings,
) -> TrucoSession:
    service = cast(TrucoService, bot.truco_service)  # type: ignore[attr-defined]
    session = await service.play_machine_turns(session.id or 0)
    names = _display_names(bot, session, interaction.guild)
    message = await _resolve_truco_message(interaction, session)

    reveal = session.last_round_reveal
    if (
        session.game_mode is TrucoGameMode.PVE
        and session.round_reveal_pending
        and reveal is not None
    ):
        if message is not None:
            reveal_view: discord.ui.View | None = None
            if session.status is TrucoGameStatus.PLAYING:
                reveal_view = TrucoTableView(bot, session, settings)
                _disable_view(reveal_view)
            try:
                await message.edit(
                    **build_truco_message_kwargs(
                        session,
                        settings,
                        display_names=names,
                        reveal_round=True,
                    ),
                    view=reveal_view,
                )
                await asyncio.sleep(3)
            except discord.HTTPException:
                message = None
        session = await service.consume_round_reveal(session.id or 0, reveal.key)
        session = await service.play_machine_turns(session.id or 0)

    view: discord.ui.View | None
    if session.status is TrucoGameStatus.LOBBY:
        view = TrucoLobbyView(bot, session.id or 0, settings)
    elif session.status is TrucoGameStatus.PLAYING:
        view = TrucoTableView(bot, session, settings)
    else:
        view = None

    names = _display_names(bot, session, interaction.guild)
    message_kwargs = build_truco_message_kwargs(
        session,
        settings,
        display_names=names,
    )
    if message is not None:
        try:
            await message.edit(**message_kwargs, view=view)
            await refresh_open_truco_hands(bot, session, settings)
            return session
        except discord.HTTPException:
            pass
    await interaction.followup.send(
        embed=build_truco_embed(session, settings),
        file=build_truco_attachment(
            session,
            settings,
            display_names=names,
        ),
        view=view,
    )
    await refresh_open_truco_hands(bot, session, settings)
    return session


async def _resolve_truco_message(
    interaction: discord.Interaction,
    session: TrucoSession,
) -> discord.Message | None:
    if interaction.message is not None and interaction.message.id == session.message_id:
        return interaction.message
    channel = interaction.channel
    if channel is None or session.message_id is None:
        return None
    try:
        return await channel.fetch_message(session.message_id)  # type: ignore[attr-defined]
    except (discord.HTTPException, AttributeError):
        return None


def _disable_view(view: discord.ui.View) -> None:
    for item in view.children:
        item.disabled = True


async def refresh_open_truco_hands(
    bot: commands.Bot,
    session: TrucoSession,
    settings: GuildEconomySettings,
) -> None:
    if session.id is None:
        return
    messages = _OPEN_TRUCO_HANDS.get(session.id, {})
    stale: list[int] = []
    for user_id, handle in list(messages.items()):
        player = session.player(user_id)
        if player is None or player.is_bot:
            stale.append(user_id)
            continue
        view: discord.ui.View | None = None
        if session.status is TrucoGameStatus.PLAYING:
            cards = session.hands.get(user_id, [])
            view = TrucoHandView(
                bot,
                session.id,
                settings,
                cards,
                hide_cards=session.is_escurona,
            )
        try:
            await _edit_truco_hand_handle(
                handle,
                build_truco_hand_embed(session, user_id),
                view,
            )
        except discord.HTTPException:
            stale.append(user_id)
    for user_id in stale:
        messages.pop(user_id, None)
    if session.status is not TrucoGameStatus.PLAYING:
        _OPEN_TRUCO_HANDS.pop(session.id, None)


def _register_truco_hand(
    game_id: int,
    user_id: int,
    handle: discord.Interaction | discord.Message | discord.WebhookMessage,
) -> None:
    _OPEN_TRUCO_HANDS.setdefault(game_id, {})[user_id] = handle


async def _edit_truco_hand_handle(
    handle: discord.Interaction | discord.Message | discord.WebhookMessage,
    embed: discord.Embed,
    view: discord.ui.View | None,
) -> None:
    if isinstance(handle, discord.Interaction):
        await handle.edit_original_response(embed=embed, view=view)
        return
    await handle.edit(embed=embed, view=view)


async def _announce_truco_finish(
    interaction: discord.Interaction,
    session: TrucoSession,
    settings: GuildEconomySettings,
) -> None:
    if session.status is not TrucoGameStatus.FINISHED or session.winning_team is None:
        return
    channel = interaction.channel
    for player in session.team_players(session.winning_team):
        if player.is_bot:
            continue
        await announce_game_result_to_channel(
            channel,
            user_id=player.user_id,
            game_name="Truco",
            stake=session.stake,
            payout=session.expected_payout_per_winner,
            settings=settings,
        )
    if session.zero_loss_announcement:
        await channel.send(session.zero_loss_announcement)  # type: ignore[union-attr]
    if all(player.is_bot for player in session.team_players(session.winning_team)):
        await channel.send("A Máquina venceu a partida de Truco.")  # type: ignore[union-attr]


def _build_description(
    session: TrucoSession,
    settings: GuildEconomySettings,
    *,
    reveal_round: bool = False,
) -> str:
    stake = format_points(session.stake, settings.currency_name)
    pot = format_points(session.pot, settings.currency_name)
    reveal = session.last_round_reveal if reveal_round else None
    if reveal is not None:
        winner = (
            f"Equipe **{_team_name(reveal.winner)}** venceu a rodada."
            if reveal.winner is not None
            else "A rodada terminou empatada."
        )
        return (
            f"{winner}\n"
            f"Rodadas desta mão: **Azul {reveal.round_wins_blue} × "
            f"{reveal.round_wins_red} Vermelha**."
        )
    if session.status is TrucoGameStatus.LOBBY:
        return (
            f"{_acceptance_state(session)}\n"
            f"Aposta: **{stake}** por jogador · Pote: **{pot}**"
        )
    if session.status is TrucoGameStatus.CANCELLED:
        return "Mesa cancelada."
    if session.status is TrucoGameStatus.FINISHED:
        return _finish_state(session, settings)

    current = (
        _truco_user_reference(session, session.current_turn_user_id)
        if session.current_turn_user_id is not None
        else "-"
    )
    status = f"Vez de {current}."
    if session.pending_challenge is not None:
        status += (
            f" Equipe {_team_name(session.pending_challenge.target_team)} "
            f"responde ao pedido de **{session.pending_challenge.proposed_value}**."
        )
    elif session.is_escurona:
        status += " Escurona em andamento."
    blue_rounds = session.round_winners.count(TrucoTeam.BLUE)
    red_rounds = session.round_winners.count(TrucoTeam.RED)
    last_round = ""
    if session.last_round_reveal is not None:
        winner = session.last_round_reveal.winner
        last_round = (
            f"\nÚltima rodada: **Equipe {_team_name(winner)} venceu**."
            if winner is not None
            else "\nÚltima rodada: **empate**."
        )
    return (
        f"{status}\n"
        f"Rodadas desta mão: **Azul {blue_rounds} × {red_rounds} Vermelha**."
        f"{last_round}"
    )


def _acceptance_state(session: TrucoSession) -> str:
    pending = [
        _truco_user_reference(session, player.user_id)
        for player in session.players
        if not player.accepted
    ]
    if not pending:
        return "Todos aceitaram."
    return "Aguardando: " + ", ".join(pending)


def _finish_state(
    session: TrucoSession,
    settings: GuildEconomySettings,
) -> str:
    if session.winning_team is None:
        return "Partida encerrada."
    payout = format_points(session.expected_payout_per_winner, settings.currency_name)
    winners = ", ".join(
        _truco_user_reference(session, player.user_id)
        for player in session.team_players(session.winning_team)
    )
    return (
        f"Vencedores: **Equipe {_team_name(session.winning_team)}**\n"
        f"{winners}\n"
        f"Pagamento por vencedor: **{payout}**"
    )


def _team_name(team: TrucoTeam) -> str:
    return "Azul" if team is TrucoTeam.BLUE else "Vermelha"


def _truco_user_reference(session: TrucoSession, user_id: int | None) -> str:
    if user_id is None:
        return "-"
    player = session.player(user_id)
    return "Máquina" if player and player.is_bot else f"<@{user_id}>"


def _next_truco_value(current: int) -> int | None:
    try:
        index = TRUCO_VALUES.index(current)
    except ValueError:
        return None
    if index + 1 >= len(TRUCO_VALUES):
        return None
    return TRUCO_VALUES[index + 1]


def _display_names(
    bot: commands.Bot,
    session: TrucoSession,
    guild: discord.Guild | None,
) -> dict[int, str]:
    resolved_guild = guild or bot.get_guild(session.guild_id)
    names: dict[int, str] = {}
    if resolved_guild is None:
        return names
    for player in session.players:
        if player.is_bot:
            names[player.user_id] = "Máquina"
            continue
        member = resolved_guild.get_member(player.user_id)
        if member is not None:
            names[player.user_id] = member.display_name
    return names
